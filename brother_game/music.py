# -*- coding: utf-8 -*-
"""Процедурная музыка по мотивам саундтрека «Брата» (без внешних файлов).

Настраиваемый секвенсор поверх mixer.Sound:
  * «балалаечный» перебор — коротко затухающая щипковая нота
    (несколько гармоник + атакующий щелчок);
  * контрабас — синус с огибающей;
  * минорный хроматический ход a-g#-g-f#-f — тот самый мотив;
  * тихая «тарелочка» — белый шум с ВЧ-фильтром.

Треки собираются заранее в один стерео-буфер (numpy), поэтому во время
игры CPU не нагружается: играет одна петля на отдельном канале.

Режимы: main (улицы), calm (дворы/сквер), tense (проблемы).
Переключение — кроссфейд двух каналов.
"""
import math

import numpy as np

try:
    from pygame import mixer
except Exception:  # pragma: no cover
    mixer = None

RATE = 44100
BPM = 96.0
BEAT = 60.0 / BPM                 # длительность четверти

A2, C3, E3, G3 = 110.0, 130.81, 164.81, 196.0
CHROM = [440.0, 415.30, 392.0, 369.99, 349.23]   # a g# g f# f


def _env_exp(t, tau):
    return np.exp(-t / tau)


def pluck(freq, dur=0.55, bright=1.0):
    """Щипковая струна: гармоники + шумовая атака."""
    n = int(RATE * dur)
    t = np.arange(n) / RATE
    sig = np.zeros(n)
    for h, amp in ((1, 1.0), (2, 0.5), (3, 0.27), (4, 0.14), (5, 0.07)):
        if h * freq > RATE / 2 - 100:
            break
        sig += amp * np.sin(2 * np.pi * freq * h * t) * _env_exp(t, 0.10 / (h ** 0.4 * bright))
    attack_n = int(RATE * 0.006)
    if attack_n > 0:
        sig[:attack_n] += np.random.randn(attack_n) * 0.35 * np.linspace(1, 0, attack_n)
    env = _env_exp(t, dur * 0.32)
    sig *= env
    pk = np.max(np.abs(sig)) or 1.0
    return sig / pk


def bass_note(freq, dur=0.5):
    n = int(RATE * dur)
    t = np.arange(n) / RATE
    vib = 1.0 + 0.004 * np.sin(2 * np.pi * 5.2 * t)
    sig = (np.sin(2 * np.pi * freq * t * vib) * 0.85
           + np.sin(2 * np.pi * freq * 2 * t) * 0.22)
    env = np.minimum(t / 0.02, 1.0) * _env_exp(t, dur * 0.55)
    sig *= env
    pk = np.max(np.abs(sig)) or 1.0
    return sig / pk


def hat(dur=0.09):
    n = int(RATE * dur)
    noise = np.random.randn(n)
    y = np.zeros(n)
    prev = 0.0
    for i in range(n):                      # однополюсный ВЧ = diff(шум)
        cur = prev + 0.85 * (noise[i] - prev)
        y[i] = noise[i] - cur
        prev = cur
    y *= _env_exp(np.arange(n) / RATE, dur * 0.4)
    pk = np.max(np.abs(y)) or 1.0
    return y / pk


def _add(buf, start, sig, gain):
    i0 = int(start * RATE)
    if i0 < 0 or i0 >= len(buf):
        return
    sl = slice(i0, min(len(buf), i0 + len(sig)))
    buf[sl] += sig[: sl.stop - sl.start] * gain


