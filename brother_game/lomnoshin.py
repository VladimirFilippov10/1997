# -*- coding: utf-8 -*-
"""Квартал улицы Ломоносова (бывший Чернышев переулок) — «Пять углов».

Историческая схема для карты вида сверху (осень 1997 года):

      ЗАГОРОДНЫЙ ПРОСПЕКТ (магистраль, маршрутки, поток)
      ────────────────────────────────────────────────────
        тротуар · ларьки · таксофон · Союзпечать
      [КОММЕРЧЕСКОЕ УЧИЛИЩЕ]   двор-котлован   сквер
      ════════ северный тротуар ═════════════════════════
        улица ЛОМОНОСОВА — двухполосная «стрела» без разметки
      ════════ южный тротуар: витрины, вывески ══════════
      [6/2 охристый][8 розовый][10-12 серый][14-16 песоч.]||[20 кирпич]
         дворы-колодцы с арками, котлованами, гаражами-ракушками
      [22][24]                ||проезд||  [26]  [28 жёлтый, башня]
      ──────────────────────── УЛИЦА РУБИНШТЕЙНА ──────────────────────

Чётная сторона (дома 6–28) задаёт «лицо» квартала: плотный ряд доходных
домов конца XIX — начала XX века разной этажности (4–5 этажей), скатные
железные крыши с трубами и слуховыми окнами, узкие дворы-колодцы за ними.
На углу с Рубинштейна — акцентный дом 28 (Гек и Вальтер, 1904–1905,
жёлтый керамический кирпич, вальмовая крыша, угловая башня); на углу с
Загородным — охристый дом 6/2 с магазинами «Овощи-Фрукты» и
«Товары для женщин».

Каждый дом чётной стороны имеет interior — проходимый план этажа
(парадная, коммунальные кухни, магазины), открывающийся по E у двери.

Реализация: District с ручной раскладкой вместо генератора.
"""
import random

from config import TILE
from district import (District, G_ASPHALT, G_BRICK, G_CONCRETE, G_GRASS,
                      G_YARD)

# ------------------------------------------------------------- палитра района
COL_OCHRE = (176, 148, 88)        # дом 6/2 — охристо-жёлтый, побелка местами
COL_PINK = (172, 148, 146)        # дом 8 — бледно-розовый
COL_GREY = (138, 138, 140)        # дома 10–12, 22 — светло-серый
COL_SAND = (178, 158, 122)        # дома 14–16, 24 — песочный
COL_YELLOW = (190, 162, 92)       # дом 28 — жёлтый керамический кирпич
COL_BRICKRED = (128, 72, 58)      # дом 20 — тёмно-красный кирпич
COL_URIAL = (150, 148, 142)       # Коммерческое училище — казённый серый


def build_lomonosov(seed=1997):
    d = LomonosovDistrict(seed=seed)
    d.build()
    return d


