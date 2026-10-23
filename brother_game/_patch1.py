# -*- coding: utf-8 -*-
import io

def edit(path, pairs):
    s = io.open(path, encoding='utf-8').read()
    for old, new in pairs:
        assert old in s, (path, old[:70])
        s = s.replace(old, new, 1)
    io.open(path, 'w', encoding='utf-8').write(s)
    print('patched', path)

# ------------------------------------------------ district.py
old_add = '''    def add_prop(self, kind=None, px=None, py=None, solid=True, radius=10,
                 **kw):
        # совместимость: kind может прийти и как kwarg (kind="car") —
        # в этом случае он описывает модель авто, а не тип пропа
        k = kw.pop("kind", None)
        if k is not None and kind is not None and k != kind:
            kw["model"] = k
        if kind is None:
            kind = k
        p = {"t": kind, "x": px, "y": py, "solid": solid, "r": radius}'''
new_add = '''    def add_prop(self, *args, **kw):
        """kind можно передать позиционно ИЛИ как kwarg kind=...
        (у машин kwarg kind означает модель кузова -> кладём в model)."""
        names = ("kind", "px", "py")
        vals = dict(zip(names, args))
        if len(args) > 3:
            raise TypeError("add_prop: too many positional args")
        for extra in ("solid", "radius"):
            if extra in kw and len(args) >= list(
                    ("kind", "px", "py", "solid", "radius")).index(extra) + 1:
                pass
        kind = vals.get("kind", kw.pop("kind", None))
        px = vals.get("px", kw.pop("px", None))
        py = vals.get("py", kw.pop("py", None))
        solid = kw.pop("solid", True)
        radius = kw.pop("radius", 10)
        k2 = kw.pop("kind", None)   # уже сняли выше, на всякий случай
        if k2 is not None and kind is not None and k2 != kind:
            kw["model"] = k2
        elif k2 is not None and kind is None:
            kind = k2
        p = {"t": kind, "x": px, "y": py, "solid": solid, "r": radius}'''
edit('district.py', [(old_add, new_add)])

# ------------------------------------------------ render.py: машины через cars.py
edit('render.py', [
    ('''        if t == "car":
            return self._get_car(p.get("model", p.get("kind", "sedan")), p.get("color", (90, 96, 110)),
                                 p.get("seed", 1), parked=True)[0]''',
     '''        if t == "car":
            return self._get_car(p.get("model", p.get("kind", "vaz2101")),
                                 p.get("color", (90, 96, 110)),
                                 p.get("seed", 1), parked=True)[0]'''),
    ('''        key = (kind, color, seed, parked)
        hit = self._car_cache.get(key)
        if hit is None:
            frames = T.make_car_frames(kind, color, seed)
            still = frames[(0, False, 0, 0)]
            mv = {}
            for phase in range(4):
                for blink in (0, 1):
                    mv[(phase, blink)] = frames[(0, True, phase, blink)]
            hit = (still, mv, T.car_headlights(color, kind))
            self._car_cache[key] = hit
        return hit''',
     '''        key = (kind, color, seed, parked)
        hit = self._car_cache.get(key)
        if hit is None:
            import cars as C
            legacy = {"sedan": "vaz2101", "van": "vaz2109",
                      "bus": "bmwe34", "truck": "vaz2101"}
            m = C.CAR_MODELS.get(kind) and kind or legacy.get(kind, "vaz2101")
            try:
                frames = C.make_model_frames(m, color, seed)
                hl = C.car_headlights(m, color)
            except Exception:
                frames = T.make_car_frames(legacy.get(kind, "sedan"), color, seed)
                hl = T.car_headlights(color, legacy.get(kind, "sedan"))
            still = frames[(0, False, 0, 0)]
            mv = {}
            for phase in range(4):
                for blink in (0, 1):
                    mv[(phase, blink)] = frames[(0, True, phase, blink)]
            hit = (still, mv, hl)
            self._car_cache[key] = hit
        return hit'''),
])
print('done')
