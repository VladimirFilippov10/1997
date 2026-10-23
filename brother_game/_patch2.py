# -*- coding: utf-8 -*-
"""Патч: нормальные фасады зданий + возможность зайти внутрь (интерьеры).

1) textures.facade_wall — вертикальный фасад доходного дома (этажи окон,
   руст, витрины, сандрики), building_block рисует его вместо полоски.
2) district.build_indoors() — печать интерьеров в отдельный буфер;
   renderer.draw() переключается на него, когда игрок внутри.
3) game.py — вход/выход по E у двери, NPC и предметы интерьера живут своей
   жизнью, подсказка «[E] войти».
"""
import io


def edit(path, pairs):
    s = io.open(path, encoding='utf-8').read()
    for old, new in pairs:
        assert old in s, (path, old[:70])
        assert s.count(old) == 1, (path, "MULTIPLE", old[:70])
        s = s.replace(old, new, 1)
    io.open(path, 'w', encoding='utf-8').write(s)
    print('patched', path)


# ================================================================ textures.py
edit('textures.py', [
    (
        '''def building_block(px_w, px_h, color=(112, 100, 92), floors=5, style="gable",
                   seed=1, tower=False):''',
        '''def facade_wall(px_w, wall_h, color=(112, 100, 92), floors=5, seed=1,
                lit_p=0.0, shop=None, ground_floor=True):
    """Вертикальный фасад доходного дома: этажи окон, руст, карнизы, витрина.

    Возвращает Surface (px_w, wall_h). Окна считаются по числу этажей
    (floors); на первом этаже — руст и витрины магазина (shop — вывеска).
    lit_p > 0 включает «жёлтые окна» (сумерки/ночь).
    """
    rnd = _rng(seed)
    s = pygame.Surface((px_w, wall_h), pygame.SRCALPHA)
    base = _shade(color, 1.0)
    s.fill(base)
    # фактура штукатурки
    for _ in range(max(12, px_w * wall_h // 90)):
        x, y = rnd.randrange(px_w), rnd.randrange(wall_h)
        c = _shade(color, rnd.uniform(0.88, 1.12)) + (rnd.randint(10, 40),)
        pygame.draw.circle(s, c, (x, y), rnd.randint(1, 2))
    # местами проступает кирпич (отвалившаяся побелка)
    if rnd.random() < 0.6 and px_w > 24 and wall_h > 20:
        bx = rnd.randrange(max(1, px_w - 20))
        by = rnd.randrange(max(1, wall_h - 16))
        bw = rnd.randint(8, min(26, px_w - 1))
        bh = rnd.randint(6, min(16, wall_h - 1))
        brick = (int(base[0] * 0.62 + 70), int(base[1] * 0.42 + 30),
                 int(base[2] * 0.38 + 24))
        patch = pygame.Surface((bw, bh), pygame.SRCALPHA)
        patch.fill(brick + (150,))
        for yy in range(0, bh, 4):
            pygame.draw.line(patch, (90, 52, 40, 160), (0, yy), (bw, yy))
        for xx in range(0, bw, 7):
            pygame.draw.line(patch, (90, 52, 40, 140), (xx, 0), (xx, bh))
        s.blit(patch, (bx, by))
    n_f = max(2, floors)
    fh = wall_h / float(n_f)
    win_c = (40, 46, 56)
    frame_c = _shade(color, 0.55)
    trim_c = _shade(color, 1.22)
    for f in range(n_f):
        fy = int(f * fh)
        # междуэтажный карниз
        pygame.draw.rect(s, trim_c, (0, fy, px_w, 2))
        pygame.draw.rect(s, _shade(color, 0.78), (0, fy + 2, px_w, 1))
        if f == n_f - 1 and ground_floor:
            continue                      # первый этаж — отдельный ритм
        rows_y = fy + int(fh * 0.22)
        win_h = max(6, int(fh * 0.52))
        win_w = max(5, min(11, int(win_h * 0.62)))
        step = max(win_w + 5, int(win_w * 2.1))
        margin = (px_w % step) // 2
        for wx in range(margin, px_w - win_w + 1, step):
            # сандрик + подоконник
            pygame.draw.rect(s, trim_c, (wx - 2, rows_y - 3, win_w + 4, 2))
            pygame.draw.rect(s, trim_c, (wx - 2, rows_y + win_h, win_w + 4, 2))
            pygame.draw.rect(s, win_c, (wx, rows_y, win_w, win_h))
            # блик стекла по диагонали
            gl = _shade(color, 1.5) + (70,)
            st = pygame.Surface((win_w, win_h), pygame.SRCALPHA)
            pygame.draw.polygon(st, gl, [(0, win_h), (win_w, 0),
                                         (win_w, max(2, win_h // 3)),
                                         (max(2, win_w // 3), win_h)])
            s.blit(st, (wx, rows_y))
            pygame.draw.rect(s, frame_c, (wx, rows_y, win_w, win_h), 1)
            pygame.draw.line(s, frame_c, (wx + win_w // 2, rows_y),
                             (wx + win_w // 2, rows_y + win_h))
            if lit_p > 0 and rnd.random() < lit_p:   # жёлтое окно к ночи
                a = int(235 * lit_p)
                lg = pygame.Surface((win_w + 6, win_h + 6), pygame.SRCALPHA)
                pygame.draw.rect(lg, (236, 206, 138, a), (3, 3, win_w, win_h))
                pygame.draw.rect(lg, (255, 220, 150, a // 4),
                                 (0, 0, win_w + 6, win_h + 6))
                s.blit(lg, (wx - 3, rows_y - 3))
    # ----- первый этаж: руст + витрины
    if ground_floor:
        gy = int((n_f - 1) * fh)
        gh_ = wall_h - gy
        rust = _shade(color, 0.82)
        pygame.draw.rect(s, rust, (0, gy, px_w, gh_))
        for yy in range(gy + 4, wall_h, 6):
            pygame.draw.line(s, _shade(color, 0.68), (0, yy), (px_w, yy))
        vw = max(16, min(34, int(gh_ * 1.5)))
        vh = max(8, gh_ - 10)
        vx = 4
        while vx + vw < px_w - 2:
            pygame.draw.rect(s, (28, 32, 40), (vx, gy + 5, vw, vh))
            glass = pygame.Surface((vw, vh), pygame.SRCALPHA)
            pygame.draw.polygon(glass, (150, 170, 190, 60),
                                [(0, vh), (vw, 0), (vw, vh)])
            s.blit(glass, (vx, gy + 5))
            pygame.draw.rect(s, _shade(color, 0.5), (vx, gy + 5, vw, vh), 1)
            if shop:                     # товар на витрине — цветные полоски
                for _ in range(3):
                    cx = vx + rnd.randint(2, max(3, vw - 6))
                    cy = gy + 5 + rnd.randint(vh // 2, max(vh // 2 + 1, vh - 4))
                    pygame.draw.rect(s, (rnd.randint(120, 220),
                                         rnd.randint(70, 160),
                                         rnd.randint(50, 120)),
                                     (cx, cy, rnd.randint(3, 7), rnd.randint(2, 4)))
            vx += vw + 8
        if shop:                         # вывеска над витринами
            sw = min(px_w - 6, max(10, 6 * len(shop)))
            sx = (px_w - sw) // 2
            pygame.draw.rect(s, (30, 26, 24), (sx, gy + 1, sw, 4))
            for i in range(sw // 3):
                pygame.draw.rect(s, (214, 196, 150), (sx + i * 3 + 1, gy + 2, 1, 2))
    return s


def interior_floor(W, H, floor_type="parquet", seed=1):
    """Тайловая текстура пола интерьера: parquet/wood/tile/linoleum/concrete."""
    size = 48
    rnd = _rng(seed)
    t = pygame.Surface((size, size), pygame.SRCALPHA)
    if floor_type in ("parquet", "wood"):
        base = (112, 84, 56) if floor_type == "parquet" else (96, 74, 52)
        t.fill(_shade(base, rnd.uniform(0.92, 1.05)))
        plank = size // 4 if floor_type == "parquet" else size // 2
        for i in range(0, size, plank):
            c = _shade(base, rnd.uniform(0.8, 1.15))
            pygame.draw.rect(t, c, (0, i, size, plank - 1))
            pygame.draw.line(t, _shade(base, 0.6), (0, i), (size, i))
            for _ in range(3):           # волокна
                yy = rnd.randrange(i + 1, max(i + 2, i + plank - 1))
                pygame.draw.line(t, _shade(base, 0.85),
                                 (rnd.randrange(size // 2), yy),
                                 (rnd.randrange(size // 2, size), yy))
        if floor_type == "parquet":      # «ёлочка»: короткая разбивка
            for i in range(0, size, plank):
                x0 = rnd.randrange(0, size - 4)
                pygame.draw.line(t, _shade(base, 0.7), (x0, i), (x0, i + plank - 1))
    elif floor_type == "tile":           # метлахская плитка
        a, b = (150, 146, 138), (92, 88, 84)
        q = size // 2
        for yy in range(0, size, q):
            for xx in range(0, size, q):
                c = a if (xx // q + yy // q) % 2 == 0 else b
                pygame.draw.rect(t, c, (xx, yy, q, q))
                pygame.draw.rect(t, _shade(c, 0.75), (xx, yy, q, q), 1)
        for yy in range(0, size, q):     # роспись по центру плиток
            for xx in range(0, size, q):
                pygame.draw.circle(t, _shade(a, 0.9), (xx + q // 2, yy + q // 2), 2)
    elif floor_type == "linoleum":
        base = (122, 96, 84)
        t.fill(base)
        for _ in range(90):
            c = _shade(base, rnd.uniform(0.8, 1.2)) + (rnd.randint(30, 120),)
            pygame.draw.circle(t, c, (rnd.randrange(size), rnd.randrange(size)),
                               rnd.randint(1, 2))
        for yy in range(0, size, 16):
            pygame.draw.line(t, _shade(base, 0.7, ), (0, yy), (size, yy))
    else:                                # concrete — бетон подъезда
        base = (104, 102, 98)
        t.fill(base)
        for _ in range(70):
            c = _shade(base, rnd.uniform(0.85, 1.12)) + (rnd.randint(20, 90),)
            pygame.draw.circle(t, c, (rnd.randrange(size), rnd.randrange(size)),
                               rnd.randint(1, 3))
        for _ in range(3):               # трещины
            x, y = rnd.randrange(size), rnd.randrange(size)
            for _ in range(6):
                nx, ny = x + rnd.randint(-6, 6), y + rnd.randint(-6, 6)
                pygame.draw.line(t, _shade(base, 0.6), (x, y), (nx, ny))
                x, y = nx, ny
    return t


def interior_wall_thick(th=10, col=(70, 66, 60), seed=3):
    """Полоса внутренней стены (перегородки) с побелкой и подтёртостью."""
    rnd = _rng(seed)
    s = pygame.Surface((th, th), pygame.SRCALPHA)
    s.fill(col)
    for _ in range(14):
        c = tuple(min(255, max(0, int(v * rnd.uniform(0.8, 1.2)))) for v in col) + \\
            (rnd.randint(20, 90),)
        pygame.draw.circle(s, c, (rnd.randrange(th), rnd.randrange(th)),
                           rnd.randint(1, 2))
    pygame.draw.line(s, _shade(col, 1.25), (0, 0), (th, 0))
    pygame.draw.line(s, _shade(col, 0.6), (0, th - 1), (th, th - 1))
    return s


def door_sheet_img(w=26, h=34, seed=1):
    """Фасадная дверь подъезда: филенчатая, тёмная, с косяком."""
    rnd = _rng(seed)
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(s, (58, 44, 36), (0, 0, w, h))          # полотно
    pygame.draw.rect(s, (36, 28, 24), (0, 0, w, h), 2)       # обвязка
    for yy in (int(h * 0.15), int(h * 0.5)):                 # филенки
        pygame.draw.rect(s, (78, 58, 44), (3, yy, w - 6, int(h * 0.28)))
        pygame.draw.rect(s, (40, 30, 26), (3, yy, w - 6, int(h * 0.28)), 1)
    pygame.draw.circle(s, (190, 170, 90), (w - 5, int(h * 0.55)), 2)  # ручка
    if rnd.random() < 0.5:                                    # табличка
        pygame.draw.rect(s, (200, 196, 186), (4, 2, w - 10, 3))
    return s


def building_block(px_w, px_h, color=(112, 100, 92), floors=5, style="gable",
                   seed=1, tower=False, facade_h=None, shop=None,
                   facade_seed=None):''',
    ),
    (
        '''    roof = roof_sheet(px_w, px_h, style, _shade(color, 0.86), seed)
    s.blit(roof, (0, 0))
    # южная стена (фасад, повёрнутый к «солнцу») — полоса с окнами
    wall_h = 7 + min(6, floors)
    wy = px_h
    pygame.draw.rect(s, _shade(color, 1.06), (0, wy, px_w, wall_h))
    pygame.draw.rect(s, _shade(color, 0.8), (0, wy, px_w, 1))
    win_w, win_h = 5, max(3, wall_h - 4)
    step = 13 if px_w > 90 else 11
    for wx in range(4, px_w - 6, step):
        lit = rnd.random() < 0.32
        c = (232, 208, 140) if lit else (44, 50, 60)
        pygame.draw.rect(s, c, (wx, wy + 2, win_w, win_h))
        pygame.draw.rect(s, _shade(color, 0.6), (wx, wy + 2, win_w, win_h), 1)''',
        '''    roof = roof_sheet(px_w, px_h, style, _shade(color, 0.86), seed)
    s.blit(roof, (0, 0))
    # южная стена — полноценный фасад доходного дома: этажи окон, руст,
    # витрины первого этажа (высота ~ половина глубины корпуса)
    wall_h = facade_h or max(26, min(int(px_h * 0.55), 20 + 6 * floors))
    wy = px_h
    fac = facade_wall(px_w, wall_h, color=color, floors=floors,
                      seed=facade_seed or (seed * 7 + 3), shop=shop)
    s.blit(fac, (0, wy))
    pygame.draw.rect(s, _shade(color, 0.8), (0, wy, px_w, 1))''',
    ),
])

