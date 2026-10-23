# -*- coding: utf-8 -*-
"""Процедурные текстуры и спрайты.

Никаких внешних картинок: всё генерируется на старте в память, поэтому
игра одинаково запускается на Windows и macOS и не тянет ассеты.
Используем pygame.surfarray + numpy (numpy идёт в комплекте с pygame-ce).

Модели «проработанные», но читаемые сверху:
  * здания — 6 типов крыш (скаты/эркер/мансарда/стеклянная крыша рынка,
    дымовые трубы с тягой, чердачные окна-«слухи», парапет с бликом);
  * автомобили — 4 кузова (седан / «папский» фургон / маршрутка / грузовик),
    фары с конусами света, мигающие поворотники, вращающиеся колёса,
    антенна, тень под корпусом;
  * человек — покадровая походка (маховые руки + перекат корпуса);
  * фонари — конус света; киоски, гаражи, стадион, вышка и т.д.
"""
import math
import random

import pygame
from pygame import surfarray

try:
    import numpy as np
except Exception:  # pragma: no cover - numpy обязателен для pygame-ce
    np = None


def _shade(col, k):
    return tuple(max(0, min(255, int(c * k))) for c in col[:3])


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
    """Асфальт: многослойный шум + «жирные» пятна старого покрытия,
    латки ремонтных служб,Aggregate-вкрапления гравия, трещины-«паутинка»."""
    s = noise_surface((size, size), (58, 60, 64), 44, seed, octaves=5)
    rnd = _rng(seed)
    # вкрапления гравия (светлые/тёмные точки)
    for _ in range(size * size // 26):
        x, y = rnd.randrange(size), rnd.randrange(size)
        v = rnd.randint(-26, 30)
        c = tuple(max(0, min(255, 58 + v + rnd.randint(-4, 4))) for _ in range(3))
        s.set_at((x, y), ((c[0] + 8, c[1] + 6, c[2] + 4) if v > 12 else c))
    # битумные пятна («масляные разводы» из гаражей)
    for _ in range(2):
        cx, cy = rnd.randrange(size), rnd.randrange(size)
        rr = rnd.randint(4, 9)
        patch = pygame.Surface((rr * 2, rr * 2), pygame.SRCALPHA)
        for i in range(rr, 0, -1):
            a = int(26 * (1 - i / rr))
            pygame.draw.circle(patch, (26, 26, 30, a), (rr, rr), i)
        s.blit(patch, (cx - rr, cy - rr))
    # латок ремонта (прямоугольный, темнее и ровнее)
    if rnd.random() < 0.3:
        px_, py_ = rnd.randrange(size - 18), rnd.randrange(size - 12)
        pw, ph = rnd.randint(12, 20), rnd.randint(8, 14)
        p = noise_surface((pw, ph), (48, 49, 52), 18, seed + 31, octaves=2)
        s.blit(p, (px_, py_))
        pygame.draw.rect(s, (42, 43, 46), (px_, py_, pw, ph), 1)
    # трещины — ветвящиеся «паутинки»
    for _ in range(3):
        x, y = rnd.randrange(size), rnd.randrange(size)
        pts = [(x, y)]
        ang = rnd.uniform(0, math.tau)
        for _ in range(7):
            ang += rnd.uniform(-0.8, 0.8)
            x += math.cos(ang) * rnd.randint(3, 8)
            y += math.sin(ang) * rnd.randint(3, 8)
            pts.append((int(x), int(y)))
        pygame.draw.lines(s, (38, 39, 43), False, pts, 1)
        if rnd.random() < 0.6:      # ответвление
            k = rnd.randrange(len(pts) - 1)
            bx, by = pts[k]
            pygame.draw.line(s, (40, 41, 45), (bx, by),
                             (bx + rnd.randint(-8, 8), by + rnd.randint(-8, 8)), 1)
    return s


def concrete(size=64, seed=2):
    """Бетонные плиты тротуара: шагрень, температурные швы, сколы, мох в швах."""
    s = noise_surface((size, size), (98, 98, 100), 30, seed, octaves=4)
    rnd = _rng(seed)
    # поверхностная шагрень — микроямки
    for _ in range(size * size // 40):
        x, y = rnd.randrange(size), rnd.randrange(size)
        d = rnd.randint(-16, 10)
        base = s.get_at((x, y))
        s.set_at((x, y), tuple(max(0, min(255, v + d)) for v in base[:3]))
    col = (76, 76, 80)
    step = size // 2
    for i in range(0, size + 1, step):
        pygame.draw.line(s, col, (i, 0), (i, size), 1)
        pygame.draw.line(s, (116, 116, 118), (i + 1, 0), (i + 1, size), 1)
        pygame.draw.line(s, col, (0, i), (size, i), 1)
        pygame.draw.line(s, (116, 116, 118), (0, i + 1), (size, i + 1), 1)
    # сколы углов плит и потёки
    for _ in range(2):
        cx, cy = rnd.randrange(step, size, step), rnd.randrange(step, size, step)
        for _ in range(rnd.randint(3, 6)):
            dx, dy = rnd.randint(-6, 6), rnd.randint(-6, 6)
            pygame.draw.circle(s, (82, 82, 84),
                               (max(0, min(size - 1, cx + dx)),
                                max(0, min(size - 1, cy + dy))), rnd.randint(1, 2))
    if rnd.random() < 0.35:   # зелень у шва — классика питерских тротуаров
        gx = rnd.randrange(0, size)
        for gy in range(0, size, 3):
            pygame.draw.line(s, (70, 92, 62), (gx, gy), (gx + rnd.randint(-2, 2), gy + 2), 1)
    return s


def brick_pavement(size=64, seed=3):
    """Брусчатка «ёлочкой» — типичный питерский тротуар.

    Кирпичи лежат под 45°, у каждого своя грань света/тени и микропросвет
    шва; местами — провалы, выбоины и patches нового кирпича.
    """
    rnd = _rng(seed)
    # рисуем крупнее и режем по центру — диагональная кладка без «ступенек»
    pad = size
    big = pygame.Surface((size + pad * 2, size + pad * 2))
    big.fill((62, 58, 56))                       # песок/швы
    bw, bh = 15, 7
    hue = rnd.choice([(96, 78, 66), (88, 82, 80), (104, 84, 70)])
    for row_i, yy in enumerate(range(-bh, big.get_height(), bh)):
        off = (row_i % 2) * (bw // 2)
        for xx in range(-bw + off, big.get_width(), bw):
            v = rnd.uniform(0.82, 1.18)
            c = tuple(max(0, min(255, int(ch * v))) for ch in hue)
            r = pygame.Rect(xx + 1, yy + 1, bw - 2, bh - 2)
            big.fill(c, r)
            # фаска: верхняя кромка светлее, нижная темнее
            top = tuple(min(255, int(ch * 1.25)) for ch in c)
            bot = tuple(int(ch * 0.7) for ch in c)
            pygame.draw.line(big, top, r.topleft, (r.right - 1, r.top))
            pygame.draw.line(big, bot, r.bottomleft, (r.right - 1, r.bottom - 1))
            if rnd.random() < 0.05:              # скол/трещина на кирпиче
                pygame.draw.line(big, (54, 50, 48),
                                 (rnd.randrange(r.left, r.right), r.top),
                                 (rnd.randrange(r.left, r.right), r.bottom), 1)
    diag = pygame.transform.rotate(big, 45)
    s = pygame.Surface((size, size))
    rect = diag.get_rect(center=(s.get_width() // 2, s.get_height() // 2))
    s.blit(diag, rect)
    # выбоины — просел шов, видна земля
    for _ in range(2):
        cx, cy = rnd.randrange(size), rnd.randrange(size)
        pygame.draw.circle(s, (56, 50, 44), (cx, cy), rnd.randint(2, 4))
    # заплатка свежего асфальта вокруг колодца — частая картина
    if rnd.random() < 0.25:
        cx, cy = rnd.randrange(size), rnd.randrange(size)
        pygame.draw.circle(s, (66, 66, 70), (cx, cy), 9)
        pygame.draw.circle(s, (52, 52, 56), (cx, cy), 9, 1)
    g = noise_surface((size, size), (0, 0, 0), 22, seed + 11)
    g.set_alpha(64)
    s.blit(g, (0, 0))
    return s


def grass(size=64, seed=4):
    """Газон после питерского лета: пятна разной высоты, примятые дорожки,
    одуванчики-«лысины», торчащая былинками трава."""
    rnd = _rng(seed)
    s = mottle((size, size), [(52, 68, 48), (46, 62, 44), (58, 74, 52),
                              (50, 64, 42), (64, 80, 54)], seed, 46)
    # «примятые тропинки» — люди ходят по короткой траве
    for _ in range(2):
        pts = []
        x, y = rnd.randrange(size), rnd.randrange(size)
        ang = rnd.uniform(0, math.tau)
        for _ in range(8):
            ang += rnd.uniform(-0.5, 0.5)
            x += math.cos(ang) * 6
            y += math.sin(ang) * 6
            pts.append((int(x), int(y)))
        pygame.draw.lines(s, (74, 84, 58), False, pts, 3)
    # былинки: вертикальные штрихи с бликом/тенью
    for _ in range(200):
        x, y = rnd.randrange(size), rnd.randrange(size)
        hgt = rnd.randint(2, 4)
        lit = rnd.random() < 0.4
        col = (86, 110, 66) if lit else (40, 56, 38)
        pygame.draw.line(s, col, (x, y), (x + rnd.randint(-1, 1), y - hgt), 1)
    # жухлые кустики
    for _ in range(8):
        x, y = rnd.randrange(size), rnd.randrange(size)
        for a in range(-2, 3):
            pygame.draw.line(s, (110, 100, 60), (x, y), (x + a * 2, y - 3), 1)
    return s


def water(size=128, seed=5):
    """Канал: глубокая вода с рябью, бликами неба и мусором у берега."""
    rnd = _rng(seed)
    s = noise_surface((size, size), (34, 48, 62), 20, seed, octaves=4)
    # донные тени — тёмные размытые полосы глубже
    for _ in range(6):
        y = rnd.randrange(size)
        pygame.draw.line(s, (26, 38, 52), (0, y), (size, y + rnd.randint(-6, 6)),
                         rnd.randint(4, 10))
    # рябь: короткие горизонтальные блики двух тонов
    for _ in range(70):
        y = rnd.randrange(size)
        x = rnd.randrange(size)
        ln = rnd.randint(5, 24)
        bright = rnd.random() < 0.3
        col = (96, 122, 148) if bright else (56, 76, 94)
        pygame.draw.line(s, col, (x, y), (x + ln, y), 1)
        if bright:
            pygame.draw.line(s, (40, 54, 70), (x, y + 1), (x + ln, y + 1), 1)
    # масляная плёнка — радужные разводы
    film = pygame.Surface((size, size), pygame.SRCALPHA)
    for _ in range(4):
        cx, cy = rnd.randrange(size), rnd.randrange(size)
        rr = rnd.randint(10, 26)
        pygame.draw.circle(film, (90, 120, 110, 14), (cx, cy), rr)
        pygame.draw.circle(film, (120, 90, 120, 10), (cx + 4, cy - 3), rr - 4)
    s.blit(film, (0, 0))
    # пена/мусор у стенки набережной (верх тайла)
    for x in range(0, size, 3):
        if rnd.random() < 0.5:
            pygame.draw.line(s, (120, 130, 132), (x, 1), (x + 2, 2), 1)
    return s


def sand(size=64, seed=6):
    """Песок детской площадки: волны от граблей, камни, следы."""
    rnd = _rng(seed)
    s = mottle((size, size), [(92, 86, 70), (84, 78, 64), (100, 94, 76),
                              (96, 90, 72)], seed, 34)
    # «волны» утрамбованного песка
    for i in range(0, size, 6):
        pts = [(x, i + int(2 * math.sin(x * 0.25 + seed))) for x in range(0, size, 4)]
        pygame.draw.lines(s, (104, 98, 80), False, pts, 1)
        pygame.draw.lines(s, (80, 74, 60), False,
                          [(x, y + 1) for x, y in pts], 1)
    # камешки и стеклышки
    for _ in range(14):
        x, y = rnd.randrange(size), rnd.randrange(size)
        pygame.draw.circle(s, (120, 116, 104), (x, y), 1)
        if rnd.random() < 0.2:
            pygame.draw.circle(s, (150, 150, 140), (x, y), 1)
    # след кроссовка
    fx, fy = rnd.randrange(4, size - 8), rnd.randrange(4, size - 8)
    pygame.draw.ellipse(s, (76, 70, 58), (fx, fy, 5, 9))
    return s


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
    """Бордюр: полоса асфальта + гранитные камни с фаской и тенями."""
    rnd = _rng(seed)
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    s.fill((*ground, 255))
    # slight асфальтовая «канавка» у камня
    pygame.draw.rect(s, (50, 51, 55, 255), (0, size // 2 - 5, size, 2))
    y0 = size // 2 - 3
    x = -(rnd.randrange(6))
    while x < size:
        pw = rnd.choice((8, 10, 12))
        c = (132, 132, 134) if rnd.random() < 0.5 else (120, 120, 124)
        pygame.draw.rect(s, c, (x, y0, min(pw, size - x), 6))
        pygame.draw.line(s, (158, 158, 160), (x, y0), (x + pw - 1, y0))
        pygame.draw.line(s, (92, 92, 96), (x, y0 + 5), (x + pw - 1, y0 + 5))
        pygame.draw.line(s, (88, 88, 92), (x + pw - 1, y0), (x + pw - 1, y0 + 5))
        x += pw
    return s


def road_marking(size=48, seed=10):
    """Дорожная разметка: стёртая краска поверх старого асфальта."""
    rnd = _rng(seed)
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    x0 = size // 2 - 2
    for dx in range(5):
        a = 210 - dx * 26
        col = (196, 194, 176, max(0, a - rnd.randint(0, 30)))
        pygame.draw.line(s, col, (x0 + dx, 6), (x0 + dx, size - 12), 1)
    # сколы/протёртости краски
    for _ in range(5):
        y = rnd.randrange(8, size - 12)
        pygame.draw.line(s, (58, 60, 64, 200), (x0 + 1, y),
                         (x0 + rnd.randint(1, 3), y + 1), 1)
    return s


def puddle(size=48, seed=11):
    rnd = _rng(seed)
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    w, h = size // 2 + rnd.randint(-4, 4), size // 3 + rnd.randint(-3, 3)
    cx, cy = size // 2, size // 2
    pygame.draw.ellipse(s, (36, 48, 62, 200), (cx - w // 2, cy - h // 2, w, h))
    # отражение неба — светлее сверху, тёмное дно снизу
    pygame.draw.ellipse(s, (74, 92, 112, 120),
                        (cx - w // 2 + 2, cy - h // 2 + 1, w - 4, h // 2))
    pygame.draw.ellipse(s, (58, 74, 92, 90),
                        (cx - w // 2 + 2, cy + h // 2 - 4, w - 4, 3))
    # грязный ободок с мусором
    pygame.draw.ellipse(s, (48, 50, 46, 110),
                        (cx - w // 2 - 1, cy - h // 2 - 1, w + 2, h + 2), 1)
    for _ in range(3):
        pygame.draw.circle(s, (90, 96, 88, 120),
                           (rnd.randrange(cx - w // 2, cx + w // 2),
                            rnd.randrange(cy - h // 2, cy + h // 2)), 1)
    return s


def crosswalk(size=48):
    """«Зебра»: полосыpainter со стёртостью и следами шин."""
    rnd = _rng(17)
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    for i in range(3):
        x0 = i * (size // 3) + 3
        w = size // 3 - 6
        for dx in range(w):
            a = 185 - abs(dx - w // 2) * 8 + rnd.randint(-14, 6)
            pygame.draw.line(s, (188, 186, 176, max(60, a)),
                             (x0 + dx, 0), (x0 + dx, size))
        # следы торможения поперёк полосы
        ty = rnd.randrange(6, size - 6)
        pygame.draw.line(s, (120, 118, 110, 90), (x0, ty), (x0 + w, ty + 1), 2)
    return s


def yard_surface(size, seed):
    """Дворовый бетон: разбитые плиты, трещины с травой, масляные лужи,
    следы шин и песочные присыпки у подъездов."""
    rnd = _rng(seed)
    s = noise_surface((size, size), (74, 74, 72), 30, seed, octaves=4)
    # плитами 1/4 тайла со швами-«тенями»
    step = max(12, size // 4)
    for i in range(0, size + 1, step):
        pygame.draw.line(s, (56, 56, 56), (i, 0), (i, size))
        pygame.draw.line(s, (92, 92, 90), (min(i + 1, size - 1), 0),
                         (min(i + 1, size - 1), size))
        pygame.draw.line(s, (56, 56, 56), (0, i), (size, i))
        pygame.draw.line(s, (92, 92, 90), (0, min(i + 1, size - 1)),
                         (size, min(i + 1, size - 1)))
    # «паутинные» трещины по плитам, в них — мох
    for _ in range(3):
        x, y = rnd.randrange(size), rnd.randrange(size)
        ang = rnd.uniform(0, math.tau)
        pts = [(x, y)]
        for _ in range(8):
            ang += rnd.uniform(-0.9, 0.9)
            x += math.cos(ang) * rnd.randint(3, 7)
            y += math.sin(ang) * rnd.randint(3, 7)
            pts.append((int(x), int(y)))
        pygame.draw.lines(s, (50, 51, 50), False, pts, 1)
        for k in range(1, len(pts) - 1, 3):
            if rnd.random() < 0.5:
                pygame.draw.line(s, (66, 84, 56), pts[k],
                                 (pts[k][0] + 1, pts[k][1] + 1), 1)
    # масляные пятна у гаражей/съездов
    for _ in range(2):
        cx, cy = rnd.randrange(size), rnd.randrange(size)
        rr = rnd.randint(4, 10)
        p = pygame.Surface((rr * 2, rr * 2), pygame.SRCALPHA)
        pygame.draw.ellipse(p, (30, 30, 34, 130), (0, 0, rr * 2, rr * 2 - 2))
        s.blit(p, (cx - rr, cy - rr))
    # присыпка песка у подъезда (летом подметают с песком)
    if rnd.random() < 0.4:
        px_, py_ = rnd.randrange(size), rnd.randrange(size)
        for _ in range(60):
            dx, dy = rnd.gauss(0, 6), rnd.gauss(0, 4)
            x = max(0, min(size - 1, int(px_ + dx)))
            y = max(0, min(size - 1, int(py_ + dy)))
            c = (rnd.randint(104, 122), rnd.randint(98, 112), rnd.randint(78, 90))
            s.set_at((x, y), c)
    return s


# ------------------------------------------------------------- здания (крыши)
ROOF_STYLES = ("gable", "hip", "mansard", "flat", "monitor", "glass")


def roof_sheet(w, h, style="gable", col=(96, 84, 78), seed=1):
    """Текстура скатной кровли: ряды «жести» / фальца, конёк, выцветания."""
    rnd = _rng(seed)
    s = pygame.Surface((max(2, w), max(2, h)))
    s.fill(col)
    dark = _shade(col, 0.72)
    light = _shade(col, 1.18)
    if style in ("gable", "mansard", "monitor"):
        step = 7 if style != "mansard" else 5
        for x in range(0, w, step):                      # вертикальные фальцы
            pygame.draw.line(s, dark, (x, 0), (x, h), 1)
            pygame.draw.line(s, light, (x + 1, 0), (x + 1, h), 1)
        ridge = h // 2 if style == "gable" else int(h * 0.32)
        pygame.draw.rect(s, light, (0, ridge - 2, w, 4))         # конёк
        pygame.draw.line(s, dark, (0, ridge + 2), (w, ridge + 2), 1)
        if style == "mansard":                             # излом мансарды
            pygame.draw.line(s, dark, (0, int(h * 0.7)), (w, int(h * 0.7)), 2)
            g = noise_surface((w, h - int(h * 0.7)), dark, 18, seed + 3)
            s.blit(g, (0, int(h * 0.7)))
    elif style == "hip":
        for i in range(0, min(w, h) // 2, 6):             # «валмовые» рёбра
            pygame.draw.line(s, dark, (i, i), (w - i, i), 1)
            pygame.draw.line(s, dark, (i, h - i), (w - i, h - i), 1)
        pygame.draw.line(s, light, (0, h // 2), (w, h // 2), 2)
    elif style == "glass":                                # крыша рынка
        s.fill(_shade(col, 0.6))
        for gx in range(0, w, 12):
            pygame.draw.line(s, (150, 160, 168), (gx, 0), (gx, h), 2)
        for gy in range(0, h, 16):
            pygame.draw.line(s, (120, 130, 138), (0, gy), (w, gy), 2)
        sh = pygame.Surface((w, h), pygame.SRCALPHA)
        for i in range(0, w + h, 26):
            pygame.draw.line(sh, (220, 232, 240, 40), (i, 0), (0, i), 3)
        s.blit(sh, (0, 0))
    else:                                                 # плоская кровля
        g = noise_surface((w, h), col, 22, seed)
        s.blit(g, (0, 0))
        for i in range(0, w, TILE_ := 48):
            pygame.draw.line(s, dark, (i, 0), (i, h), 1)
        for j in range(0, h, TILE_):
            pygame.draw.line(s, dark, (0, j), (w, j), 1)
        pygame.draw.rect(s, light, (0, 0, w, 2))
    # выцветание / пятна
    ov = noise_surface((w, h), (0, 0, 0), 30, seed + 9)
    ov.set_alpha(46)
    s.blit(ov, (0, 0))
    return s


def chimney_surf(size=12, brick=(104, 78, 66)):
    """Кирпичная труба с шапкой и отлётом (псевдо-объём)."""
    s = pygame.Surface((size * 3, size * 4), pygame.SRCALPHA)
    body = pygame.Rect(size, size * 2, size, size * 2)
    pygame.draw.rect(s, brick, body)
    pygame.draw.rect(s, _shade(brick, 0.75), (body.right - 3, body.top, 3, body.height))
    for y in range(body.top + 3, body.bottom, 4):
        pygame.draw.line(s, _shade(brick, 0.85), (body.left, y), (body.right - 3, y), 1)
    pygame.draw.rect(s, (58, 56, 54), (size - 2, size, size + 4, 5))   # колпак
    pygame.draw.rect(s, (30, 30, 32), (size + 1, size + 1, size - 2, 3))  # канал
    return s


def building_block(px_w, px_h, color=(112, 100, 92), floors=5, style="gable",
                   seed=1, tower=False):
    """Статичная «печать» дома для буфера карты: крыша + объём + детали.

    Псевдо-3D сверху: южная стена подсвечена полосой фасада с окнами,
    севернее — тень; по коньку — трубы, слуховые окна, антенны.
    Возвращает Surface размером (px_w + 10, px_h + 16) — рисовать по rect.
    """
    rnd = _rng(seed)
    pad_r, pad_b = 10, 16
    s = pygame.Surface((px_w + pad_r, px_h + pad_b), pygame.SRCALPHA)
    roof = roof_sheet(px_w, px_h, style, _shade(color, 0.86), seed)
    s.blit(roof, (0, 0))
    # южная стена (фасад, повёрнутый к «солнцу») — полоса с окнами
    wall_h = 7 + min(6, floors)
    wy = px_h
    pygame.draw.rect(s, _shade(color, 1.06), (0, wy, px_w, wall_h))
    pygame.draw.rect(s, _shade(color, 0.8), (0, wy, px_w, 1))
    win_w, win_h = 5, max(3, wall_h - 4)
    step = 13 if px_w > 90 else 11
    for wx in range(4, px_w - 6, step):
        lit = rnd.random() < 0.32
        c = (232, 208, 140) if lit else (44, 50, 60)
        pygame.draw.rect(s, c, (wx, wy + 2, win_w, win_h))
        pygame.draw.rect(s, _shade(color, 0.6), (wx, wy + 2, win_w, win_h), 1)
    # восточная стена — в тени
    pygame.draw.rect(s, _shade(color, 0.55), (px_w, 2, pad_r - 2, px_h - 2))
    # парапет с бликом
    pygame.draw.rect(s, _shade(color, 1.2), (0, 0, px_w, px_h), 2)
    pygame.draw.line(s, _shade(color, 1.35), (0, 0), (px_w, 0), 1)
    # слуховые окна («бычки») по коньку
    ridge_y = px_h // 2 if style == "gable" else int(px_h * 0.3)
    if style in ("gable", "mansard", "hip"):
        for dx in range(14, max(15, px_w - 14), 34):
            dorm_x = min(px_w - 10, dx)
            pygame.draw.rect(s, _shade(color, 1.1), (dorm_x, ridge_y - 6, 9, 7))
            pygame.draw.rect(s, (60, 66, 76), (dorm_x + 2, ridge_y - 4, 5, 4))
            pygame.draw.polygon(s, _shade(color, 0.7),
                                [(dorm_x - 1, ridge_y - 6), (dorm_x + 10, ridge_y - 6),
                                 (dorm_x + 5, ridge_y - 10)])
    # дымовые трубы (с «отлётом» на северо-запад)
    n_ch = max(1, px_w // 120) + rnd.randint(0, 1)
    for i in range(n_ch):
        cx = rnd.randrange(8, max(9, px_w - 20))
        cy = rnd.randrange(6, max(7, px_h - 24))
        ch = chimney_surf(7, _shade(color, 0.72))
        s.blit(ch, (cx, cy - 10))
    # антенна / флагшток на крупных домах
    if px_w > 150 and rnd.random() < 0.7:
        ax, ay = rnd.randrange(10, px_w - 10), rnd.randrange(6, px_h // 2)
        pygame.draw.line(s, (70, 72, 76), (ax, ay), (ax, ay - 14), 2)
        pygame.draw.line(s, (90, 92, 96), (ax - 5, ay - 12), (ax + 5, ay - 12), 1)
        pygame.draw.line(s, (90, 92, 96), (ax - 4, ay - 9), (ax + 4, ay - 9), 1)
    if tower:     # угловая башенка / эркер-башня (как у доходных домов)
        tx, ty = px_w - 26, px_h // 2
        pygame.draw.circle(s, _shade(color, 1.12), (tx, ty), 15)
        pygame.draw.circle(s, _shade(color, 0.7), (tx, ty), 15, 2)
        for a in range(0, 360, 45):
            x2 = tx + math.cos(math.radians(a)) * 15
            y2 = ty + math.sin(math.radians(a)) * 15
            pygame.draw.line(s, _shade(color, 0.8), (tx, ty), (int(x2), int(y2)), 1)
        pygame.draw.circle(s, (150, 120, 90), (tx, ty), 5)
    return s


# ------------------------------------------------------------ автомобили
CAR_KINDS = ("sedan", "van", "bus", "truck")


def car_body(kind="sedan", color=(90, 96, 110), seed=1):
    """Статичный корпус машины вид сверху (без света/колёс)."""
    rnd = _rng(seed)
    dims = {"sedan": (46, 22), "van": (48, 24), "bus": (58, 23), "truck": (56, 23)}
    w, h = dims.get(kind, (46, 22))
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    light = _shade(color, 1.25)
    dark = _shade(color, 0.7)
    glass = (30, 36, 46)
    if kind == "sedan":
        pygame.draw.rect(s, color, (0, 1, w, h - 2), border_radius=6)
        pygame.draw.rect(s, dark, (0, 1, w, h - 2), 1, border_radius=6)
        pygame.draw.rect(s, glass, (w // 2 - 9, 4, 18, h - 8), border_radius=3)  # салон
        pygame.draw.rect(s, light, (w // 2 - 10, 3, 20, 2))                     # крыша блик
        pygame.draw.line(s, dark, (w // 2 - 1, 3), (w // 2 - 1, h - 3), 1)      # B-стойка
        pygame.draw.rect(s, (18, 20, 24), (w - 7, 4, 5, h - 8), border_radius=2)  # решётка
        pygame.draw.rect(s, (235, 230, 190), (2, 4, 3, 4))                      # фары
        pygame.draw.rect(s, (235, 230, 190), (2, h - 8, 3, 4))
        pygame.draw.rect(s, (180, 40, 34), (w - 3, 4, 2, 4))                    # стопы
        pygame.draw.rect(s, (180, 40, 34), (w - 3, h - 8, 2, 4))
        if rnd.random() < 0.5:                                                  # антенна
            pygame.draw.line(s, (200, 200, 205), (w - 12, 2), (w - 10, 0), 1)
    elif kind == "van":
        pygame.draw.rect(s, color, (0, 0, w, h), border_radius=5)
        cab = (w // 3)
        pygame.draw.rect(s, glass, (cab - 8, 3, 10, h - 6))                     # лобовое
        pygame.draw.rect(s, _shade(color, 0.9), (cab, 2, w - cab - 3, h - 4), 1)
        for vx in range(cab + 6, w - 8, 10):                                    # заклёпки/двери
            pygame.draw.line(s, dark, (vx, 2), (vx, h - 2), 1)
        pygame.draw.rect(s, (235, 230, 190), (2, 4, 3, 4))
        pygame.draw.rect(s, (235, 230, 190), (2, h - 8, 3, 4))
        pygame.draw.rect(s, (180, 40, 34), (w - 3, 3, 2, h - 6))
    elif kind == "bus":
        pygame.draw.rect(s, color, (0, 1, w, h - 2), border_radius=6)
        pygame.draw.rect(s, glass, (6, 3, w - 14, 4))                           # окна слева
        pygame.draw.rect(s, glass, (6, h - 7, w - 14, 4))
        for bx in range(8, w - 10, 9):                                          # стойки
            pygame.draw.line(s, color, (bx, 3), (bx, 7), 1)
            pygame.draw.line(s, color, (bx, h - 7), (bx, h - 3), 1)
        pygame.draw.rect(s, _shade(color, 1.2), (0, h // 2 - 1, w, 2))          # полоса
        pygame.draw.rect(s, glass, (w - 8, 5, 4, h - 10))                       # лобовое
        pygame.draw.rect(s, (235, 230, 190), (2, 4, 3, 4))
        pygame.draw.rect(s, (235, 230, 190), (2, h - 8, 3, 4))
    else:  # truck
        cab_w = 16
        pygame.draw.rect(s, _shade(color, 0.85), (cab_w, 1, w - cab_w, h - 2),
                         border_radius=3)                                       # кузов
        pygame.draw.rect(s, color, (0, 2, cab_w, h - 4), border_radius=4)       # кабина
        pygame.draw.rect(s, glass, (cab_w - 7, 4, 5, h - 8))
        for rx in range(cab_w + 4, w - 4, 8):                                   # рифление
            pygame.draw.line(s, _shade(color, 0.65), (rx, 2), (rx, h - 2), 1)
        pygame.draw.rect(s, (235, 230, 190), (2, 5, 2, 4))
        pygame.draw.rect(s, (235, 230, 190), (2, h - 9, 2, 4))
        pygame.draw.rect(s, (180, 40, 34), (w - 3, 4, 2, h - 8))
    return s


WHEEL_IMG = None
HEADLIGHT_CONE = None


def wheel_img():
    global WHEEL_IMG
    if WHEEL_IMG is None:
        WHEEL_IMG = pygame.Surface((8, 8), pygame.SRCALPHA)
        pygame.draw.circle(WHEEL_IMG, (16, 16, 18), (4, 4), 4)
        pygame.draw.line(WHEEL_IMG, (60, 60, 64), (1, 4), (7, 4), 1)
        pygame.draw.line(WHEEL_IMG, (60, 60, 64), (4, 1), (4, 7), 1)
    return WHEEL_IMG


def headlight_cone(length=64):
    """Тёплый конус света фар (мягкий, через концентрические полигоны)."""
    global HEADLIGHT_CONE
    if HEADLIGHT_CONE is not None and HEADLIGHT_CONE.get_width() == length * 2:
        return HEADLIGHT_CONE
    w = length * 2
    s = pygame.Surface((w, length), pygame.SRCALPHA)
    for i in range(10):
        k = i / 10
        L = length * (1 - k * 0.82)
        halfw = 6 + (length * 0.42) * k
        a = int(26 * (1 - k) ** 1.5)
        pts = [(0, length // 2 - 2), (L, length // 2 - halfw),
               (L, length // 2 + halfw), (0, length // 2 + 2)]
        pygame.draw.polygon(s, (255, 236, 190, a), pts)
    HEADLIGHT_CONE = s
    return s


def make_car_frames(kind="sedan", color=(90, 96, 110), seed=1):
    """Анимированный автомобиль: 8 направлений × (стоп / 4 фазы колёс
    × мигалка поворотника). Ключ кадра: (moving_bool, wheel_phase 0..3, blink 0/1).

    Возвращает dict[ (dir_idx, moving, phase, blink) ] -> Surface.
    dir_idx: 0 = едет «на восток» (+x), дальше против часовой по 45°.
    """
    frames = {}
    base = car_body(kind, color, seed)
    bw, bh = base.get_size()
    dims = {"sedan": (46, 22), "van": (48, 24), "bus": (58, 23), "truck": (56, 23)}
    _, h = dims.get(kind, (46, 22))
    # точки колёс (для кузова, ориентированного на восток)
    if kind == "sedan":
        wheels = [(9, 1), (9, h - 1), (bw - 12, 1), (bw - 12, h - 1)]
    elif kind == "van":
        wheels = [(10, 0), (10, h), (bw - 12, 0), (bw - 12, h)]
    elif kind == "bus":
        wheels = [(10, 0), (10, h), (bw - 22, 0), (bw - 22, h), (bw - 10, 0), (bw - 10, h)]
    else:
        wheels = [(8, 0), (8, h), (bw - 20, 0), (bw - 20, h), (bw - 8, 0), (bw - 8, h)]
    # позиция переднего левого поворотника (для мигалки)
    blink_pos = (3, 6) if kind != "truck" else (3, 6)

    def compose(moving, phase, blink):
        surf = pygame.Surface((bw + 8, h + 8), pygame.SRCALPHA)
        # тень под машиной
        sh = pygame.Surface((bw + 8, h + 8), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 60), (4, 5, bw, h))
        surf.blit(sh, (0, 0))
        wh = wheel_img()
        for (wx, wy) in wheels:
            img = pygame.transform.rotate(wh, phase * 45 if moving else 0)
            surf.blit(img, img.get_rect(center=(wx + 4, wy + 4)))
        surf.blit(base, (4, 4))
        if blink:
            gl = pygame.Surface((10, 10), pygame.SRCALPHA)
            pygame.draw.circle(gl, (255, 190, 60, 220), (5, 5), 4)
            pygame.draw.circle(gl, (255, 240, 180, 255), (5, 5), 2)
            surf.blit(gl, (blink_pos[0], blink_pos[1]))
        return surf

    still = {}
    for moving in (False, True):
        for phase in (range(4) if moving else (0,)):
            for blink in (0, 1):
                still[(moving, phase, blink)] = compose(moving, phase, blink)
    # поворот корпуса: pygame.rotate даёт CCW; индексы направлений тоже CCW
    for d in range(8):
        rotang = d * 45
        for key, img in still.items():
            r = pygame.transform.rotate(img, rotang) if rotang else img
            frames[(d,) + key] = r
    return frames


def car_headlights(color=(90, 96, 110), kind="sedan"):
    """Парные точки фар на носу (для свечения ночью) — локальные смещения."""
    dims = {"sedan": (46, 22), "van": (48, 24), "bus": (58, 23), "truck": (56, 23)}
    w, h = dims.get(kind, (46, 22))
    return [(3, 6), (3, h - 6)]


# ------------------------------------------------------------------ деревья
def tree_canopy(size=64, seed=1):
    """Крона сверху — плотная, многослойная, с солнечной стороной ярче."""
    rnd = _rng(seed)
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    cx, cy = size // 2, size // 2
    base_r = size * 0.42
    # тень кроны (низ/право темнее)
    for _ in range(20):
        a = rnd.uniform(0, math.tau)
        r = rnd.uniform(base_r * 0.55, base_r)
        x = int(cx + math.cos(a) * r * 0.75)
        y = int(cy + math.sin(a) * r * 0.75 + 2)
        col = (rnd.randint(24, 38), rnd.randint(40, 56), rnd.randint(24, 36), 235)
        pygame.draw.circle(s, col, (x, y), rnd.randint(size // 9, size // 5))
    # основнойmass
    for _ in range(22):
        a = rnd.uniform(0, math.tau)
        r = rnd.uniform(0, base_r * 0.8)
        x = int(cx + math.cos(a) * r)
        y = int(cy + math.sin(a) * r)
        lit = 1.0 + 0.5 * (-math.cos(a) - math.sin(a)) / 2      # сев-зап светлее
        g = int(rnd.randint(52, 74) * min(1.5, lit))
        col = (int(34 * lit * 0.8), g, int(34 * lit * 0.75), 240)
        pygame.draw.circle(s, col, (x, y), rnd.randint(size // 10, size // 6))
    # блики листвы
    for _ in range(10):
        a = rnd.uniform(math.pi * 0.9, math.pi * 1.6)
        r = rnd.uniform(0, base_r * 0.7)
        x = int(cx + math.cos(a) * r)
        y = int(cy + math.sin(a) * r)
        pygame.draw.circle(s, (96, 122, 70, 200), (x, y), rnd.randint(2, 4))
    return s


def tree_trunk(size=26, seed=1):
    """Ствол с корнями и корой (рисуется ниже кроны, сортировка по Y)."""
    rnd = _rng(seed)
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    cx, cy = size // 2, size // 2 + 2
    for _ in range(5):                                            # корни
        a = rnd.uniform(0, math.tau)
        pygame.draw.line(s, (44, 34, 26), (cx, cy),
                         (int(cx + math.cos(a) * 9), int(cy + math.sin(a) * 7)), 2)
    pygame.draw.circle(s, (66, 50, 38), (cx, cy), 6)
    pygame.draw.circle(s, (40, 30, 24), (cx, cy), 6, 2)
    pygame.draw.circle(s, (84, 66, 50), (cx - 1, cy - 1), 3)      # сердцевина света
    return s


# --------------------------------------------------------- объекты улицы
def kiosk(seed=1):
    """Ларёк «Сода/печать» — цветной навес-полоска + витрина."""
    rnd = _rng(seed)
    w, h = 44, 30
    s = pygame.Surface((w + 8, h + 12), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 60), (4, 6, w, h))
    col = rnd.choice([(150, 60, 50), (70, 100, 140), (120, 110, 60)])
    pygame.draw.rect(s, col, (4, 4, w, h), border_radius=3)
    pygame.draw.rect(s, _shade(col, 0.7), (4, 4, w, h), 2, border_radius=3)
    awning = pygame.Surface((w + 10, 10), pygame.SRCALPHA)
    for i in range(0, w + 10, 8):
        c = (220, 210, 200) if (i // 8) % 2 == 0 else _shade(col, 1.2)
        pygame.draw.rect(awning, c, (i, 0, min(8, w + 10 - i), 8))
    s.blit(awning, (3, h - 2))
    pygame.draw.rect(s, (36, 42, 52), (8, 8, w - 16, 10))         # окно
    for bx in range(10, w - 10, 6):                               # товары
        pygame.draw.rect(s, rnd.choice([(200, 180, 90), (160, 90, 90), (120, 160, 120)]),
                         (bx, 10, 3, 6))
    return s


def garage(seed=1):
    """Гараж кооператива: ржавая крыша + ворота со щитами."""
    rnd = _rng(seed)
    w, h = 44, 26
    s = pygame.Surface((w + 8, h + 12), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 55), (4, 6, w, h))
    rust = (104, 78, 60)
    pygame.draw.rect(s, rust, (4, 4, w, h))
    for i in range(4, w + 4, 6):                                  # профлист
        pygame.draw.line(s, _shade(rust, 0.8), (i, 4), (i, 4 + h), 1)
    ov = noise_surface((w, h), (0, 0, 0), 40, seed)
    ov.set_alpha(60)
    s.blit(ov, (4, 4))
    gate = (58, 60, 64)
    pygame.draw.rect(s, gate, (8, h - 2, w - 16, 8))              # ворота (фасад)
    pygame.draw.line(s, _shade(gate, 0.7), (8, h + 2), (w, h + 2), 1)
    pygame.draw.rect(s, (30, 32, 36), (w - 10, 6, 5, 5))          # замок/вентканал
    return s


def bench(size=40, h=16, seed=1):
    rnd = _rng(seed)
    s = pygame.Surface((size, h + 4), pygame.SRCALPHA)
    col = (96, 74, 52)
    pygame.draw.ellipse(s, (0, 0, 0, 50), (2, 6, size - 4, h - 4))
    for i in range(2):                                            # две доски сиденья
        y = 2 + i * 5
        pygame.draw.rect(s, _shade(col, 1.0 + 0.08 * i), (1, y, size - 2, 4),
                         border_radius=2)
        pygame.draw.line(s, _shade(col, 0.7), (1, y + 4), (size - 2, y + 4), 1)
    pygame.draw.rect(s, _shade(col, 0.8), (1, h - 4, size - 2, 3))  # спинка
    for x in (4, size - 6):                                       # опоры
        pygame.draw.line(s, (40, 40, 42), (x, h - 2), (x, h + 2), 2)
    return s


def trash(size=24, seed=1):
    s = pygame.Surface((size + 4, size + 4), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 55), (2, 4, size, size))
    cx = cy = (size + 4) // 2
    pygame.draw.circle(s, (58, 66, 58), (cx, cy), size // 2 - 2)
    pygame.draw.circle(s, (40, 46, 42), (cx, cy), size // 2 - 2, 2)
    pygame.draw.circle(s, (34, 38, 34), (cx, cy), size // 2 - 5)  # горловина
    pygame.draw.arc(s, (110, 116, 110), (cx - 8, cy - 8, 16, 16), math.pi, 2 * math.pi, 2)
    return s


def lamp_post(seed=1):
    """Фонарь: столб с основанием и светящейся головой (свет — отдельно)."""
    s = pygame.Surface((26, 34), pygame.SRCALPHA)
    cx = 13
    pygame.draw.ellipse(s, (0, 0, 0, 60), (cx - 8, 22, 16, 8))    # тень основания
    pygame.draw.rect(s, (52, 54, 58), (cx - 2, 6, 4, 22))         # столб
    pygame.draw.rect(s, (70, 72, 78), (cx - 1, 6, 1, 22))         # блик
    pygame.draw.rect(s, (44, 46, 50), (cx - 5, 26, 10, 4))        # цоколь
    pygame.draw.line(s, (52, 54, 58), (cx, 8), (cx + 7, 5), 3)    # кронштейн
    pygame.draw.ellipse(s, (60, 62, 66), (cx + 3, 0, 10, 7))      # корпус лампы
    pygame.draw.ellipse(s, (240, 226, 160), (cx + 5, 2, 6, 4))    # лампа
    return s


def lamp_glow(radius=90):
    """Мягкое тёплое пятно света фонаря (ночью)."""
    s = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    for i in range(12, 0, -1):
        r = int(radius * i / 12)
        a = int(7 * (12 - i) ** 1.2)
        pygame.draw.circle(s, (255, 224, 150, a), (radius, radius), r)
    return s


def tower(size=52, seed=1):
    """Телевыжка: основание, решётчатая мачта, красное мигающее небо."""
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    cx = size // 2
    pygame.draw.ellipse(s, (0, 0, 0, 60), (cx - 16, size - 14, 32, 10))
    pygame.draw.polygon(s, (84, 86, 92), [(cx, 2), (cx + 14, size - 8), (cx - 14, size - 8)])
    pygame.draw.polygon(s, (60, 62, 68), [(cx, 2), (cx + 14, size - 8), (cx - 14, size - 8)], 2)
    for i in range(3, size - 10, 6):                              # перекладины
        k = (i - 2) / (size - 10)
        hw = int(14 * k)
        pygame.draw.line(s, (66, 68, 74), (cx - hw, i + 2), (cx + hw, i + 2), 1)
    pygame.draw.circle(s, (200, 60, 48), (cx, 5), 3)
    return s


def beacon_red(t_s):
    """Пульсация красного огня вышки (для анимации в renderer)."""
    return 0.5 + 0.5 * math.sin(t_s * 3.4)


# ------------------------------------------------------------------- персонаж
JACKET_MAIN = (62, 66, 74)


def person_frame(radius=11, jacket=JACKET_MAIN, facing=0.0, swing=0.0,
                 bob=0.0, shadow=True, skin=(198, 170, 142), hat=(40, 42, 48)):
    """Один кадр походки человека вид сверху.

    swing ∈ [-1..1] — фаза маха рук (левая/правая в противофазе),
    bob   ∈ [0..1] — вертикальный перекат корпуса (масштаб плеч).
    """
    d = radius * 2 + 8
    s = pygame.Surface((d, d), pygame.SRCALPHA)
    cx, cy = d // 2, d // 2
    if shadow:
        pygame.draw.ellipse(s, (0, 0, 0, 70), (3, 5, d - 6, d - 7))
    sy = 1.0 + 0.06 * bob                          # «присед-подъём» корпуса
    shoulder = pygame.Surface((d, d), pygame.SRCALPHA)
    wdt = int((d - 6) * (1.0 - 0.05 * abs(swing)))
    pygame.draw.ellipse(shoulder, jacket, ((d - wdt) // 2, 4, wdt, int((d - 8) * sy)))
    pygame.draw.ellipse(shoulder, _shade(jacket, 0.72),
                        ((d - wdt) // 2, 4, wdt, int((d - 8) * sy)), 1)
    pygame.draw.ellipse(shoulder, _shade(jacket, 1.18),
                        ((d - wdt) // 2 + 2, 6, wdt - 8, 4))   # плечевой блик
    rot = pygame.transform.rotate(shoulder, math.degrees(facing) + 90)
    s.blit(rot, rot.get_rect(center=(cx, cy)))
    # руки: вдоль тела, качаются вдоль направления движения
    perp = facing + math.pi / 2
    for side, ph in ((-1, swing), (1, -swing)):
        hx = cx + math.cos(perp) * (radius - 1) * side \
            + math.cos(facing) * ph * 5
        hy = cy + math.sin(perp) * (radius - 1) * side \
            + math.sin(facing) * ph * 5
        pygame.draw.circle(s, _shade(jacket, 0.88), (int(hx), int(hy)), radius // 2)
        pygame.draw.circle(s, (46, 40, 36), (int(hx), int(hy)), radius // 2 - 2)  # варежка
    # голова чуть впереди корпуса
    hx = cx + math.cos(facing) * 2.5
    hy = cy + math.sin(facing) * 2.5
    pygame.draw.circle(s, skin, (int(hx), int(hy)), radius // 2 + 1)
    pygame.draw.circle(s, hat, (int(hx), int(hy)), radius // 2)
    pygame.draw.circle(s, _shade(hat, 0.7), (int(hx), int(hy)), radius // 2, 1)
    pygame.draw.line(s, _shade(hat, 1.3), (int(hx - 3), int(hy - 3)),
                     (int(hx + 2), int(hy - 4)), 1)
    return s


def make_person_walkset(jacket=JACKET_MAIN, radius=11, hat=(44, 46, 52),
                        skin=(200, 170, 142), steps=6):
    """Походочный набор: 8 направлений × `steps` кадров цикла шага.

    Ключ: (dir_index 0..7, frame 0..steps-1). Кадр 0 = стоит.
    """
    frames = {}
    for i in range(8):
        ang = i * math.tau / 8
        frames[(i, 0)] = person_frame(radius, jacket, facing=ang, swing=0.0, bob=0.0,
                                      hat=hat, skin=skin)
        for fr in range(1, steps):
            ph = fr / steps * math.tau
            frames[(i, fr)] = person_frame(radius, jacket, facing=ang,
                                           swing=math.sin(ph),
                                           bob=abs(math.sin(ph)),
                                           hat=hat, skin=skin)
    return frames


# совместимость со старым кодом
def person(radius=11, jacket=(62, 66, 74), skin=(196, 168, 140),
           hat=(40, 42, 48), facing=0.0, shadow=True):
    return person_frame(radius, jacket, facing=facing, shadow=shadow,
                        skin=skin, hat=hat)


def make_player_frames(jacket=(62, 66, 74)):
    """Старый API -> новый набор ходьбы (8 направлений × 6 кадров)."""
    return make_person_walkset(jacket=jacket)


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
