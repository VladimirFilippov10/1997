# -*- coding: utf-8 -*-
"""Автопарк 1997 года: ВАЗ-2101 «Копейка», ВАЗ-2109 «Самара», BMW E34.

Каждая машина описана геометрией кузова (вид сверху) и палитрой цветов,
которые реально встречались в Питере в конце 90-х. Из геометрии собираются
спрайты: корпус + тонированные стёкла с бликами + крыша + молдинги +
поворотники/стопы + колёса с фазами вращения.
"""
import math

import pygame


def _shade(col, k):
    return tuple(max(0, min(255, int(c * k))) for c in col[:3])


# ------------------------------------------------------------------ модели
CAR_MODELS = {
    "vaz2101": {
        "label": "ВАЗ-2101",
        "dims": (46, 21),            # длина × ширина в px (масштаб тайла 48)
        "wheelbase": (10, 35),       # x передних / задних колёс
        "track": 1.5,                # выступ колеса за корпус
        "colors": {
            "lada_blue": ((74, 96, 128), "синий"),
            "lada_white": ((196, 194, 184), "белый"),
            "lada_green": ((84, 108, 84), "зелёный"),
            "lada_red": ((140, 56, 48), "красный"),
            "lada_black": ((52, 52, 56), "чёрный"),
            "lada_beige": ((158, 142, 110), "бежевый"),
        },
        "shape": "classic",          # прямоугольный классический кузов
        "cabin": (17, 27),           # начало/конец кабины по длине
        "hood_len": 13,
        "trunk_len": 9,
        "round_lights": True,
    },
    "vaz2109": {
        "label": "ВАЗ-2109",
        "dims": (48, 22),
        "wheelbase": (11, 38),
        "track": 1.5,
        "colors": {
            "zerch": ((104, 116, 128), "«Зерч» серо-голубой"),
            "tuzi": ((70, 84, 100), "тёмно-синий"),
            "asphalt": ((92, 94, 96), "асфальт"),
            "marlboro": ((150, 52, 44), "красный"),
            "snowflake": ((200, 200, 196), "снежная королева"),
            "nesterova": ((84, 104, 78), "зелёный Нестеровой"),
        },
        "shape": "hatch",            # приземистый хэтчбек, скошенный зад
        "cabin": (16, 34),
        "hood_len": 12,
        "trunk_len": 6,              # короткий хэтхвост
        "round_lights": False,       # прямоугольная оптика
    },
    "bmwe34": {
        "label": "BMW E34",
        "dims": (54, 24),
        "wheelbase": (12, 43),
        "track": 2.0,
        "colors": {
            "alpinewhite": ((214, 216, 218), "Alpinweiss"),
            "brilliantblue": ((44, 62, 96), "Brilliantblau"),
            "schwarz": ((38, 38, 42), "Schwarz"),
            "dunkelgruen": ((46, 62, 52), "Dunkelgruen"),
            "bronze": ((122, 96, 62), "bronze metallic"),
            "corcona": ((140, 60, 52), "Corconared"),
        },
        "shape": "sedan90",          # вытянутый «клиновидный» седан
        "cabin": (19, 40),
        "hood_len": 15,
        "trunk_len": 11,
        "round_lights": False,
        "kidney": True,              # решётка «ноздри BMW»
        "chrome": True,              # хромированная окантовка окон
    },
}


def dims_for(model):
    return CAR_MODELS.get(model, CAR_MODELS["vaz2101"])["dims"]