# ================================================================ district.py
edit('district.py', [
    (
        '''        self.blocked.discard((tx, ty))
        d = {"x": px, "y": py, "r": TILE * 0.8, "level": level_key,
             "label": label or self.interiors[level_key]["label"]}
        self.doors.append(d)
        self.flat.append({"t": "steps", "x": tx, "y": ty,
                          "seed": self.rnd.randrange(99)})
        return d''',
        '''        self.blocked.discard((tx, ty))
        # чтобы в проём нельзя было влететь сбоку — блокируем соседние
        # клетки фасада, кроме самой двери
        if side in ("south", "north"):
            self.blocked.add((tx - 1, ty))
            self.blocked.add((tx + 1, ty))
        else:
            self.blocked.add((tx, ty - 1))
            self.blocked.add((tx, ty + 1))
        d = {"x": px, "y": py, "r": TILE * 0.8, "level": level_key,
             "label": label or self.interiors[level_key]["label"],
             "side": side}
        self.doors.append(d)
        self.flat.append({"t": "steps", "x": tx, "y": ty,
                          "seed": self.rnd.randrange(99)})
        self.flat.append({"t": "doorface", "x": tx, "y": ty, "rot": side,
                          "seed": self.rnd.randrange(99)})
        return d''',
    ),
    (
        '''    def finalize(self):
        """Спавн игрока в гарантированно проходимой клетке."""''',
        '''    def build_indoors(self):
        """Печатает все интерьеры в dict {key: Surface} (один раз при старте)."""
        import textures as T
        out = {}
        for key, lvl in self.interiors.items():
            W, H = lvl["w"], lvl["h"]
            surf = pygame.Surface((W * TILE, H * TILE))
            fl = T.interior_floor(W, H, lvl.get("floor", "concrete"),
                                  seed=hash(key) % 9999)
            for ty in range(H):
                for tx in range(W):
                    surf.blit(fl, (tx * TILE, ty * TILE))
            # стены-перегородки
            wt = T.interior_wall_thick(TILE, (74, 70, 64),
                                       seed=hash(key + "w") % 997)
            for (tx, ty) in lvl["blocked"]:
                surf.blit(wt, (tx * TILE, ty * TILE))
            # выходная дверь — светлый проём с порогом
            ex, ey = lvl["exit"]
            etx, ety = int(ex // TILE), int(ey // TILE)
            pygame.draw.rect(surf, (24, 22, 20),
                             (etx * TILE + 6, ety * TILE + 6, TILE - 12, TILE - 12))
            pygame.draw.rect(surf, (150, 130, 90),
                             (etx * TILE + 6, ety * TILE + TILE - 12, TILE - 12, 6))
            lvl["surface"] = surf
            out[key] = surf
        return out

    def finalize(self):
        """Спавн игрока в гарантированно проходимой клетке."""''',
    ),
])

