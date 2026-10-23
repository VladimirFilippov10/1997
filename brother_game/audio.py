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


def build_audio():
    eng = AudioEngine()
    if eng.ok:
        steps = {}
        for surf in ("asphalt", "concrete", "grass", "brick", "wood"):
            variants = []
            for v in range(4):
                s = eng.make_step(surf, seed=v * 13 + 1)
                if s is not None:
                    variants.append(s)
            steps[surf] = variants
        wind = eng.make_ambience(kind="wind")
        city = eng.make_ambience(kind="city", seconds=5.0)
        click = eng.make_click(freq=720)
        return eng, steps, wind, city, click
    # заглушки
    eng = NullAudio()
    return eng, {k: [None] for k in ("asphalt", "concrete", "grass", "brick", "wood")}, None, None, None
