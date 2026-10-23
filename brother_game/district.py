# -*- coding: utf-8 -*-
"""Генерация района Петербургской стороны (вид сверху).

Схема взята по мотивам реального квартала: Никитская улица,
Переяславский переулок, Меднозаводской переулок и Большой П.С. пр.,
канал Грибоедова-подобная вода с мостами внизу карты.

Модель данных — «уровни» (как в Tilemap-редакторе):
  ground  — тайлы земли (асфальт, кирпич, трава, вода)
  flat    — плоские объекты (бордюр, разметка, лужи, зебра)
  walls   — непроходимые стены домов (рисуется крыша)
  over    — навесы (листва деревьев; проходят сквозь них)
  props   — высокие объекты (машины, столбы, лавки, урны, люди)

Каждый объект — dict со слоем, позицией в тайлах/пикселях и типом.
"""
import math
import random

from config import GRID_W, GRID_H, TILE, PLAYER_RADIUS

# --------------------------------------------------------------- типы тайлов
G_ASPHALT = "asphalt"
G_CONCRETE = "concrete"
G_BRICK = "brick"
G_GRASS = "grass"
G_WATER = "water"
G_SAND = "sand"
G_YARD = "yard"          # бетон во дворе

SURFACE_SOUND = {
    G_ASPHALT: "asphalt",
    G_CONCRETE: "concrete",
    G_BRICK: "brick",
    G_GRASS: "grass",
    G_SAND: "wood",
    G_YARD: "concrete",
    G_WATER: "grass",     # на воде шагов нет — тишина/бульк позже
}