# ================================================================ render.py
edit('render.py', [
    (
        '''            "porch": lambda: T.steps_tile(9),
        }''',
        '''            "porch": lambda: T.steps_tile(9),
            "doorface": lambda: T.door_sheet_img(),
        }''',
    ),
    (
        '''            block = T.building_block(rect.width, rect.height, w["color"],
                                     w.get("floors", 5), w.get("style", "gable"),
                                     w.get("seed", 1), w.get("tower", False))''',
        '''            block = T.building_block(rect.width, rect.height, w["color"],
                                     w.get("floors", 5), w.get("style", "gable"),
                                     w.get("seed", 1), w.get("tower", False),
                                     shop=w.get("shop"))''',
    ),
    (
        '''        self.map_surface = surf
        return surf''',
        '''        self.map_surface = surf
        # интерьеры домов — печатаются один раз в отдельные буферы
        try:
            self.indoors = d.build_indoors()
        except Exception:
            self.indoors = {}
        return surf''',
    ),
    (
        '''    def draw(self, camera, player, time_s, inventory_sel, messages):
        d = self.d
        camx, camy = camera
        camx = int(max(0, min(self.world_px_w - WINDOW_W, camx)))
        camy = int(max(0, min(self.world_px_h - WINDOW_H, camy)))
        view = pygame.Rect(camx, camy, WINDOW_W, WINDOW_H)
        self._blit_n = 0

        self.screen.blit(self.map_surface, (0, 0), view)
        self._blit_n += 1''',
        '''    def draw(self, camera, player, time_s, inventory_sel, messages):
        d = self.d
        camx, camy = camera
        view = pygame.Rect(camx, camy, WINDOW_W, WINDOW_H)
        self._blit_n = 0

        lvl = d.active_grid()
        self._lvl = lvl
        if lvl is not None:
            # ---- внутри здания: свой буфер пола/стен, камера по интерьеру
            iw, ih = lvl["w"] * TILE, lvl["h"] * TILE
            camx = int(max(0, min(max(0, iw - WINDOW_W), camx)))
            camy = int(max(0, min(max(0, ih - WINDOW_H), camy)))
            view = pygame.Rect(camx, camy, WINDOW_W, WINDOW_H)
            bg = getattr(lvl, "_surf_ref", None)
            if bg is None:
                bg = getattr(self, "indoors", {}).get(lvl["key"])
            if bg is not None:
                r = bg.get_rect()
                r.topleft = (camx, camy)
                self.screen.blit(bg, (0, 0), r.clamp(pygame.Rect(0, 0, iw, ih)))
            else:
                self.screen.fill((36, 34, 32))
            self._draw_interior_extras(lvl, camx, camy, time_s)
        else:
            camx = int(max(0, min(self.world_px_w - WINDOW_W, camx)))
            camy = int(max(0, min(self.world_px_h - WINDOW_H, camy)))
            view = pygame.Rect(camx, camy, WINDOW_W, WINDOW_H)
            self.screen.blit(self.map_surface, (0, 0), view)
            self._blit_n += 1''',
    ),
    (
        '''        # ---- предметы на земле (поверх карты)
        lvl_now = d.active_grid()
        item_list = lvl_now["items"] if lvl_now else d.items''',
        '''        # ---- предметы на земле (поверх карты)
        lvl_now = lvl
        item_list = lvl_now["items"] if lvl_now else d.items''',
    ),
    (
        '''        # ---- блики воды (анимация)
        if self._water_y is not None:''',
        '''        # ---- блики воды (анимация)
        if self._water_y is not None and lvl is None:''',
    ),
    (
        '''        lvl = d.active_grid()
        npcs = lvl["npcs"] if lvl else d.npcs
        items = lvl["items"] if lvl else d.items
        props_in = lvl["props"] if lvl else None
        if props_in is not None:
            for p in props_in:
                if view.inflate(140, 140).collidepoint(p["x"], p["y"]):
                    draw_list.append((p["y"], "prop", p))''',
        '''        npcs = lvl["npcs"] if lvl else d.npcs
        props_in = lvl["props"] if lvl else None
        if props_in is not None:
            for p in props_in:
                if view.inflate(140, 140).collidepoint(p["x"], p["y"]):
                    draw_list.append((p["y"], "prop", p))''',
    ),
    (
        '''        # ---- верхний слой: листва, трубы теплотрассы (+ пар из вентилей)
        for o in d.over:''',
        '''        # ---- верхний слой: листва, трубы теплотрассы (+ пар из вентилей)
        for o in ([] if lvl else d.over):''',
    ),
    (
        '''        # ---- подписи мест
        font = get_font(20)
        for z in d.zones:''',
        '''        # ---- указатели дверей: снаружи — «войти», внутри — «выйти»
        if lvl is None:
            for dr in d.doors:
                if view.inflate(120, 120).collidepoint(dr["x"], dr["y"]):
                    sx, sy = dr["x"] - camx, dr["y"] - camy - 26
                    pulse = 0.6 + 0.4 * math.sin(time_s * 4.0)
                    fr = pygame.Rect(sx - 16, sy - 12, 32, 24)
                    pygame.draw.rect(self.screen, (20, 18, 16, 200), fr)
                    pygame.draw.rect(self.screen,
                                     (int(220 * pulse + 30), int(190 * pulse + 20), 90),
                                     fr, 1)
                    dm = T.door_sheet_img(14, 20, seed=int(dr["x"]))
                    self.screen.blit(dm, dm.get_rect(center=(sx, sy)))
        else:
            ex, ey = lvl["exit"]
            sx, sy = ex - camx, ey - camy - 30
            pulse = 0.6 + 0.4 * math.sin(time_s * 4.0)
            fr = pygame.Rect(sx - 20, sy - 11, 40, 22)
            pygame.draw.rect(self.screen, (20, 18, 16), fr)
            pygame.draw.rect(self.screen,
                             (int(220 * pulse + 30), int(190 * pulse + 20), 90), fr, 1)
            draw_text(self.screen, "ВЫХОД", (sx, sy), size=12,
                      color=(230, 220, 180), center=True)
        # ---- подписи мест
        font = get_font(20)
        for z in ([] if lvl else d.zones):''',
    ),
    (
        '''        # ---- ночь: темнота с «дырами» света
        if self.night > 0.02:
            self._draw_night(lights)''',
        '''        # ---- ночь: темнота с «дырами» света (в домах — свои лампы)
        if lvl is not None:
            for pr in lvl.get("lamps", []):
                lights.append((pr["x"] - camx, pr["y"] - camy - 6, 0.8))
        if self.night > 0.02 and lvl is None:
            self._draw_night(lights)
        elif lvl is not None:
            # в интерьере всегда сумерки: лёгкий синий флэт + ореоны ламп
            dim = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
            dim.fill((10, 12, 20, 70))
            self.screen.blit(dim, (0, 0))
            glow = self._lamp_glow()
            for (lx, ly, inten) in lights:
                size = max(24, int(150 * inten))
                img = pygame.transform.scale(glow, (size, size))
                tmp = img.copy()
                tmp.set_alpha(60)
                self.screen.blit(tmp, tmp.get_rect(center=(int(lx), int(ly))))''',
    ),
    (
        '''    def _draw_night(self, lights):''',
        '''    def _draw_interior_extras(self, lvl, camx, camy, time_s):
        """Детали интерьера: плафоны, вывески магазинов, тёплый свет."""
        # потолочные плафоны (рисуются поверх мебели, как настенные огни)
        for pr in lvl.get("lamps", []):
            sx, sy = pr["x"] - camx, pr["y"] - camy
            if -40 < sx < WINDOW_W + 40 and -40 < sy < WINDOW_H + 40:
                halo = pygame.Surface((30, 30), pygame.SRCALPHA)
                k = 0.85 + 0.15 * math.sin(time_s * 2.3 + pr["x"])
                pygame.draw.circle(halo, (255, 226, 160, int(70 * k)), (15, 15), 12)
                pygame.draw.circle(halo, (255, 244, 210, 230), (15, 15), 4)
                self.screen.blit(halo, (sx - 15, sy - 15))
        # вывеска магазина внутри уровня
        shop = lvl.get("shop")
        if shop:
            cx = lvl["w"] * TILE // 2 - camx
            cy = 14 - camy
            sf = get_font(14, bold=True)
            txt = sf.render(shop, True, (236, 224, 190))
            rect = txt.get_rect(center=(cx, cy))
            bg = pygame.Surface((rect.width + 12, rect.height + 4), pygame.SRCALPHA)
            bg.fill((26, 22, 20, 210))
            self.screen.blit(bg, (rect.left - 6, rect.top - 2))
            self.screen.blit(txt, rect)
        # название подъезда/квартиры мелкой строкой внизу
        lab = lvl.get("label")
        if lab:
            draw_text(self.screen, lab, (12, WINDOW_H - 64), size=14,
                      color=(170, 166, 158), bg=(16, 18, 22, 150))

    def _draw_night(self, lights):''',
    ),
])

