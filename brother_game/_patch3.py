# -*- coding: utf-8 -*-
"""Патч 3: фасады с витринами магазинов, интерьеры с мебелью/плафонами,
надёжная отрисовка буфера интерьера (blit с обрезкой источника)."""
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
        '''    elif floor_type == "linoleum":
        base = (122, 96, 84)
        t.fill(base)
        for _ in range(90):
            c = _shade(base, rnd.uniform(0.8, 1.2)) + (rnd.randint(30, 120),)
            pygame.draw.circle(t, c, (rnd.randrange(size), rnd.randrange(size)),
                               rnd.randint(1, 2))
        for yy in range(0, size, 16):
            pygame.draw.line(t, _shade(base, 0.7, ), (0, yy), (size, yy))''',
        '''    elif floor_type == "linoleum":
        base = (122, 96, 84)
        t.fill(base)
        for _ in range(90):
            c = _shade(base, rnd.uniform(0.8, 1.2)) + (rnd.randint(30, 120),)
            pygame.draw.circle(t, c, (rnd.randrange(size), rnd.randrange(size)),
                               rnd.randint(1, 2))
        for yy in range(0, size, 16):
            pygame.draw.line(t, _shade(base, 0.7), (0, yy), (size, yy))''',
    ),
])

# ================================================================ district.py
edit('district.py', [
    # import pygame на уровне модуля — build_indoors не должен падать молча
    (
        '''import math
import random

from config import GRID_W, GRID_H, TILE, PLAYER_RADIUS''',
        '''import math
import random

import pygame

from config import GRID_W, GRID_H, TILE, PLAYER_RADIUS''',
    ),
    # фасад дома получает вывеску магазина (витрины на крыше-блоке)
    (
        '''        self.interiors[key] = lvl
        wall["interior"] = key
        return lvl''',
        '''        # вывеска первого этажа -> витрины на южном фасаде блока
        if shop_cells:
            wall["shop"] = shop_cells[0].get("label")
        elif label and any(k in label.upper() for k in
                           ("МАГ", "ОВОЩ", "КОМИС", "АПТЕК", "ХОЗТ",
                            "ПРОД", "ЖЕНЩ")):
            wall["shop"] = label.split("·")[-1].strip()
        self.interiors[key] = lvl
        wall["interior"] = key
        return lvl''',
    ),
    # интерьер: перегородки тоньше, проходы свободны, мебель вписана в сетку
    (
        '''        for r in (rooms or []):                 # внутренние перегородки
            rx, ry, rw, rh = r
            for x in range(rx, min(W, rx + rw)):
                for y in range(ry, min(H, ry + rh)):
                    s.add((x, y))''',
        '''        for r in (rooms or []):                 # внутренние перегородки
            rx, ry, rw, rh = r
            for x in range(rx, min(W, rx + rw)):
                for y in range(ry, min(H, ry + rh)):
                    if 0 < x < W - 1 and 0 < y < H - 1:
                        s.add((x, y))''',
    ),
    (
        '''        for pr in (props or []):
            d = {"t": pr[0], "x": pr[1] * TILE + TILE // 2,
                 "y": pr[2] * TILE + TILE // 2, "solid": True,
                 "r": pr[3] if len(pr) > 3 else 12}
            lvl["props"].append(d)''',
        '''        for pr in (props or []):
            ptx, pty = pr[1], pr[2]
            # мебель не ставим в стену и не запечатываем выход/спавн
            if (ptx, pty) in s:
                continue
            d = {"t": pr[0], "x": ptx * TILE + TILE // 2,
                 "y": pty * TILE + TILE // 2, "solid": True,
                 "r": pr[3] if len(pr) > 3 else 12}
            lvl["props"].append(d)
            s.add((ptx, pty))       # мебель непроходима по своей клетке
        # плафоны: один в центре уровня + по одному на «комнату»-перегородку
        lamps = [{"x": W * TILE // 2, "y": H * TILE // 2}]
        for r in (rooms or [])[:3]:
            lamps.append({"x": (r[0] + max(1, r[2] // 2)) * TILE + TILE // 2,
                          "y": (r[1] + max(1, r[3] // 2)) * TILE + TILE // 2})
        lvl["lamps"] = lamps''',
    ),
    # печать интерьера: светлая побелка стен, тёмная окантовка, парадные двери
    (
        '''            # стены-перегородки
            wt = T.interior_wall_thick(TILE, (74, 70, 64),
                                       seed=hash(key + "w") % 997)
            for (tx, ty) in lvl["blocked"]:
                surf.blit(wt, (tx * TILE, ty * TILE))''',
        '''            # стены: побелка сверху, тёмная «отмашка» снизу, трещины бетона
            wt = T.interior_wall_thick(TILE, (122, 116, 106),
                                       seed=abs(hash(key + "w")) % 997)
            for (tx, ty) in lvl["blocked"]:
                surf.blit(wt, (tx * TILE, ty * TILE))
                px0, py0 = tx * TILE, ty * TILE
                pygame.draw.rect(surf, (58, 54, 50),
                                 (px0, py0 + TILE - 7, TILE, 7))    # плинтус
                pygame.draw.line(surf, (168, 162, 150), (px0, py0),
                                 (px0 + TILE - 1, py0))             # свет верха
                # примыкания соседних клеток — тёмный шов
                if (tx + 1, ty) not in lvl["blocked"]:
                    pygame.draw.line(surf, (46, 42, 38),
                                     (px0 + TILE - 1, py0), (px0 + TILE - 1, py0 + TILE))
                if (tx, ty + 1) not in lvl["blocked"]:
                    pygame.draw.line(surf, (46, 42, 38),
                                     (px0, py0 + TILE - 1), (px0 + TILE, py0 + TILE - 1))''',
    ),
    (
        '''            fl = T.interior_floor(W, H, lvl.get("floor", "concrete"),
                                  seed=hash(key) % 9999)''',
        '''            fl = T.interior_floor(W, H, lvl.get("floor", "concrete"),
                                  seed=abs(hash(key)) % 9999)''',
    ),
])

# ================================================================ render.py
edit('render.py', [
    (
        '''            bg = getattr(lvl, "_surf_ref", None)
            if bg is None:
                bg = getattr(self, "indoors", {}).get(lvl["key"])
            if bg is not None:
                r = bg.get_rect()
                r.topleft = (camx, camy)
                self.screen.blit(bg, (0, 0), r.clamp(pygame.Rect(0, 0, iw, ih)))
            else:
                self.screen.fill((36, 34, 32))''',
        '''            bg = getattr(self, "indoors", {}).get(lvl["key"])
            if bg is not None:
                # blit с source-rect: берём только видимую часть буфера
                sx1 = min(iw - camx, WINDOW_W)
                sy1 = min(ih - camy, WINDOW_H)
                src = pygame.Rect(camx, camy, max(0, sx1), max(0, sy1))
                self.screen.blit(bg, (0, 0), src)
                if sx1 < WINDOW_W or sy1 < WINDOW_H:
                    dark = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
                    dark.fill((10, 10, 14, 220))
                    self.screen.blit(dark, (max(0, sx1), 0),
                                     (0, 0, WINDOW_W - max(0, sx1), WINDOW_H))
            else:
                self.screen.fill((36, 34, 32))''',
    ),
])

print("PATCH3 APPLIED")
