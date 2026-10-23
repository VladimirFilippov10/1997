# -*- coding: utf-8 -*-
"""Процедурные текстуры и спрайты.

Никаких внешних картинок: всё генерируется на старте в память, поэтому
игра одинаково запускается на Windows и macOS и не тянет ассеты.
Используем pygame.surfarray + numpy (numpy идёт в комплекте с pygame-ce).
"""
import math
import random

import pygame
from pygame import surfarray

try:
    import numpy as np
except Exception:  # pragma: no cover - numpy обязателен для pygame-ce
    np = None


# ------------------------------------------------------------------ утилиты
def _rng(seed):
    return random.Random(seed)


def noise_surface(size, base, amp, seed, octaves=3):
    """Шумная прямоугольная поверхность (grain/бетон/асфальт)."""
    w, h = size
    rnd = _rng(seed)
    if np is not None:
        arr = np.full((w, h, 3), base, dtype=np.float32)
        for o in range(octaves):
            scale = 1 << (o + 1)          # 2,4,8...
            gw, gh = max(2, w // scale), max(2, h // scale)
            block = np.random.RandomState(seed + o * 977).rand(gh, gw, 3)
            block = (block - 0.5) * (amp / (o + 1))
            zoomed = np.repeat(np.repeat(block, scale, axis=0), scale, axis=1)
            zoomed = zoomed[:w, :h]
            arr += zoomed
        arr = np.clip(arr, 0, 255).astype(np.uint8)
        s = pygame.Surface((w, h))
        if hasattr(surfarray, "blit"):
            surfarray.blit(s, arr)
        else:  # pygame-ce: массив должен быть в формате (h, w, 3)
            surfarray.pixels3d(s)[:, :, :] = np.transpose(arr, (1, 0, 2))
        return s
    # запасной вариант без numpy
    s = pygame.Surface((w, h))
    s.fill(base)
    px = pygame.PixelArray(s)
    for _ in range(w * h // 6):
        x, y = rnd.randrange(w), rnd.randrange(h)
        d = rnd.randint(-amp // 2, amp // 2)
        c = tuple(max(0, min(255, v + d)) for v in base)
        px[x, y] = c
    del px
    return s


def mottle(size, colors, seed, blobs=40):
    """Пятнистая поверхность (дворы, трава, ржавчина)."""
    w, h = size
    rnd = _rng(seed)
    s = pygame.Surface((w, h))
    s.fill(colors[0])
    for _ in range(blobs):
        cx, cy = rnd.randrange(w), rnd.randrange(h)
        r = rnd.randint(2, max(3, min(w, h) // 4))
        col = rnd.choice(colors)
        pygame.draw.circle(s, col, (cx, cy), r)
    grain = noise_surface((w, h), (0, 0, 0), 26, seed + 5)
    grain.set_alpha(70)
    s.blit(grain, (0, 0))
    return s


# --------------------------------------------------------------- тайлы земли
def asphalt(size=64, seed=1):
    s = noise_surface((size, size), (58, 60, 64), 40, seed, octaves=4)
    rnd = _rng(seed)
    # трещины
    for _ in range(3):
        pts = []
        x, y = rnd.randrange(size), rnd.randrange(size)
        for _ in range(6):
            pts.append((x, y))
            x += rnd.randint(-9, 9)
            y += rnd.randint(-9, 9)
        if len(pts) > 1:
            pygame.draw.lines(s, (40, 41, 45), False, pts, 1)
    return s


def concrete(size=64, seed=2):
    s = noise_surface((size, size), (96, 96, 98), 26, seed, octaves=3)
    rnd = _rng(seed)
    col = (78, 78, 82)
    step = size // 2
    for i in range(0, size + 1, step):
        pygame.draw.line(s, col, (i, 0), (i, size), 1)
        pygame.draw.line(s, col, (0, i), (size, i), 1)
    return s


def brick_pavement(size=64, seed=3):
    """«Ёлочка» из кирпичей — типичный питерский тротуар."""
    s = pygame.Surface((size, size))
    s.fill((70, 66, 64))
    rnd = _rng(seed)
    bw, bh = 16, 8
    y = 0
    while y < size:
        x = 0
        while x < size:
            c = (rnd.randint(88, 108), rnd.randint(70, 86), rnd.randint(62, 74))
            r = pygame.Rect(x, y, bw - 1, bh - 1)
            s.fill(c, r)
            x += bw
        y += bh
    g = noise_surface((size, size), (0, 0, 0), 20, seed + 11)
    g.set_alpha(60)
    s.blit(g, (0, 0))
    return s


def grass(size=64, seed=4):
    s = mottle((size, size), [(52, 68, 48), (46, 62, 44), (58, 74, 52)], seed, 30)
    rnd = _rng(seed)
    for _ in range(120):
        x, y = rnd.randrange(size), rnd.randrange(size)
        pygame.draw.line(s, (62, 82, 54), (x, y), (x + rnd.randint(-1, 1), y - 2), 1)
    return s


def water(size=128, seed=5):
    s = noise_surface((size, size), (34, 48, 62), 22, seed, octaves=3)
    rnd = _rng(seed)
    for _ in range(40):
        y = rnd.randrange(size)
        x = rnd.randrange(size)
        ln = rnd.randint(6, 26)
        pygame.draw.line(s, (58, 78, 96), (x, y), (x + ln, y), 1)
    return s


def sand(size=64, seed=6):
    return mottle((size, size), [(92, 86, 70), (84, 78, 64), (100, 94, 76)], seed, 24)


def wall_face(size=64, seed=7):
    """Фасад дома (вид сверху — плоская крыша/стена)."""
    s = noise_surface((size, size), (110, 104, 98), 24, seed, octaves=3)
    rnd = _rng(seed)
    for _ in range(rnd.randint(2, 5)):
        x = rnd.randrange(size)
        pygame.draw.line(s, (86, 82, 78), (x, 0), (x, size), 2)
    return s


def roof_face(size=64, seed=8):
    s = noise_surface((size, size), (92, 88, 84), 22, seed, octaves=3)
    rnd = _rng(seed)
    for _ in range(6):
        y = rnd.randrange(size)
        pygame.draw.line(s, (72, 68, 66), (0, y), (size, y), 1)
    return s


# ------------------------------------------------------- плоские объекты
def curb_tile(size=48, seed=9, ground=(58, 60, 64)):
    """Бордюр: полоса асфальта + светлый камень."""
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    s.fill((*ground, 255))
    pygame.draw.rect(s, (128, 128, 130), (0, size // 2 - 3, size, 6))
    pygame.draw.rect(s, (150, 150, 152), (0, size // 2 - 3, size, 2))
    return s


def road_marking(size=48, seed=10):
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.rect(s, (190, 188, 170), (size // 2 - 2, 6, 4, size - 12))
    return s


def puddle(size=48, seed=11):
    rnd = _rng(seed)
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    w, h = size // 2 + rnd.randint(-4, 4), size // 3 + rnd.randint(-3, 3)
    pygame.draw.ellipse(s, (40, 52, 66, 190), (size // 2 - w // 2, size // 2 - h // 2, w, h))
    pygame.draw.ellipse(s, (70, 88, 108, 120), (size // 2 - w // 2 + 2, size // 2 - h // 2 + 1, w - 4, 3), 1)
    return s


def crosswalk(size=48):
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    for i in range(3):
        pygame.draw.rect(s, (180, 180, 172), (i * (size // 3) + 3, 0, size // 3 - 6, size))
    return s


# ------------------------------------------------------------- высокие объекты
def building(size=48, floors=5, seed=1, roof=None, shade=0.85):
    """Кубик дома с «крышей» и лёгким объёмом (тень по нижнему краю)."""
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    base = roof or (92, 88, 84)
    dark = tuple(int(c * shade) for c in base)
    s.fill((*base, 255))
    # конёк/скаты
    for i in range(0, size, max(6, size // floors)):
        pygame.draw.line(s, dark, (0, i), (size, i), 1)
    pygame.draw.rect(s, (*dark, 255), (0, 0, size, 3))
    pygame.draw.rect(s, (*dark, 255), (0, size - 4, size, 4))
    rnd = _rng(seed)
    # трубы / вентиляция
    for _ in range(rnd.randint(1, 3)):
        x, y = rnd.randrange(4, size - 6), rnd.randrange(4, size - 6)
        pygame.draw.rect(s, (70, 66, 64), (x, y, 4, 4))
    return s


def car(size=(46, 22), color=(90, 96, 110), seed=1, angle=0):
    rnd = _rng(seed)
    w, h = size
    body = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(body, color, (0, 2, w, h - 4), border_radius=5)
    light = tuple(min(255, c + 40) for c in color)
    pygame.draw.rect(body, light, (w // 4, 4, w // 3, h - 8), border_radius=3)
    pygame.draw.rect(body, (20, 22, 26), (w - 8, 4, 4, h - 8))
    pygame.draw.rect(body, (200, 200, 160), (2, 4, 3, 4))
    pygame.draw.rect(body, (200, 200, 160), (2, h - 8, 3, 4))
    if angle:
        body = pygame.transform.rotate(body, angle)
    return body


def tree_canopy(size=64, seed=1):
    """Крона сверху — прозрачный слой над головой игрока."""
    rnd = _rng(seed)
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    cx, cy = size // 2, size // 2
    for _ in range(14):
        a = rnd.uniform(0, math.tau)
        r = rnd.uniform(size * 0.18, size * 0.42)
        x = int(cx + math.cos(a) * r)
        y = int(cy + math.sin(a) * r)
        col = (rnd.randint(38, 62), rnd.randint(58, 82), rnd.randint(36, 54), 235)
        pygame.draw.circle(s, col, (x, y), rnd.randint(size // 8, size // 5))
    pygame.draw.circle(s, (48, 70, 44, 240), (cx, cy), size // 4)
    return s


def lamp_post(size=24, seed=1):
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.circle(s, (40, 40, 44, 160), (size // 2, size // 2), size // 2 - 1)
    pygame.draw.circle(s, (70, 70, 76), (size // 2, size // 2), 4)
    pygame.draw.circle(s, (230, 220, 150), (size // 2, size // 2), 2)
    return s


def bench(size=40, h=16, seed=1):
    rnd = _rng(seed)
    s = pygame.Surface((size, h), pygame.SRCALPHA)
    col = (96, 74, 52)
    pygame.draw.rect(s, col, (0, 0, size, h // 2), border_radius=2)
    pygame.draw.rect(s, tuple(int(c * 0.8) for c in col), (0, h // 2, size, h // 2 - 1), border_radius=2)
    for x in range(4, size, size // 4):
        pygame.draw.line(s, (40, 40, 42), (x, h - 2), (x, h), 2)
    return s


def trash(size=24, seed=1):
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.circle(s, (58, 66, 58), (size // 2, size // 2), size // 2 - 2)
    pygame.draw.circle(s, (40, 46, 42), (size // 2, size // 2), size // 2 - 5, 2)
    pygame.draw.circle(s, (120, 120, 120), (size // 2, size // 2), 3)
    return s


# ------------------------------------------------------------------- персонаж
def person(radius=11, jacket=(62, 66, 74), skin=(196, 168, 140),
           hat=(40, 42, 48), facing=0.0, shadow=True):
    """Человек вид сверху: плечи-овал, куртка, шапка, рукавицы-кулаки."""
    d = radius * 2 + 6
    s = pygame.Surface((d, d), pygame.SRCALPHA)
    cx, cy = d // 2, d // 2
    if shadow:
        sh = pygame.Surface((d, d), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 70), (2, 4, d - 4, d - 6))
        s.blit(sh, (0, 0))
    # плечи (овал поперёк направления)
    ang = math.degrees(facing) + 90
    shoulder = pygame.Surface((d, d), pygame.SRCALPHA)
    pygame.draw.ellipse(shoulder, jacket, (2, 4, d - 4, d - 8))
    pygame.draw.ellipse(shoulder, tuple(int(c * 0.75) for c in jacket),
                        (2, 4, d - 4, d - 8), 1)
    rot = pygame.transform.rotate(shoulder, ang)
    rect = rot.get_rect(center=(cx, cy))
    s.blit(rot, rect.topleft)
    # руки вдоль тела
    for side in (-1, 1):
        ax = cx + math.cos(facing + math.pi / 2 * side) * (radius - 2)
        ay = cy + math.sin(facing + math.pi / 2 * side) * (radius - 2)
        pygame.draw.circle(s, tuple(int(c * 0.9) for c in jacket),
                           (int(ax), int(ay)), radius // 2)
    # голова / шапка
    hx = cx + math.cos(facing) * 2
    hy = cy + math.sin(facing) * 2
    pygame.draw.circle(s, skin, (int(hx), int(hy)), radius // 2 + 1)
    pygame.draw.circle(s, hat, (int(hx), int(hy)), radius // 2)
    pygame.draw.circle(s, tuple(int(c * 0.7) for c in hat),
                       (int(hx), int(hy)), radius // 2, 1)
    return s


def make_player_frames(jacket=(62, 66, 74)):
    """8 направлений × 2 кадра покачивания — кэш спрайтов игрока."""
    frames = {}
    for i in range(8):
        ang = i * math.tau / 8
        for bob in (0.0, 1.5):
            f = ang + math.sin(bob) * 0.0
            fr = person(radius=11, jacket=jacket, facing=f,
                        hat=(44, 46, 52), skin=(200, 170, 142))
            if bob:
                fr = pygame.transform.rotozoom(fr, 3, 1.0)
            frames[(i, int(bob))] = fr
    return frames


# --------------------------------------------------------------------- предметы
ITEM_COLORS = {
    "bread": (178, 132, 74),
    "cigarettes": (200, 190, 170),
    "money": (150, 170, 140),
    "ttt": (120, 124, 130),
    "vodka": (150, 190, 200),
    "bag": (120, 96, 70),
    "key": (190, 170, 90),
    "newspaper": (200, 200, 195),
}


def item_icon(name, size=34, seed=1):
    rnd = _rng(seed)
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    col = ITEM_COLORS.get(name, (150, 150, 150))
    if name == "bread":
        pygame.draw.ellipse(s, col, (3, size // 3, size - 6, size // 2))
        for i in range(3):
            pygame.draw.line(s, (140, 100, 56), (8 + i * 7, size // 3 + 2),
                             (12 + i * 7, size // 2), 2)
    elif name == "cigarettes":
        pygame.draw.rect(s, (170, 40, 40), (4, 8, size - 8, size - 16), border_radius=3)
        pygame.draw.rect(s, (230, 226, 210), (7, 10, size - 14, 5))
    elif name == "money":
        pygame.draw.rect(s, col, (3, 8, size - 6, size - 16))
        pygame.draw.rect(s, (110, 130, 100), (3, 8, size - 6, size - 16), 2)
        pygame.draw.circle(s, (110, 130, 100), (size // 2, size // 2), 5)
    elif name == "ttt":
        pygame.draw.circle(s, col, (size // 2, size // 2), size // 2 - 3)
        pygame.draw.circle(s, (70, 72, 78), (size // 2, size // 2), size // 2 - 6, 2)
        pygame.draw.rect(s, (60, 62, 68), (size // 2 - 2, 4, 4, 8))
    elif name == "vodka":
        pygame.draw.rect(s, col, (size // 2 - 6, 8, 12, size - 12), border_radius=3)
        pygame.draw.rect(s, (210, 210, 210), (size // 2 - 3, 3, 6, 6))
    elif name == "bag":
        pygame.draw.rect(s, col, (5, 10, size - 10, size - 14), border_radius=4)
        pygame.draw.arc(s, (80, 64, 46), (size // 2 - 8, 2, 16, 12), math.pi, 2 * math.pi, 2)
    elif name == "key":
        pygame.draw.circle(s, col, (10, size // 2), 6)
        pygame.draw.rect(s, col, (14, size // 2 - 2, size - 18, 4))
    else:  # newspaper
        pygame.draw.rect(s, col, (4, 6, size - 8, size - 12))
        for i in range(4):
            pygame.draw.line(s, (120, 120, 118), (8, 10 + i * 5), (size - 8, 10 + i * 5), 1)
    return s


def hotbar_frame(size=52, selected=False):
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    bg = (28, 30, 36, 210) if not selected else (48, 52, 62, 235)
    pygame.draw.rect(s, bg, (0, 0, size, size), border_radius=6)
    edge = COL_ACCENT_E if selected else (90, 92, 100, 200)
    pygame.draw.rect(s, edge, (0, 0, size, size), 2, border_radius=6)
    return s


COL_ACCENT_E = (200, 60, 48, 255)
