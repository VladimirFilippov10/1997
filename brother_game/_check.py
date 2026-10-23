import os
os.environ.setdefault("SDL_VIDEODRIVER","dummy")
os.environ.setdefault("SDL_AUDIODRIVER","dummy")
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"]="1"
import pygame; pygame.init(); pygame.display.set_mode((640,480))
from game import Game
g = Game(headless=False)
print("spawn:", g.district.spawn, "solid?", g.district.is_solid_tile(*[int(v//48) for v in g.district.spawn]))
it = next(i for i in g.district.items if not i["taken"])
print("item:", it["label"], (it["x"], it["y"]))
g.player.x, g.player.y = it["x"]+20, it["y"]
near = g.nearest_item()
print("nearest:", near and near["label"])
g.pick_up()
print("inv after pick:", g.inventory.labels())
g.use_selected()
print("inv after use:", g.inventory.labels(), "health:", g.player.health)
# проверка ходьбы в 4 сторонах без застревания
import math
for ang in range(0,360,45):
    dx,dy = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    x0,y0=g.player.x,g.player.y
    for _ in range(90): g.update(1/60,(dx,dy,False))
    print(f"dir {ang:3d}: moved {math.hypot(g.player.x-x0,g.player.y-y0):.0f}px steps={g.player.steps}")
