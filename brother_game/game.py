# -*- coding: utf-8 -*-
"""Игровой цикл: ввод, физика, подбор/использование предметов, камера."""
import math
import random

import pygame

import textures as T
from audio import build_audio
from config import (FPS, RUN_SPEED, TILE, WINDOW_H, WINDOW_W, COL_ACCENT)
from district import build_district
from lomnoshin import build_lomonosov
from hud import draw_hud
from inventory import Inventory, Item
from player import Player, WalkerNPC
from render import Renderer, draw_text

ITEM_LABELS = {
    "bread": "Батон", "cigarettes": "Прима", "money": "Деньги", "ttt": "ТТТ",
    "vodka": "Поллитра", "bag": "Сумка", "key": "Ключи", "newspaper": "Газета",
}
USE_TEXT = {
    "bread": "Данила отломил кусок батона. Неплохо для начала.",
    "cigarettes": "Закурил. В Питере без куртки зябко.",
    "money": "Пересчитал деньги. Мелочь, а приятно.",
    "ttt": "ТТТ — «так-так-так». Хорошее слово.",
    "vodka": "Поллитра зашла, но идти стало веселее.",
    "bag": "Сумка тяжёлая. Внутри что-то звенит.",
    "key": "Ключи. Подходящие?",
    "newspaper": "Прочитал газету. Новости так себе.",
}


