# -*- coding: utf-8 -*-
"""Инвентарь: хотбар (1..0), выбор слота, подбор предметов, use/drop."""
import pygame

from config import COL_ACCENT, INVENTORY_SLOTS


class Item:
    def __init__(self, name, label, count=1):
        self.name = name          # ключ для иконки
        self.label = label        # подпись по-русски
        self.count = count

    def __repr__(self):
        return f"Item({self.name}x{self.count})"


class Inventory:
    def __init__(self, slots=INVENTORY_SLOTS):
        self.slots = [None] * slots
        self.selected = 0

    # ------------------------------------------------------------- операции
    def add(self, item):
        """Ставим предмет: стакаем одинаковые, иначе первый пустой слот."""
        if isinstance(item, dict):
            item = Item(item["name"], item["label"])
        for i, s in enumerate(self.slots):
            if s is not None and s.name == item.name:
                s.count += item.count
                return i
        for i, s in enumerate(self.slots):
            if s is None:
                self.slots[i] = item
                return i
        return -1  # инвентарь забит

    def remove_at(self, idx, n=1):
        s = self.slots[idx]
        if s is None:
            return None
        s.count -= n
        if s.count <= 0:
            self.slots[idx] = None
        return s

    def selected_item(self):
        return self.slots[self.selected]

    def select(self, idx):
        if 0 <= idx < len(self.slots):
            self.selected = idx
            return True
        return False

    def cycle(self, d):
        self.selected = (self.selected + d) % len(self.slots)

    @property
    def total_items(self):
        return sum(s.count for s in self.slots if s)

    def labels(self):
        return [f"{s.label} x{s.count}" for s in self.slots if s]


def draw_hotbar(screen, inv, renderer_font, icons, sel_frames, base_x=None, y=None):
    """Нижний ряд слотов с цифрами и подписью выбранного предмета."""
    size = 52
    gap = 6
    n = len(inv.slots)
    if base_x is None:
        base_x = (screen.get_width() - (n * size + (n - 1) * gap)) // 2
    if y is None:
        y = screen.get_height() - size - 14
    from textures import hotbar_frame
    for i, slot in enumerate(inv.slots):
        x = base_x + i * (size + gap)
        frame = sel_frames[inv.selected == i]
        screen.blit(frame, (x, y))
        if slot is not None:
            icon = icons[slot.name]
            r = icon.get_rect(center=(x + size // 2, y + size // 2))
            screen.blit(icon, r)
            # счётчик
            if slot.count > 1:
                renderer_font(screen, str(slot.count), (x + size - 12, y + size - 16),
                              size=15, color=(235, 235, 230), bold=True)
        # номер слота (10-й показываем как 0)
        num = str((i + 1) % 10)
        renderer_font(screen, num, (x + 4, y + 2), size=13, color=(150, 152, 158))
    # подпись выбранного (рисуем по центру через topleft — lambda не знает center)
    it = inv.selected_item()
    if it:
        wpx = len(it.label) * 9.5
        renderer_font(screen, it.label,
                      (int(screen.get_width() / 2 - wpx / 2), max(0, y - 24)),
                      size=18, color=COL_ACCENT, bold=True)
    return pygame.Rect(base_x, y, n * size + (n - 1) * gap, size)
