# -*- coding: utf-8 -*-
"""Проверка: фасады + вход внутрь каждого здания (headless)."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import math
import pygame
pygame.init()
pygame.display.set_mode((640, 480))

from game import Game
from config import TILE, WINDOW_W, WINDOW_H

g = Game(headless=False)
d = g.district
print("doors:", len(d.doors), "interiors:", len(d.interiors),
      "indoors buffers:", len(g.renderer.indoors))
assert len(d.doors) == len(d.interiors) == len(g.renderer.indoors) > 0

ok = 0
for dr in d.doors:
    # ставим игрока ровно на дверь и жмём E
    g.player.x, g.player.y = dr["x"], dr["y"] + TILE * 0.5
    assert g.near_door() is not None, ("door not found", dr["label"])
    assert g.toggle_door(), ("enter failed", dr["label"])
    lvl = d.active_grid()
    assert lvl is not None and lvl["key"] == dr["level"]
    # игрок не внутри стен
    assert not d.circle_blocked(g.player.x, g.player.y, g.player.radius), \
        ("spawn blocked", dr["label"])
    # кадр внутри рисуется без ошибок
    g.camera = [g.player.x - WINDOW_W / 2, g.player.y - WINDOW_H / 2]
    g.draw()
    # немного ходим внутрь — коллизии по мини-сетке
    for _ in range(30):
        g.update(1 / 60, (0, -1, False))
    g.draw()
    # выходим
    ex, ey = lvl["exit"]
    g.player.x, g.player.y = ex, ey - TILE * 0.4
    assert g.toggle_door(), ("exit failed", dr["label"])
    assert not d.in_level
    assert not d.circle_blocked(g.player.x, g.player.y, g.player.radius), \
        ("out-of-door blocked", dr["label"])
    ok += 1
    print(f"OK {dr['label']:28s} enter/exit @ ({dr['x']:.0f},{dr['y']:.0f})")
print("all doors roundtrip:", ok)

# подбор предмета внутри дома
dr = d.doors[0]
g.player.x, g.player.y = dr["x"], dr["y"] + TILE * 0.5
g.toggle_door()
lvl = d.active_grid()
it = next(i for i in lvl["items"] if not i["taken"])
g.player.x, g.player.y = it["x"] + 10, it["y"]
n0 = g.inventory.total_items
g.pick_up()
assert g.inventory.total_items == n0 + 1, "interior pickup failed"
print("interior pickup OK:", it["label"])
g.exit_door()

# ночной кадр улицы с фасадами
g.time_of_day = 20.5
g._update_day_night(0.0)
g.player.x, g.player.y = 30 * TILE, 27 * TILE
g.camera = [g.player.x - WINDOW_W / 2, g.player.y - WINDOW_H / 2]
g.draw()
pygame.image.save(g.screen, "_shot_street_night.png")
g.time_of_day = 13.0
g._update_day_night(0.0)
g.draw()
pygame.image.save(g.screen, "_shot_street_day.png")
# кадр интерьера
g.toggle_door()
g.draw()
pygame.image.save(g.screen, "_shot_interior.png")
print("shots saved; blits/frame:", g.renderer._blit_n)
print("ALL INTERIOR TESTS PASSED")