class Game:
    def __init__(self, headless=False):
        self.headless = headless
        self.running = True
        self.clock = None
        self.time_s = 0.0
        self.messages = []
        self.show_map = False
        # ---- цикл суток: утро/день/вечер/ночь. 1 игровые сутки = DAY_LEN сек.
        self.DAY_LEN = 240.0
        self.time_of_day = 17.6          # сумерки — сразу видны фары и фонари
        self._night_cache = -1.0
        # погода: ясно / морось / дождь; переключается сама + T вручную
        self.weather_mode = "drizzle"
        self._weather_t = 0.0
        self._next_change = random.uniform(50, 90)
        self.muted = False
        self.rnd = random.Random(11)

        # ---- мир: квартал улицы Ломоносова (историческая схема «Пяти углов»);
        # при любой ошибке — откат на процедурный район Петербургской стороны
        try:
            self.district = build_lomonosov(seed=1997)
        except Exception as exc:      # pragma: no cover
            import traceback
            traceback.print_exc()
            print("[warn] Ломоносов не построился:", exc)
            self.district = build_district(seed=7)
        self.player = Player(self.district.spawn[0], self.district.spawn[1], self.district)
        self.walkers = [WalkerNPC(n) for n in self.district.npcs]
        self.inventory = Inventory()
        self.camera = [self.player.x - WINDOW_W / 2, self.player.y - WINDOW_H / 2]

        # ---- графика
        if not headless:
            pygame.display.set_mode((WINDOW_W, WINDOW_H))
            self.screen = pygame.display.get_surface()
            pygame.display.set_caption("БРАТ: ПИТЕР")
            self.renderer = Renderer(self.screen, self.district)
            self.renderer.build_map_surface()
        else:
            self.screen = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
            self.renderer = None

        # ---- иконки предметов + хотбар
        self.item_icons = {k: T.item_icon(k, 34, seed=i * 5 + 1)
                           for i, k in enumerate(ITEM_LABELS)}
        self.hotbar_frames = (T.hotbar_frame(52, False), T.hotbar_frame(52, True))

        # ---- звук
        self.audio, snd = build_audio()
        self.sfx = snd  # полный словарь синтезированных звуков
        self.step_sounds = {k: v for k, v in snd.items()
                            if k in ("asphalt", "concrete", "grass", "brick", "wood")}
        self.wind = snd.get("wind")
        self.city = snd.get("city")
        self.click = snd.get("click")
        if self.audio.ok:
            self.audio.play(self.wind, loops=-1, volume=0.5)
            self.audio.play(self.city, loops=-1, volume=0.35)
            rain_sfx = snd.get("rain")
            if rain_sfx is not None:
                self.audio.play(rain_sfx, loops=-1, volume=0.0)
                self._rain_channel = True

        self._held_printed = False

    # ------------------------------------------------------------- утилиты
    def say(self, text, color=(240, 240, 235), size=20, bold=False, life=3.5):
        self.messages.append({"text": text, "color": color, "size": size,
                              "bold": bold, "life": life,
                              "t": pygame.time.get_ticks() / 1000.0})

    def surface_name(self, surf_key):
        return {"asphalt": "асфальт", "concrete": "бетон", "brick": "кирпич",
                "grass": "трава", "wood": "доски/песок"}.get(surf_key, surf_key)

    def nearest_item(self):
        best, bd = None, TILE * 1.2
        for it in self.district.items:
            if it["taken"]:
                continue
            d = math.hypot(it["x"] - self.player.x, it["y"] - self.player.y)
            if d < bd:
                bd, best = d, it
        return best

    # --------------------------------------------------------------- действия
    def pick_up(self):
        it = self.nearest_item()
        if it is None:
            return
        slot = self.inventory.add(Item(it["name"], ITEM_LABELS.get(it["name"], it["label"])))
        if slot < 0:
            self.say("Карманы полны", color=(230, 160, 90))
            return
        it["taken"] = True
        self.say(f"Подобрано: {ITEM_LABELS.get(it['name'], it['label'])}",
                 color=(240, 210, 90))
        self.audio.play(self.click)

    def use_selected(self):
        item = self.inventory.selected_item()
        if item is None:
            self.say("Пусто в этом слоте", color=(180, 180, 180))
            return
        text = USE_TEXT.get(item.name, f"Использовано: {item.label}")
        self.say(text, color=(200, 220, 200))
        if item.name == "bread":
            self.player.health = min(100.0, self.player.health + 6)
        elif item.name == "vodka":
            self.player.health = min(100.0, self.player.health + 12)
        self.inventory.remove_at(self.inventory.selected, 1)

    def drop_selected(self):
        item = self.inventory.selected_item()
        if item is None:
            return
        self.inventory.remove_at(self.inventory.selected, 1)
        tx, ty = int(self.player.x // TILE), int(self.player.y // TILE)
        # кладём у ног
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                x, y = tx + dx, ty + dy
                if 0 <= x < self.district.w and 0 <= y < self.district.h \
                        and not self.district.is_solid_tile(x, y):
                    self.district.items.append({
                        "name": item.name, "label": item.label,
                        "x": x * TILE + TILE // 2, "y": y * TILE + TILE // 2,
                        "taken": False})
                    self.say(f"Выброшено: {item.label}", color=(200, 170, 150))
                    return

    # ---------------------------------------------------------------- шаги
    def on_step(self, surface, run):
        variants = self.step_sounds.get(surface) or self.step_sounds["asphalt"]
        snd = self.rnd.choice(variants) if variants else None
        vol = 0.9 if run else 0.7
        if not self.muted:
            self.audio.play(snd, volume=vol)

    def set_muted(self, muted):
        """Выключение звука: останавливаем фоновые петли и шаги."""
        self.muted = muted
        if not self.audio.ok:
            return
        try:
            import pygame.mixer as mx
            if muted:
                mx.stop()          # тишина для всех каналов (фоновые петли)
            else:
                # возобновляем эмбиент
                self.audio.play(self.wind, loops=-1, volume=0.5)
                self.audio.play(self.city, loops=-1, volume=0.35)
        except Exception:
            pass

    # ---------------------------------------------------------------- update
    def handle_events(self):
        keys = pygame.key.get_pressed()
        dx = (keys[pygame.K_d] or keys[pygame.K_RIGHT]) - (keys[pygame.K_a] or keys[pygame.K_LEFT])
        dy = (keys[pygame.K_s] or keys[pygame.K_DOWN]) - (keys[pygame.K_w] or keys[pygame.K_UP])
        run = bool(keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT])
        return dx, dy, run

    def update(self, dt, input_state=None):
        if input_state is None:
            dx = dy = 0
            run = False
        else:
            dx, dy, run = input_state
        self.player.update(dx, dy, run, dt, on_step=self.on_step)
        for w in self.walkers:
            w.update(dt)
        # мягкая камера
        tx = self.player.x - WINDOW_W / 2
        ty = self.player.y - WINDOW_H / 2
        k = 1.0 - math.exp(-dt * 7.0)
        self.camera[0] += (tx - self.camera[0]) * k
        self.camera[1] += (ty - self.camera[1]) * k
        self.time_s += dt

    def draw(self):
        if self.headless:
            return
        self.renderer.draw(self.camera, self.player, self.time_s,
                           self.inventory.selected, self.messages)
        draw_hud(self.screen, self)

    # ---------------------------------------------------------------- main loop
    def run(self):
        self.clock = pygame.time.Clock()
        self.say("Петербургская сторона. Осень.", color=COL_ACCENT, size=26, bold=True, life=4.5)
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            dt = min(dt, 0.05)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    self.on_key(event.key)
                elif event.type == pygame.MOUSEWHEEL:
                    self.inventory.cycle(1 if event.y > 0 else -1)
            state = self.handle_events()
            self.update(dt, state)
            self.draw()
            pygame.display.flip()
        self.audio.free()
        pygame.quit()

    def on_key(self, key):
        K = pygame.K
        if key == K_ESCAPE:
            self.running = False
        elif key == K_e:
            self.pick_up()
        elif key == K_f:
            self.use_selected()
        elif key == K_g:
            self.drop_selected()
        elif key == K_TAB:
            self.show_map = not self.show_map
        elif key == K_m:
            self.set_muted(not self.muted)
            self.say("Звук выключен" if self.muted else "Звук включён",
                     color=(180, 180, 180))
        elif K_1 <= key <= K_9:
            self.inventory.select(key - K_1)
        elif key == K_0:
            self.inventory.select(9 % len(self.inventory.slots))
        elif key == K_F3:
            self.toggle_debug()

    def toggle_debug(self):
        self.debug = not getattr(self, "debug", False)


def auto_demo(frames=240, headless=True):
    """Прогон механики без окна: ходьба по точкам + подбор предмета."""
    g = Game(headless=headless)
    path = [(0, -1), (1, 0), (1, -1), (0, 1), (-1, 0)]
    step_i = 0
    held = 60
    for f in range(frames):
        if f % held == 0:
            step_i = (step_i + 1) % len(path)
        dx, dy = path[step_i]
        g.update(1 / FPS, (dx, dy, f % 120 < 40))
        if f == frames - 30:
            g.pick_up()
    return g