class LomonosovDistrict(District):
    """Ручной квартал Ломоносова: три улицы, чётная/нечётная стороны."""

    def __init__(self, w=96, h=72, seed=1997):
        super().__init__(w=w, h=h, seed=seed)
        self.signs = []           # вывески магазинов {text,x,y}
        self.stall_lights = []    # огоньки ларьков (ночью)
        self.rows = {"zagorodny": 6, "lom_n": 20, "lom_s": 28, "rubin": 44}

    # ================================================================ сборка
    def build(self):
        self._streets()
        self._odd_side()          # нечётная: училище, дворы-котлованы
        self._even_side()         # чётная: дома 6..28 + интерьеры
        self._shops_and_stalls()
        self._yards_details()
        self._cars()
        self._npcs_on_sidewalks()
        self._props_all()
        self.finalize()
        return self

    # ------------------------------------------------------------ улицы
    def _streets(self):
        rnd = self.rnd
        self.fill_ground(0, 0, self.w, self.h, G_ASPHALT)

        # Загородный проспект — широкая магистраль (rows 2..10)
        self.fill_ground(0, 2, self.w, 10, G_ASPHALT)
        self.fill_ground(0, 10, self.w, 12, G_BRICK)          # южный тротуар
        for tx in range(0, self.w, 2):
            self.flat.append({"t": "curb", "x": tx, "y": 9})
        for ty in (5, 6):
            for tx in range(1, self.w, 3):
                self.flat.append({"t": "mark", "x": tx, "y": ty})

        # улица Ломоносова — двухполосная стрела (rows 21..27)
        self.fill_ground(0, 21, self.w, 28, G_ASPHALT)
        self.fill_ground(0, 19, self.w, 21, G_BRICK)          # северный тротуар
        self.fill_ground(0, 28, self.w, 30, G_BRICK)          # южный тротуар
        for tx in range(self.w):
            self.flat.append({"t": "curb", "x": tx, "y": 20})
            self.flat.append({"t": "curb", "x": tx, "y": 28})
        for tx in range(2, self.w - 2, 4):                    # почти стёртая
            if rnd.random() < 0.5:
                self.flat.append({"t": "mark", "x": tx, "y": 24})

        # улица Рубинштейна (rows 41..46)
        self.fill_ground(0, 41, self.w, 47, G_ASPHALT)
        self.fill_ground(0, 39, self.w, 41, G_BRICK)
        self.fill_ground(0, 47, self.w, 49, G_BRICK)
        for tx in range(self.w):
            self.flat.append({"t": "curb", "x": tx, "y": 40})
            self.flat.append({"t": "curb", "x": tx, "y": 47})
        for tx in range(1, self.w, 3):
            self.flat.append({"t": "mark", "x": tx, "y": 44})

        # внутриквартальный проезд между домами 16 и 20 (переулок)
        px = 56
        self.fill_ground(px, 12, px + 3, 41, G_ASPHALT)
        self.fill_ground(px - 1, 12, px, 41, G_BRICK)
        self.fill_ground(px + 3, 12, px + 4, 41, G_BRICK)

        # зебры на перекрёстках
        for zx in (px + 1, 12, 78):
            self.flat.append({"t": "crosswalk", "x": zx, "y": 23})
        for zx in (px + 1, 30, 70):
            self.flat.append({"t": "crosswalk", "x": zx, "y": 43})

        # мокрый асфальт: заплатки, маслянистые пятна, лужи
        for _ in range(300):
            tx = rnd.randrange(self.w)
            ty = rnd.choice([rnd.randrange(21, 28), rnd.randrange(2, 10),
                             rnd.randrange(41, 47)])
            t = rnd.choice(["puddle", "stain", "stain", "patch", "leaf"])
            self.flat.append({"t": t, "x": tx, "y": ty,
                              "seed": rnd.randrange(999)})
            if t == "puddle":
                self.puddles.append((tx * TILE + TILE // 2, ty * TILE + TILE // 2))
        # лужи вдоль бордюров — радужные разводы бензина
        for tx in range(0, self.w, 2):
            for ty in (20, 27, 28, 9):
                if rnd.random() < 0.28:
                    self.flat.append({"t": "puddle", "x": tx, "y": ty,
                                      "seed": rnd.randrange(999)})
                    self.puddles.append((tx * TILE + TILE // 2, ty * TILE + TILE // 2))

    # ------------------------------------------------- нечётная сторона
    def _odd_side(self):
        """Коммерческое училище, сквер, дворы-котлованы (ремонт сетей)."""
        rnd = self.rnd
        # монументальный корпус Коммерческого училища
        uw = self.add_wall_block(4, 13, 24, 5, COL_URIAL, floors=4)
        uw["style"] = "mansard"
        uw["tower"] = True
        self.zones.append({"label": "КОММЕРЧЕСКОЕ УЧИЛИЩЕ",
                           "x": 16 * TILE, "y": 12 * TILE})
        # сквер перед училищем (ряды голых лип)
        self.fill_ground(4, 18, 28, 19, G_GRASS)
        for i in range(7):
            cx = (5 + i * 3.4) * TILE + TILE // 2
            self.over.append({"t": "tree", "x": cx, "y": 18 * TILE + TILE // 2,
                              "size": 58, "seed": 400 + i})
            self.add_prop("trunk", cx, 18 * TILE + TILE // 2,
                          solid=True, radius=8, seed=i)

        # двор-котлован №1 — ремонт теплотрассы (закрыт щитами)
        self._trench(range(6, 10), range(15, 18))
        # второй двор с флигелем и ещё одним котлованом
        fw = self.add_wall_block(32, 14, 12, 3, tuple(int(c * 0.88) for c in COL_GREY), 3)
        fw["style"] = "gable"
        self._trench(range(46, 51), range(15, 18))
        # трубы теплотрассы идут через дворы — пар над люками
        for tx in range(30, 55, 2):
            self.vents.append((tx * TILE + TILE // 2, 18 * TILE + TILE // 2))
        self.over.append({"t": "pipe", "x": 40 * TILE, "y": 18 * TILE,
                          "size": 24})

    def _trench(self, xs, ys):
        """Открытый котлован: траншея непроходима, вокруг — грунт двора."""
        for tx in xs:
            for ty in ys:
                self.ground[ty][tx] = G_YARD
                self.blocked.add((tx, ty))
                self.flat.append({"t": "trench", "x": tx, "y": ty,
                                  "seed": self.rnd.randrange(99)})

    # ---------------------------------------------------- чётная сторона
    def _even_side(self):
        """Дома 6..28: фасады, дворы-колодцы, interiors с планировкой."""
        rnd = self.rnd
        # фасадный ряд вдоль южной стороны Ломоносова: rows 29..32 (4 тайла)
        facades = [
            # x, ширина, цвет, этажи, крыша, имя дома
            (4, 12, COL_OCHRE, 5, "mansard", "ДОМ 6/2"),
            (17, 9, COL_PINK, 5, "gable", "ДОМ 8"),
            (27, 10, COL_GREY, 4, "gable", "ДОМ 10-12"),
            (38, 10, COL_SAND, 5, "hip", "ДОМ 14-16"),
            (49, 6, COL_SAND, 5, "gable", "ДОМ 16"),
            (60, 10, COL_BRICKRED, 4, "monitor", "ДОМ 20"),
            (71, 8, COL_GREY, 5, "gable", "ДОМ 22-24"),
            (80, 15, COL_YELLOW, 5, "hip", "ДОМ 28"),
        ]
        self.buildings = {}
        for (bx, bw, col, floors, style, name) in facades:
            wall = self.add_wall_block(bx, 29, bw, 4, col, floors)
            wall["style"] = style
            wall["facade"] = col
            wall["name"] = name
            # акцентная угловая башня — только у дома 28 (как в реальности)
            wall["tower"] = (name == "ДОМ 28")
            # задний дворовый корпус того же дома (двор-колодец)
            yd = self.add_wall_block(bx + 1, 35, max(3, bw - 2), 3,
                                     tuple(int(c * 0.9) for c in col), 3)
            yd["style"] = rnd.choice(("gable", "flat"))
            # бетон двора между корпусами
            self.fill_ground(bx, 33, bx + bw, 35, G_YARD)
            # арка во двор со стороны Ломоносова
            ax_ = bx + bw // 2
            self.blocked.discard((ax_, 33))
            self.blocked.discard((ax_, 32))
            self.flat.append({"t": "arch", "x": ax_, "y": 33, "rot": 90,
                              "seed": rnd.randrange(99)})
            self.buildings[name] = wall
        # угловой дом 6/2 «загибается» на Загородный проспект
        corner = self.add_wall_block(4, 24, 3, 5, COL_OCHRE, 5)
        corner["style"] = "mansard"
        # дом 28 Гекa и Вальтера — угол Рубинштейна, башня над карнизом
        tw = self.add_wall_block(90, 34, 5, 5, COL_YELLOW, 5)
        tw["style"] = "hip"
        tw["tower"] = True
        self.zones.append({"label": "ДОМ ГЕКА И ВАЛЬТЕРА · 1904",
                           "x": 87 * TILE, "y": 38 * TILE})
        self.zones.append({"label": "УЛИЦА ЛОМОНОСОВА", "x": 24 * TILE,
                           "y": 24 * TILE})
        self.zones.append({"label": "ЗАГОРОДНЫЙ ПРОСПЕКТ", "x": 66 * TILE,
                           "y": 5 * TILE})
        self.zones.append({"label": "УЛ. РУБИНШТЕЙНА · ПЯТЬ УГЛОВ",
                           "x": 40 * TILE, "y": 44 * TILE})
        self._make_interiors()

    # -------------------------------------------------- interiors домов
    def _make_interiors(self):
        """Планы этажей: парадные, коммуналки, магазины первого этажа."""
        B = self.buildings

        # --- ДОМ 6/2: парадная с лепниной + «Овощи-Фрукты» и «Товары для женщин»
        w6 = B["ДОМ 6/2"]
        lvl = self.add_building_interior(
            w6, floor_type="parquet", label="ПОДЪЕЗД · ДОМ 6",
            rooms=[(2, 1, 1, 3), (6, 1, 1, 4), (2, 4, 5, 1)],
            items=[("newspaper", "Газета", 4, 2), ("bread", "Батон", 8, 3)],
            npcs=[(3, 5, 9, 5, (96, 84, 70))],
            props=[("counter", 9, 2, 14), ("crate", 3, 3, 10)],
            door_side="south")
        lvl["shop"] = "ОВОЩИ-ФРУКТЫ"
        self.add_door(w6["x"], w6["y"], lvl["key"], side="south")

        # --- ДОМ 8: коммунальная квартира Данилы (кухня, коридор, комнаты)
        w8 = B["ДОМ 8"]
        lvl = self.add_building_interior(
            w8, floor_type="wood", label="КВАРТИРА · ДОМ 8",
            rooms=[(2, 2, 1, 3), (5, 1, 1, 4)],
            items=[("ttt", "ТТТ", 6, 3), ("vodka", "Поллитра", 2, 4),
                   ("bag", "Сумка", 7, 2)],
            npcs=[(6, 4, 6, 2, (88, 60, 60))],
            props=[("table", 3, 4, 12), ("stove", 1, 2, 10)],
            door_side="south")
        self.add_door(w8["x"], w8["y"], lvl["key"], side="south")

        # --- ДОМ 10-12: подъезд с почтовыми ящиками и табличками комнат
        w10 = B["ДОМ 10-12"]
        lvl = self.add_building_interior(
            w10, floor_type="tile", label="ПОДЪЕЗД · ДОМ 10",
            rooms=[(3, 1, 1, 3), (7, 2, 1, 2)],
            items=[("cigarettes", "Прима", 5, 3)],
            npcs=[(2, 4, 8, 4, (60, 70, 64))],
            props=[("mailbox", 4, 1, 9)],
            door_side="south")
        self.add_door(w10["x"], w10["y"], lvl["key"], side="south")

        # --- ДОМ 14-16: комиссионный магазин (хрусталь, видеомагнитофоны)
        w14 = B["ДОМ 14-16"]
        lvl = self.add_building_interior(
            w14, floor_type="linoleum", label="КОМИССИОННЫЙ",
            rooms=[(2, 3, 6, 1), (9, 1, 1, 4)],
            items=[("money", "Деньги", 4, 4), ("key", "Ключи", 8, 2),
                   ("newspaper", "Газета", 2, 2)],
            npcs=[(3, 2, 7, 2, (52, 56, 66)), (10, 4, 4, 4, (110, 108, 100))],
            props=[("counter", 5, 3, 14), ("shelf", 10, 2, 12),
                   ("shelf", 10, 4, 12)],
            shop_cells=[{"x": 2, "y": 1, "w": 8, "h": 4, "label": "КОМИССИОНКА"}],
            door_side="south")
        self.add_door(w14["x"], w14["y"], lvl["key"], side="south")

        # --- ДОМ 20: хозяйственный магазин + подъезд
        w20 = B["ДОМ 20"]
        lvl = self.add_building_interior(
            w20, floor_type="concrete", label="ХОЗТОВАРЫ · ДОМ 20",
            rooms=[(4, 1, 1, 3), (2, 3, 5, 1)],
            items=[("bag", "Сумка", 3, 2), ("money", "Деньги", 6, 4)],
            npcs=[(2, 2, 6, 2, (84, 72, 96))],
            props=[("counter", 3, 3, 14)],
            door_side="south")
        self.add_door(w20["x"], w20["y"], lvl["key"], side="south")

        # --- ДОМ 22-24: подъезд (обычный, тёмный, с керосиновой lampой)
        w22 = B["ДОМ 22-24"]
        lvl = self.add_building_interior(
            w22, floor_type="parquet", label="ПОДЪЕЗД · ДОМ 22",
            rooms=[(2, 2, 1, 2)],
            items=[("bread", "Батон", 4, 3)],
            npcs=[(5, 4, 2, 4, (66, 78, 72))],
            door_side="south")
        self.add_door(w22["x"], w22["y"], lvl["key"], side="south")

        # --- ДОМ 28: продмаг с импортными шоколадками (Snickers, Mars)
        w28 = B["ДОМ 28"]
        lvl = self.add_building_interior(
            w28, floor_type="tile", label="ПРОДМАГ · ДОМ 28",
            rooms=[(3, 2, 8, 1), (3, 5, 8, 1), (13, 1, 1, 3)],
            items=[("bread", "Батон", 5, 3), ("vodka", "Поллитра", 9, 3),
                   ("cigarettes", "Прима", 7, 6)],
            npcs=[(14, 4, 4, 4, (96, 84, 70))],
            props=[("fridge", 12, 2, 12), ("counter", 8, 4, 14),
                   ("shelf", 4, 2, 10), ("shelf", 4, 5, 10)],
            shop_cells=[{"x": 2, "y": 1, "w": 11, "h": 5, "label": "ПРОДУКТЫ"}],
            door_side="south")
        lvl["shop"] = "ПРОДМАГ"
        self.add_door(w28["x"], w28["y"], lvl["key"], side="south")

    # ------------------------------------------- магазины и уличная торговля
    def _shops_and_stalls(self):
        rnd = self.rnd
        # козырьки витрин над южным тротуаром (слой over — проходят сквозь)
        awnings = [(5, 11), (17, 8), (27, 9), (60, 9), (80, 13)]
        for (ax, aw) in awnings:
            for tx in range(ax, min(self.w, ax + aw)):
                self.over.append({"t": "awning", "x": tx * TILE + TILE // 2,
                                  "y": 29 * TILE - TILE // 2, "size": aw,
                                  "seed": rnd.randrange(99)})
        # металлические ларьки у угла Загородного: сигареты, пиво, газеты
        for (tx, ty) in [(14, 11), (16, 11), (18, 11), (72, 11), (74, 11)]:
            self.add_prop("stall", tx * TILE + TILE // 2, ty * TILE + TILE // 2,
                          solid=True, radius=15, seed=rnd.randrange(99),
                          kind=rnd.choice(("metal", "metal", "kiosk90")))
            self.stall_lights.append((tx * TILE + TILE // 2,
                                      ty * TILE + TILE // 2))
        # вывески на фасадах (рисуются поверх статичной карты)
        self.signs = [
            {"text": "ОВОЩИ-ФРУКТЫ", "x": 8 * TILE, "y": 28 * TILE},
            {"text": "ТОВАРЫ ДЛЯ ЖЕНЩИН", "x": 14 * TILE, "y": 28 * TILE},
            {"text": "ПРОДУКТЫ", "x": 31 * TILE, "y": 28 * TILE},
            {"text": "ОБУВЬ", "x": 42 * TILE, "y": 28 * TILE},
            {"text": "ХОЗТОВАРЫ", "x": 63 * TILE, "y": 28 * TILE},
            {"text": "КОМИССИОННЫЙ", "x": 67 * TILE, "y": 28 * TILE},
            {"text": "АПТЕКА", "x": 74 * TILE, "y": 28 * TILE},
            {"text": "ПРОДМАГ", "x": 85 * TILE, "y": 28 * TILE},
            {"text": "СОЮЗПЕЧАТЬ", "x": 46 * TILE, "y": 11 * TILE},
        ]

    # ------------------------------------------------------- детали дворов
    def _yards_details(self):
        rnd = self.rnd
        # зелёные metal-контейнеры у арок
        for (tx, ty) in [(8, 34), (21, 34), (31, 34), (43, 34), (64, 34),
                         (76, 34), (84, 34), (12, 17), (48, 18)]:
            if not self.is_solid_tile(tx, ty):
                self.add_prop("bin", tx * TILE + TILE // 2, ty * TILE + TILE // 2,
                              solid=True, radius=9, seed=rnd.randrange(99))
        # бельевые верёвки во дворах
        for (tx, ty) in [(10, 34), (30, 34), (66, 34), (86, 34), (36, 18)]:
            if not self.is_solid_tile(tx, ty):
                self.add_prop("clothesline", tx * TILE, ty * TILE,
                              solid=False, radius=6, seed=rnd.randrange(99))
        # гаражи-ракушки вдоль дворов (ранний капитализм)
        for (tx, ty) in [(34, 34), (36, 34), (38, 34), (70, 34), (72, 34)]:
            if not self.is_solid_tile(tx, ty):
                self.add_prop("garage", tx * TILE + TILE // 2,
                              ty * TILE + TILE // 2, solid=True, radius=13,
                              seed=rnd.randrange(99))
        # чугунные решётки подвальных окон вдоль фасадов
        for tx in list(range(4, 55)) + list(range(60, 95)):
            if self.ground[28][tx] == G_BRICK and rnd.random() < 0.22:
                self.flat.append({"t": "grate", "x": tx, "y": 28,
                                  "seed": rnd.randrange(99)})
        # гранитные ступени парадных
        for (tx, ty) in [(10, 33), (21, 33), (32, 33), (43, 33), (65, 33),
                         (75, 33), (87, 33)]:
            self.flat.append({"t": "steps", "x": tx, "y": ty,
                              "seed": rnd.randrange(99)})
        # голые деревья во дворах (листва уже опала)
        bare = [(6, 17), (14, 16), (35, 17), (44, 16), (9, 34), (24, 34),
                (45, 34), (78, 34), (88, 34), (52, 36), (68, 18)]
        for (tx, ty) in bare:
            if not self.is_solid_tile(tx, ty):
                self.add_prop("bare_tree", tx * TILE + TILE // 2,
                              ty * TILE + TILE // 2, solid=True, radius=8,
                              seed=rnd.randrange(99))
        # мокрый бурый слой листвы на тротуарах
        for tx in range(self.w):
            if rnd.random() < 0.35:
                self.flat.append({"t": "leaf", "x": tx, "y": 19,
                                  "seed": rnd.randrange(999)})
            if rnd.random() < 0.35:
                self.flat.append({"t": "leaf", "x": tx, "y": 28,
                                  "seed": rnd.randrange(999)})

    # --------------------------------------------------------- автопарк
    def _cars(self):
        rnd = self.rnd
        hist = ("vaz2101", "vaz2101", "vaz2109", "vaz2109", "bmwe34")
        # припаркованные вдоль северного края Ломоносова
        tx = 4
        while tx < self.w - 3:
            if rnd.random() < 0.72:
                px, py = tx * TILE + TILE // 2, 21 * TILE + TILE // 2
                if self.car_spot_free(px, py):
                    self.add_car(px, py, angle=0 if rnd.random() < 0.7 else 180,
                                 parked=True, model=rnd.choice(hist))
            tx += rnd.choice((3, 3, 4))
        # южная сторона — местами, с просветами у витрин
        tx = 6
        while tx < self.w - 3:
            if rnd.random() < 0.5:
                px, py = tx * TILE + TILE // 2, 27 * TILE + TILE // 2
                if self.car_spot_free(px, py):
                    self.add_car(px, py, angle=180 if rnd.random() < 0.6 else 0,
                                 parked=True, model=rnd.choice(hist))
            tx += rnd.choice((4, 5))
        # «блатные» E34 у комиссионки и у дома 28
        for (tx, ty) in [(68, 27), (83, 27), (75, 43)]:
            px, py = tx * TILE + TILE // 2, ty * TILE + TILE // 2
            if self.car_spot_free(px, py):
                self.add_car(px, py, angle=0, parked=True, model="bmwe34")
        # дворы: копейки/девятки у флигелей
        for (tx, ty, ang) in [(30, 34, 90), (41, 34, 90), (14, 34, 90),
                              (52, 34, 90), (82, 34, 90), (10, 15, 0)]:
            px, py = tx * TILE + TILE // 2, ty * TILE + TILE // 2
            if self.car_spot_free(px, py):
                self.add_car(px, py, angle=ang, parked=True,
                             model=rnd.choice(("vaz2101", "vaz2109")))
        # поток по Ломоносова: копейка, девятка, E34
        self.movers.append({"t": "car", "kind": "vaz2101", "color": (74, 96, 128),
                            "x": 10 * TILE, "y": 23 * TILE + TILE // 2, "r": 13,
                            "solid": False, "dir": 1, "speed": 88.0,
                            "horn_t": 5.0, "ax": 3 * TILE,
                            "bx": (self.w - 3) * TILE, "angle": 0, "seed": 11,
                            "model": "vaz2101"})
        self.movers.append({"t": "car", "kind": "vaz2109", "color": (92, 94, 96),
                            "x": 60 * TILE, "y": 25 * TILE + TILE // 2, "r": 13,
                            "solid": False, "dir": -1, "speed": 96.0,
                            "horn_t": 8.0, "ax": 3 * TILE,
                            "bx": (self.w - 3) * TILE, "angle": 180, "seed": 12,
                            "model": "vaz2109"})
        self.movers.append({"t": "car", "kind": "bmwe34", "color": (44, 62, 96),
                            "x": 30 * TILE, "y": 23 * TILE + TILE // 2, "r": 13,
                            "solid": False, "dir": 1, "speed": 118.0,
                            "horn_t": 12.0, "ax": 3 * TILE,
                            "bx": (self.w - 3) * TILE, "angle": 0, "seed": 13,
                            "model": "bmwe34"})
        # маршрутка К-27 по Загородному проспекту
        self.movers.append({"t": "car", "kind": "bus", "color": (176, 158, 60),
                            "x": 20 * TILE, "y": 6 * TILE + TILE // 2, "r": 13,
                            "solid": False, "dir": 1, "speed": 72.0,
                            "horn_t": 6.0, "ax": 3 * TILE,
                            "bx": (self.w - 3) * TILE, "angle": 0, "seed": 14})
        # грузовик ГАЗон с брезентовым тентом — разгрузка у Овощей
        self.add_car(11 * TILE + TILE // 2, 15 * TILE + TILE // 2, angle=90,
                     kind="truck", color=(70, 84, 70), parked=True)
        # «скорая» у Рубинштейна
        self.add_car(50 * TILE + TILE // 2, 43 * TILE + TILE // 2, angle=0,
                     kind="van", color=(196, 194, 184), parked=True)

    # --------------------------------------------------- прохожие на тротуарах
    def _npcs_on_sidewalks(self):
        rnd = self.rnd
        jackets = [(70, 74, 84), (96, 84, 70), (60, 70, 64), (88, 60, 60),
                   (110, 108, 100), (52, 56, 66), (84, 72, 96), (66, 78, 72)]
        paths = [
            ((4, 20), (54, 20)), ((60, 20), (94, 20)),      # северный тротуар
            ((6, 28), (54, 28)), ((62, 28), (92, 28)),      # южный тротуар
            ((8, 11), (40, 11)), ((52, 11), (88, 11)),      # Загородный
            ((10, 40), (48, 40)), ((60, 47), (90, 47)),     # Рубинштейна
            ((57, 14), (57, 39)),                            # переулком
            ((10, 34), (24, 34)), ((64, 34), (86, 34)),     # дворы
        ]
        for i, (a, b) in enumerate(paths):
            n = 1 if i < 6 else rnd.randint(1, 2)
            for k in range(n):
                ax, ay = a[0] * TILE + TILE // 2, a[1] * TILE + TILE // 2
                bx, by = b[0] * TILE + TILE // 2, b[1] * TILE + TILE // 2
                self.npcs.append({
                    "x": ax, "y": ay, "a": (ax, ay), "b": (bx, by),
                    "r": 11, "jacket": jackets[(i + k) % len(jackets)],
                    "speed": rnd.uniform(40, 82), "phase": rnd.random(),
                    "dir": rnd.choice((1, -1)), "facing": 0.0,
                    "walk_t": rnd.uniform(0, 6.28),
                })

    # ------------------------------------------------------ предметы/фон
    def _props_all(self):
        rnd = self.rnd
        # фонари вдоль всех трёх улиц (редкие, жёлтые — как в 97-м)
        for row in (10, 20, 28, 40, 47):
            for tx in range(3, self.w, 7):
                self.add_prop("lamp", tx * TILE + TILE // 2, row * TILE,
                              solid=True, radius=7, seed=rnd.randrange(99))
        # урны
        for i in range(14):
            tx = 4 + (i * 7) % (self.w - 8)
            ty = rnd.choice([19, 28, 11, 40])
            if not self.is_solid_tile(tx, ty):
                self.add_prop("trash", tx * TILE + TILE // 2, ty * TILE,
                              solid=True, radius=7)
        # скамейки в сквере училища
        for (tx, ty) in [(12, 18), (18, 18), (70, 40)]:
            if not self.is_solid_tile(tx, ty):
                self.add_prop("bench", tx * TILE, ty * TILE, solid=True,
                              radius=9, angle=0, seed=rnd.randrange(99))
        # телефон-автомат (рядом продавали карточки для таксофонов)
        self.add_prop("phonebox", 22 * TILE + TILE // 2, 11 * TILE + TILE // 2,
                      solid=True, radius=11, seed=3)
        self.add_prop("phonebox", 78 * TILE + TILE // 2, 40 * TILE + TILE // 2,
                      solid=True, radius=11, seed=4)
        # газетный киоск «Союзпечать»
        self.add_prop("kiosk", 46 * TILE + TILE // 2, 11 * TILE + TILE // 2,
                      solid=True, radius=16, seed=7)
        # игровые автоматы «Морской бой» у комиссионки
        for i in range(2):
            self.add_prop("arcade", (69 + i) * TILE + TILE // 2,
                          28 * TILE + TILE // 2, solid=True, radius=9, seed=i)
        # подбираемые предметы — быт квартала 1997
        from player import find_walkable
        spots = [
            ("bread", "Батон", 12, 20), ("cigarettes", "Прима", 34, 28),
            ("money", "Деньги", 58, 22), ("newspaper", "Газета", 45, 11),
            ("bag", "Сумка", 70, 40), ("vodka", "Поллитра", 88, 28),
            ("key", "Ключи", 24, 34), ("ttt", "ТТТ", 82, 44),
            ("bread", "Батон", 6, 47), ("cigarettes", "Прима", 52, 16),
        ]
        for name, label, tx, ty in spots:
            px, py = tx * TILE + TILE // 2, ty * TILE + TILE // 2
            if self.is_solid_tile(tx, ty):
                px, py = find_walkable(self, px, py, r=6)
            self.items.append({"name": name, "label": label,
                               "x": px, "y": py, "taken": False})
        # спавн Данилы — северный тротуар Ломоносова, напротив дома 6
        self.spawn = (10 * TILE + TILE // 2, 20 * TILE + TILE // 2)

    def finalize(self):
        from player import find_walkable
        sx, sy = self.spawn
        self.spawn = find_walkable(self, sx, sy)
        return self