def build_track(kind="main", bars=8):
    """Собирает один луп (float-буфер) выбранного настроения."""
    beat_per_bar = 4
    total = bars * beat_per_bar * BEAT
    buf = np.zeros(int(RATE * total) + RATE)   # хвост для реверба-хвоста

    # прогрессия Am — F — G — Am ... с хроматическим спуском
    roots = [A2 / 2, A2 / 2, (349.23 / 2), (392.0 / 2)]
    chorddn = {0: [A2, C3, E3], 1: [A2, C3, E3], 2: [349.23, 440.0, 523.25],
               3: [392.0, 493.88, 587.33]}

    for b in range(bars):
        bar_t = b * beat_per_bar * BEAT
        root = roots[b % 4]
        ch = chorddn[b % 4]
        # --- бас: долгие ноты
        _add(buf, bar_t, bass_note(root, BEAT * 1.9), 0.5)
        _add(buf, bar_t + BEAT * 2, bass_note(root * (1.5 if b % 4 != 3 else 1.0),
                                              BEAT * 1.6), 0.42)
        # --- перебор восьмыми (Arpeggio «низ-верх-низ»)
        order = [0, 1, 2, 1, 0, 2, 1, 2]
        for e in range(beat_per_bar * 2):
            t = bar_t + e * BEAT / 2
            f = ch[order[e % len(order)]]
            g = 0.30 if kind == "calm" else 0.38
            if e % 2 == 1:
                g *= 0.75
            _add(buf, t, pluck(f, 0.5 if kind != "calm" else 0.7, bright=0.9), g)
        # --- мелодия: мотив появляется каждые 2 такта
        if kind in ("main", "tense") and b % 2 == 0:
            seq = CHROM if b % 4 == 0 else [ch[2], ch[1], ch[0], ch[1], ch[2]]
            for i, f in enumerate(seq):
                t = bar_t + i * BEAT * 0.5
                _add(buf, t, pluck(f * 2.0, 0.42, bright=1.4), 0.22)
        # --- «тарелочка»
        if kind != "calm":
            for e in range(beat_per_bar):
                _add(buf, bar_t + e * BEAT + BEAT * 0.5, hat(), 0.05)

    if kind == "tense":
        # тревожный гул + редкие удары
        n = len(buf)
        t = np.arange(n) / RATE
        drone = np.sin(2 * np.pi * 49.0 * t) * 0.10 + np.sin(2 * np.pi * 49.7 * t) * 0.08
        trem = 0.6 + 0.4 * np.sin(2 * np.pi * 0.18 * t)
        buf += drone * trem
        for b in range(bars):
            _add(buf, b * beat_per_bar * BEAT, bass_note(A2 / 2, 0.25) * 1.4, 0.5)

    # мягкий лимитер
    pk = np.max(np.abs(buf)) or 1.0
    buf = np.tanh(buf / pk * 1.6) * 0.62
    # убираем лишний хвост
    cut = int(RATE * total)
    tail = int(RATE * 1.2)
    loop_buf = buf[:cut + tail]
    # кроссфейд хвоста с началом — чтобы петля была бесшовной
    fade = int(RATE * 0.4)
    loop_buf[:fade] = loop_buf[:fade] * np.linspace(0, 1, fade) + \
        buf[cut:cut + fade] * np.linspace(1, 0, fade)
    loop_buf = loop_buf[:cut]
    return loop_buf, total


class MusicPlayer:
    """Два канала с кроссфейдом между настроениями."""

    def __init__(self):
        self.ok = False
        self.sounds = {}
        self.channels = []
        self.current = None
        if mixer is None:
            return
        try:
            if not mixer.get_init():
                mixer.pre_init(RATE, -16, 2, 2048)
                mixer.init()
            self.ok = True
        except Exception:
            self.ok = False

    def build(self, kinds=("main", "calm", "tense")):
        if not self.ok:
            return
        rng = np.random.RandomState(5)
        np.random.seed(int(rng.rand() * 2 ** 31))    # стабильные «шумы» при сборке
        for k in kinds:
            buf, _ = build_track(k, bars=8)
            pcm = (np.clip(buf, -1, 1) * 32767).astype(np.int16)
            pcm = np.column_stack([pcm, pcm])
            self.sounds[k] = mixer.Sound(array=pcm)
        self.channels = [mixer.Channel(0), mixer.Channel(1)]
        try:
            for c in self.channels:
                c.set_volume(0.0)
        except Exception:
            pass

    def switch(self, kind, fade_ms=1500):
        """Плавное переключение на трек `kind` (другой канал гаснет)."""
        if not self.ok or kind not in self.sounds:
            return
        if self.current == kind:
            return
        free, busy = (self.channels[0], self.channels[1]) \
            if (not self.channels[0].get_busy()) else (self.channels[1], self.channels[0])
        snd = self.sounds[kind]
        try:
            free.play(snd, loops=-1, fade_ms=fade_ms)
            free.set_volume(1.0)
            busy.fadeout(fade_ms)
        except Exception:
            try:
                free.play(snd, loops=-1)
            except Exception:
                return
        self.current = kind

    def set_volume(self, v):
        if not self.ok:
            return
        for c in self.channels:
            try:
                if c.get_busy():
                    c.set_volume(max(0.0, min(1.0, v)))
            except Exception:
                pass

    def stop(self):
        if self.ok:
            for c in self.channels:
                try:
                    c.stop()
                except Exception:
                    pass
