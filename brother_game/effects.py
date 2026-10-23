# -*- coding: utf-8 -*-
"""Погода и визуальные эффекты (вид сверху).

Всё рисуется поверх мира на отдельном оверлей-серфее:
  * дождь — три слоя капель с разной скоростью (параллакс) + «косой» штрих;
  * лужи под дождём покрываются расходящимися кругами (рябь);
  * молния — вспышка всего экрана + раскаты грома (callback в звук);
  * туманное дыхание и пар из теплотрассы — мягкие дрейфующие облака;
  * частицы: брызги из-под ног, искры, листья на ветру;
  * потёки по стёклам (статичная карта) — лёгкий «питерский» штрих;
  * снег как alternate-режим погоды.

Эффекты дёшевы: N капель фиксировано, рябь ограничена сверху,
вспышки — один.fillRect.
"""
import math
import random

import pygame

from config import TILE, WINDOW_H, WINDOW_W


class Rain:
    """Дождь: слои капель + рябь в лужах + редкие молнии."""

    def __init__(self, intensity=0.75, storm=True):
        self.intensity = intensity          # 0..1
        self.storm = storm                  # с грозами?
        self.drops = []
        self.ripples = []
        self._ripple_pool = []              # переиспользуем объекты
        self.t = 0.0
        self.flash = 0.0                    # яркость вспышки 0..1
        self.next_bolt = random.uniform(9.0, 16.0)
        self.thunder_cb = None              # callback(level) -> играть гром
        self.wind = random.uniform(-42, -22)
        self._sprites = self._make_sprites()

    @staticmethod
    def _make_sprites():
        """3 варианта капли — тонкий косой штрих с альфой."""
        out = []
        for ln, alpha in ((7, 90), (10, 120), (13, 150)):
            s = pygame.Surface((ln + 4, ln + 4), pygame.SRCALPHA)
            pygame.draw.line(s, (178, 196, 220, alpha),
                             (2, 2), (2 + ln * 0.45, 2 + ln), 1)
            out.append(s)
        return out

    def set_intensity(self, v):
        self.intensity = max(0.0, min(1.0, v))

    def update(self, dt, puddles):
        self.t += dt
        n_target = int(90 + 380 * self.intensity)
        # ветер слегка «гуляет»
        wv = self.wind + math.sin(self.t * 0.23) * 12
        # ---- капли
        while len(self.drops) < n_target:
            layer = random.choice((0, 1, 2))
            self.drops.append([random.uniform(0, WINDOW_W),
                               random.uniform(-WINDOW_H, WINDOW_H), layer])
        if len(self.drops) > n_target:
            del self.drops[n_target:]
        for dr in self.drops:
            speed = (340, 520, 760)[dr[2]] * (0.75 + 0.5 * self.intensity)
            dr[1] += speed * dt
            dr[0] += wv * dt * (0.5 + dr[2] * 0.35)
            if dr[1] > WINDOW_H + 20 or not (-40 < dr[0] < WINDOW_W + 40):
                dr[0] = random.uniform(-20, WINDOW_W + 20)
                dr[1] = random.uniform(-80, -10)
        # ---- рябь в лужах (world coords)
        if puddles and self.intensity > 0.08:
            rate = 3 + int(26 * self.intensity)
            for _ in range(rate):
                if random.random() < 0.6 and len(self.ripples) < 90:
                    px, py = random.choice(puddles)
                    r = self._ripple_pool.pop() if self._ripple_pool else \
                        [0.0, 0.0, 0.0, 0.0]
                    r[0], r[1] = px + random.uniform(-22, 22), py + random.uniform(-12, 12)
                    r[2] = 0.0                      # возраст
                    r[3] = random.uniform(0.7, 1.2)  # длительность
                    self.ripples.append(r)
        for r in list(self.ripples):
            r[2] += dt
            if r[2] >= r[3]:
                self.ripples.remove(r)
                if len(self._ripple_pool) < 120:
                    self._ripple_pool.append(r)
        # ---- молнии
        if self.storm and self.intensity > 0.5:
            self.next_bolt -= dt
            if self.next_bolt <= 0:
                self.flash = 0.85
                self.next_bolt = random.uniform(7.0, 17.0)
                delay = random.uniform(0.4, 1.6)
                pygame.time.set_timer(pygame.USEREVENT + 1,
                                      int(delay * 1000), repeat=False)
        if self.flash > 0:
            self.flash = max(0.0, self.flash - dt * 2.2)

    def draw(self, screen, camx, camy):
        # рябь — в мировых координатах
        for r in self.ripples:
            sx, sy = r[0] - camx, r[1] - camy
            if not (-30 < sx < WINDOW_W + 30 and -30 < sy < WINDOW_H + 30):
                continue
            k = r[2] / r[3]
            rad = 2 + k * 11
            a = int(150 * (1 - k))
            pygame.draw.circle(screen, (150, 175, 205, a), (int(sx), int(sy)),
                               int(rad), 1)
        # капли — в экранных
        for x, y, layer in self.drops:
            screen.blit(self._sprites[layer], (int(x), int(y)))
        # вспышка
        if self.flash > 0:
            ov = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
            ov.fill((210, 220, 240, int(120 * self.flash)))
            screen.blit(ov, (0, 0))