# ------------------------------------------------------------- отрисовка
def _body_polygon(w, h, shape):
    """Верхний контур корпуса (для полигона) — форма зависит от модели."""
    r = 3
    if shape == "hatch":
        pts = [(r, 1), (w - 8, 0), (w, 3), (w, h - 3), (w - 8, h), (r, h - 1),
               (0, h - r - 1), (0, r + 1)]
    elif shape == "sedan90":
        pts = [(2, 2), (w // 3, 0), (int(w * 0.72), 0), (w - 2, 2), (w, 5),
               (w, h - 5), (w - 2, h - 2), (int(w * 0.72), h), (w // 3, h),
               (2, h - 2), (0, h - 5), (0, 5)]
    else:  # classic
        pts = [(r, 0), (w - r, 0), (w, r), (w, h - r), (w - r, h), (r, h),
               (0, h - r), (0, r)]
    return pts


def car_sprite(model="vaz2101", color=(74, 96, 128), seed=1):
    """Кузов машины вид сверху, ориентирован «на восток» (+x = морда)."""
    spec = CAR_MODELS.get(model, CAR_MODELS["vaz2101"])
    w, h = spec["dims"]
    S = spec["shape"]
    cx0, cx1 = spec["cabin"]
    rnd = __import__("random").Random(seed)

    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    light = _shade(color, 1.3)
    mid = _shade(color, 1.0)
    dark = _shade(color, 0.72)
    darker = _shade(color, 0.55)
    glass_dark = (26, 32, 42)
    glass_lit = (64, 82, 104)

    # ---- основной корпус
    pygame.draw.polygon(surf, mid, _body_polygon(w, h, S))
    # градиент освещения: северная сторона светлее южной
    ov = pygame.Surface((w, h), pygame.SRCALPHA)
    for yy in range(h):
        a = int(46 * (1 - yy / max(1, h - 1)))
        pygame.draw.line(ov, (*light, a), (0, yy), (w, yy))
    ov2 = pygame.Surface((w, h), pygame.SRCALPHA)
    for yy in range(h):
        a = int(38 * (yy / max(1, h - 1)))
        pygame.draw.line(ov2, (*darker, a), (0, yy), (w, yy))
    mask = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.polygon(mask, (255, 255, 255, 255), _body_polygon(w, h, S))
    ov.set_alpha(255)
    tmp = ov.copy()
    tmp.blit(ov2, (0, 0), special_flags=pygame.BLEND_ALPHA_SDL2)
    surf.blit(tmp, (0, 0), mask)

    # ---- капот: линия замка + подштамповка
    pygame.draw.line(surf, dark, (spec["hood_len"], 2), (spec["hood_len"], h - 2), 1)
    if S == "sedan90":
        pygame.draw.line(surf, light, (2, h // 2 - 4), (spec["hood_len"] - 2, h // 2 - 4), 1)
        pygame.draw.line(surf, light, (2, h // 2 + 4), (spec["hood_len"] - 2, h // 2 + 4), 1)

    # ---- кабина/крыша
    roof = pygame.Rect(cx0, 2, cx1 - cx0, h - 4)
    # лобовое стекло (скошенное у девятки/E34)
    slant = 4 if S != "classic" else 2
    glass_pts_f = [(cx0, 3), (cx0 + slant, 3), (cx0 + slant, h - 3), (cx0, h - 3)]
    pygame.draw.polygon(surf, glass_dark, glass_pts_f)
    pygame.draw.polygon(surf, glass_lit, [(cx0 + 1, 4), (cx0 + slant - 1, 4),
                                          (cx0 + slant - 1, h // 2 - 2), (cx0 + 1, h // 2 - 2)])
    # боковые окна
    side_w = max(4, (cx1 - cx0) // 2 - 2)
    for gx, gw in ((cx0 + slant + 2, side_w), (cx1 - side_w - 2, side_w)):
        pygame.draw.rect(surf, glass_dark, (gx, 3, gw, 4))
        pygame.draw.rect(surf, glass_dark, (gx, h - 7, gw, 4))
        pygame.draw.rect(surf, glass_lit, (gx + 1, 4, gw - 2, 1))
        pygame.draw.rect(surf, glass_lit, (gx + 1, h - 6, gw - 2, 1))
    # заднее стекло
    if S == "hatch":
        pygame.draw.polygon(surf, glass_dark, [(cx1 - 2, 3), (cx1 + 2, 5),
                                               (cx1 + 2, h - 5), (cx1 - 2, h - 3)])
    else:
        pygame.draw.rect(surf, glass_dark, (cx1 - slant, 3, slant + 1, h - 6))
    # крыша — чуть светлее корпуса, с продольными усилителями
    pygame.draw.rect(surf, _shade(color, 1.12), (cx0 + slant + 1, 6,
                                                 cx1 - cx0 - 2 * slant - 2, h - 12))
    for ly in (h // 2 - 2, h // 2 + 2):
        pygame.draw.line(surf, dark, (cx0 + slant + 2, ly), (cx1 - slant - 2, ly), 1)
    if spec.get("chrome"):
        pygame.draw.rect(surf, (170, 176, 184), (cx0, 2, cx1 - cx0, h - 4), 1)

    # ---- двери: линии + ручки
    door_x = (cx0 + cx1) // 2
    for ddx in (door_x,):
        pygame.draw.line(surf, dark, (ddx, 2), (ddx, h - 2), 1)
    if S == "sedan90":
        pygame.draw.line(surf, dark, (cx0 + 2, 2), (cx0 + 2, h - 2), 1)
    for hx in (door_x - 3, cx1 - 4):
        pygame.draw.rect(surf, _shade(color, 0.6), (hx, 5, 3, 1))
        pygame.draw.rect(surf, _shade(color, 0.6), (hx, h - 6, 3, 1))

    # ---- молдинги по борту
    mould = (30, 30, 34) if S != "classic" else _shade(color, 0.65)
    pygame.draw.line(surf, mould, (3, h - 2), (w - 3, h - 2), 1)
    pygame.draw.line(surf, mould, (3, 1), (w - 3, 1), 1)

    # ---- багажник / хэтхвост
    trunk_x = cx1 + (2 if S == "hatch" else 3)
    pygame.draw.line(surf, dark, (trunk_x, 2), (trunk_x, h - 2), 1)
    if S == "hatch":
        pygame.draw.rect(surf, (150, 36, 30), (w - 3, 3, 2, 5))
        pygame.draw.rect(surf, (150, 36, 30), (w - 3, h - 8, 2, 5))
        pygame.draw.rect(surf, (230, 226, 200), (w - 3, h // 2 - 2, 2, 4))  # ЗФ
    else:
        for sy in (4, h - 7):
            pygame.draw.rect(surf, (150, 36, 30), (w - 3, sy, 3, 3))

    # ---- оптика спереди
    if spec["round_lights"]:
        for cy in (5, h - 6):
            pygame.draw.circle(surf, (236, 232, 200), (3, cy), 2)
            pygame.draw.circle(surf, (150, 140, 90), (3, cy), 2, 1)
        pygame.draw.rect(surf, (236, 232, 200), (2, h // 2 - 1, 2, 2))  # доп. фары
    else:
        pygame.draw.rect(surf, (236, 232, 200), (1, 3, 3, 4))
        pygame.draw.rect(surf, (236, 232, 200), (1, h - 7, 3, 4))
    # поворотники
    for cy in (3, h - 5):
        pygame.draw.rect(surf, (240, 170, 60), (5 if not spec["round_lights"] else 6, cy, 2, 2))

    # ---- решётка радиатора
    if spec.get("kidney"):
        for gy in (h // 2 - 5, h // 2 + 1):
            pygame.draw.rect(surf, (24, 24, 28), (1, gy, 3, 4), border_radius=1)
            pygame.draw.rect(surf, (150, 154, 160), (1, gy, 3, 4), 1, border_radius=1)
    else:
        pygame.draw.rect(surf, (24, 24, 28), (1, 6, 2, h - 12))
        for i in range(6, h - 6, 2):
            pygame.draw.line(surf, (70, 72, 78), (1, i), (2, i))

    # ---- зеркала
    pygame.draw.rect(surf, dark, (cx0 + 1, 0, 3, 2))
    pygame.draw.rect(surf, dark, (cx0 + 1, h - 2, 3, 2))

    # ---- номерной знак
    pygame.draw.rect(surf, (220, 220, 216), (w - 8, h // 2 - 2, 6, 4))
    pygame.draw.rect(surf, (60, 60, 64), (w - 8, h // 2 - 2, 6, 4), 1)

    # ---- «дворники» и антенна для атмосферы
    if rnd.random() < 0.6:
        ax, ay = cx0 - 2, rnd.choice((3, h - 4))
        pygame.draw.line(surf, (30, 30, 34), (ax, ay), (ax - 4, ay), 1)
    if S != "hatch" and rnd.random() < 0.5:
        pygame.draw.line(surf, (190, 192, 198), (trunk_x - 2, 2), (trunk_x - 3, 0), 1)

    # обводка корпуса
    pygame.draw.polygon(surf, _shade(color, 0.5), _body_polygon(w, h, S), 1)
    return surf


def make_model_frames(model, color, seed=1):
    """Кадры как у T.make_car_frames: dict[(dir,moving,phase,blink)] -> Surface.

    Колёса вращаются (4 фазы), на краю полосы мигает поворотник, ночью
    renderer сам добавляет конусы фар по точкам car_headlights().
    """
    base = car_sprite(model, color, seed)
    bw, bh = base.get_size()
    spec = CAR_MODELS.get(model, CAR_MODELS["vaz2101"])
    wx_f, wx_r = spec["wheelbase"]
    track = spec["track"]
    wheels = [(wx_f, -track), (wx_f, bh + track), (wx_r, -track), (wx_r, bh + track)]

    wh = pygame.Surface((9, 5), pygame.SRCALPHA)
    wh.fill((14, 14, 16, 255))
    frames = {}
    still_parts = pygame.Surface((bw + 8, bh + 8), pygame.SRCALPHA)
    sh = pygame.Surface((bw + 8, bh + 8), pygame.SRCALPHA)
    pygame.draw.ellipse(sh, (0, 0, 0, 60), (4, 5, bw, bh))
    still_parts.blit(sh, (0, 0))

    def compose(moving, phase, blink):
        surf = still_parts.copy()
        for (x, y) in wheels:
            img = wh
            if moving:
                img = pygame.transform.rotate(wh, phase * 45)
                rect = img.get_rect(center=(x + 4, y + 4))
                surf.blit(img, rect)
            else:
                rect = pygame.Rect(x + 4 - wh.get_width() // 2,
                                   y + 4 - wh.get_height() // 2,
                                   wh.get_width(), wh.get_height())
                surf.blit(wh, rect)
        surf.blit(base, (4, 4))
        if blink:
            gl = pygame.Surface((10, 10), pygame.SRCALPHA)
            pygame.draw.circle(gl, (255, 190, 60, 220), (5, 5), 4)
            pygame.draw.circle(gl, (255, 240, 180, 255), (5, 5), 2)
            surf.blit(gl, (6, bh // 2 - 8 if model == "classic" else 2))
            surf.blit(gl, (6, bh - 2))
        return surf

    cache = {}
    for moving in (False, True):
        for phase in (range(4) if moving else (0,)):
            for blink in (0, 1):
                cache[(moving, phase, blink)] = compose(moving, phase, blink)
    for d in range(8):
        rotang = d * 45
        for key, img in cache.items():
            r = pygame.transform.rotate(img, rotang) if rotang else img
            frames[(d,) + key] = r
    return frames


def car_headlights(model, color=None):
    spec = CAR_MODELS.get(model, CAR_MODELS["vaz2101"])
    w, h = spec["dims"]
    if spec["round_lights"]:
        return [(3, 5), (3, h - 6)]
    return [(2, 5), (2, h - 5)]


def random_color(model, rnd):
    keys = list(CAR_MODELS[model]["colors"].keys())
    return CAR_MODELS[model]["colors"][rnd.choice(keys)][0]