# ================================================================ game.py
edit('game.py', [
    (
        '''        self.walkers = [WalkerNPC(n) for n in self.district.npcs]''',
        '''        self.walkers = [WalkerNPC(n) for n in self.district.npcs]
        self._interior_walkers = []   # NPC внутри текущего уровня
        self._return_pos = None       # куда вернуться при выходе''',
    ),
    (
        '''    def nearest_item(self):
        best, bd = None, TILE * 1.2
        for it in self.district.items:
            if it["taken"]:
                continue
            d = math.hypot(it["x"] - self.player.x, it["y"] - self.player.y)
            if d < bd:
                bd, best = d, it
        return best''',
        '''    def nearest_item(self):
        best, bd = None, TILE * 1.2
        lvl = self.district.active_grid()
        pool = lvl["items"] if lvl else self.district.items
        for it in pool:
            if it["taken"]:
                continue
            d = math.hypot(it["x"] - self.player.x, it["y"] - self.player.y)
            if d < bd:
                bd, best = d, it
        return best

    # -------------------------------------------------- вход/выход из зданий
    def near_door(self):
        """Ближайшая внешняя дверь в радиусе действия (или None)."""
        if self.district.in_level:
            return None
        best, bd = None, TILE * 1.1
        for dr in self.district.doors:
            d = math.hypot(dr["x"] - self.player.x, dr["y"] - self.player.y)
            if d < dr["r"] + 8 and d < bd:
                bd, best = d, dr
        return best

    def enter_door(self, dr):
        lvl = self.district.interiors.get(dr["level"])
        if lvl is None:
            return
        self._return_pos = (self.player.x, self.player.y)
        self.district.enter_level(lvl["key"])
        # посадить Данилу у входа в интерьер
        sx, sy = lvl["spawn"]
        self.player.x, self.player.y = sx, sy
        self.camera = [self.player.x - WINDOW_W / 2, self.player.y - WINDOW_H / 2]
        self._interior_walkers = [WalkerNPC(n) for n in lvl["npcs"]]
        self.say(lvl["label"], color=(240, 210, 120), size=22, bold=True, life=2.5)
        if self.audio.ok:
            self.audio.play(self.click, volume=0.7)

    def exit_door(self):
        lvl = self.district.active_grid()
        if lvl is None:
            return
        self.district.enter_level(None)
        self._interior_walkers = []
        rx, ry = self._return_pos or self.district.spawn
        # ставим ровно на клетку двери снаружи, чуть отступив от фасада
        dr = None
        for cand in self.district.doors:
            if cand["level"] == lvl["key"]:
                dr = cand
                break
        if dr is not None:
            side = dr.get("side", "south")
            off = TILE * 0.9
            rx, ry = dr["x"], dr["y"]
            if side == "south":
                ry += off
            elif side == "north":
                ry -= off
            elif side == "west":
                rx -= off
            else:
                rx += off
        from player import find_walkable
        rx, ry = find_walkable(self.district, rx, ry, r=self.player.radius)
        self.player.x, self.player.y = rx, ry
        self.camera = [rx - WINDOW_W / 2, ry - WINDOW_H / 2]
        if self.audio.ok:
            self.audio.play(self.click, volume=0.7)

    def toggle_door(self):
        """E у двери: войти; E у выхода внутри: выйти (если рядом нет предмета)."""
        if self.district.in_level:
            lvl = self.district.active_grid()
            ex, ey = lvl["exit"]
            if math.hypot(ex - self.player.x, ey - self.player.y) < TILE * 1.2:
                self.exit_door()
                return True
            return False
        dr = self.near_door()
        if dr is not None:
            self.enter_door(dr)
            return True
        return False''',
    ),
    (
        '''    def pick_up(self):
        it = self.nearest_item()
        if it is None:
            return''',
        '''    def pick_up(self):
        if self.toggle_door():
            return
        it = self.nearest_item()
        if it is None:
            return''',
    ),
    (
        '''        self.player.update(dx, dy, run, dt, on_step=self.on_step)
        for w in self.walkers:
            w.update(dt)''',
        '''        self.player.update(dx, dy, run, dt, on_step=self.on_step)
        for w in self.walkers:
            w.update(dt)
        for w in self._interior_walkers:
            w.update(dt)''',
    ),
    (
        '''        tx = self.player.x - WINDOW_W / 2
        ty = self.player.y - WINDOW_H / 2
        k = 1.0 - math.exp(-dt * 7.0)''',
        '''        tx = self.player.x - WINDOW_W / 2
        ty = self.player.y - WINDOW_H / 2
        if self.district.in_level:
            lvl = self.district.active_grid()
            tx = max(0.0, min(tx, max(0.0, lvl["w"] * TILE - WINDOW_W)))
            ty = max(0.0, min(ty, max(0.0, lvl["h"] * TILE - WINDOW_H)))
        k = 1.0 - math.exp(-dt * 7.0)''',
    ),
])

