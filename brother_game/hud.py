# -*- coding: utf-8 -*-
"""HUD: хотбар, инфо-панель, подсказки, сообщения, миникарта района."""
import math

import pygame

from config import COL_ACCENT, COL_TEXT, MINIMAP_SIZE, TILE
from inventory import draw_hotbar
from render import draw_casio_clock, draw_text


def draw_hud(screen, game):
    d = game.district
    player = game.player
    inv = game.inventory
    W, H = screen.get_size()

    # ------------------------------------------------------ инфо-панель слева
    panel = pygame.Surface((300, 120), pygame.SRCALPHA)
    panel.fill((16, 18, 22, 190))
    screen.blit(panel, (12, 12))
    speed_kmh = player.speed_now * 0.072      # px/с → условный «км/ч» для флейвора
    mode = "БЕГ" if player.running else ("ИДЁТ" if player.moving else "СТОИТ")
    lines = [
        ("ДАНИЛА БАГРОВ", 18, COL_ACCENT, True),
        (f"Скорость: {speed_kmh:.1f} км/ч   ({mode})", 15, COL_TEXT, False),
        (f"Покрытие под ногами: {game.surface_name(player.surface)}", 15, COL_TEXT, False),
        (f"Шагов сделано: {player.steps}", 15, COL_TEXT, False),
        (f"Предметов в карманах: {inv.total_items}", 15, COL_TEXT, False),
    ]
    y = 24
    for text, size, col, bold in lines:
        draw_text(screen, text, (22, y), size=size, color=col, bold=bold)
        y += size + 5

    # ---------------------------------------------------- здоровье (полоска)
    bar = pygame.Rect(22, y + 2, 200, 10)
    pygame.draw.rect(screen, (40, 42, 48), bar, border_radius=4)
    fillw = int(bar.width * max(0.0, player.health / 100.0))
    pygame.draw.rect(screen, (120, 170, 110), (bar.x, bar.y, fillw, bar.height),
                     border_radius=4)

    # ------------------------------------------------------------- хотбар
    draw_hotbar(screen, inv, lambda s, t, p, size=16, color=COL_TEXT, bold=False: draw_text(
        s, t, p, size=size, color=color, bold=bold), game.item_icons,
        game.hotbar_frames)

    # ------------------------------------------- CASIO-часы (игровое время)
    tod = getattr(game, "time_of_day", 12.0)
    clock_face = draw_casio_clock(screen, tod, scale=0.9)
    hh = int(tod) % 24
    phase = ("ночь" if (hh >= 21 or hh < 5) else
             "утро" if hh < 8 else "день" if hh < 17 else "вечер")
    wname = {"clear": "ясно", "drizzle": "морось", "rain": "дождь"}.get(
        getattr(game, "weather_mode", "clear"), "")
    draw_text(screen, f"{phase} · {wname} · N — перемотка, T — погода",
              (W - clock_face.get_width() // 2 - 14,
               H - clock_face.get_height() - 52), size=13,
              color=(170, 176, 186), center=True, bg=(16, 18, 22, 150))

    # ------------------------------------------------------- строка подсказок
    hint = ("WASD — идти · Shift — бежать · E — подобрать · F — использовать · "
            "Q — выбросить · 1..0 / колесо — слот · Tab — карта · M — звук · Esc — выход")
    draw_text(screen, hint, (W // 2, H - 8), size=14, color=(170, 172, 178), center=True,
              bg=(16, 18, 22, 150))

    # -------------------------------------------------------- всплывающие сообщения
    now = pygame.time.get_ticks() / 1000.0
    yy = 150
    for msg in list(game.messages):
        age = now - msg["t"]
        if age > msg.get("life", 3.5):
            game.messages.remove(msg)
            continue
        alpha = 255 if age < msg.get("life", 3.5) - 0.8 else int(255 * (msg["life"] - age) / 0.8)
        c = tuple(min(255, v) for v in msg["color"])
        draw_text(screen, msg["text"], (W // 2, yy), size=msg.get("size", 20),
                  color=c, center=True, bold=msg.get("bold", False))
        yy += 26

    # --------------------------------------------------- индикатор цели (E)
    near = game.nearest_item()
    if near is not None:
        sx = near["x"] - game.camera[0]
        sy = near["y"] - game.camera[1]
        ring = pygame.Surface((46, 46), pygame.SRCALPHA)
        pulse = 1 + 0.12 * math.sin(now * 6)
        pygame.draw.circle(ring, (*COL_ACCENT, 220), (23, 23), int(20 * pulse), 2)
        screen.blit(ring, (sx - 23, sy - 23))
        draw_text(screen, "[E] взять: " + near["label"], (sx, sy - 34), size=15,
                  color=(240, 240, 235), center=True, bg=(16, 18, 22, 180))

    # ------------------------------------------------------------- миникарта
    if game.show_map:
        _draw_minimap(screen, game, big=True)
    else:
        _draw_minimap(screen, game, big=False)


def _draw_minimap(screen, game, big=False):
    d = game.game_district if hasattr(game, "game_district") else game.district
    W, H = screen.get_size()
    size = MINIMAP_SIZE if big else 140
    pad = 10
    rect = pygame.Rect(W - size - pad, pad, size, size)
    bg = pygame.Surface((size + 2 * pad, size + 2 * pad), pygame.SRCALPHA)
    bg.fill((14, 16, 20, 210))
    screen.blit(bg, (rect.left - pad, rect.top - pad))

    scale = size / max(d.w, d.h)
    mw, mh = int(d.w * scale), int(d.h * scale)
    mm = pygame.Surface((mw, mh))
    mm.fill((28, 30, 34))
    # земля
    colors = {"asphalt": (52, 54, 58), "concrete": (86, 86, 90),
              "brick": (92, 76, 68), "grass": (48, 66, 46),
              "water": (30, 46, 62), "sand": (88, 82, 66), "yard": (66, 68, 62)}
    for ty in range(d.h):
        row = d.ground[ty]
        for tx in range(d.w):
            mm.set_at((int(tx * scale), int(ty * scale)), colors.get(row[tx], (40, 40, 44)))
    # стены кварталов
    for w in d.walls:
        r = pygame.Rect(int(w["x"] * scale), int(w["y"] * scale),
                        max(1, int(w["w"] * scale)), max(1, int(w["h"] * scale)))
        pygame.draw.rect(mm, (150, 140, 128), r)
    # предметы
    for it in d.items:
        if not it["taken"]:
            x = int(it["x"] / TILE * scale)
            y = int(it["y"] / TILE * scale)
            pygame.draw.circle(mm, (240, 210, 90), (x, y), 2)
    # npc
    for n in game.walkers:
        x = int(n.x / TILE * scale)
        y = int(n.y / TILE * scale)
        pygame.draw.circle(mm, (120, 130, 140), (x, y), 2)
    # игрок
    px = int(game.player.x / TILE * scale)
    py = int(game.player.y / TILE * scale)
    pygame.draw.circle(mm, COL_ACCENT, (px, py), 3)
    pygame.draw.line(mm, COL_ACCENT, (px, py),
                     (px + math.cos(game.player.facing) * 6,
                      py + math.sin(game.player.facing) * 6), 1)
    mm = pygame.transform.scale(mm, (size, size))
    screen.blit(mm, rect.topleft)
    label = "КАРТА РАЙОНА (Tab)" if big else "ПЕТЕРБУРГСКАЯ СТОРОНА"
    draw_text(screen, label, (rect.centerx, rect.bottom + 12), size=13,
              color=(170, 172, 178), center=True)