class District:
    """Карта района: сетка земли + списки объектов."""

    def __init__(self, w=GRID_W, h=GRID_H, seed=7):
        self.w, self.h = w, h
        self.seed = seed
        self.rnd = random.Random(seed)
        self.ground = [[G_ASPHALT] * w for _ in range(h)]
        self.flat = []      # {t,x,y,rot}
        self.walls = []     # {x,y,w,h,color,floors}  (в тайлах)
        self.over = []      # {t,x,y,size}            (в пикселях)
        self.props = []     # {t,x,y,...}             (в пикселях)
        self.items = []     # {name,x,y,label,taken}
        self.npcs = []      # {x,y,r,jacket,mode,path,speed}
        self.zones = []     # подписи мест {label,x,y}
        self.blocked = set()  # (tx,ty) — непроходимые клетки
        self.water_y = None
        self.spawn = (14 * TILE, 30 * TILE)

    # ----------------------------------------------------------- helpers
    def fill_ground(self, x0, y0, x1, y1, t):
        for ty in range(max(0, y0), min(self.h, y1)):
            for tx in range(max(0, x0), min(self.w, x1)):
                self.ground[ty][tx] = t

    def is_solid_tile(self, tx, ty):
        if tx < 0 or ty < 0 or tx >= self.w or ty >= self.h:
            return True
        if self.ground[ty][tx] == G_WATER:
            return True
        return (tx, ty) in self.blocked

    def add_wall_block(self, x, y, w, h, color=None, floors=5):
        self.walls.append({"x": x, "y": y, "w": w, "h": h,
                           "color": color or (92, 88, 84), "floors": floors})
        for ty in range(y, y + h):
            for tx in range(x, x + w):
                if 0 <= tx < self.w and 0 <= ty < self.h:
                    self.blocked.add((tx, ty))

    def add_prop(self, kind, px, py, solid=True, radius=10, **kw):
        p = {"t": kind, "x": px, "y": py, "solid": solid, "r": radius}
        p.update(kw)
        self.props.append(p)
        if solid:
            tx, ty = int(px // TILE), int(py // TILE)
            self.blocked.add((tx, ty))
        return p

    # ------------------------------------------------------- генерация карты
    def build(self):
        self._streets_and_canal()
        self._courtyard_blocks()
        self._landmarks()
        self._props()
        self._items()
        self._npcs()
        self.finalize()
        return self

    def _streets_and_canal(self):
        """Проспекты, переулки, канал с набережной и мостами."""
        rnd = self.rnd
        # фон — асфальт, потом всё перекроем
        self.fill_ground(0, 0, self.w, self.h, G_ASPHALT)

        canal_top = 60                      # строки 60..71 — вода
        self.water_y = canal_top
        self.fill_ground(0, canal_top, self.w, self.h, G_WATER)
        # набережная (бетон) вдоль канала
        self.fill_ground(0, canal_top - 3, self.w, canal_top, G_CONCRETE)
        # травяная полоса у воды + бордюр
        self.fill_ground(0, canal_top - 4, self.w, canal_top - 3, G_GRASS)
        for tx in range(self.w):
            self.flat.append({"t": "curb", "x": tx, "y": canal_top - 4})
            if rnd.random() < 0.5:
                self.flat.append({"t": "mark", "x": tx, "y": canal_top - 1})

        # мосты через канал
        for bx in (18, 46, 74):
            self.fill_ground(bx, canal_top - 3, bx + 5, self.h, G_CONCRETE)
            for tx in range(bx, bx + 5):
                for ty in range(canal_top - 3, self.h):
                    self.blocked.discard((tx, ty))
            self.flat.append({"t": "crosswalk", "x": bx + 2, "y": canal_top - 3})
            for ty in range(canal_top - 3, canal_top):
                self.flat.append({"t": "mark", "x": bx, "y": ty})
                self.flat.append({"t": "mark", "x": bx + 4, "y": ty})

        # большой проспект (вертикальный) — Широкая ул.
        av_x = 52
        self.fill_ground(av_x, 0, av_x + 7, canal_top - 3, G_ASPHALT)
        for ty in range(0, canal_top - 3):
            if ty % 2 == 0:
                self.flat.append({"t": "mark", "x": av_x + 3, "y": ty})
        for tx in range(av_x, av_x + 7):
            self.flat.append({"t": "curb", "x": tx, "y": 0})
        # тротуары из кирпича вдоль проспекта
        self.fill_ground(av_x - 2, 0, av_x, canal_top - 3, G_BRICK)
        self.fill_ground(av_x + 7, 0, av_x + 9, canal_top - 3, G_BRICK)

        # горизонтальные улицы: Никитская, Большая П.С., Переяславский
        for row in (12, 30, 44):
            width = 6 if row != 44 else 4
            self.fill_ground(0, row, self.w, row + width, G_ASPHALT)
            self.fill_ground(0, row - 2, self.w, row, G_BRICK)
            self.fill_ground(0, row + width, self.w, row + width + 2, G_BRICK)
            for tx in range(0, self.w, 2):
                self.flat.append({"t": "curb", "x": tx, "y": row - 1})
                self.flat.append({"t": "curb", "x": tx, "y": row + width})
            for tx in range(1, self.w, 3):
                self.flat.append({"t": "mark", "x": tx, "y": row + width // 2})
            # зебры на перекрёстках
            for zx in (av_x + 1, 22, 70):
                self.flat.append({"t": "crosswalk", "x": zx, "y": row + width // 2 - 1})

        # узкие переулки (меднозаводской/переяславский)
        for col in (24, 38, 68, 82):
            self.fill_ground(col, 14, col + 3, 44, G_ASPHALT)
            self.fill_ground(col - 1, 14, col, 44, G_BRICK)
            self.fill_ground(col + 3, 14, col + 4, 44, G_BRICK)

    def _courtyard_blocks(self):
        """Кварталы «колодцем»: дома по периметру, двор внутри."""
        rnd = self.rng = self.rnd
        blocks = [
            (4, 2, 18, 9), (28, 2, 20, 9), (60, 2, 18, 9), (82, 2, 10, 9),
            (4, 18, 18, 10), (28, 18, 8, 10), (39, 18, 9, 10),
            (60, 18, 18, 10), (82, 18, 10, 10),
            (4, 34, 18, 8), (28, 34, 8, 8), (39, 34, 9, 8), (60, 34, 18, 8),
            (82, 34, 10, 8),
            (4, 48, 18, 8), (28, 48, 20, 8), (60, 48, 18, 8), (82, 48, 10, 8),
        ]
        palettes = [(112, 100, 92), (96, 92, 96), (122, 104, 88),
                    (88, 96, 100), (104, 88, 84), (118, 112, 100)]
        for i, (bx, by, bw, bh) in enumerate(blocks):
            col = palettes[i % len(palettes)]
            self.fill_ground(bx, by, bx + bw, by + bh, G_YARD)
            thick = 1
            # периметр — стены
            self.add_wall_block(bx, by, bw, thick, col, rnd.randint(4, 7))
            self.add_wall_block(bx, by + bh - thick, bw, thick, col, rnd.randint(4, 7))
            self.add_wall_block(bx, by + thick, thick, bh - 2 * thick, col, rnd.randint(4, 7))
            self.add_wall_block(bx + bw - thick, by + thick, thick, bh - 2 * thick, col, rnd.randint(4, 7))
            # арка в одном из углов (проход во двор)
            gate_side = rnd.choice(["left", "right", "top"])
            if gate_side == "left":
                gy = by + bh // 2
                self.blocked.discard((bx, gy))
                self.fill_ground(bx, gy, bx + 1, gy + 1, G_YARD)
            elif gate_side == "right":
                gy = by + bh // 2
                self.blocked.discard((bx + bw - 1, gy))
            else:
                gx = bx + bw // 2
                self.blocked.discard((gx, by))
            # внутренний флигель
            if bw > 12 and bh > 6:
                fx, fy = bx + 4, by + 3
                fw, fh = max(3, bw - 10), max(2, bh - 7)
                self.add_wall_block(fx, fy, fw, fh, tuple(int(c * 0.9) for c in col), 3)
                # детская площадка во дворе
                self.fill_ground(fx, fy + fh, fx + 3, fy + fh + 2, G_SAND)

    def _landmarks(self):
        """Знаковые точки: рынок, гаражи, стадион, вышка, теплотрасса."""
        rnd = self.rnd
        # ------------------------------------------------ рынок (крытые ряды)
        mx, my = 60, 18
        self.fill_ground(mx + 2, my + 2, mx + 14, my + 8, G_CONCRETE)
        for i in range(3):
            self.add_wall_block(mx + 3 + i * 4, my + 3, 3, 2, (150, 60, 50), 1)
        self.zones.append({"label": "РЫНОК", "x": (mx + 8) * TILE, "y": (my + 1) * TILE})
        # ------------------------------------------------ гаражный кооператив
        gx, gy = 82, 48
        self.fill_ground(gx, gy, gx + 9, gy + 6, G_YARD)
        for r in range(2):
            for c in range(4):
                self.add_wall_block(gx + 1 + c * 2, gy + 1 + r * 2, 2, 1,
                                    (104, 78, 60), 1)
        self.zones.append({"label": "ГАРАЖИ", "x": (gx + 4) * TILE, "y": (gy - 1) * TILE})
        # ------------------------------------------------ стадион с беговой дорожкой
        sx, sy = 28, 34
        self.fill_ground(sx + 1, sy + 1, sx + 7, sy + 6, G_GRASS)
        self.fill_ground(sx + 2, sy + 2, sx + 6, sy + 5, G_SAND)
        for tx in range(sx + 1, sx + 7):
            self.flat.append({"t": "track", "x": tx, "y": sy})
            self.flat.append({"t": "track", "x": tx, "y": sy + 6})
        self.zones.append({"label": "СТАДИОН", "x": (sx + 4) * TILE, "y": (sy - 1) * TILE})
        # ------------------------------------------------ телевыжка / подстанция
        tx_, ty_ = 44, 48
        self.fill_ground(tx_, ty_, tx_ + 3, ty_ + 3, G_CONCRETE)
        self.add_prop("tower", (tx_ + 1) * TILE + TILE // 2, (ty_ + 1) * TILE + TILE // 2,
                      solid=True, radius=14)
        # ------------------------------------------------ теплотрасса над двором
        for cx in range(4, 22):
            self.over.append({"t": "pipe", "x": cx * TILE + TILE // 2, "y": 26 * TILE})
        # ------------------------------------------------ сквер у канала
        self.fill_ground(30, 56, 40, 59, G_GRASS)
        for i in range(6):
            self.over.append({"t": "tree", "x": (31 + i) * TILE + TILE // 2,
                              "y": 57 * TILE + TILE // 2, "size": 72, "seed": 100 + i})
            self.add_prop("trunk", (31 + i) * TILE + TILE // 2, 57 * TILE + TILE // 2,
                          solid=True, radius=8)

    def _props(self):
        """Машины, фонари, лавки, урны, киоски, деревья вдоль улиц."""
        rnd = self.rnd
        car_colors = [(90, 96, 110), (120, 60, 52), (70, 84, 70), (110, 108, 96),
                      (60, 62, 66), (130, 110, 70), (86, 70, 100)]
        # машины вдоль широкой улицы rows 12/30/44 и проспекта
        for row in (12, 30, 44):
            for tx in range(2, self.w - 2, 4):
                if self.ground[row + 1][tx] == G_ASPHALT and rnd.random() < 0.55:
                    ang = 0 if rnd.random() < 0.8 else 90
                    px = tx * TILE + TILE // 2
                    py = (row + 1) * TILE + TILE // 2
                    self.add_prop("car", px, py, solid=True, radius=13,
                                  color=rnd.choice(car_colors), angle=ang,
                                  seed=rnd.randrange(999))
        # припаркованные у дворов
        for (bx, by, bw, bh) in [(4, 18, 18, 10), (60, 2, 18, 9), (4, 48, 18, 8)]:
            for i in range(3):
                px = (bx + 3 + i * 3) * TILE
                py = (by + bh - 2) * TILE
                if not self.is_solid_tile(int(px // TILE), int(py // TILE)):
                    self.add_prop("car", px, py, solid=True, radius=13,
                                  color=rnd.choice(car_colors), angle=90,
                                  seed=rnd.randrange(999))
        # фонари на тротуарах
        for row in (10, 36, 50):
            for tx in range(3, self.w, 8):
                self.add_prop("lamp", tx * TILE + TILE // 2, row * TILE,
                              solid=True, radius=7)
        # лавки + урны в сквере и дворах
        for i in range(8):
            px = rnd.choice([(32 + i) * TILE, (8 + i * 2) * TILE, (64 + i * 2) * TILE])
            py = rnd.choice([56 * TILE, 24 * TILE, 40 * TILE])
            if not self.is_solid_tile(int(px // TILE), int(py // TILE)):
                self.add_prop("bench", px, py, solid=True, radius=9,
                              angle=rnd.choice([0, 90]), seed=i)
        for i in range(10):
            px = (6 + i * 7) * TILE
            py = (12 + (i % 3) * 16) * TILE
            if not self.is_solid_tile(int(px // TILE), int(py // TILE)):
                self.add_prop("trash", px, py, solid=True, radius=7)
        # деревья вдоль набережной и проспекта
        for i in range(0, self.w, 5):
            for py_row in (54,):
                self.over.append({"t": "tree", "x": i * TILE + TILE // 2,
                                  "y": py_row * TILE, "size": 68, "seed": 200 + i})
                self.add_prop("trunk", i * TILE + TILE // 2, py_row * TILE,
                              solid=True, radius=8)
        for j in range(2, 56, 5):
            self.over.append({"t": "tree", "x": 50 * TILE, "y": j * TILE,
                              "size": 64, "seed": 300 + j})
            self.add_prop("trunk", 50 * TILE, j * TILE, solid=True, radius=8)
        # лужи и мусор на асфальте
        for _ in range(120):
            tx, ty = rnd.randrange(self.w), rnd.randrange(self.water_y or self.h)
            if self.ground[ty][tx] in (G_ASPHALT, G_BRICK, G_YARD) \
                    and (tx, ty) not in self.blocked:
                self.flat.append({"t": rnd.choice(["puddle", "stain", "leaf"]),
                                  "x": tx, "y": ty, "seed": rnd.randrange(999)})

    def _items(self):
        """Подбираемые предметы для инвентаря (по мотивам фильма)."""
        from player import find_walkable
        spots = [
            ("bread", "Батон", 14, 27),
            ("cigarettes", "Прима", 22, 15),
            ("money", "Деньги", 55, 33),
            ("ttt", "ТТТ", 66, 21),
            ("vodka", "Поллитра", 46, 58),
            ("bag", "Сумка", 30, 47),
            ("key", "Ключи", 84, 51),
            ("newspaper", "Газета", 10, 13),
            ("bread", "Батон", 70, 45),
            ("money", "Деньги", 34, 20),
            ("cigarettes", "Прима", 62, 55),
            ("ttt", "ТТТ", 8, 50),
        ]
        for name, label, tx, ty in spots:
            px, py = tx * TILE + TILE // 2, ty * TILE + TILE // 2
            # если клетка непроходима — ищем свободную рядом (чтобы можно было дойти)
            if self.is_solid_tile(tx, ty):
                px, py = find_walkable(self, px, py, r=6)
            self.items.append({"name": name, "label": label,
                               "x": px, "y": py, "taken": False})

    def _npcs(self):
        """Прохожие: патрулируют тротуары и дворы."""
        rnd = self.rnd
        jackets = [(70, 74, 84), (96, 84, 70), (60, 70, 64), (88, 60, 60),
                   (110, 108, 100), (52, 56, 66)]
        paths = [
            ((6, 11), (46, 11)), ((30, 29), (70, 29)), ((6, 43), (46, 43)),
            ((53, 6), (53, 52)), ((20, 55), (44, 55)), ((60, 17), (90, 17)),
            ((8, 33), (24, 33)), ((62, 47), (88, 47)),
        ]
        for i, (a, b) in enumerate(paths):
            ax, ay = a[0] * TILE + TILE // 2, a[1] * TILE + TILE // 2
            bx, by = b[0] * TILE + TILE // 2, b[1] * TILE + TILE // 2
            self.npcs.append({
                "x": ax, "y": ay, "a": (ax, ay), "b": (bx, by),
                "r": 11, "jacket": jackets[i % len(jackets)],
                "speed": rnd.uniform(42, 78), "phase": rnd.uniform(0, 1),
                "dir": 1, "facing": 0.0,
            })

    # ------------------------------------------------------- доступ к данным
    def finalize(self):
        """Спавн игрока в гарантированно проходимой клетке."""
        from player import find_walkable
        sx, sy = self.spawn
        self.spawn = find_walkable(self, sx, sy, r=PLAYER_RADIUS)
        return self

    def ground_at_px(self, px, py):
        tx, ty = int(px // TILE), int(py // TILE)
        tx = max(0, min(self.w - 1, tx))
        ty = max(0, min(self.h - 1, ty))
        return self.ground[ty][tx]

    def surface_sound(self, px, py):
        return SURFACE_SOUND.get(self.ground_at_px(px, py), "asphalt")

    def circle_blocked(self, px, py, r):
        """Пересекает ли круг непроходимую область (стены/вода/пропы)."""
        # грубая проверка по 8 точкам окружности + центру
        pts = [(px, py)]
        for k in range(8):
            a = k * math.tau / 8
            pts.append((px + math.cos(a) * r, py + math.sin(a) * r))
        for x, y in pts:
            tx, ty = int(x // TILE), int(y // TILE)
            if self.is_solid_tile(tx, ty):
                return True
        for p in self.props:
            if not p.get("solid"):
                continue
            dx, dy = p["x"] - px, p["y"] - py
            rr = r + p.get("r", 10)
            if dx * dx + dy * dy < rr * rr:
                return True
        return False

    def rect_blocked(self, px, py, w, h):
        for x in range(int(px), int(px + w) + 1, TILE // 2):
            for y in range(int(py), int(py + h) + 1, TILE // 2):
                if self.is_solid_tile(int(x // TILE), int(y // TILE)):
                    return True
        return False


def build_district(seed=7):
    return District(seed=seed).build()