class Steam:
    """Пар/дыхание: мягкие облака, поднимающиеся вверх и живущие ~2 сек."""

    def __init__(self, sprite):
        self.sprite = sprite
        self.parts = []     # [x, y, age, life, scale, drift]

    def emit(self, x, y, n=1, rise=-16.0):
        for _ in range(n):
            if len(self.parts) > 260:
                self.parts.pop(0)
            self.parts.append([x + random.uniform(-6, 6),
                               y + random.uniform(-4, 4),
                               0.0, random.uniform(1.4, 2.6),
                               random.uniform(0.5, 1.3),
                               random.uniform(-7, 7)])

    def update(self, dt):
        for p in list(self.parts):
            p[2] += dt
            p[1] -= 16.0 * dt          # подъём (экран/мир — одинаково по Y)
            p[0] += p[5] * dt
            p[4] += dt * 0.35          # растёт
            if p[2] >= p[3]:
                self.parts.remove(p)

    def draw(self, screen, camx, camy):
        s = self.sprite
        for x, y, age, life, scale, _ in self.parts:
            k = age / life
            a = 1.0 - k
            sz = max(4, int(s.get_width() * scale))
            img = pygame.transform.smoothscale(s, (sz, sz)) if abs(sz - s.get_width()) > 3 else s
            tmp = img.copy()
            tmp.set_alpha(int(120 * a * a))
            screen.blit(tmp, (int(x - camx - sz / 2), int(y - camy - sz / 2)))


class Particles:
    """Мелкие частицы: брызги от шагов, искры, опавшие листья на ветру."""

    def __init__(self):
        self.parts = []         # dict(x,y,vx,vy,age,life,col,size,grav,fade)
        self.leaves = []        # бесконечные «ветровые» листья

    def splash(self, x, y, n=6, col=(150, 175, 200)):
        for _ in range(n):
            a = random.uniform(-math.pi, 0)       # вверх-в стороны
            sp = random.uniform(30, 95)
            self.parts.append(dict(x=x, y=y, vx=math.cos(a) * sp,
                                   vy=math.sin(a) * sp * 0.55,
                                   age=0.0, life=random.uniform(0.25, 0.5),
                                   col=col, size=random.uniform(1.5, 3.0),
                                   grav=220.0))

    def sparks(self, x, y, n=8):
        for _ in range(n):
            a = random.uniform(0, math.tau)
            sp = random.uniform(60, 190)
            self.parts.append(dict(x=x, y=y, vx=math.cos(a) * sp,
                                   vy=math.sin(a) * sp,
                                   age=0.0, life=random.uniform(0.2, 0.6),
                                   col=(255, random.randint(170, 220), 90),
                                   size=random.uniform(1.2, 2.4), grav=60.0))

    def leaf(self, x, y):
        if len(self.leaves) < 26:
            self.leaves.append(dict(x=x, y=y, t=random.uniform(0, 9),
                                    ph=random.uniform(0, 6.28),
                                    col=random.choice([(122, 92, 52), (140, 104, 60),
                                                      (96, 78, 48)]),
                                    spin=random.uniform(-3, 3)))

    def update(self, dt, wind=(-30.0, 6.0)):
        for p in list(self.parts):
            p["age"] += dt
            if p["age"] >= p["life"]:
                self.parts.remove(p)
                continue
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            p["vy"] += p["grav"] * dt
        for lf in self.leaves:
            lf["t"] += dt
            lf["x"] += wind[0] * dt + math.sin(lf["t"] * 2 + lf["ph"]) * 14 * dt
            lf["y"] += wind[1] * dt + math.cos(lf["t"] * 1.6 + lf["ph"]) * 10 * dt

    def cull(self, view_rect):
        pad = 200
        r = view_rect.inflate(pad * 2, pad * 2)
        self.parts = [p for p in self.parts if r.collidepoint(p["x"], p["y"])]
        self.leaves = [l for l in self.leaves if r.collidepoint(l["x"], l["y"])]

    def draw(self, screen, camx, camy):
        for p in self.parts:
            k = 1.0 - p["age"] / p["life"]
            sx, sy = int(p["x"] - camx), int(p["y"] - camy)
            if not (-8 < sx < WINDOW_W + 8 and -8 < sy < WINDOW_H + 8):
                continue
            surf = pygame.Surface((6, 6), pygame.SRCALPHA)
            pygame.draw.circle(surf, (*p["col"], int(230 * k)), (3, 3),
                               max(1, int(p["size"] * k + 0.5)))
            screen.blit(surf, (sx - 3, sy - 3))
        for lf in self.leaves:
            sx, sy = int(lf["x"] - camx), int(lf["y"] - camy)
            if not (-16 < sx < WINDOW_W + 16 and -16 < sy < WINDOW_H + 16):
                continue
            img = pygame.Surface((9, 5), pygame.SRCALPHA)
            pygame.draw.ellipse(img, (*lf["col"], 220), (0, 0, 9, 5))
            img = pygame.transform.rotate(img, lf["t"] * lf["spin"] * 57)
            screen.blit(img, img.get_rect(center=(sx, sy)))


