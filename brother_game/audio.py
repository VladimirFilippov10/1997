# -*- coding: utf-8 -*-
"""Синтез звуков (шаги, ветер, машины) — без внешних аудиофайлов.

pygame mixer недоступен (CI/Headless, нет драйвера звука) — модуль
молча деградирует в заглушку, игра продолжает работать.
"""
import math
import random

import numpy as np

try:
    from pygame import mixer
except Exception:  # pragma: no cover
    mixer = None

_RATE = 22050
_BUFSIZE = 1024


def _channels():
    """Сколько каналов у микшера после init (иногда SDL форсирует стерео)."""
    try:
        return max(1, mixer.get_init()[2])
    except Exception:
        return 1


def _to_sound(samples, gain=1.0):
    """float32 [-1..1] -> pygame Sound (int16), совместимо mono/stereo."""
    arr = np.clip(samples * gain, -1.0, 1.0)
    pcm = (arr * 32767).astype(np.int16)
    if _channels() >= 2:
        pcm = np.column_stack([pcm, pcm])   # (n, 2) для стерео-микшера
    return mixer.Sound(array=pcm)


class AudioEngine:
    def __init__(self):
        self.ok = False
        self.channels = {}
        if mixer is None:
            return
        try:
            mixer.pre_init(_RATE, -16, 1, _BUFSIZE)
            mixer.init()
            self.ok = True
        except Exception:
            try:  # некоторые сборки SDL требуют стерео — пробуем снова
                mixer.pre_init(_RATE, -16, 2, _BUFSIZE)
                mixer.init()
                self.ok = True
            except Exception:
                self.ok = False

    # ---------------------------------------------------------- генераторы
    def make_step(self, surface="asphalt", seed=1):
        """Короткий «шорох» шага: шумовой всплеск + низкочастотный удар."""
        if not self.ok:
            return None
        rnd = random.Random(seed)
        dur = 0.075
        n = int(_RATE * dur)
        t = np.arange(n) / _RATE
        env = np.exp(-t * 34.0)
        noise = np.random.RandomState(rnd.randrange(1 << 30)).randn(n)
        # простой однополюсный фильтр (разные поверхности = разная яркость)
        cutoff = {"asphalt": 0.45, "concrete": 0.6, "grass": 0.22,
                  "brick": 0.55, "wood": 0.35}.get(surface, 0.45)
        y = np.zeros(n)
        prev = 0.0
        for i in range(n):
            prev = prev + cutoff * (noise[i] - prev)
            y[i] = prev
        thump = np.sin(2 * math.pi * rnd.uniform(70, 95) * t) * np.exp(-t * 55)
        sig = 0.7 * y / (np.max(np.abs(y)) + 1e-6) + 0.55 * thump
        return _to_sound(sig, gain=0.5)

    def make_ambience(self, seconds=4.0, kind="wind"):
        """Зацикленный фон: зимний питерский ветер / гул проспекта."""
        if not self.ok:
            return None
        n = int(_RATE * seconds)
        white = np.random.RandomState(7).randn(n)
        b = np.zeros(n)
        a = np.zeros(n)
        alpha = 0.02 if kind == "wind" else 0.008
        prev = 0.0
        for i in range(n):
            prev += alpha * (white[i] - prev)
            b[i] = prev
        prev = 0.0
        for i in range(n):
            prev += 0.002 * (b[i] - prev)
            a[i] = prev
        sig = a / (np.max(np.abs(a)) + 1e-6)
        # лёгкая модуляция, чтобы «дышало»
        mod = 0.6 + 0.4 * np.sin(2 * math.pi * np.arange(n) / _RATE * 0.25)
        sig *= mod
        # кроссфейд концов для бесшовной петли
        fade = int(_RATE * 0.25)
        sig[:fade] = sig[:fade] * np.linspace(0, 1, fade) + \
            sig[-fade:] * np.linspace(1, 0, fade)
        sig = np.concatenate([sig[:-fade], sig[:fade]])
        return _to_sound(sig, gain=0.35)

    def make_engine(self, seconds=2.0):
        """Низкочастотный гул трамвая/машины для дальней улицы."""
        if not self.ok:
            return None
        n = int(_RATE * seconds)
        t = np.arange(n) / _RATE
        sig = np.sin(2 * math.pi * 55 * t) * 0.5 + np.sin(2 * math.pi * 82 * t) * 0.3
        sig += np.random.RandomState(3).randn(n) * 0.08
        sig /= np.max(np.abs(sig)) + 1e-6
        return _to_sound(sig, gain=0.25)

    def make_click(self, freq=880, dur=0.05):
        if not self.ok:
            return None
        n = int(_RATE * dur)
        t = np.arange(n) / _RATE
        env = np.exp(-t * 60)
        sig = np.sin(2 * math.pi * freq * t) * env
        return _to_sound(sig, gain=0.3)

    # ------------------------------------------------- новые звуки города
    def _lowpass(self, x, alpha):
        y = np.empty_like(x)
        prev = 0.0
        for i in range(len(x)):
            prev += alpha * (x[i] - prev)
            y[i] = prev
        return y

    def make_rain(self, seconds=6.0):
        """Бесшовный шум дождя: розовый шум + капельки сверху."""
        if not self.ok:
            return None
        n = int(_RATE * seconds)
        rs = np.random.RandomState(21)
        white = rs.randn(n)
        body = self._lowpass(white, 0.12)
        body /= np.max(np.abs(body)) + 1e-9
        sig = 0.75 * body
        # отдельные капли — короткие ВЧ-всплески
        for _ in range(int(seconds * 26)):
            i = rs.randint(0, n - 400)
            f = rs.uniform(1200, 4200)
            tt = np.arange(300) / _RATE
            tick = np.sin(2 * math.pi * f * tt) * np.exp(-tt * 90)
            sig[i:i + 300] += 0.05 * tick
        fade = int(_RATE * 0.3)
        a = sig[:fade].copy()
        b = sig[-fade:].copy()
        sig[:fade] = a * np.linspace(0, 1, fade) + b * np.linspace(1, 0, fade)
        sig[-fade:] = sig[:fade]
        sig = sig[:-fade]
        pk = np.max(np.abs(sig)) or 1.0
        return _to_sound(sig / pk, gain=0.5)

    def make_thunder(self, seconds=3.2):
        """Гром: низкий гул с медленным «раскатом» и треском в начале."""
        if not self.ok:
            return None
        n = int(_RATE * seconds)
        t = np.arange(n) / _RATE
        rs = np.random.RandomState(88)
        rumble = self._lowpass(rs.randn(n), 0.015)
        rumble /= np.max(np.abs(rumble)) + 1e-9
        shape = (np.minimum(t / 0.08, 1.0) * np.exp(-t * 0.9)
                 + 0.5 * np.maximum(0.0, np.sin(t * 6.3 - 1.0)) * np.exp(-t * 1.4))
        crack = self._lowpass(rs.randn(n), 0.5)[: int(0.25 * _RATE)]
        sig = rumble * shape * 0.9
        sig[: len(crack)] += crack * 0.5 * np.exp(-t[:len(crack)] * 18)
        pk = np.max(np.abs(sig)) or 1.0
        return _to_sound(sig / pk, gain=0.85)

    def make_horn(self):
        """Сигнал машины на улице: две «клаксон»-ноты."""
        if not self.ok:
            return None
        dur = 0.7
        n = int(_RATE * dur)
        t = np.arange(n) / _RATE
        f1, f2 = 392.0, 494.0
        seg = int(n * 0.45)
        sig = np.zeros(n)
        for i, (a, b, ln) in enumerate(((0, seg, 1.0), (seg, n, 0.8))):
            tt = t[a:b] - t[a]
            fr = f1 if i == 0 else f2
            tone = np.sin(2 * math.pi * fr * tt) + 0.4 * np.sin(2 * math.pi * fr * 2 * tt) \
                   + 0.2 * np.sin(2 * math.pi * fr * 3 * tt)
            env = np.minimum(tt / 0.02, 1.0) * np.exp(-tt * 2.2)
            sig[a:b] = tone * env
        pk = np.max(np.abs(sig)) or 1.0
        return _to_sound(sig / pk, gain=0.3)

    def make_splash(self):
        """Брызги из-под ноги по луже."""
        if not self.ok:
            return None
        n = int(_RATE * 0.18)
        t = np.arange(n) / _RATE
        rs = np.random.RandomState(5)
        noise = rs.randn(n)
        y = self._lowpass(noise, 0.35)
        y /= np.max(np.abs(y)) + 1e-9
        sig = y * np.exp(-t * 22)
        return _to_sound(sig, gain=0.35)

    def make_breath(self):
        """Пар-дыхание: дуновение шума с нарастанием и спадом."""
        if not self.ok:
            return None
        n = int(_RATE * 0.8)
        t = np.arange(n) / _RATE
        rs = np.random.RandomState(9)
        noise = self._lowpass(rs.randn(n), 0.08)
        noise /= np.max(np.abs(noise)) + 1e-9
        env = np.sin(np.pi * t / (n / _RATE)) ** 2
        sig = noise * env
        return _to_sound(sig, gain=0.16)

    def make_pickup(self):
        if not self.ok:
            return None
        n = int(_RATE * 0.16)
        t = np.arange(n) / _RATE
        f = 660 + 0 * t
        chirp = np.sin(2 * math.pi * (f + t * 900) * t)
        sig = chirp * np.exp(-t * 22)
        return _to_sound(sig, gain=0.25)

    # ------------------------------------------------------------ воспроизведение
    def play(self, sound, channel=None, loops=0, volume=1.0):
        if not self.ok or sound is None:
            return
        try:
            if channel is None:
                ch = sound.play(loops=loops)
            else:
                ch = channel
                ch.play(sound, loops=loops)
            if ch is not None:
                ch.set_volume(volume)
        except Exception:
            pass

    def reserve(self, name, count):
        if not self.ok:
            return
        try:
            mixer.set_num_channels(max(count, 16))
        except Exception:
            pass
        self.channels[name] = None

    def free(self):
        if self.ok:
            try:
                mixer.quit()
            except Exception:
                pass


