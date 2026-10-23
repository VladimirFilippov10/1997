# -*- coding: utf-8 -*-
"""Точка входа.

Запуск:
    python main.py                — обычная игра (нужен дисплей)
    python main.py --demo         — headless-прогон механики + скриншоты в ./shots
    python main.py --screenshot   — один кадр с HUD и сохранение в ./shots/game.png

Игра «по мотивам фильма „Брат“»: вид сверху, район Петербургской стороны,
инвентарь, механика ходьбы/бега со звуком шагов по разным покрытиям.
"""
import argparse
import os
import sys

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame  # noqa: E402

from config import FPS, WINDOW_H, WINDOW_W  # noqa: E402


def ensure_cwd():
    """Чтобы импорты и пути работали из любого места запуска."""
    here = os.path.dirname(os.path.abspath(__file__))
    if os.getcwd() != here:
        os.chdir(here)
    if here not in sys.path:
        sys.path.insert(0, here)


def run_game():
    from game import Game
    g = Game(headless=False)
    g.run()


def take_screenshots(frames_list):
    """Headless-рендер отдельных состояний в PNG (для проверки без монитора)."""
    from game import Game
    shots_dir = os.path.join(os.getcwd(), "shots")
    os.makedirs(shots_dir, exist_ok=True)
    pygame.init()
    pygame.display.set_mode((WINDOW_W, WINDOW_H))
    for spec in frames_list:
        g = Game(headless=False)
        dx, dy = spec.get("input", (0, 0))
        for _ in range(spec.get("walk", 0)):
            g.update(1 / FPS, (dx, dy, spec.get("run", False)))
        pdx, pdy = spec.get("pick_dir", (0, 0))
        for _ in range(spec.get("pick_walk", 0)):
            g.update(1 / FPS, (pdx, pdy, False))
        if spec.get("teleport_near_item"):
            it = next((i for i in g.district.items if not i["taken"]), None)
            if it:
                g.player.x, g.player.y = it["x"] + 20, it["y"]
        if spec.get("pick"):
            g.pick_up()
        if spec.get("use"):
            g.use_selected()
        g.show_map = bool(spec.get("map"))
        g.draw()
        path = os.path.join(shots_dir, spec["name"] + ".png")
        pygame.image.save(g.screen, path)
        print("saved:", path, f"steps={g.player.steps}", f"inv={g.inventory.labels()}")
        del g
    pygame.quit()


def demo():
    from game import auto_demo
    g = auto_demo(frames=360)
    print(f"демо завершено: шагов={g.player.steps}, скорость={g.player.speed_now:.1f}px/s, "
          f"покрытие={g.player.surface}, инвентарь={g.inventory.labels()}")


def main():
    ensure_cwd()
    ap = argparse.ArgumentParser(description="БРАТ: ПИТЕР — вид сверху")
    ap.add_argument("--demo", action="store_true", help="headless-прогон механики")
    ap.add_argument("--screenshot", action="store_true", help="один кадр в shots/game.png")
    ap.add_argument("--shots", action="store_true", help="серия проверочных кадров")
    args = ap.parse_args()

    if args.demo:
        demo()
        return
    if args.screenshot or args.shots:
        if args.screenshot:
            specs = [{"name": "game", "walk": 90, "input": (1, 0), "pick": False}]
        else:
            specs = [
                {"name": "idle", "walk": 0},
                {"name": "walking", "walk": 120, "input": (0, -1)},
                {"name": "running", "walk": 150, "input": (1, 0), "run": True},
                {"name": "inventory", "teleport_near_item": True,
                 "pick": True, "use": True},
                {"name": "map", "walk": 40, "input": (-1, 0), "map": True},
            ]
        take_screenshots(specs)
        return
    run_game()


if __name__ == "__main__":
    main()