def make_steam_sprite(size=64):
    """Мягкое пятно пара — гауссов блин с неровным краем."""
    rnd = random.Random(4)
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    cx = cy = size // 2
    for i in range(9):
        r = size // 2 - i * (size // 20)
        a = 16 + i * 5
        off = (rnd.randint(-4, 4), rnd.randint(-4, 4))
        pygame.draw.circle(s, (215, 222, 230, a), (cx + off[0], cy + off[1]), max(2, r))
    return s


def streaks_surface(seed=3):
    """Статичная карта потёков по «стеклу камеры» — питерский дождь."""
    rnd = random.Random(seed)
    s = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
    for _ in range(26):
        x = rnd.randrange(WINDOW_W)
        y = rnd.randrange(WINDOW_H - 160)
        ln = rnd.randint(40, 150)
        pts = [(x, y)]
        for _ in range(6):
            y += ln // 6
            x += rnd.randint(-3, 3)
            pts.append((x, y))
        pygame.draw.lines(s, (190, 205, 225, 26), False, pts, 2)
        pygame.draw.circle(s, (210, 225, 245, 40), pts[-1], 2)
    return s


class WeatherSystem:
    """Дирижёр погоды: дождь + пар + частицы + потёки + ветер листьев."""

    def __init__(self, district=None):
        self.rain = Rain(intensity=0.7, storm=True)
        self.steam = Steam(make_steam_sprite(64))
        self.particles = Particles()
        self.streaks = streaks_surface()
        self.puddles = []           # world-координаты луж (заполняет renderer)
        self.enabled = True
        self.gust_t = 0.0

    def bind_district_visuals(self, puddle_points):
        self.puddles = puddle_points

    def update(self, dt, time_s):
        if not self.enabled:
            return
        self.rain.update(dt, self.puddles)
        self.steam.update(dt)
        self.particles.update(dt)
        # периодически срываем листья с деревьев
        self.gust_t -= dt
        if self.gust_t <= 0:
            self.gust_t = random.uniform(0.4, 1.4)
            if self.puddles:      # рядом с лужами есть деревья — просто у экрана
                pass

    def spawn_leaf_near(self, x, y):
        self.particles.leaf(x + random.uniform(-120, 120),
                            y + random.uniform(-120, 60))

    def step_splash(self, x, y, surface, running):
        """Вызывается игроком на каждом шаге."""
        if surface == "water" :
            return
        wet = self.rain.intensity > 0.15
        if wet or surface in ("grass",):
            n = 4 + (3 if running else 0)
            self.particles.splash(x, y + 8, n=n)
        if wet and random.random() < 0.5:
            self.steam.emit(x, y + 6, n=1)

    def draw_overlay(self, screen, camx, camy):
        if not self.enabled:
            return
        self.steam.draw(screen, camx, camy)
        self.particles.draw(screen, camx, camy)
        self.rain.draw(screen, camx, camy)
        # потёки — только когда идёт дождь, полупрозрачно
        if self.rain.intensity > 0.05:
            st = self.streaks
            st.set_alpha(int(90 * min(1.0, self.rain.intensity + 0.25)))
            # медленный дрейф вниз
            off = int(self.rain.t * 26) % 60
            screen.blit(st, (0, -off))
            screen.blit(st, (0, WINDOW_H - off))
