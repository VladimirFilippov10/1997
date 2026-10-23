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
        self._vis = set()               # (x,y) тайлов с видимой стеной — для отладки
        self.show_walls = False         # F3: подсветка невидимых стен
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
        # вариации асфальта, чтобы не было заметно сетки — 6 штук
        variants = [T.asphalt(size, s) for s in (21, 22, 23, 24, 25, 26)]
        self.variants_asphalt = variants
        self.tiles = cache
        self.stains = []
        for s in range(6):
            surf = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(surf, (44, 46, 50, 120),
                               (size // 2 + (s % 3 - 1) * 6, size // 2 + (s // 3 - 1) * 5),
                               size // 4)
            self.stains.append(surf)
        # явный список «плоских» тайлов: если типа нет — генерируем заглушку,
        # а не молча теряем объект (раньше "patch" не рисовался нигде)
        builders = {
            "curb": lambda: T.curb_tile(size, 9),
            "mark": lambda: T.road_marking(size, 10),
            "puddle": lambda: T.puddle(size, 11),
            "crosswalk": lambda: T.crosswalk(size),
            "track": lambda: self._track_tile(size),
            "trench": lambda: T.trench_tile(3),
            "grate": lambda: T.grate_tile(5),
            "steps": lambda: T.steps_tile(7),
            "patch": lambda: T.patch_tile(size, 41),
            "porch": lambda: T.steps_tile(9),
            "doorface": lambda: T.door_sheet_img(),
        }
        self.flat_tiles = {}
        for name, fn in builders.items():
            try:
                self.flat_tiles[name] = fn()
            except Exception:
                ph = pygame.Surface((size, size), pygame.SRCALPHA)
                ph.fill((90, 90, 96, 120))
                self.flat_tiles[name] = ph
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
            # регистрируем видимые тайлы — всё, чего нет в этом списке,
            # но попало в blocked, станет «невидимой стеной» (ловится F3)
            for ty in range(w["y"], w["y"] + w["h"]):
                for tx in range(w["x"], w["x"] + w["w"]):
                    self._vis.add((tx, ty))
            block = T.building_block(rect.width, rect.height, w["color"],
                                     w.get("floors", 5), w.get("style", "gable"),
                                     w.get("seed", 1), w.get("tower", False),
                                     shop=w.get("shop"))
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
        # интерьеры домов — печатаются один раз в отдельные буферы
        try:
            self.indoors = d.build_indoors()
        except Exception:
            self.indoors = {}
        return surf

    # --------------------------------------------------------- динамические
    def _get_prop_img(self, p):
        t = p["t"]
        if t == "car":
            return self._get_car(p.get("model", p.get("kind", "vaz2101")),
                                 p.get("color", (90, 96, 110)),
                                 p.get("seed", 1), parked=True)[0]
        key = (t, p.get("angle", 0), p.get("color"), p.get("seed", 0), p.get("size"))
        img = self._prop_cache.get(key)
        if img is not None:
            return img
        builders = {
            "lamp": lambda: T.lamp_post(p.get("seed", 1)),
            "bench": lambda: T.bench(40, 16, p.get("seed", 1)),
            "trash": lambda: T.trash(24, p.get("seed", 1)),
            "trunk": lambda: T.tree_trunk(26, p.get("seed", 1)),
            "tower": lambda: T.tower(52, p.get("seed", 1)),
            "kiosk": lambda: T.kiosk(p.get("seed", 1)),
            "garage": lambda: T.garage(p.get("seed", 1)),
            "stall": lambda: T.stall(p.get("seed", 1), p.get("model") or "metal"),
            "phonebox": lambda: T.phonebox(p.get("seed", 1)),
            "arcade": lambda: T.arcade(p.get("seed", 1)),
            "bin": lambda: T.dumpster(p.get("seed", 1)),
            "clothesline": lambda: T.clothesline(p.get("seed", 1)),
            "bare_tree": lambda: T.bare_tree(p.get("seed", 1)),
            # интерьерная мебель: стол, плита, витрина, ящик, полка, холодильник
            "table": lambda: self._interior_box((78, 58, 44), 30),
            "stove": lambda: self._interior_box((70, 70, 74), 28),
            "counter": lambda: self._interior_box((96, 78, 58), 40),
            "crate": lambda: self._interior_box((112, 92, 60), 24),
            "shelf": lambda: self._interior_box((84, 70, 56), 34),
            "fridge": lambda: self._interior_box((188, 188, 182), 26),
            "mailbox": lambda: self._interior_box((96, 104, 112), 22),
        }
        fn = builders.get(t)
        if fn is not None:
            try:
                img = fn()
            except Exception:
                img = None
        if img is None:
            # заглушка вместо пустого пикселя — объект виден и не «исчезает»
            img = pygame.Surface((16, 16), pygame.SRCALPHA)
            img.fill((120, 118, 112, 220))
            pygame.draw.rect(img, (60, 60, 64, 255), (0, 0, 16, 16), 1)
        if p.get("angle"):
            img = pygame.transform.rotate(img, p["angle"])
        self._prop_cache[key] = img
        return img

    def _interior_box(self, col, size):
        """Простая мебель для интерьеров: крышка + тень."""
        s = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.rect(s, col, (1, 1, size - 2, size - 2), border_radius=2)
        light = tuple(min(255, int(c * 1.25)) for c in col)
        dark = tuple(int(c * 0.6) for c in col)
        pygame.draw.line(s, light, (2, 2), (size - 3, 2))
        pygame.draw.line(s, dark, (2, size - 3), (size - 3, size - 3))
        sh = pygame.Surface((size, 6), pygame.SRCALPHA)
        sh.fill((0, 0, 0, 70))
        s.blit(sh, (0, size - 2))
        return s

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
            import cars as C
            legacy = {"sedan": "vaz2101", "van": "vaz2109",
                      "bus": "bmwe34", "truck": "vaz2101"}
            m = C.CAR_MODELS.get(kind) and kind or legacy.get(kind, "vaz2101")
            try:
                frames = C.make_model_frames(m, color, seed)
                hl = C.car_headlights(m, color)
            except Exception:
                frames = T.make_car_frames(legacy.get(kind, "sedan"), color, seed)
                hl = T.car_headlights(color, legacy.get(kind, "sedan"))
            still = frames[(0, False, 0, 0)]
            mv = {}
            for phase in range(4):
                for blink in (0, 1):
                    mv[(phase, blink)] = frames[(0, True, phase, blink)]
            hit = (still, mv, hl)
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
        view = pygame.Rect(camx, camy, WINDOW_W, WINDOW_H)
        self._blit_n = 0

        lvl = d.active_grid()
        self._lvl = lvl
        if lvl is not None:
            # ---- внутри здания: свой буфер пола/стен, камера по интерьеру
            iw, ih = lvl["w"] * TILE, lvl["h"] * TILE
            camx = int(max(0, min(max(0, iw - WINDOW_W), camx)))
            camy = int(max(0, min(max(0, ih - WINDOW_H), camy)))
            view = pygame.Rect(camx, camy, WINDOW_W, WINDOW_H)
            bg = getattr(self, "indoors", {}).get(lvl["key"])
            if bg is not None:
                # blit с source-rect: берём только видимую часть буфера
                sx1 = min(iw - camx, WINDOW_W)
                sy1 = min(ih - camy, WINDOW_H)
                src = pygame.Rect(camx, camy, max(0, sx1), max(0, sy1))
                self.screen.blit(bg, (0, 0), src)
                if sx1 < WINDOW_W or sy1 < WINDOW_H:
                    dark = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
                    dark.fill((10, 10, 14, 220))
                    self.screen.blit(dark, (max(0, sx1), 0),
                                     (0, 0, WINDOW_W - max(0, sx1), WINDOW_H))
            else:
                self.screen.fill((36, 34, 32))
            self._draw_interior_extras(lvl, camx, camy, time_s)
        else:
            camx = int(max(0, min(self.world_px_w - WINDOW_W, camx)))
            camy = int(max(0, min(self.world_px_h - WINDOW_H, camy)))
            view = pygame.Rect(camx, camy, WINDOW_W, WINDOW_H)
            self.screen.blit(self.map_surface, (0, 0), view)
            self._blit_n += 1

        # ---- блики воды (анимация)
        if self._water_y is not None and lvl is None:
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
        lvl_now = lvl
        item_list = lvl_now["items"] if lvl_now else d.items
        for it in item_list:
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
        if self.night > 0.05 and lvl is None:
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
        npcs = lvl["npcs"] if lvl else d.npcs
        props_in = lvl["props"] if lvl else None
        if props_in is not None:
            for p in props_in:
                if view.inflate(140, 140).collidepoint(p["x"], p["y"]):
                    draw_list.append((p["y"], "prop", p))
        for n in npcs:
            if lvl is not None:
                # координаты уличных прохожих вне плана этажа — не рисуем
                if not (0 < n["x"] < lvl["w"] * TILE and
                        0 < n["y"] < lvl["h"] * TILE):
                    continue
            if view.inflate(140, 140).collidepoint(n["x"], n["y"]):
                draw_list.append((n["y"], "npc", n))
        draw_list.append((player.y, "player", player))
        draw_list.sort(key=lambda e: e[0])

        lights = []          # источники света для ночного оверлея
        self._lights_n = 0   # сколько источников реально горит (для баланса лучей)

        for _, kind, obj in draw_list:
            if kind == "prop":
                img = self._get_prop_img(obj)
                sx, sy = obj["x"] - camx, obj["y"] - camy
                self.screen.blit(img, img.get_rect(center=(sx, sy)))
                self._blit_n += 1
                if obj["t"] == "lamp" and self.night > 0.25:
                    lights.append((sx, sy - 20, 1.0))
                    self._lights_n += 1
                elif obj["t"] in ("stall", "kiosk") and self.night > 0.35:
                    lights.append((sx, sy - 8, 0.5))
                elif obj["t"] == "arcade" and self.night > 0.3:
                    lights.append((sx, sy - 6, 0.35))
            elif kind == "mover":
                m = obj
                still, mv, hl = self._get_car(m.get("model", m.get("kind", "sedan")),
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
                # конусы фар ночью — под корпусом; габариты/стопы в сумерках
                if self.night > 0.2:
                    cone = T.headlight_cone(72)
                    for (hx, hy) in hl:
                        pt = pygame.math.Vector2(hx - img.get_width() / 2,
                                                 hy - img.get_height() / 2)
                        pt = pt.rotate(math.radians(-ddeg))
                        cxp, cyp = sx + pt.x + img.get_width() / 2, sy + pt.y + img.get_height() / 2
                        cr = pygame.transform.rotate(cone, ddeg)
                        self.screen.blit(cr, cr.get_rect(center=(cxp + cr.get_width() / 2 - 10, cyp)))
                        lights.append((cxp, cyp, 1.0))
                        self._lights_n += 1
                        self._blit_n += 1
                    # красные габариты сзади машины (корпус смотрит на восток:
                    # x=0 — корма, x=w — морда; pygame.rotate(90) поднимает нос на экран)
                    w_img, h_img = img.get_size()
                    ang = -di * 45.0
                    for off in (-h_img / 4, h_img / 4):
                        p = pygame.math.Vector2(3, h_img / 2 + off).rotate(ang)
                        rx = sx + p.x - w_img / 2
                        ry = sy + p.y - h_img / 2
                        rad = 3 if m.get("brake") else 2
                        ta = int(210 * min(1.0, self.night * 1.8))
                        dot = pygame.Surface((rad * 2 + 6, rad * 2 + 6), pygame.SRCALPHA)
                        pygame.draw.circle(dot, (255, 60, 40, ta // 3),
                                           (rad + 3, rad + 3), rad + 3)
                        pygame.draw.circle(dot, (255, 40, 30, ta), (rad + 3, rad + 3), rad)
                        self.screen.blit(dot, (int(rx - rad - 3), int(ry - rad - 3)))
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
        for o in ([] if lvl else d.over):
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
            elif o["t"] == "awning":
                sx, sy = o["x"] - camx, o["y"] - camy
                if -o.get("size", 8) * TILE < sx < WINDOW_W + TILE:
                    img = self._prop_cache.get(("awning", o.get("size"), o.get("seed")))
                    if img is None:
                        img = T.awning(o.get("size", 8), o.get("seed", 1))
                        self._prop_cache[("awning", o.get("size"), o.get("seed"))] = img
                    self.screen.blit(img, img.get_rect(midbottom=(sx, sy)))
                    self._blit_n += 1
        # ---- вывески магазинов: светящиеся табло (ночью — с ореолом и неоновым мерцанием)
        if self.night > 0.15:
            for sg in getattr(d, "signs", []):
                sx, sy = sg["x"] - camx, sg["y"] - camy
                if view.inflate(260, 80).collidepoint(sx, sy):
                    lights.append((sx, sy, 0.7))
        for sg in getattr(d, "signs", []):
            sx, sy = sg["x"] - camx, sg["y"] - camy
            if -200 < sx < WINDOW_W + 200 and -60 < sy < WINDOW_H + 60:
                sf = get_font(13, bold=True)
                night_k = self.night
                flick = 1.0
                if night_k > 0.4:      # ламповое табло слегка дрожит
                    flick = 0.86 + 0.14 * math.sin(time_s * 9.0 + sg["x"] * 0.13) \
                        * math.sin(time_s * 3.7 + sg["y"] * 0.07)
                txt_col = (int(232 * flick + 20 * night_k),
                           int(224 * flick + 14 * night_k),
                           int(190 * flick))
                txt = sf.render(sg["text"], True, txt_col)
                rect = txt.get_rect(center=(int(sx), int(sy)))
                bgw, bgh = rect.width + 12, rect.height + 6
                bg = pygame.Surface((bgw, bgh), pygame.SRCALPHA)
                # днём — тёмная щита, ночью — подсвеченная изнутри
                k = int(210 + 40 * night_k)
                bg.fill((int(24 + 30 * night_k * flick),
                         int(22 + 26 * night_k * flick),
                         int(28 + 20 * night_k * flick), k))
                self.screen.blit(bg, (rect.left - 6, rect.top - 3))
                pygame.draw.rect(self.screen, (70, 66, 60),
                                 (rect.left - 6, rect.top - 3, bgw, bgh), 1)
                if night_k > 0.25:
                    halo = pygame.Surface((bgw + 44, bgh + 44), pygame.SRCALPHA)
                    a = int(60 * night_k * max(0.4, flick))
                    pygame.draw.rect(halo, (255, 214, 140, a),
                                     (10, 10, bgw + 24, bgh + 24), border_radius=10)
                    self.screen.blit(halo, (rect.left - 6 - 22, rect.top - 3 - 22))
                self.screen.blit(txt, rect)
                self._blit_n += 3
        # ---- ночные огоньки ларьков
        if self.night > 0.2:
            for lx, ly in getattr(d, "stall_lights", []):
                if view.inflate(120, 120).collidepoint(lx, ly):
                    sx, sy = lx - camx, ly - camy
                    k = 0.75 + 0.25 * math.sin(time_s * 3.1 + lx * 0.07)
                    halo = pygame.Surface((26, 26), pygame.SRCALPHA)
                    pygame.draw.circle(halo, (255, 210, 120, int(90 * k * self.night)),
                                       (13, 13), 11)
                    pygame.draw.circle(halo, (255, 236, 180, int(220 * k)),
                                       (13, 13), 3)
                    self.screen.blit(halo, (sx - 13, sy - 20))
                    lights.append((sx, sy - 14, 0.6 * k))
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

        # ---- указатели дверей: снаружи — «войти», внутри — «выйти»
        if lvl is None:
            for dr in d.doors:
                if view.inflate(120, 120).collidepoint(dr["x"], dr["y"]):
                    sx, sy = dr["x"] - camx, dr["y"] - camy - 26
                    pulse = 0.6 + 0.4 * math.sin(time_s * 4.0)
                    fr = pygame.Rect(sx - 16, sy - 12, 32, 24)
                    pygame.draw.rect(self.screen, (20, 18, 16, 200), fr)
                    pygame.draw.rect(self.screen,
                                     (int(220 * pulse + 30), int(190 * pulse + 20), 90),
                                     fr, 1)
                    dm = T.door_sheet_img(14, 20, seed=int(dr["x"]))
                    self.screen.blit(dm, dm.get_rect(center=(sx, sy)))
        else:
            ex, ey = lvl["exit"]
            sx, sy = ex - camx, ey - camy - 30
            pulse = 0.6 + 0.4 * math.sin(time_s * 4.0)
            fr = pygame.Rect(sx - 20, sy - 11, 40, 22)
            pygame.draw.rect(self.screen, (20, 18, 16), fr)
            pygame.draw.rect(self.screen,
                             (int(220 * pulse + 30), int(190 * pulse + 20), 90), fr, 1)
            draw_text(self.screen, "ВЫХОД", (sx, sy), size=12,
                      color=(230, 220, 180), center=True)
        # ---- подписи мест
        font = get_font(20)
        for z in ([] if lvl else d.zones):
            sx, sy = z["x"] - camx, z["y"] - camy
            if -200 < sx < WINDOW_W + 200 and -100 < sy < WINDOW_H + 100:
                txt = font.render(z["label"], True, (180, 180, 178))
                rect = txt.get_rect(center=(sx, sy))
                bg = pygame.Surface((rect.width + 10, rect.height + 4), pygame.SRCALPHA)
                bg.fill((18, 20, 24, 150))
                self.screen.blit(bg, (rect.left - 5, rect.top - 2))
                self.screen.blit(txt, rect)
                self._blit_n += 2

        # ---- ночь: темнота с «дырами» света (в домах — свои лампы)
        if lvl is not None:
            for pr in lvl.get("lamps", []):
                lights.append((pr["x"] - camx, pr["y"] - camy - 6, 0.8))
        if self.night > 0.02 and lvl is None:
            self._draw_night(lights)
        elif lvl is not None:
            # в интерьере всегда сумерки: лёгкий синий флэт + ореоны ламп
            dim = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
            dim.fill((10, 12, 20, 70))
            self.screen.blit(dim, (0, 0))
            glow = self._lamp_glow()
            for (lx, ly, inten) in lights:
                size = max(24, int(150 * inten))
                img = pygame.transform.scale(glow, (size, size))
                tmp = img.copy()
                tmp.set_alpha(60)
                self.screen.blit(tmp, tmp.get_rect(center=(int(lx), int(ly))))
        # ---- подкраска кадра по фазе суток (рассвет/закат/ночь)
        self._sky_tint_overlay()

        # ---- F3: подсветка невидимых стен (blocked-клетки без видимой графики)
        if getattr(self, "show_walls", False):
            for (tx, ty) in d.blocked:
                if (tx, ty) not in self._vis:
                    pygame.draw.rect(self.screen, (255, 40, 40, 90),
                                     (tx * TILE - camx, ty * TILE - camy, TILE, TILE))
                    pygame.draw.rect(self.screen, (255, 120, 120),
                                     (tx * TILE - camx, ty * TILE - camy, TILE, TILE), 1)
            for p in d.props:
                if p.get("solid") and p["t"] != "car":
                    r = pygame.Rect(p["x"] - p.get("r", 10) - camx,
                                    p["y"] - p.get("r", 10) - camy,
                                    p.get("r", 10) * 2, p.get("r", 10) * 2)
                    pygame.draw.rect(self.screen, (80, 160, 255), r, 1)

        # ---- виньетка / туман + погода поверх мира
        self._vignette(camx, camy, player)
        if self.weather:
            self.weather.draw_overlay(self.screen, camx, camy)

    def _draw_interior_extras(self, lvl, camx, camy, time_s):
        """Детали интерьера: плафоны, вывески магазинов, тёплый свет."""
        # потолочные плафоны (рисуются поверх мебели, как настенные огни)
        for pr in lvl.get("lamps", []):
            sx, sy = pr["x"] - camx, pr["y"] - camy
            if -40 < sx < WINDOW_W + 40 and -40 < sy < WINDOW_H + 40:
                halo = pygame.Surface((30, 30), pygame.SRCALPHA)
                k = 0.85 + 0.15 * math.sin(time_s * 2.3 + pr["x"])
                pygame.draw.circle(halo, (255, 226, 160, int(70 * k)), (15, 15), 12)
                pygame.draw.circle(halo, (255, 244, 210, 230), (15, 15), 4)
                self.screen.blit(halo, (sx - 15, sy - 15))
        # вывеска магазина внутри уровня
        shop = lvl.get("shop")
        if shop:
            cx = lvl["w"] * TILE // 2 - camx
            cy = 14 - camy
            sf = get_font(14, bold=True)
            txt = sf.render(shop, True, (236, 224, 190))
            rect = txt.get_rect(center=(cx, cy))
            bg = pygame.Surface((rect.width + 12, rect.height + 4), pygame.SRCALPHA)
            bg.fill((26, 22, 20, 210))
            self.screen.blit(bg, (rect.left - 6, rect.top - 2))
            self.screen.blit(txt, rect)
        # название подъезда/квартиры мелкой строкой внизу
        lab = lvl.get("label")
        if lab:
            draw_text(self.screen, lab, (12, WINDOW_H - 64), size=14,
                      color=(170, 166, 158), bg=(16, 18, 22, 150))

    def _draw_night(self, lights):
        """Ночь: маска темноты с «дырами» от фонарей, фар и вывесок."""
        a = int(175 * self.night)
        dark = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
        dark.fill((8, 10, 20, a))
        glow = self._lamp_glow()
        gp = None
        try:
            import numpy as np
            base = pygame.surfarray.pixels_alpha(dark).copy()
            gp = pygame.surfarray.pixels_alpha(glow)
            for (lx, ly, inten) in lights[:48]:
                r = glow.get_rect(center=(int(lx), int(ly)))
                x0, x1 = max(0, r.left), min(WINDOW_W, r.right)
                y0, y1 = max(0, r.top), min(WINDOW_H, r.bottom)
                if x0 >= x1 or y0 >= y1:
                    continue
                gx0, gy0 = x0 - r.left, y0 - r.top
                gsub = gp[gx0:gx0 + (x1 - x0), gy0:gy0 + (y1 - y0)]
                sub = base[x0:x1, y0:y1]
                red = int(a * min(1.0, inten))
                sub -= np.minimum(sub, (gsub.astype(np.int16) * red // 255)).astype(sub.dtype)
            pygame.surfarray.pixels_alpha(dark)[:, :] = base
            del base
        except Exception:
            pass
        self.screen.blit(dark, (0, 0))
        # тёплые ореоны поверх (аддитивно)
        warm = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
        for (lx, ly, inten) in lights[:48]:
            size = max(24, int(192 * inten))
            img = pygame.transform.scale(glow, (size, size)) if size != glow.get_width() else glow
            tmp = img.copy()
            tmp.set_alpha(int(70 * self.night * inten))
            warm.blit(tmp, tmp.get_rect(center=(int(lx), int(ly))))
        self.screen.blit(warm, (0, 0))
        # объёмные лучи в глубокой ночи — только ближайшие источники
        if self.night > 0.45 and lights:
            beam = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
            for (bx, by, bi) in lights[:12]:
                length = int(130 * bi)
                seg = pygame.Surface((length, 30), pygame.SRCALPHA)
                for i in range(0, length, 5):
                    al = int(22 * bi * (1 - i / length))
                    pygame.draw.line(seg, (255, 226, 170, al), (i, 6 + i % 4),
                                     (i, 24 - i % 4))
                rect = seg.get_rect(midleft=(int(bx), int(by)))
                beam.blit(seg, rect)
            self.screen.blit(beam, (0, 0))
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

    def _sky_tint_overlay(self):
        """Подкраска кадра по фазе суток (game writes renderer.sky_tint)."""
        tint, alpha = getattr(self, "sky_tint", ((255, 255, 255), 0))
        if alpha <= 0:
            return
        key = (tint, alpha)
        ov = getattr(self, "_sky_tint_img", None)
        ovk = getattr(self, "_sky_tint_key", None)
        if ov is None or ovk != key:
            ov = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
            ov.fill((tint[0], tint[1], tint[2], alpha))
            self._sky_tint_img = ov
            self._sky_tint_key = key
        self.screen.blit(ov, (0, 0))


# ------------------------------------------------------------- CASIO-часы
def segment_surface(seg_w, seg_h, on_color, off_color):
    """Один «сегмент» семисегментного индикатора: вытянутая трапеция."""
    s = pygame.Surface((seg_w, seg_h), pygame.SRCALPHA)
    inset = max(1, seg_h // 3)
    pts = [(inset, 0), (seg_w - inset, 0), (seg_w, seg_h / 2),
           (seg_w - inset, seg_h), (inset, seg_h), (0, seg_h / 2)]
    pygame.draw.polygon(s, on_color, pts)
    return s


class CasioClock:
    """Цифровые часы в стиле CASIO (как у Багрова на запястье):
    тёмный прямоугольный корпус, зелёное ЖK-окно, крупные сегментные
    цифры ЧЧ:ММ:СС, тонкие подписи дней недели сверху."""

    # карта сегментов цифр: a..g (стандартная семисегментная нумерация)
    DIGIT_MAP = {
        "0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd",
        "4": "fgbc", "5": "afgcd", "6": "afgecd", "7": "abc",
        "8": "abcdefg", "9": "abcdfg", "-": "g", " ": "",
    }
    DAYS = ("ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС")

    def __init__(self, scale=1.0):
        self.scale = scale
        self.on_color = (150, 235, 170)          # холодный ЖК-зелёный
        self.off_color = (34, 58, 42)            # «погасшие» сегменты
        self.glass = (16, 30, 22)
        self.build()

    # ------------------------------------------------------------------ сборка
    def build(self):
        sc = self.scale
        self.digit_w = max(8, int(22 * sc))
        self.digit_h = max(16, int(40 * sc))
        th = max(3, int(6 * sc))                 # толщина сегмента
        vlen = int((self.digit_h - 3 * th) / 2)  # длина вертикального
        hlen = self.digit_w - 2 * th             # длина горизонтального
        self.seg_v = segment_surface(th, vlen, self.on_color, self.on_color)
        self.seg_h = segment_surface(hlen, th, self.on_color, self.on_color)
        self.seg_v_off = segment_surface(th, vlen, self.off_color, self.off_color)
        self.seg_h_off = segment_surface(hlen, th, self.off_color, self.off_color)

        self.win_pad = (int(14 * sc), int(10 * sc))
        gap = max(3, int(8 * sc))                # межцифровой интервал
        colon_w = max(5, int(10 * sc))
        n_digits = 6                              # ЧЧ:ММ:СС
        self.win_w = n_digits * self.digit_w + 2 * gap + 2 * colon_w \
            + int(10 * sc)
        self.win_h = self.digit_h + int(12 * sc)
        top_band = max(10, int(14 * sc))         # полоса «CASIO / дни недели»
        frame = max(4, int(8 * sc))              # рамка корпуса
        self.body = pygame.Surface(
            (self.win_w + 2 * self.win_pad[0] + 2 * frame,
             self.win_h + 2 * self.win_pad[1] + 2 * frame + top_band),
            pygame.SRCALPHA)
        bw, bh = self.body.get_size()
        # корпус — тёмный пластик с лёгким градиентом и бликом
        for yy in range(bh):
            k = 0.75 + 0.5 * (1 - yy / max(1, bh - 1))
            c = tuple(min(255, int(v * k)) for v in (52, 54, 60))
            pygame.draw.line(self.body, c, (0, yy), (bw - 1, yy))
        pygame.draw.rect(self.body, (26, 27, 30), (0, 0, bw, bh),
                         max(1, int(2 * sc)), border_radius=int(8 * sc))
        # стеклянное окно
        wx, wy = frame + self.win_pad[0], frame + top_band + self.win_pad[1]
        glass = pygame.Surface((self.win_w, self.win_h), pygame.SRCALPHA)
        glass.fill((*self.glass, 255))
        pygame.draw.rect(glass, (8, 14, 10), (0, 0, self.win_w, self.win_h),
                         max(1, int(2 * sc)))
        self.body.blit(glass, (wx, wy))
        self.win_pos = (wx, wy)
        # надписи: CASIO слева, дни недели справа
        f_big = get_font(max(8, int(11 * sc)), bold=True)
        f_sm = get_font(max(6, int(8 * sc)))
        brand = f_big.render("CASIO", True, (214, 216, 220))
        self.body.blit(brand, (frame + int(6 * sc),
                               frame + (top_band - brand.get_height()) // 2))
        days_x = bw - frame - int(6 * sc)
        for ab in reversed(self.DAYS):
            d_img = f_sm.render(ab, True, (150, 152, 158))
            days_x -= d_img.get_width() + int(3 * sc)
            self.body.blit(d_img, (days_x,
                                   frame + (top_band - d_img.get_height()) // 2))
        #Precompute digit layouts
        self._digit_cache = {}
        self._colon_img = self._make_colon()
        self._dim_colon_img = self._make_dim_colon()

    def _make_colon(self):
        sc = self.scale
        w = max(5, int(10 * sc))
        s = pygame.Surface((w, self.digit_h), pygame.SRCALPHA)
        r = max(1, int(2.6 * sc))
        for yy in (self.digit_h * 0.3, self.digit_h * 0.7):
            pygame.draw.circle(s, self.on_color, (w // 2, int(yy)), r)
        return s

    def _make_dim_colon(self):
        """Тот же двоичный разделитель, но «погасший» (для мигания ~2 Гц)."""
        sc = self.scale
        w = max(5, int(10 * sc))
        s = pygame.Surface((w, self.digit_h), pygame.SRCALPHA)
        r = max(1, int(2.6 * sc))
        dim = tuple(int(c * 0.22) for c in self.on_color)
        for yy in (self.digit_h * 0.3, self.digit_h * 0.7):
            pygame.draw.circle(s, dim, (w // 2, int(yy)), r)
        return s

    # ------------------------------------------------------------------ логика
    @staticmethod
    def time_string(time_of_day):
        t = time_of_day % 24.0
        hh = int(t)
        mm = int((t - hh) * 60)
        ss = int(round(((t - hh) * 60 - mm) * 60))
        if ss >= 60:
            ss, mm = 0, mm + 1
        if mm >= 60:
            mm, hh = 0, (hh + 1) % 24
        return f"{hh:02d}:{mm:02d}:{ss:02d}"

    def _draw_digit(self, target, x, y, ch):
        """Рисуем одну цифру: все 7 позиций, «лишние» сегменты погашены."""
        lit = self.DIGIT_MAP.get(ch, "")
        th = max(3, int(6 * self.scale))
        half_v = (self.digit_h - 3 * th) // 2
        pos = {
            "a": (x + th, y, "h"),
            "b": (x + self.digit_w - th, y + th, "v"),
            "c": (x + self.digit_w - th, y + 2 * th + half_v, "v"),
            "d": (x + th, y + self.digit_h - th, "h"),
            "e": (x, y + 2 * th + half_v, "v"),
            "f": (x, y + th, "v"),
            "g": (x + th, y + (self.digit_h - th) // 2, "h"),
        }
        for name, (sx, sy, orient) in pos.items():
            if orient == "h":
                img = self.seg_h if name in lit else self.seg_h_off
            else:
                img = self.seg_v if name in lit else self.seg_v_off
            target.blit(img, (sx, sy))

    def render_face(self, time_of_day):
        """Поверхность часов с текущим игровым временем (мигает «:»)."""
        ts = self.time_string(time_of_day)
        blink = (int(time_of_day * 2) % 2) == 0   # двоеточие мигает ~2 Гц
        key = (ts, blink)
        face = self._digit_cache.get(key)
        if face is None:
            face = self.body.copy()
            wx, wy = self.win_pos
            x = wx + int(5 * self.scale)
            y = wy + int(6 * self.scale)
            gap = max(3, int(8 * self.scale))
            for ch in ts:
                if ch == ":":
                    img = self._colon_img if blink else self._dim_colon_img
                    face.blit(img, (x, y))
                    x += self._colon_img.get_width() + gap
                else:
                    self._draw_digit(face, x, y, ch)
                    x += self.digit_w + gap
            if len(self._digit_cache) > 4800:
                self._digit_cache.clear()
            self._digit_cache[key] = face
        return face


_CLOCK_INSTANCE = None


def draw_casio_clock(screen, time_of_day, pos=None, scale=1.0):
    """Рисует CASIO-часы в углу экрана (по умолчанию — правый нижний)."""
    global _CLOCK_INSTANCE
    if _CLOCK_INSTANCE is None or abs(_CLOCK_INSTANCE.scale - scale) > 1e-6:
        _CLOCK_INSTANCE = CasioClock(scale=scale)
    face = _CLOCK_INSTANCE.render_face(time_of_day)
    W, H = screen.get_size()
    if pos is None:
        pos = (W - face.get_width() - 14, H - face.get_height() - 46)
    shadow = pygame.Surface((face.get_width() + 6, face.get_height() + 6),
                            pygame.SRCALPHA)
    pygame.draw.rect(shadow, (0, 0, 0, 90), (3, 3, face.get_width(),
                                             face.get_height()),
                     border_radius=8)
    screen.blit(shadow, pos)
    screen.blit(face, pos)
    return face


# ---------------------------------------------------------------- шрифты
_FONT_CACHE = {}
_FONT_PATHS = None       # найденный системный TTF с кириллицей


def _find_cyrillic_fonts():
    """Список путей к TTF, гарантированно содержащим кириллицу
    (DejaVu/Liberation на Linux, Arial на Windows, LucidaGrande/PingFang на macOS)."""
    global _FONT_PATHS
    if _FONT_PATHS is not None:
        return _FONT_PATHS
    import glob
    import os as _os
    import platform
    cands = []
    names = ["DejaVuSans.ttf", "DejaVuSans-Bold.ttf",
             "LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf",
             "FreeSans.ttf"]
    dirs = ["/usr/share/fonts", "/usr/local/share/fonts",
            _os.path.join(_os.path.expanduser("~"), ".fonts"),
            _os.path.join(_os.environ.get("WINDIR", "C:\\Windows"), "Fonts")]
    for d in dirs:
        for pat in names:
            cands += glob.glob(_os.path.join(d, "**", pat), recursive=True)
    if platform.system() == "Darwin":
        cands += ["/System/Library/Fonts/Supplemental/Arial.ttf",
                  "/Library/Fonts/Arial.ttf",
                  "/System/Library/Fonts/Helvetica.ttc"]
    else:
        cands += [_os.path.join(_os.environ.get("WINDIR", "C:\\Windows"),
                                "Fonts", "arial.ttf"),
                  _os.path.join(_os.environ.get("WINDIR", "C:\\Windows"),
                                "Fonts", "segoeui.ttf"),
                  _os.path.join(_os.environ.get("WINDIR", "C:\\Windows"),
                                "Fonts", "tahoma.ttf")]
    ok = []
    test = "АБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"
    for p in cands:
        try:
            ft = pygame.font.Font(p, 16)
            w1 = ft.size(test)[0]
            w2 = ft.size("AAAAAAAAAAAAAA")[0]
            if w1 > 40 and abs(w1 - w2) > 2:   # не «тофу» и не одинаковые глифы
                ok.append(p)
        except Exception:
            continue
    _FONT_PATHS = ok
    return ok


class _NoFont:
    """Заглушка для среды без шрифтов (CI/headless)."""

    def __init__(self, size):
        self.size_px = size

    def render(self, text, aa=False, color=(0, 0, 0)):
        h = max(8, int(self.size_px * 1.2))
        return pygame.Surface((max(1, 7 * len(str(text))), h), pygame.SRCALPHA)

    def size(self, text):
        return (max(1, 7 * len(str(text))), max(8, int(self.size_px * 1.2)))

    def get_height(self):
        return max(8, int(self.size_px * 1.2))

    def get_ascent(self):
        return max(6, int(self.size_px * 0.9))


def get_font(size, bold=False):
    key = (size, bold)
    f = _FONT_CACHE.get(key)
    if f is None:
        f = None
        # 1) проверенные TTF с кириллицей — самый надёжный путь
        paths = _find_cyrillic_fonts()
        if paths:
            want = "Bold" if bold else "Regular"
            best = None
            for p in paths:
                base = p.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
                if want.lower() in base.lower():
                    best = p
                    break
            try:
                f = pygame.font.Font(best or paths[0], size)
                if best is None and bold:
                    f.set_bold(True)
            except Exception:
                f = None
        # 2) SysFont как запасной вариант
        if f is None:
            try:
                f = pygame.font.SysFont(
                    "dejavusans,liberationsans,freesans,arial,helveticaneue",
                    size, bold=bold)
            except Exception:
                f = None
        # 3) встроенный фонт pygame + ручной включаемый bold
        if f is None:
            try:
                f = pygame.font.Font(None, size)
                if bold:
                    f.set_bold(True)
            except Exception:
                f = _NoFont(size)
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
