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

        # ---- погода/эффекты: создаём и привязываем к рендереру,
        # обновляются из Game.update(); в headless просто молча живут
        try:
            from effects import WeatherSystem
            self.weather = WeatherSystem(self.district)
            puddle_pts = [(f["x"] * TILE + TILE // 2, f["y"] * TILE + TILE // 2)
                          for f in self.district.flat if f["t"] == "puddle"]
            self.weather.bind_district_visuals(puddle_pts)
        except Exception:
            self.weather = None
        if self.renderer is not None:
            self.renderer.weather = self.weather
        self._apply_weather()

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
                ch = self.audio.play(rain_sfx, loops=-1, volume=0.0)
                self._rain_channel = True
                if ch is not None:
                    snd["rain_channel"] = ch

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

    # ------------------------------------------------------- цикл суток/погода
    def _sky_tint(self):
        """Лёгкая цветовая подкраска мира по фазе суток."""
        h = self.time_of_day % 24.0
        if 5.0 <= h < 8.0:                      # рассвет — тёплый розовый
            k = (h - 5.0) / 3.0
            return (255, 196, 150), int(26 * math.sin(math.pi * k))
        if 17.0 <= h < 20.5:                    # закат — янтарный
            k = (h - 17.0) / 3.5
            return (255, 170, 110), int(30 * math.sin(math.pi * k))
        if h >= 20.5 or h < 5.0:                # ночь — холодный синий
            return (70, 90, 160), 22
        return (255, 255, 255), 0               # день — без подкраски

    def _update_day_night(self, dt):
        """Часы игры: 1 сутки = DAY_LEN сек; считает night (0..1) для рендера."""
        self.time_of_day = (self.time_of_day + dt * 24.0 / self.DAY_LEN) % 24.0
        h = self.time_of_day
        dawn, sunrise, sunset, dusk = 4.6, 6.4, 19.2, 21.0
        if sunrise <= h <= sunset:
            night = 0.0
        elif h < dawn or h > 24 - (24 - dusk):  # глубокая ночь
            night = 1.0
        elif dawn <= h < sunrise:
            night = 1.0 - (h - dawn) / (sunrise - dawn)
        else:                                   # sunset..dusk — сумерки
            night = (h - sunset) / (dusk - sunset)
        self._night_cache = max(0.0, min(1.0, night))
        if self.renderer is not None:
            self.renderer.night = self._night_cache
            tint, ta = self._sky_tint()
            self.renderer.sky_tint = (tint, ta)

    def _update_weather(self, dt):
        """Погода сама переключается: ясно -> морось -> дождь; T — вручную."""
        self._weather_t += dt
        if self._weather_t >= self._next_change:
            self._weather_t = 0.0
            self._next_change = random.uniform(50, 90)
            order = ["clear", "drizzle", "rain"]
            self.weather_mode = order[(order.index(self.weather_mode) + 1)
                                      % len(order)] if self.weather_mode in order \
                else "drizzle"
            self._apply_weather()
            self.say({"clear": "Небо расчистилось.",
                      "drizzle": "Накрапал мелкий дождик.",
                      "rain": "Пошёл серьёзный питерский дождь."}
                     .get(self.weather_mode, ""), color=(180, 190, 200), life=2.5)

    def _apply_weather(self):
        w = getattr(self, "weather", None)
        if w is None:
            return
        m = self.weather_mode
        w.rain.set_intensity({"clear": 0.0, "drizzle": 0.28, "rain": 0.8}.get(m, 0.4))
        w.rain.storm = (m == "rain")
        try:
            import pygame.mixer as mx
            ch = self.sfx.get("rain_channel")
            if ch is not None and self.audio.ok and not self.muted:
                ch.set_volume({"clear": 0.0, "drizzle": 0.25, "rain": 0.6}.get(m, 0.3))
        except Exception:
            pass

    def cycle_weather(self):
        order = ["clear", "drizzle", "rain"]
        i = order.index(self.weather_mode) if self.weather_mode in order else -1
        self.weather_mode = order[(i + 1) % len(order)]
        self._weather_t = 0.0
        self._next_change = random.uniform(50, 90)
        self._apply_weather()
        label = {"clear": "ясно", "drizzle": "морось", "rain": "дождь"}[self.weather_mode]
        self.say(f"Погода: {label}", color=(180, 190, 200), life=2.0)

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
        # ---- транспорт: едущие машины (район сам считает траектории)
        events = []
        try:
            events = self.district.update_movers(dt, (self.player.x, self.player.y))
        except Exception:
            events = []
        horn = self.sfx.get("horn")
        for ev in events:
            if ev[0] == "horn" and self.audio.ok and not self.muted and horn is not None:
                self.audio.play(horn, volume=max(0.15, min(1.0, ev[3])))
        # ---- цикл суток и погода
        self._update_day_night(dt)
        self._update_weather(dt)
        # ---- эффекты (дождь/пар/частицы) — живут в renderer.weather
        if self.renderer is not None and self.renderer.weather is not None:
            self.renderer.weather.update(dt, self.time_s)
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
        self.say("Петербургская сторона. Осень.", color=COL_ACCENT, size=26,
                 bold=True, life=4.5)
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
        if key == pygame.K_ESCAPE:
            self.running = False
        elif key == pygame.K_e:
            self.pick_up()
        elif key == pygame.K_f:
            self.use_selected()
        elif key == pygame.K_g:
            self.drop_selected()
        elif key == pygame.K_TAB:
            self.show_map = not self.show_map
        elif key == pygame.K_m:
            self.set_muted(not self.muted)
            self.say("Звук выключен" if self.muted else "Звук включён",
                     color=(180, 180, 180))
        elif key == pygame.K_t:
            # вручную переключить погоду (ясно -> морось -> дождь)
            self.cycle_weather()
        elif key == pygame.K_n:
            # быстро перемотать на 2 часа вперёд — смотреть ночной свет/фары
            self.time_of_day = (self.time_of_day + 2.0) % 24.0
            self._update_day_night(0.0)
            hh = int(self.time_of_day) % 24
            self.say(f"Время: {hh:02d}:00", color=(200, 210, 230), life=2.0)
        elif pygame.K_1 <= key <= pygame.K_9:
            self.inventory.select(key - pygame.K_1)
        elif key == pygame.K_0:
            self.inventory.select(9 % len(self.inventory.slots))
        elif key == pygame.K_F3:
            self.toggle_debug()

    def toggle_debug(self):
        self.debug = not getattr(self, "debug", False)
        if self.renderer is not None:
            self.renderer.show_walls = self.debug


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
