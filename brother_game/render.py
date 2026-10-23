# -*- coding: utf-8 -*-
"""Отрисовка района и персонажа (вид сверху).

Оптимизация под «шустро»:
 * ground+flat+стены печатаются один раз в общий буфер карты (Surface),
   дальше blit видимой области — O(экран);
 * динамические объекты (машины/люди/деревья) сортируются по Y
   (painter's algorithm) и рисуются только попавшие в камеру;
 * над игроком рисуется слой листвы и козырьков.
"""
import math

import pygame

import textures as T
from config import (COL_ACCENT, COL_TEXT, LAYER_GROUND, TILE, WINDOW_H, WINDOW_W)

WORLD_W_T = None  # заполняется из district


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
                    img = self.tiles["asphalt"] if False else img
                else:
                    img = self.tiles.get(t, self.tiles["asphalt"])
                surf.blit(img, (tx * TILE, y))
        # ---- flat
        for f in d.flat:
            t = f["t"]
            px, py = f["x"] * TILE, f["y"] * TILE
            if t == "stain":
                surf.blit(self.stains[f.get("seed", 0) % len(self.stains)], (px, py))
            elif t == "leaf":
                surf.blit(self.leaves[f.get("seed", 0) % len(self.leaves)], (px, py))
            elif t in self.flat_tiles:
                img = self.flat_tiles[t]
                if t == "puddle":
                    img = pygame.transform.rotate(img, f.get("seed", 0) % 90)
                surf.blit(img, (px, py))
        # ---- стены домов (крыша + тень внутрь двора)
        for w in d.walls:
            rect = pygame.Rect(w["x"] * TILE, w["y"] * TILE, w["w"] * TILE, w["h"] * TILE)
            roof = tuple(int(c * 0.82) for c in w["color"])
            surf.fill(roof, rect)
            # скаты
            for i in range(0, rect.height, max(8, TILE // 2)):
                pygame.draw.line(surf, tuple(int(c * 0.7) for c in w["color"]),
                                 (rect.left, rect.top + i), (rect.right, rect.top + i), 1)
            for i in range(0, rect.width, TILE):
                pygame.draw.line(surf, tuple(int(c * 0.75) for c in w["color"]),
                                 (rect.left + i, rect.top), (rect.left + i, rect.bottom), 1)
            # парапет
            pygame.draw.rect(surf, tuple(int(c * 1.12) for c in w["color"]), rect, 2)
            # тень от дома на юг (внизу)
            sh = pygame.Surface((rect.width, 8), pygame.SRCALPHA)
            sh.fill((0, 0, 0, 70))
            if rect.bottom + 8 < self.world_px_h:
                surf.blit(sh, (rect.left, rect.bottom))
        self.map_surface = surf
        return surf

    # --------------------------------------------------------- динамические
    def _get_prop_img(self, p):
        key = (p["t"], p.get("angle", 0), p.get("color"), p.get("seed", 0), p.get("size"))
        img = self._prop_cache.get(key)
        if img is not None:
            return img
        t = p["t"]
        if t == "car":
            ang = p.get("angle", 0)
            img = T.car((46, 22), p.get("color", (90, 96, 110)), p.get("seed", 1), ang)
        elif t == "lamp":
            img = T.lamp_post(22, p.get("seed", 1))
        elif t == "bench":
            img = T.bench(40, 16, p.get("seed", 1))
            if p.get("angle"):
                img = pygame.transform.rotate(img, p["angle"])
        elif t == "trash":
            img = T.trash(22, p.get("seed", 1))
        elif t == "trunk":
            img = pygame.Surface((20, 20), pygame.SRCALPHA)
            pygame.draw.circle(img, (58, 46, 36), (10, 10), 7)
            pygame.draw.circle(img, (40, 32, 26), (10, 10), 7, 2)
        elif t == "tower":
            img = pygame.Surface((44, 44), pygame.SRCALPHA)
            pygame.draw.polygon(img, (90, 92, 98), [(22, 2), (38, 42), (6, 42)])
            pygame.draw.line(img, (60, 62, 68), (22, 2), (22, 42), 2)
            pygame.draw.circle(img, (200, 60, 48), (22, 6), 3)
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

    def _get_npc(self, n):
        key = (n["jacket"], int(n["facing"] / (math.tau / 8)))
        img = self._npc_cache.get(key)
        if img is None:
            img = T.person(radius=11, jacket=n["jacket"], facing=key[1] * math.tau / 8,
                           hat=(48, 44, 40), skin=(190, 165, 140))
            self._npc_cache[key] = img
        return img

    # ------------------------------------------------------------- draw
    def draw(self, camera, player, time_s, inventory_sel, messages):
        d = self.d
        camx, camy = camera
        camx = int(max(0, min(self.world_px_w - WINDOW_W, camx)))
        camy = int(max(0, min(self.world_px_h - WINDOW_H, camy)))
        view = pygame.Rect(camx, camy, WINDOW_W, WINDOW_H)

        self.screen.blit(self.map_surface, (0, 0), view)

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

        # ---- collect sorted drawables (props + npcs + player) by Y
        draw_list = []
        for p in d.props:
            if view.inflate(120, 120).collidepoint(p["x"], p["y"]):
                draw_list.append((p["y"], "prop", p))
        for n in d.npcs:
            if view.inflate(120, 120).collidepoint(n["x"], n["y"]):
                draw_list.append((n["y"], "npc", n))
        draw_list.append((player.y, "player", player))
        draw_list.sort(key=lambda e: e[0])

        for _, kind, obj in draw_list:
            if kind == "prop":
                img = self._get_prop_img(obj)
                sx, sy = obj["x"] - camx, obj["y"] - camy
                self.screen.blit(img, img.get_rect(center=(sx, sy)))
            elif kind == "npc":
                img = self._get_npc(obj)
                sx, sy = obj["x"] - camx, obj["y"] - camy
                self.screen.blit(img, img.get_rect(center=(sx, sy)))
            else:
                img = player.sprite(time_s)
                sx, sy = obj.x - camx, obj.y - camy
                self.screen.blit(img, img.get_rect(center=(sx, sy)))

        # ---- верхний слой: листва, трубы
        for o in d.over:
            if o["t"] == "tree" and view.inflate(160, 160).collidepoint(o["x"], o["y"]):
                img = self._get_tree(o)
                sx, sy = o["x"] - camx, o["y"] - camy
                self.screen.blit(img, img.get_rect(center=(sx, sy)))
            elif o["t"] == "pipe":
                sx, sy = o["x"] - camx, o["y"] - camy
                if -TILE < sx < WINDOW_W + TILE:
                    pygame.draw.rect(self.screen, (74, 70, 68),
                                     (sx - TILE // 2, sy - 6, TILE, 12))
                    pygame.draw.rect(self.screen, (96, 92, 88),
                                     (sx - TILE // 2, sy - 6, TILE, 3))

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

        # ---- виньетка / туман (дешёвая имитация осеннего Петербурга)
        self._vignette(camx, camy, player)

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