# ================================================================ hud.py
edit('hud.py', [
    (
        '''    # ------------------------------------------------------- строка подсказок
    hint = ("WASD — идти · Shift — бежать · E — подобрать · F — использовать · "
            "Q — выбросить · 1..0 / колесо — слот · Tab — карта · M — звук · Esc — выход")''',
        '''    # --------------------------------------------- подсказка у двери / inside
    if d.in_level:
        lvl = d.active_grid()
        ex, ey = lvl["exit"]
        if math.hypot(ex - player.x, ey - player.y) < TILE * 1.2:
            sx, sy = ex - game.camera[0], ey - game.camera[1] - 40
            draw_text(screen, "[E] выйти на улицу", (sx, sy), size=15,
                      color=(240, 232, 200), center=True, bg=(16, 18, 22, 180))
    else:
        dr = game.near_door()
        if dr is not None:
            sx, sy = dr["x"] - game.camera[0], dr["y"] - game.camera[1] - 44
            draw_text(screen, f"[E] войти: {dr['label']}", (sx, sy), size=15,
                      color=(240, 232, 200), center=True, bg=(16, 18, 22, 180))

    # ------------------------------------------------------- строка подсказок
    hint = ("WASD — идти · Shift — бежать · E — подобрать/войти · F — использовать · "
            "Q — выбросить · 1..0 / колесо — слот · Tab — карта · M — звук · Esc — выход")''',
    ),
    (
        '''def _draw_minimap(screen, game, big=False):
    d = game.game_district if hasattr(game, "game_district") else game.district
    W, H = screen.get_size()''',
        '''def _draw_minimap(screen, game, big=False):
    d = game.game_district if hasattr(game, "game_district") else game.district
    if d.in_level:
        _draw_levelmap(screen, game)
        return
    W, H = screen.get_size()''',
    ),
    (
        '''    label = "КАРТА РАЙОНА (Tab)" if big else "ПЕТЕРБУРГСКАЯ СТОРОНА"
    draw_text(screen, label, (rect.centerx, rect.bottom + 12), size=13,
              color=(170, 172, 178), center=True)''',
        '''    label = "КАРТА РАЙОНА (Tab)" if big else "ПЕТЕРБУРГСКАЯ СТОРОНА"
    draw_text(screen, label, (rect.centerx, rect.bottom + 12), size=13,
              color=(170, 172, 178), center=True)


def _draw_levelmap(screen, game):
    """Мини-план этажа, когда Данила внутри здания."""
    d = game.district
    lvl = d.active_grid()
    W, H = screen.get_size()
    size = 140
    pad = 10
    rect = pygame.Rect(W - size - pad, pad, size, size)
    bg = pygame.Surface((size + 2 * pad, size + 2 * pad), pygame.SRCALPHA)
    bg.fill((14, 16, 20, 210))
    screen.blit(bg, (rect.left - pad, rect.top - pad))
    scale = size / max(lvl["w"], lvl["h"])
    mm = pygame.Surface((max(1, int(lvl["w"] * scale)),
                         max(1, int(lvl["h"] * scale))))
    mm.fill((92, 78, 58))
    for (tx, ty) in lvl["blocked"]:
        pygame.draw.rect(mm, (48, 44, 40),
                         (int(tx * scale), int(ty * scale),
                          max(1, int(scale)), max(1, int(scale))))
    ex, ey = lvl["exit"]
    pygame.draw.rect(mm, (220, 200, 110),
                     (int(ex / TILE * scale) - 1, int(ey / TILE * scale) - 1, 3, 3))
    px = int(game.player.x / TILE * scale)
    py = int(game.player.y / TILE * scale)
    pygame.draw.circle(mm, COL_ACCENT, (px, py), 3)
    mm = pygame.transform.scale(mm, (rect.width, rect.height))
    screen.blit(mm, rect.topleft)
    draw_text(screen, lvl["label"], (rect.centerx, rect.bottom + 12), size=13,
              color=(170, 172, 178), center=True)''',
    ),
])

print("ALL PATCHES APPLIED")
