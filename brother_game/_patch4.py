# -*- coding: utf-8 -*-
"""Патч 4: вход в интерьер — телепорт к двери с улицы (клетка фасада
непроходима), наружные NPC не рисуются внутри, ночные окна фасадов —
только снаружи."""
import io


def edit(path, pairs):
    s = io.open(path, encoding='utf-8').read()
    for old, new in pairs:
        assert old in s, (path, old[:70])
        assert s.count(old) == 1, (path, "MULTIPLE", old[:70])
        s = s.replace(old, new, 1)
    io.open(path, 'w', encoding='utf-8').write(s)
    print('patched', path)


# ================================================================ game.py
edit('game.py', [
    (
        '''        self._return_pos = (self.player.x, self.player.y)
        self.district.enter_level(lvl["key"])
        # посадить Данилу у входа в интерьер
        sx, sy = lvl["spawn"]
        self.player.x, self.player.y = sx, sy''',
        '''        self._return_pos = (self.player.x, self.player.y)
        self.district.enter_level(lvl["key"])
        # посадить Данилу у входа в интерьер (у южной стены — у двери)
        sx, sy = lvl["spawn"][0], lvl["h"] * TILE - TILE * 1.25
        self.player.x, self.player.y = sx, sy''',
    ),
])

# ================================================================ render.py
edit('render.py', [
    (
        '''        # ---- ночные окна подъездов (пока не темно — не видны)
        if self.night > 0.05:''',
        '''        # ---- ночные окна подъездов (пока не темно — не видны)
        if self.night > 0.05 and lvl is None:''',
    ),
    (
        '''        for n in npcs:
            if view.inflate(140, 140).collidepoint(n["x"], n["y"]):
                draw_list.append((n["y"], "npc", n))''',
        '''        for n in npcs:
            if lvl is not None:
                # координаты уличных прохожих вне плана этажа — не рисуем
                if not (0 < n["x"] < lvl["w"] * TILE and
                        0 < n["y"] < lvl["h"] * TILE):
                    continue
            if view.inflate(140, 140).collidepoint(n["x"], n["y"]):
                draw_list.append((n["y"], "npc", n))''',
    ),
])

print("PATCH4 APPLIED")
