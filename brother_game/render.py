# -*- coding: utf-8 -*-
"""Отрисовка района и персонажа (вид сверху).

Оптимизация под «шустро»:
 * ground+flat+стены печатаются один раз в общий буфер карты (Surface),
   дальше blit видимой области — O(экран);
 * динамические объекты (машины/люди/деревья) сортируются по Y
   (painter's algorithm) и рисуются только попавшие в камеру;
 * над игроком рисуется слой листвы, козырьков и крон деревьев;
 * анимации: транспорт (колёса/поворотники/фары),походка людей, дым из
   труб, пар теплотрассы, огоньки вышки, блики воды, погода (effects.py);
 * ночной цикл: темновый оверлей с «дырами» света от фонарей и фар.
"""
import math
import random

import pygame

import textures as T
from config import (COL_ACCENT, COL_TEXT, LAYER_GROUND, TILE, WINDOW_H, WINDOW_W)


def _dir_index(deg):
    """Угол корпуса (0=восток, CCW, как у pygame.rotate) -> индекс 0..7."""
    return int(((-deg) % 360) / 45 + 0.5) % 8


class Renderer:
    def __init__(self, screen, district):
        self.screen = screen
        self.d = district
        self.world_px_w = district.w * TILE
        self.world_px_h = district.h * TILE
        self.tiles = {}
        self._build_tile_cache()
        self.map_surface = None
        self.shadow_surface = None
        self._prop_cache = {}
        self._npc_cache = {}
        self._car_cache = {}
        self.weather = None               # game подвешивает WeatherSystem
        self.night = 0.0                  # 0 день .. 1 ночь (lerp яркости)
        self.chimneys = []                # точки дымовых труб (world px)
        self.lit_windows = []             # окна, зажигающиеся к ночи
        self._frame_fx = []               # события кадра: ('steam',x,y,n)
        self._blit_n = 0                  # статистика для debug
        self._water_y = getattr(district, "water_y", None)

    # ------------------------------------------------------------ тайлы
    def _build_tile_cache(self):
        d = self.d
        size = TILE
        cache = {
            "asphalt": T.asphalt(size, 1),
            "concrete": T.concrete(size, 2),
            "brick": T.brick_pavement(size, 3),
            "grass": T.grass(size, 4),
            "water": pygame.transform.smoothscale(T.water(128, 5), (size, size)),
            "sand": T.sand(size, 6),
            "yard": T.noise_surface((size, size), (70, 72, 66), 26, 12, 3),
        }
        # вариации асфальта, чтобы не было заметно сетки
        variants = [T.asphalt(size, s) for s in (21, 22, 23)]
        self.variants_asphalt = variants
        self.tiles = cache
        # плоские
        self.flat_tiles = {
            "curb": T.curb_tile(size, 9),
            "mark": T.road_marking(size, 10),
            "puddle": T.puddle(size, 11),
            "crosswalk": T.crosswalk(size),
            "track": self._track_tile(size),
        }
        self.stains = []
        for s in range(6):
            surf = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(surf, (44, 46, 50, 120),
                               (size // 2 + (s % 3 - 1) * 6, size // 2 + (s // 3 - 1) * 5),
                               size // 4)
            self.stains.append(surf)
        self.leaves = []
        for s in range(4):
            surf = pygame.Surface((size, size), pygame.SRCALPHA)
            rnd = __import__("random").Random(s * 7 + 3)
            for _ in range(6):
                x, y = rnd.randrange(size), rnd.randrange(size)
                c = (rnd.randint(90, 130), rnd.randint(70, 90), rnd.randint(40, 60), 200)
                pygame.draw.circle(surf, c, (x, y), rnd.randint(2, 4))
            self.leaves.append(surf)

    def _track_tile(self, size):
        s = pygame.Surface((size, size), pygame.SRCALPHA)
        s.fill((120, 74, 58, 255))
        pygame.draw.line(s, (150, 100, 80), (0, 2), (size, 2), 2)
        return s

    def _arch_tile(self, rot=0, seed=1):
        """Арка во двор: тёмный свод + отсвет фонаря внутри."""
        rnd = random.Random(seed)
        s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        wall = (64, 60, 58)
        pygame.draw.rect(s, wall, (0, 0, TILE, TILE))
        arch = pygame.Rect(8, 6, TILE - 16, TILE - 10)
        pygame.draw.rect(s, (18, 18, 22), arch, border_radius=10)
        pygame.draw.arc(s, (96, 90, 86), (8, 2, TILE - 16, 30), math.pi, 2 * math.pi, 2)
        # «просвет» двора за аркой
        pygame.draw.rect(s, (44, 48, 44), (14, 18, TILE - 28, TILE - 24),
                         border_radius=6)
        if rnd.random() < 0.6:
            pygame.draw.circle(s, (240, 220, 150, 200), (TILE // 2, 26), 3)
        if rot:
            s = pygame.transform.rotate(s, rot)
        return s

    # ------------------------------------------------------ статический буфер
    def build_map_surface(self, on_progress=None):
        """Печатает всю карту в один Surface (делает это один раз при старте)."""
        d = self.d
        surf = pygame.Surface((self.world_px_w, self.world_px_h))
        # ---- ground
        for ty in range(d.h):
            row = d.ground[ty]
            y = ty * TILE
            for tx in range(d.w):
                t = row[tx]
                if t == "asphalt":
                    img = self.variants_asphalt[(tx * 7 + ty * 13) % len(self.variants_asphalt)]
                else:
                    img = self.tiles.get(t, self.tiles["asphalt"])
                surf.blit(img, (tx * TILE, y))
        # ---- flat
        arch_cache = {}
        for f in d.flat:
            t = f["t"]
            px, py = f["x"] * TILE, f["y"] * TILE
            if t == "stain":
                surf.blit(self.stains[f.get("seed", 0) % len(self.stains)], (px, py))
            elif t == "leaf":
                surf.blit(self.leaves[f.get("seed", 0) % len(self.leaves)], (px, py))
            elif t == "arch":
                key = (f.get("rot", 0), f.get("seed", 0) % 4)
                if key not in arch_cache:
                    arch_cache[key] = self._arch_tile(*key)
                img = arch_cache[key]
                r = img.get_rect(center=(px + TILE // 2, py + TILE // 2))
                surf.blit(img, r)
            elif t in self.flat_tiles:
                img = self.flat_tiles[t]
                if t == "puddle":
                    img = pygame.transform.rotate(img, f.get("seed", 0) % 90)
                surf.blit(img, (px, py))
        # ---- дома: проработанная «печать» крыши с объёмом и деталями
        self.chimneys = []
        self.lit_windows = []
        rnd = random.Random(d.seed * 3 + 1)
        for w in d.walls:
            rect = pygame.Rect(w["x"] * TILE, w["y"] * TILE, w["w"] * TILE, w["h"] * TILE)
            block = T.building_block(rect.width, rect.height, w["color"],
                                     w.get("floors", 5), w.get("style", "gable"),
                                     w.get("seed", 1), w.get("tower", False))
            surf.blit(block, rect.topleft)
            # тень дома на юг — мягкая полоса
            sh = pygame.Surface((rect.width + 8, 10), pygame.SRCALPHA)
            pygame.draw.ellipse(sh, (0, 0, 0, 60), (0, 0, rect.width + 8, 14))
            if rect.bottom + 12 < self.world_px_h:
                surf.blit(sh, (rect.left - 4, rect.bottom + 6))
            # точки труб (для дыма) — внутри прямоугольника
            n_ch = max(1, rect.width // 120)
            for _ in range(n_ch):
                cx = rnd.randrange(rect.left + 10, max(rect.left + 11, rect.right - 24))
                cy = rnd.randrange(rect.top + 6, max(rect.top + 7, rect.bottom - 26))
                self.chimneys.append((cx, cy))
            # «окна подъездов» во двор: светящиеся к ночи окна фасада
            step = 13 if rect.width > 90 else 11
            wx0 = rect.left + 4
            while wx0 + 5 < rect.right - 6:
                if rnd.random() < 0.35:
                    self.lit_windows.append((wx0, rect.bottom + 9, rnd.random()))
                wx0 += step
        self.map_surface = surf
        return surf

    # --------------------------------------------------------- динамические
    def _get_prop_img(self, p):
        t = p["t"]
        if t == "car":
            return self._get_car(p.get("kind", "sedan"), p.get("color", (90, 96, 110)),
                                 p.get("seed", 1), parked=True)[0]
        key = (t, p.get("angle", 0), p.get("color"), p.get("seed", 0), p.get("size"))
        img = self._prop_cache.get(key)
        if img is not None:
            return img
        if t == "lamp":
            img = T.lamp_post(p.get("seed", 1))
        elif t == "bench":
            img = T.bench(40, 16, p.get("seed", 1))
            if p.get("angle"):
                img = pygame.transform.rotate(img, p["angle"])
        elif t == "trash":
            img = T.trash(24, p.get("seed", 1))
        elif t == "trunk":
            img = T.tree_trunk(26, p.get("seed", 1))
        elif t == "tower":
            img = T.tower(52, p.get("seed", 1))
        elif t == "kiosk":
            img = T.kiosk(p.get("seed", 1))
        elif t == "garage":
            img = T.garage(p.get("seed", 1))
        else:
            img = pygame.Surface((10, 10), pygame.SRCALPHA)
        self._prop_cache[key] = img
        return img

    def _get_tree(self, o):
        key = ("tree", o.get("size"), o.get("seed"))
        img = self._prop_cache.get(key)
        if img is None:
            img = T.tree_canopy(o.get("size", 64), o.get("seed", 1))
            self._prop_cache[key] = img
        return img

    def _get_car(self, kind, color, seed, parked=False):
        """Кадры машины: (still_img, {(phase,blink): moving_img}, dims)."""
        key = (kind, color, seed, parked)
        hit = self._car_cache.get(key)
        if hit is None:
            frames = T.make_car_frames(kind, color, seed)
            still = frames[(0, False, 0, 0)]
            mv = {}
            for phase in range(4):
                for blink in (0, 1):
                    mv[(phase, blink)] = frames[(0, True, phase, blink)]
            hit = (still, mv, T.car_headlights(color, kind))
            self._car_cache[key] = hit
        return hit

    def _get_npc(self, n):
        key = (n["jacket"], int(n["facing"] / (math.tau / 8)))
        img = self._npc_cache.get(key)
        if img is None:
            img = T.person(radius=11, jacket=n["jacket"], facing=key[1] * math.tau / 8,
                           hat=(48, 44, 40), skin=(190, 165, 140))
            self._npc_cache[key] = img
        return img

    def _walkset(self, jacket, hat=(44, 46, 52), skin=(200, 170, 142)):
        key = ("ws", jacket, hat, skin)
        ws = self._npc_cache.get(key)
        if ws is None:
            ws = T.make_person_walkset(jacket=jacket, hat=hat, skin=skin)
            self._npc_cache[key] = ws
        return ws

    def _lamp_glow(self):
        g = getattr(self, "_lamp_glow_img", None)
        if g is None:
            g = T.lamp_glow(96)
            self._lamp_glow_img = g
        return g

    # ------------------------------------------------------------- draw
    def draw(self, camera, player, time_s, inventory_sel, messages):
        d = self.d
        camx, camy = camera
        camx = int(max(0, min(self.world_px_w - WINDOW_W, camx)))
        camy = int(max(0, min(self.world_px_h - WINDOW_H, camy)))
        view = pygame.Rect(camx, camy, WINDOW_W, WINDOW_H)
        self._blit_n = 0

        self.screen.blit(self.map_surface, (0, 0), view)
        self._blit_n += 1

        # ---- блики воды (анимация)
        if self._water_y is not None:
            wy0 = int(self._water_y * TILE - camy)
            if -TILE < wy0 < WINDOW_H:
                band = pygame.Rect(0, max(0, wy0), WINDOW_W,
                                   min(WINDOW_H - max(0, wy0),
                                       (d.h * TILE) - self._water_y * TILE))
                if band.height > 4:
                    gl = pygame.Surface((band.width, band.height), pygame.SRCALPHA)
                    for i in range(0, band.width, 26):
                        ph = time_s * 1.3 + i * 0.13
                        yy = int(band.height * (0.3 + 0.25 * math.sin(ph)))
                        a = int(26 + 22 * math.sin(ph * 1.7))
                        pygame.draw.line(gl, (190, 210, 230, max(6, a)),
                                         (i, yy), (i + 14, yy + 2), 2)
                    self.screen.blit(gl, (0, band.top))
                    self._blit_n += 1

        # ---- предметы на земле (поверх карты)
        for it in d.items:
            if it["taken"]:
                continue
            sx, sy = it["x"] - camx, it["y"] - camy
            if not (-40 < sx < WINDOW_W + 40 and -40 < sy < WINDOW_H + 40):
                continue
            bob = math.sin(time_s * 3 + it["x"]) * 2
            glow = pygame.Surface((40, 40), pygame.SRCALPHA)
            pygame.draw.circle(glow, (240, 220, 120, 40), (20, 20), 16 + int(bob))
            self.screen.blit(glow, (sx - 20, sy - 20 + bob))
            icon = T.item_icon(it["name"], 26, seed=hash(it["label"]) % 99)
            self.screen.blit(icon, (sx - icon.get_width() // 2,
                                    sy - icon.get_height() // 2 + bob))
            self._blit_n += 2

        # ---- ночные окна подъездов (пока не темно — не видны)
        if self.night > 0.05:
            for wx, wy, k in self.lit_windows:
                sx, sy = wx - camx, wy - camy
                if -10 < sx < WINDOW_W + 10 and -10 < sy < WINDOW_H + 10:
                    on = self.night > (0.25 + 0.5 * k)
                    if on:
                        flick = 0.8 + 0.2 * math.sin(time_s * 2.2 + wx)
                        c = (int(236 * flick), int(200 * flick), int(120 * flick))
                        pygame.draw.rect(self.screen, c, (sx, sy, 5, 4))
                        self._blit_n += 1

        # ---- collect sorted drawables (props + movers + npcs + player) by Y
        draw_list = []
        for p in d.props:
            if view.inflate(140, 140).collidepoint(p["x"], p["y"]):
                draw_list.append((p["y"], "prop", p))
        for m in d.movers:
            if view.inflate(160, 160).collidepoint(m["x"], m["y"]):
                draw_list.append((m["y"], "mover", m))
        for n in d.npcs:
            if view.inflate(140, 140).collidepoint(n["x"], n["y"]):
                draw_list.append((n["y"], "npc", n))
        draw_list.append((player.y, "player", player))
        draw_list.sort(key=lambda e: e[0])

        lights = []          # источники света для ночного оверлея
        cones = []           # конусы фар (x, y, angle_deg)

        for _, kind, obj in draw_list:
            if kind == "prop":
                img = self._get_prop_img(obj)
                sx, sy = obj["x"] - camx, obj["y"] - camy
                self.screen.blit(img, img.get_rect(center=(sx, sy)))
                self._blit_n += 1
                if obj["t"] == "lamp":
                    lights.append((sx, sy - 20, 1.0))
                elif obj["t"] == "car" and self.night > 0.35:
                    pass   # припаркованные без света
            elif kind == "mover":
                m = obj
                still, mv, hl = self._get_car(m.get("kind", "sedan"),
                                              m.get("color", (90, 96, 110)),
                                              m.get("seed", 1))
                phase = int(m.get("wheel", 0)) % 4
                blink = int(m.get("blink", 0))
                img = mv[(phase, blink)]
                ddeg = m.get("angle", 0)
                di = _dir_index(ddeg)
                img = pygame.transform.rotate(img, di * 45) if di else img
                sx, sy = m["x"] - camx, m["y"] - camy
                rect = img.get_rect(center=(sx, sy))
                # конусы фар ночью — под корпусом
                if self.night > 0.25:
                    cone = T.headlight_cone(64)
                    for (hx, hy) in hl:
                        pt = pygame.math.Vector2(hx - img.get_width() / 2,
                                                 hy - img.get_height() / 2)
                        pt = pt.rotate(math.radians(-ddeg))
                        cxp, cyp = sx + pt.x + img.get_width() / 2, sy + pt.y + img.get_height() / 2
                        cr = pygame.transform.rotate(cone, ddeg)
                        self.screen.blit(cr, cr.get_rect(center=(cxp + cr.get_width() / 2 - 10, cyp)))
                        lights.append((cxp, cyp, 1.0))
                        self._blit_n += 1
                self.screen.blit(img, rect)
                self._blit_n += 1
            elif kind == "npc":
                ws = self._walkset(obj["jacket"])
                idx = int((obj["facing"] + math.tau / 16) % math.tau / (math.tau / 8))
                fr = int(obj.get("walk_t", 0) / (math.tau / 6)) % 6
                img = ws[(idx, fr)]
                sx, sy = obj["x"] - camx, obj["y"] - camy
                self.screen.blit(img, img.get_rect(center=(sx, sy)))
                self._blit_n += 1
            else:
                img = player.sprite(time_s)
                sx, sy = obj.x - camx, obj.y - camy
                self.screen.blit(img, img.get_rect(center=(sx, sy)))
                self._blit_n += 1
                if self.night > 0.3:
                    breath = abs(math.sin(player.bob_t * 0.5))
                    if self.weather and (breath > 0.8 or self.night > 0.6):
                        self.weather.steam.emit(obj.x, obj.y - 6, n=1)

        # ---- верхний слой: листва, трубы теплотрассы (+ пар из вентилей)
        for o in d.over:
            if o["t"] == "tree" and view.inflate(180, 180).collidepoint(o["x"], o["y"]):
                img = self._get_tree(o)
                sx, sy = o["x"] - camx, o["y"] - camy
                sway = math.sin(time_s * 0.9 + o["x"] * 0.01) * 2
                self.screen.blit(img, img.get_rect(center=(sx + sway, sy)))
                self._blit_n += 1
            elif o["t"] == "pipe":
                sx, sy = o["x"] - camx, o["y"] - camy
                if -TILE < sx < WINDOW_W + TILE:
                    pygame.draw.rect(self.screen, (74, 70, 68),
                                     (sx - TILE // 2, sy - 6, TILE, 12))
                    pygame.draw.rect(self.screen, (96, 92, 88),
                                     (sx - TILE // 2, sy - 6, TILE, 3))
                    pygame.draw.rect(self.screen, (58, 56, 54),
                                     (sx - TILE // 2, sy - 6, TILE, 12), 1)
                    self._blit_n += 1
        # пар из вентилей теплотрассы
        if self.weather:
            for vx, vy in d.vents:
                if view.inflate(120, 120).collidepoint(vx, vy):
                    if random.random() < 0.10:
                        self.weather.steam.emit(vx, vy, n=2)

        # огонь вышки (мигает)
        for p in d.props:
            if p["t"] == "tower" and view.inflate(120, 120).collidepoint(p["x"], p["y"]):
                k = T.beacon_red(time_s)
                sx, sy = p["x"] - camx - p.get("r", 14) + 26, p["y"] - camy - p.get("r", 14) + 5
                halo = pygame.Surface((16, 16), pygame.SRCALPHA)
                pygame.draw.circle(halo, (255, 70, 50, int(120 * k)), (8, 8), 6)
                pygame.draw.circle(halo, (255, 120, 90, int(255 * k)), (8, 8), 2)
                self.screen.blit(halo, (sx, sy))
                lights.append((sx + 8, sy + 8, 0.5 * k))
                self._blit_n += 1

        # ---- подписи мест
        font = get_font(20)
        for z in d.zones:
            sx, sy = z["x"] - camx, z["y"] - camy
            if -200 < sx < WINDOW_W + 200 and -100 < sy < WINDOW_H + 100:
                txt = font.render(z["label"], True, (180, 180, 178))
                rect = txt.get_rect(center=(sx, sy))
                bg = pygame.Surface((rect.width + 10, rect.height + 4), pygame.SRCALPHA)
                bg.fill((18, 20, 24, 150))
                self.screen.blit(bg, (rect.left - 5, rect.top - 2))
                self.screen.blit(txt, rect)
                self._blit_n += 2

        # ---- ночь: темнота с «дырами» света
        if self.night > 0.02:
            self._draw_night(lights)

        # ---- виньетка / туман + погода поверх мира
        self._vignette(camx, camy, player)
        if self.weather:
            self.weather.draw_overlay(self.screen, camx, camy)

    def _draw_night(self, lights):
        dark = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
        a = int(175 * self.night)
        dark.fill((8, 10, 20, a))
        glow = self._lamp_glow()
        punch = pygame.Surface((glow.get_width(), glow.get_height()), pygame.SRCALPHA)
        punch.fill((0, 0, 0, 0))
        # «вычитание» темноты: рисуем прозрачные пятна через colorkey-маску
        import pygame.surfarray as sa
        base = pygame.surfarray.pixels_alpha(dark)
        gp = pygame.surfarray.pixels_alpha(glow)
        # инверсия: где свет — уменьшаем альфу темноты
        for (lx, ly, inten) in lights[:60]:
            r = glow.get_rect(center=(int(lx), int(ly)))
            if not (-200 < r.left < WINDOW_W + 200):
                continue
            sub = base[max(0, r.left):min(WINDOW_W, r.right),
                       max(0, r.top):min(WINDOW_H, r.bottom)]
            gsub = gp[r.left - r.x if r.left >= 0 else 0:(r.right - r.x) if r.right <= WINDOW_W else glow.get_width(),
                      r.top - r.y if r.top >= 0 else 0:(r.bottom - r.y) if r.bottom <= WINDOW_H else glow.get_height()]
            try:
                import numpy as np
                red = int(a * inten)
                sub -= np.minimum(sub, (gsub.astype(np.int16) * red // 255)).astype(sub.dtype)
            except Exception:
                pass
        del base, gp
        self.screen.blit(dark, (0, 0))
        # тёплые ореоны поверх (аддитивно)
        warm = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
        for (lx, ly, inten) in lights[:60]:
            img = pygame.transform.scale(glow, (int(192 * inten), int(192 * inten)))                 if inten != 1.0 else glow
            tmp = img.copy()
            tmp.set_alpha(int(70 * self.night * inten))
            warm.blit(tmp, tmp.get_rect(center=(int(lx), int(ly))))
        self.screen.blit(warm, (0, 0))
        self._blit_n += 2


    def _vignette(self, camx, camy, player):
        if not hasattr(self, "_vig"):
            vig = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
            cx, cy = WINDOW_W // 2, WINDOW_H // 2
            maxd = math.hypot(cx, cy)
            step = 8
            for r in range(int(maxd), 0, -step):
                a = int(150 * (r / maxd) ** 2)
                pygame.draw.circle(vig, (12, 14, 18, a), (cx, cy), r, step)
            self._vig = vig
        self.screen.blit(self._vig, (0, 0))


# ---------------------------------------------------------------- шрифты
_FONT_CACHE = {}


def get_font(size, bold=False):
    key = (size, bold)
    f = _FONT_CACHE.get(key)
    if f is None:
        try:
            f = pygame.font.SysFont("dejavusans,liberation,freesans,arial", size, bold=bold)
        except Exception:
            f = pygame.font.Font(None, size)
        _FONT_CACHE[key] = f
    return f


def draw_text(screen, text, pos, size=18, color=COL_TEXT, bold=False, center=False,
              bg=None):
    font = get_font(size, bold)
    img = font.render(text, True, color)
    rect = img.get_rect(center=pos) if center else img.get_rect(topleft=pos)
    if bg is not None:
        pad = 4
        bgs = pygame.Surface((rect.width + pad * 2, rect.height + pad * 2), pygame.SRCALPHA)
        bgs.fill(bg)
        screen.blit(bgs, (rect.left - pad, rect.top - pad))
    screen.blit(img, rect)
    return rect