class NullAudio(AudioEngine):
    """Заглушка для headless-режима."""

    def __init__(self):
        self.ok = False
        self.channels = {}

    def make_step(self, *a, **k):
        return None

    def make_ambience(self, *a, **k):
        return None

    def make_engine(self, *a, **k):
        return None

    def make_click(self, *a, **k):
        return None

    def make_rain(self, *a, **k):
        return None

    def make_thunder(self, *a, **k):
        return None

    def make_horn(self, *a, **k):
        return None

    def make_splash(self, *a, **k):
        return None

    def make_breath(self, *a, **k):
        return None

    def make_pickup(self, *a, **k):
        return None


def build_audio():
    """Возвращает (движок, словарь всех синтезированных звуков)."""
    eng = AudioEngine()
    sounds = {surf: [] for surf in ("asphalt", "concrete", "grass", "brick", "wood")}
    if eng.ok:
        for surf in sounds:
            for v in range(4):
                s = eng.make_step(surf, seed=v * 13 + 1)
                if s is not None:
                    sounds[surf].append(s)
        sounds["wind"] = eng.make_ambience(kind="wind")
        sounds["city"] = eng.make_ambience(kind="city", seconds=5.0)
        sounds["click"] = eng.make_click(freq=720)
        sounds["rain"] = eng.make_rain()
        sounds["thunder"] = eng.make_thunder()
        sounds["horn"] = eng.make_horn()
        sounds["splash"] = eng.make_splash()
        sounds["breath"] = eng.make_breath()
        sounds["pickup"] = eng.make_pickup()
    else:
        eng = NullAudio()
        for k in ("wind", "city", "click", "rain", "thunder", "horn",
                  "splash", "breath", "pickup"):
            sounds[k] = None
    return eng, sounds
