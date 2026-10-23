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

# покрытия внутри зданий -> звук шагов
INTERIOR_SOUND = {
    "parquet": "wood", "wood": "wood", "linoleum": "concrete",
    "tile": "concrete", "concrete": "concrete", "carpet": "grass",
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
        self.movers = []    # ездящие машины: {t,x,y,dir,speed,ax,bx,...}
        self.puddles = []   # world-координаты луж (рябь дождя)
        self.vents = []     # точки теплотрассы, из которых валит пар
        self.zones = []     # подписи мест {label,x,y}
        self.blocked = set()  # (tx,ty) — непроходимые клетки
        self.interiors = {}   # key -> dict уровня внутри здания
        self.doors = []       # {x,y,r,level,label} — входы в здания
        self.water_y = None
        self.spawn = (14 * TILE, 30 * TILE)

    # --------------------------------------------------- текущий уровень
    def active_grid(self):
        """None = улица; иначе dict интерьера (своя сетка blocked)."""
        return getattr(self, "_level", None)

    def enter_level(self, key):
        self._level = self.interiors[key] if key else None

    @property
    def in_level(self):
        lvl = self.active_grid()
        return lvl is not None

    def level_blocked(self, lvl, tx, ty):
        if tx < 0 or ty < 0 or tx >= lvl["w"] or ty >= lvl["h"]:
            return True
        return (tx, ty) in lvl["blocked"]

    def circle_blocked_level(self, lvl, px, py, r):
        x0 = int((px - r) // TILE); x1 = int((px + r) // TILE)
        y0 = int((py - r) // TILE); y1 = int((py + r) // TILE)
        for ty in range(y0, y1 + 1):
            for tx in range(x0, x1 + 1):
                if self.level_blocked(lvl, tx, ty):
                    cx = max(tx * TILE, min(px, tx * TILE + TILE))
                    cy = max(ty * TILE, min(py, ty * TILE + TILE))
                    if (cx - px) ** 2 + (cy - py) ** 2 < r * r:
                        return True
        return False

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

    def add_wall_block(self, x, y, w, h, color=None, floors=5, interior=None):
        rnd = self.rnd
        style = rnd.choice(("gable", "gable", "mansard", "hip", "flat", "monitor"))
        tower = (w >= 3 and h >= 2 and rnd.random() < 0.18)
        wall = {"x": x, "y": y, "w": w, "h": h,
                "color": color or (92, 88, 84), "floors": floors,
                "style": style, "tower": tower,
                "seed": rnd.randrange(1 << 20),
                "interior": interior}          # dict уровня или None
        self.walls.append(wall)
        if interior is None:                   # глухой дом — непроходим целиком
            for ty in range(y, y + h):
                for tx in range(x, x + w):
                    if 0 <= tx < self.w and 0 <= ty < self.h:
                        self.blocked.add((tx, ty))
        return wall

    # ------------------------------------------------------- интерьеры (уровни)
    def add_interior(self, key, W, H, walls_tiles, floor_type=G_CONCRETE,
                     spawn_tx=0, spawn_ty=0, exit_tx=None, exit_ty=None,
                     items=None, npcs=None, label="ПОДЪЕЗД"):
        """Отдельный «уровень» внутри здания: своя мини-сетка коллизий.

        walls_tiles — множество (tx,ty) непроходимых клеток;
        exit_*      — клетка двери (по умолчанию — середина южной стены).
        Возвращает dict уровня.
        """
        lvl = {
            "key": key, "label": label, "w": W, "h": H,
            "blocked": set(walls_tiles), "floor": floor_type,
            "spawn": (spawn_tx * TILE + TILE // 2, spawn_ty * TILE + TILE // 2),
            "exit": ((exit_tx if exit_tx is not None else W // 2) * TILE + TILE // 2,
                     ((H - 1) if exit_ty is None else exit_ty) * TILE + TILE // 2),
            "items": [], "npcs": [],
            "props": [],
        }
        for it in (items or []):
            lvl["items"].append({"name": it[0], "label": it[1],
                                 "x": it[2] * TILE + TILE // 2,
                                 "y": it[3] * TILE + TILE // 2, "taken": False})
        for n in (npcs or []):
            ax, ay = n[0] * TILE + TILE // 2, n[1] * TILE + TILE // 2
            bx, by = n[2] * TILE + TILE // 2, n[3] * TILE + TILE // 2
            lvl["npcs"].append({
                "x": ax, "y": ay, "a": (ax, ay), "b": (bx, by),
                "r": 11, "jacket": n[4] if len(n) > 4 else (88, 84, 80),
                "speed": self.rnd.uniform(30, 55), "phase": self.rnd.random(),
                "dir": 1, "facing": 0.0, "walk_t": self.rnd.uniform(0, 6.28),
            })
        self.interiors[key] = lvl
        return lvl

    def add_building_interior(self, wall, W=None, H=None, floor_type=G_CONCRETE,
                              label="ПОДЪЕЗД", rooms=None, corridors=None,
                              items=None, npcs=None, props=None, shop_cells=None,
                              door_side="south"):
        """Интерьер, повторяющий план дома-прямоугольника (wall из add_wall_block).

        Стены дома становятся стенами уровня; внутри — дворовая/парадная
        планировка: перегородки (rooms), магазины на 1-м этаже (shop_cells),
        предметы и NPC. Дверь — с выбранной стороны фасада.
        Возвращает dict уровня (ключ "key" = id интерьера).
        """
        key = f"bld_{wall['x']}_{wall['y']}"
        W = W or wall["w"]
        H = H or wall["h"]
        s = set()
        for x in range(W):                      # периметр = наружные стены
            s.add((x, 0)); s.add((x, H - 1))
        for y in range(H):
            s.add((0, y)); s.add((W - 1, y))
        for r in (rooms or []):                 # внутренние перегородки
            rx, ry, rw, rh = r
            for x in range(rx, min(W, rx + rw)):
                for y in range(ry, min(H, ry + rh)):
                    s.add((x, y))
        # двери комнат — вырезаем проёмы рядом с каждой комнатой
        for p in getattr(self, "_room_doors", []):
            pass
        dx, dy = None, None
        if door_side == "south":
            dx, dy = W // 2, H - 1
        elif door_side == "north":
            dx, dy = W // 2, 0
        elif door_side == "west":
            dx, dy = 0, H // 2
        else:
            dx, dy = W - 1, H // 2
        s.discard((dx, dy))
        if door_side in ("south", "north"):
            s.discard((dx - 1, dy)); s.discard((dx + 1, dy))
        else:
            s.discard((dx, dy - 1)); s.discard((dx, dy + 1))
        exit_px = (dx * TILE + TILE // 2, dy * TILE + TILE // 2)
        spawn = ((W // 2) * TILE + TILE // 2, max(1, H - 2) * TILE + TILE // 2)
        lvl = {"key": key, "label": label, "w": W, "h": H, "blocked": s,
               "floor": floor_type, "spawn": spawn, "exit": exit_px,
               "items": [], "npcs": [], "props": [],
               "wall": (wall["x"], wall["y"], W, H),
               "facade": wall.get("color", (110, 104, 98)),
               "floors_n": wall.get("floors", 5),
               "shops": list(shop_cells or []), "kind": "building"}
        for it in (items or []):
            lvl["items"].append({"name": it[0], "label": it[1],
                                 "x": it[2] * TILE + TILE // 2,
                                 "y": it[3] * TILE + TILE // 2, "taken": False})
        for n in (npcs or []):
            ax, ay = n[0] * TILE + TILE // 2, n[1] * TILE + TILE // 2
            bx, by = n[2] * TILE + TILE // 2, n[3] * TILE + TILE // 2
            lvl["npcs"].append({
                "x": ax, "y": ay, "a": (ax, ay), "b": (bx, by),
                "r": 11, "jacket": n[4] if len(n) > 4 else (88, 84, 80),
                "speed": self.rnd.uniform(28, 52), "phase": self.rnd.random(),
                "dir": 1, "facing": 0.0, "walk_t": self.rnd.uniform(0, 6.28)})
        for pr in (props or []):
            d = {"t": pr[0], "x": pr[1] * TILE + TILE // 2,
                 "y": pr[2] * TILE + TILE // 2, "solid": True,
                 "r": pr[3] if len(pr) > 3 else 12}
            lvl["props"].append(d)
        self.interiors[key] = lvl
        wall["interior"] = key
        return lvl

    def build_doors(self):
        """После построения района: проходимые арки/подъезды в домах с
        интерьерами + разблокировка клетки двери."""
        for w in self.walls:
            it = w.get("interior")
            if not it:
                continue
            lvl = self.interiors[it]
            ex, ey = lvl["exit"]
            tx, ty = int(ex // TILE), int(ey // TILE)
            # дверь — на южном фасаде дома (или заданная клетка)
            self.blocked.discard((tx, ty))
            self.blocked.discard((tx, ty - 1))
            self.doors.append({"x": ex, "y": ey, "r": TILE * 0.75,
                               "level": it, "label": lvl["label"]})
            # плоская деталь: крыльцо/арка видна на карте
            self.flat.append({"t": "porch", "x": tx, "y": ty,
                              "seed": self.rnd.randrange(99)})

    def add_door(self, wx, wy, level_key, label=None, side="south"):
        """Дверь дома (bx,by — левый верхний тайл корпуса) в интерьер level_key.

        Клетка фасада разблокируется; рядом рисуются гранитные ступени.
        """
        wall = None
        for w in self.walls:
            if w["x"] == wx and w["y"] == wy:
                wall = w
                break
        if wall is None or level_key not in self.interiors:
            return None
        wall["interior"] = level_key
        if side == "south":
            tx, ty = wall["x"] + wall["w"] // 2, wall["y"] + wall["h"] - 1
            px, py = tx * TILE + TILE // 2, ty * TILE + TILE - 6
        elif side == "north":
            tx, ty = wall["x"] + wall["w"] // 2, wall["y"]
            px, py = tx * TILE + TILE // 2, ty * TILE + 6
        else:  # западная/восточная стена
            ty_ = wall["y"] + wall["h"] // 2
            if side == "west":
                tx, ty = wall["x"], ty_
                px, py = tx * TILE + 6, ty * TILE + TILE // 2
            else:
                tx, ty = wall["x"] + wall["w"] - 1, ty_
                px, py = tx * TILE + TILE - 6, ty * TILE + TILE // 2
        self.blocked.discard((tx, ty))
        d = {"x": px, "y": py, "r": TILE * 0.8, "level": level_key,
             "label": label or self.interiors[level_key]["label"]}
        self.doors.append(d)
        self.flat.append({"t": "steps", "x": tx, "y": ty,
                          "seed": self.rnd.randrange(99)})
        return d

    def level_at_px(self, px, py):
        """Рядом с дверью? Возвращает dict двери или None."""
        best, bd = None, 1e9
        for d in self.doors:
            dist = math.hypot(d["x"] - px, d["y"] - py)
            if dist < d["r"] and dist < bd:
                best, bd = d, dist
        return best

    def add_prop(self, kind, px, py, solid=True, radius=10, **kw):
        p = {"t": kind, "x": px, "y": py, "solid": solid, "r": radius}
        p.update(kw)
        self.props.append(p)
        if solid:
            tx, ty = int(px // TILE), int(py // TILE)
            self.blocked.add((tx, ty))
        return p

    def add_car(self, px, py, color=None, angle=0, kind=None, seed=None,
                solid=True, parked=False, model=None):
        """Автомобиль: исторический автопарк 1997 (ВАЗ-2101, ВАЗ-2109, BMW E34)
        плюс «фон» из фургонов/автобусов/грузовиков того времени."""
        rnd = self.rnd
        from cars import CAR_MODELS, random_color as rnd_color
        hist_models = ("vaz2101", "vaz2109", "bmwe34")
        if kind in (None, "sedan"):
            k = rnd.choice(hist_models)
        else:
            k = kind
        if model:
            k = model
        c = color or (rnd_color(k, rnd) if k in CAR_MODELS
                      else rnd.choice([(150, 140, 120), (120, 130, 150),
                                       (176, 158, 60), (90, 96, 110)]))
        p = self.add_prop("car", px, py, solid=solid, radius=13,
                          color=c, angle=angle, kind=k,
                          seed=seed if seed is not None else rnd.randrange(999),
                          parked=parked)
        return p

    def car_spot_free(self, px, py):
        """Свободно ли место под машину (не стена/вода/другая машина)."""
        tx, ty = int(px // TILE), int(py // TILE)
        if self.is_solid_tile(tx, ty):
            return False
        for p in self.props:
            if p["t"] == "car" and abs(p["x"] - px) < 40 and abs(p["y"] - py) < 40:
                return False
        return True

    def _historic_parking(self):
        """Автопарк тех лет вдоль проспектов и во дворах: копейки, девятки, E34.

        Улицы «живые»: у края полосы стоят машины, между ними — редкие
        прохожие; в дворах — «иномарки» у подъездов и «жигули» у гаражей.
        """
        rnd = self.rnd
        rows = [12, 14, 30, 32, 44, 46]          # ряды припаркованных полос
        for row in rows:
            tx = 3
            while tx < self.w - 3:
                step = rnd.choice((3, 3, 4))
                if rnd.random() < 0.72:
                    px = tx * TILE + TILE // 2
                    py = row * TILE + TILE // 2
                    if self.car_spot_free(px, py):
                        ang = 0 if rnd.random() < 0.8 else 180
                        self.add_car(px, py, angle=ang, parked=True)
                tx += step
        # дворы: у подъездов — «девятки» и пару «бэшек» на квартал
        yard_spots = [(7, 24), (12, 25), (17, 24), (31, 24), (36, 25),
                      (63, 24), (68, 25), (73, 24), (7, 40), (12, 41),
                      (63, 40), (68, 41), (85, 42), (31, 40), (36, 41)]
        for i, (tx, ty) in enumerate(yard_spots):
            px, py = tx * TILE + TILE // 2, ty * TILE + TILE // 2
            if not self.car_spot_free(px, py):
                continue
            model = rnd.choice(("vaz2101", "vaz2101", "vaz2109",
                                "vaz2109", "vaz2109", "bmwe34"))
            self.add_car(px, py, angle=rnd.choice((90, 270)),
                         parked=True, model=model)
        # «блатные» E34 у рынка и у лучшего подъезда
        for (tx, ty) in [(57, 15), (76, 33), (24, 47)]:
            px, py = tx * TILE + TILE // 2, ty * TILE + TILE // 2
            if self.car_spot_free(px, py):
                self.add_car(px, py, angle=0, parked=True, model="bmwe34")

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
            # периметр — стены (каждый корпус получает свой стиль кровли)
            for (wx, wy, ww, wh) in ((bx, by, bw, thick),
                                     (bx, by + bh - thick, bw, thick),
                                     (bx, by + thick, thick, bh - 2 * thick),
                                     (bx + bw - thick, by + thick, thick, bh - 2 * thick)):
                w = self.add_wall_block(wx, wy, ww, wh, col, rnd.randint(4, 7))
                if w is None:
                    continue
                # продольные корпуса — двускатная жесть, поперечные — вальма/мансарда
                if ww >= wh:
                    w["style"] = rnd.choice(("gable", "gable", "mansard"))
                else:
                    w["style"] = rnd.choice(("hip", "flat", "monitor"))
                # угловые башенки-эркеры у «парадных» длинных корпусов
                w["tower"] = (ww >= 14 and rnd.random() < 0.5)
            # арки-проходы во двор (плюс плоская деталь «арочный свод»)
            for side in rnd.sample(["left", "right", "top"], 2):
                if side == "left":
                    gy = by + bh // 2
                    self.blocked.discard((bx, gy))
                    self.flat.append({"t": "arch", "x": bx, "y": gy, "rot": 0,
                                      "seed": rnd.randrange(99)})
                elif side == "right":
                    gy = by + bh // 2
                    self.blocked.discard((bx + bw - 1, gy))
                    self.flat.append({"t": "arch", "x": bx + bw - 1, "y": gy,
                                      "rot": 0, "seed": rnd.randrange(99)})
                else:
                    gx = bx + bw // 2
                    self.blocked.discard((gx, by))
                    self.flat.append({"t": "arch", "x": gx, "y": by, "rot": 90,
                                      "seed": rnd.randrange(99)})
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
            w = self.add_wall_block(mx + 3 + i * 4, my + 3, 3, 2, (150, 60, 50), 1)
            if w is not None:
                w["style"] = "glass"          # стеклянные навесы рядов
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
        """Машины (в т.ч. ездящие), фонари, лавки, урны, киоски, гаражи, деревья."""
        rnd = self.rng = self.rnd
        car_colors = [(90, 96, 110), (120, 60, 52), (70, 84, 70), (110, 108, 96),
                      (60, 62, 66), (130, 110, 70), (86, 70, 100), (140, 132, 110)]
        kinds = ("sedan", "sedan", "van", "bus", "truck")

        def car_row(row, tx_from, tx_to, step=4, p=0.55, moving=False):
            for tx in range(tx_from, tx_to, step):
                if self.ground[row + 1][tx] != G_ASPHALT or rnd.random() > p:
                    continue
                px = tx * TILE + TILE // 2
                py = (row + 1) * TILE + TILE // 2
                kw = dict(color=rnd.choice(car_colors), angle=0,
                          kind=rnd.choice(kinds), seed=rnd.randrange(999))
                if moving:
                    self.movers.append({
                        "t": "car", "x": px, "y": py, "r": 13, "solid": False,
                        "dir": 1 if rnd.random() < 0.5 else -1,
                        "speed": rnd.uniform(55, 120), "horn_t": rnd.uniform(2, 14),
                        "ax": tx_from * TILE, "bx": tx_to * TILE, **kw})
                else:
                    self.add_car(px, py, color=kw["color"], angle=kw["angle"],
                                 kind=kw["kind"], seed=kw["seed"], parked=True)

        # припаркованные вдоль широкой улицы rows 12/30/44
        for row in (12, 30, 44):
            car_row(row, 2, self.w - 2, p=0.5)
        # «оживлённый» проспект — машины едут туда-сюда по рядам 13 и 31
        car_row(13, 2, self.w - 2, step=9, p=0.9, moving=True)
        car_row(31, 2, self.w - 2, step=11, p=0.85, moving=True)
        # маршрутка по кольцу проспекта 47/48
        self.movers.append({"t": "car", "kind": "bus", "color": (176, 158, 60),
                            "x": 10 * TILE, "y": 47 * TILE + TILE // 2, "r": 13,
                            "solid": False, "dir": 1, "speed": 70.0,
                            "horn_t": 6.0, "ax": 3 * TILE, "bx": (self.w - 3) * TILE,
                            "angle": 0, "seed": 42})
        # троллейбус вдоль набережной
        self.movers.append({"t": "car", "kind": "bus", "color": (120, 130, 150),
                            "x": 60 * TILE, "y": 53 * TILE + TILE // 2, "r": 13,
                            "solid": False, "dir": -1, "speed": 55.0,
                            "horn_t": 9.0, "ax": 4 * TILE, "bx": (self.w - 4) * TILE,
                            "angle": 0, "seed": 43})
        # выезд со двора: фургон петляет по внутриквартальному проезду
        self.movers.append({"t": "car", "kind": "van", "color": (150, 140, 120),
                            "x": 30 * TILE, "y": 27 * TILE, "r": 13, "solid": False,
                            "dir": 1, "speed": 42.0, "horn_t": 20.0,
                            "ax": 26 * TILE, "bx": 44 * TILE, "ay": 27 * TILE,
                            "by": 27 * TILE, "angle": 0, "seed": 44})
        # припаркованные у дворов
        for (bx, by, bw, bh) in [(4, 18, 18, 10), (60, 2, 18, 9), (4, 48, 18, 8)]:
            for i in range(3):
                px = (bx + 3 + i * 3) * TILE
                py = (by + bh - 2) * TILE
                if not self.is_solid_tile(int(px // TILE), int(py // TILE)):
                    self.add_prop("car", px, py, solid=True, radius=13,
                                  color=rnd.choice(car_colors), angle=90,
                                  kind=rnd.choice(("sedan", "van")),
                                  seed=rnd.randrange(999))
        # фонари на тротуарах
        for row in (10, 36, 50):
            for tx in range(3, self.w, 8):
                self.add_prop("lamp", tx * TILE + TILE // 2, row * TILE,
                              solid=True, radius=7)
        # киоски и гаражи у рынка / угла кварталов
        for (px, py) in [(58, 20), (75, 20), (26, 14), (56, 46), (80, 32)]:
            self.add_prop("kiosk", px * TILE, py * TILE, solid=True, radius=16,
                          seed=rnd.randrange(99))
        for i in range(4):
            px = (84 + (i % 2) * 3) * TILE
            py = (44 + (i // 2) * 2) * TILE
            if not self.is_solid_tile(int(px // TILE), int(py // TILE)):
                self.add_prop("garage", px, py, solid=True, radius=15,
                              seed=rnd.randrange(99))
        # скамейки + урны в сквере и дворах
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
        # теплотрасса: точки, из которых валит пар (vent'ы)
        for cx in range(4, 22, 3):
            self.vents.append((cx * TILE + TILE // 2, 26 * TILE))
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
        # лужи и мусор на асфальте; координаты луж — для ряби дождя
        for _ in range(120):
            tx, ty = rnd.randrange(self.w), rnd.randrange(self.water_y or self.h)
            if self.ground[ty][tx] in (G_ASPHALT, G_BRICK, G_YARD) \
                    and (tx, ty) not in self.blocked:
                t = rnd.choice(["puddle", "stain", "leaf"])
                self.flat.append({"t": t, "x": tx, "y": ty, "seed": rnd.randrange(999)})
                if t == "puddle":
                    self.puddles.append((tx * TILE + TILE // 2,
                                         ty * TILE + TILE // 2))

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
                "dir": 1, "facing": 0.0, "walk_t": rnd.uniform(0, 6.28),
            })

    # ------------------------------------------------------- доступ к данным
    def finalize(self):
        """Спавн игрока в гарантированно проходимой клетке."""
        from player import find_walkable
        sx, sy = self.spawn
        self.spawn = find_walkable(self, sx, sy, r=PLAYER_RADIUS)
        return self

    def ground_at_px(self, px, py):
        lvl = self.active_grid()
        if lvl is not None:
            return lvl["floor"]
        tx, ty = int(px // TILE), int(py // TILE)
        tx = max(0, min(self.w - 1, tx))
        ty = max(0, min(self.h - 1, ty))
        return self.ground[ty][tx]

    def surface_sound(self, px, py):
        lvl = self.active_grid()
        if lvl is not None:
            return INTERIOR_SOUND.get(lvl["floor"], "concrete")
        return SURFACE_SOUND.get(self.ground_at_px(px, py), "asphalt")

    def circle_blocked(self, px, py, r):
        """Пересекает ли круг непроходимую область (стены/вода/пропы).

        Если активен интерьер здания — коллизии идут по его мини-сетке.
        """
        lvl = self.active_grid()
        if lvl is not None:
            if self.circle_blocked_level(lvl, px, py, r):
                return True
            for p in lvl["props"]:
                if not p.get("solid"):
                    continue
                dx, dy = p["x"] - px, p["y"] - py
                rr = r + p.get("r", 10)
                if dx * dx + dy * dy < rr * rr:
                    return True
            return False
        # точная проверка: растеризуем круг по клеткам сетки
        x0 = int((px - r) // TILE); x1 = int((px + r) // TILE)
        y0 = int((py - r) // TILE); y1 = int((py + r) // TILE)
        for ty in range(y0, y1 + 1):
            for tx in range(x0, x1 + 1):
                if self.is_solid_tile(tx, ty):
                    cx = max(tx * TILE, min(px, tx * TILE + TILE))
                    cy = max(ty * TILE, min(py, ty * TILE + TILE))
                    if (cx - px) ** 2 + (cy - py) ** 2 < r * r:
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

    # -------------------------------------------------- анимация транспорта
    def update_movers(self, dt, player_pos=None):
        """Ездящие машины туда-сюда по участкам. Возвращает список событий
        ('horn', x, y) — когда машина сигналит рядом с игроком."""
        events = []
        for m in self.movers:
            m["wheel"] = (m.get("wheel", 0.0) + dt * m["speed"] * 0.05) % 4
            m["dir_t"] = m.get("dir_t", 0.0) + dt
            ax, bx = m["ax"], m["bx"]
            ay = m.get("ay", m["y"])
            by = m.get("by", m["y"])
            horiz = abs(bx - ax) >= abs(by - ay)
            if horiz:
                m["x"] += m["dir"] * m["speed"] * dt
                m["y"] = ay if m["dir"] > 0 else by
                m["angle"] = 0 if m["dir"] > 0 else 180
                if m["x"] > bx:
                    m["x"], m["dir"] = bx, -1
                elif m["x"] < ax:
                    m["x"], m["dir"] = ax, 1
            else:
                m["y"] += m["dir"] * m["speed"] * dt
                m["angle"] = 270 if m["dir"] > 0 else 90
                if m["y"] > by:
                    m["y"], m["dir"] = by, -1
                elif m["y"] < ay:
                    m["y"], m["dir"] = ay, 1
            # мигалка поворотника при «развороте» на краю участка
            near_edge = (m["x"] - ax < 60) or (bx - m["x"] < 60) if horiz \
                else (m["y"] - ay < 60) or (by - m["y"] < 60)
            m["blink"] = 1 if (near_edge and int(m["dir_t"] * 3) % 2 == 0) else 0
            # гудок рядом с игроком — не чаще раза в N секунд
            m["horn_t"] -= dt
            if m["horn_t"] <= 0:
                m["horn_t"] = random.uniform(9, 22)
                if player_pos:
                    d = math.hypot(m["x"] - player_pos[0], m["y"] - player_pos[1])
                    if d < 320:
                        events.append(("horn", m["x"], m["y"], max(0.15, 1 - d / 340)))
        return events


def build_district(seed=7):
    return District(seed=seed).build()
