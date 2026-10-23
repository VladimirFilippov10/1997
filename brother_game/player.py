# -*- coding: utf-8 -*-
"""Игрок (Данила Багров) и NPC-прохожие: физика ходьбы, шаги, анимация."""
import math
import random

from config import (MAX_HEALTH, PLAYER_RADIUS, RUN_SPEED, STEP_LENGTH, TILE,
                    WALK_SPEED)

# Проходимые предметы: не добавляем их в blocked — подбор работает по E рядом.
NON_BLOCKING_PROPS = set()


class Player:
    def __init__(self, x, y, district):
        self.x, self.y = float(x), float(y)
        self.vx = self.vy = 0.0
        self.facing = -math.pi / 2          # смотрит «на север»
        self.district = district
        self.radius = PLAYER_RADIUS
        self.health = MAX_HEALTH
        # параметры походки
        self._stride = 0.0                  # накопленная дистанция шага
        self.step_phase = 0                 # 0/1 — качание корпуса
        self.steps = 0
        self.moving = False
        self.running = False
        self.speed_now = 0.0
        self.surface = "asphalt"
        self.bob_t = 0.0

    # ------------------------------------------------------------ движение
    def update(self, dx, dy, run, dt, on_step=None):
        """dx,dy — единичный вектор намерения (WASD). Возвращает True если шагнул."""
        target = 0.0
        if dx or dy:
            mag = math.hypot(dx, dy)
            dx, dy = dx / mag, dy / mag
            target = RUN_SPEED if run else WALK_SPEED
            # плавный разворот в сторону движения
            want = math.atan2(dy, dx)
            diff = (want - self.facing + math.pi) % math.tau - math.pi
            self.facing += max(-0.35, min(0.35, diff))

        # сглаживание скорости (ускорение/торможение)
        k = 1.0 - math.exp(-dt * 14.0)
        self.vx += (dx * target - self.vx) * k
        self.vy += (dy * target - self.vy) * k
        if abs(self.vx) < 1 and abs(self.vy) < 1 and not (dx or dy):
            self.vx = self.vy = 0.0

        moved = math.hypot(self.vx, self.vy) * dt
        stepped = False
        if moved > 0.0001:
            # коллизии по осям отдельно (скользим вдоль стен)
            nx = self.x + self.vx * dt
            if not self.district.circle_blocked(nx, self.y, self.radius):
                self.x = nx
            else:
                self.vx *= 0.2
            ny = self.y + self.vy * dt
            if not self.district.circle_blocked(self.x, ny, self.radius):
                self.y = ny
            else:
                self.vy *= 0.2
            # счётчик шагов: звук/анимация привязаны к дистанции, а не ко времени
            self._stride += moved
            stride_len = STEP_LENGTH * (0.78 if run else 1.0)
            while self._stride >= stride_len:
                self._stride -= stride_len
                self.steps += 1
                self.step_phase ^= 1
                stepped = True
                if on_step:
                    self.surface = self.district.surface_sound(self.x, self.y)
                    on_step(self.surface, run)
        self.moving = moved > 6.0 * dt
        self.running = run and self.moving
        self.speed_now = math.hypot(self.vx, self.vy)
        if self.moving:
            self.bob_t += dt * (9.5 if run else 6.0)
        return stepped

    def sprite(self, time_s):
        idx = int((self.facing + math.tau / 16) % math.tau / (math.tau / 8))
        bob = int(abs(math.sin(self.bob_t)) > 0.5) if self.moving else 0
        from textures import make_player_frames
        frames = _get_frames()
        return frames[(idx, bob)]

    @property
    def tile(self):
        return int(self.x // TILE), int(self.y // TILE)


_FRAMES = None


def _get_frames():
    global _FRAMES
    if _FRAMES is None:
        from textures import make_player_frames
        _FRAMES = make_player_frames(jacket=(62, 66, 74))
    return _FRAMES


class WalkerNPC:
    """Прохожий туда-сюда по тротуару."""

    def __init__(self, spec):
        self.x, self.y = spec["x"], spec["y"]
        self.a = spec["a"]
        self.b = spec["b"]
        self.speed = spec["speed"]
        self.dir = spec["dir"]
        self.jacket = spec["jacket"]
        self.r = spec["r"]
        self.facing = 0.0
        self.phase = spec.get("phase", 0.0)

    def update(self, dt):
        ax, ay = self.a
        bx, by = self.b
        # простая линейная интерполяция между точками
        p = self.phase
        self.x = ax + (bx - ax) * p
        self.y = ay + (by - ay) * p
        length = math.hypot(bx - ax, by - ay) or 1
        self.phase += self.dir * (self.speed * dt) / length
        if self.phase >= 1:
            self.phase = 1
            self.dir = -1
        elif self.phase <= 0:
            self.phase = 0
            self.dir = 1
        self.facing = math.atan2((by - ay) * self.dir, (bx - ax) * self.dir)


def find_walkable(district, x, y, r=14, max_try=60, rnd=None):
    """Ближайшая проходимая точка рядом с (x, y)."""
    import math as _m
    rnd = rnd or random.Random(3)
    district.circle_blocked(x, y, r)
    if not district.circle_blocked(x, y, r):
        return x, y
    for i in range(max_try):
        a = i * _m.tau / max_try
        for rad in (TILE, TILE * 2, TILE * 3, TILE * 5):
            nx = x + _m.cos(a) * rad
            ny = y + _m.sin(a) * rad
            if not district.circle_blocked(nx, ny, r):
                return nx, ny
    return x, y
