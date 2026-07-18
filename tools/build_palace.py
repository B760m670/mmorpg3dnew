#!/usr/bin/env python3
"""HERO-объект №1 — Большой Гатчинский дворец, массинг ПО РЕАЛЬНОМУ КОНТУРУ.

Не «коробка» и не выдумка: берём настоящий след дворца из buildings.json
(44 вершины, 278×208 м — весь ансамбль с галереями и каре), ставим на рельеф
и поднимаем ПЕРЕМЕННОЙ высотой — так, чтобы читался реальный силуэт:
  · высокий центральный корпус (садовая, северная сторона) ~18 м;
  · низкие полукруглые галереи, охватывающие плац (южная сторона) ~8 м;
  · приподнятые концевые каре (Кухонное/Арсенальное) на юж. углах ~16 м;
  · две пятигранные башни над корпусом (Часовая/Сигнальная) ~32 м.
Всё в координатах движка (X=восток, Z=−север, ноль=дворец), формат буфера — как
у города (CITY, 2 поверхности: стены/кровли). Детали фасада (окна, карнизы,
облицовка) и скатные кровли/купол — следующие шаги, по референсам.

Запуск: python3 tools/build_palace.py
"""
import json
import math
import os
import struct

from build_city import Surface, load_dem, ground, shoelace  # общий конвейер

ROOT = os.path.join(os.path.dirname(__file__), "..")
SRC = os.path.join(ROOT, "game2", "data", "real", "buildings.json")
OUT = os.path.join(ROOT, "game2", "assets", "city", "gatchina_palace.bin")

PALACE_XY = (19.0, 37.0)     # центр дворца (данные: восток, север)

# высоты массинга (м над цоколем)
H_GALLERY = 8.0
H_CORPS = 18.0
H_CARE = 16.0
H_TOWER = 32.0


def find_palace_ring():
    b = json.load(open(SRC))
    best = None
    for it in b:
        for p in it.get("polys", []):
            if not p or len(p[0]) < 4:
                continue
            r = p[0]
            a = abs(shoelace(r))
            cx = sum(q[0] for q in r) / len(r)
            cy = sum(q[1] for q in r) / len(r)
            d = math.hypot(cx - PALACE_XY[0], cy - PALACE_XY[1])
            if d < 60.0 and (best is None or a > best[0]):
                best = (a, r)
    assert best, "контур дворца не найден у %s" % (PALACE_XY,)
    return best[1]


def height_field(x, y):
    """Высота массы в точке следа (данные восток x, север y). Даёт силуэт:
    север=корпус (высоко), юг=галереи (низко), юж.углы=каре, всё гладко."""
    cx, cy = PALACE_XY
    ny = y - cy
    # корпус — северная (садовая) сторона
    corps = _smooth(ny, 5.0, 45.0)
    # концевые каре — далеко на юг и к краям по востоку
    care = _smooth(-ny, 55.0, 95.0) * _smooth(abs(x - cx), 70.0, 105.0)
    h = H_GALLERY + (H_CORPS - H_GALLERY) * corps
    h = max(h, H_GALLERY + (H_CARE - H_GALLERY) * care)
    return h


def _smooth(v, a, b):
    if v <= a:
        return 0.0
    if v >= b:
        return 1.0
    t = (v - a) / (b - a)
    return t * t * (3.0 - 2.0 * t)


def add_prism(walls, roofs, ring_xy, base, h_of):
    """Призма: внешнее кольцо ring_xy (движок X,Z, CCW), стены base..base+h,
    кровля-крышка. h_of(x,z)->высота над цоколем в вершине (переменная)."""
    m = len(ring_xy)
    # ориентация CCW
    if shoelace(ring_xy) < 0:
        ring_xy = list(reversed(ring_xy))
    perim = 0.0
    for k in range(m):
        x0, z0 = ring_xy[k]
        x1, z1 = ring_xy[(k + 1) % m]
        ex, ez = x1 - x0, z1 - z0
        el = math.hypot(ex, ez)
        if el < 1e-4:
            continue
        nx, nz = ez / el, -ex / el          # внешняя нормаль CCW
        h0 = h_of(x0, z0)
        h1 = h_of(x1, z1)
        u0, u1 = perim, perim + el
        perim += el
        b0 = walls.add(x0, base, z0, nx, 0, nz, u0, 0)
        b1 = walls.add(x1, base, z1, nx, 0, nz, u1, 0)
        t0 = walls.add(x0, base + h0, z0, nx, 0, nz, u0, h0)
        t1 = walls.add(x1, base + h1, z1, nx, 0, nz, u1, h1)
        walls.tri(b0, t0, b1)
        walls.tri(b1, t0, t1)
    # кровля — ear-clip кольца, каждая вершина на своей высоте
    from build_city import ear_clip
    tris = ear_clip(ring_xy)
    ridx = [roofs.add(x, base + h_of(x, z), z, 0, 1, 0, x * 0.2, z * 0.2)
            for x, z in ring_xy]
    for ia, ib, ic in tris:
        roofs.tri(ridx[ia], ridx[ib], ridx[ic])


def pentagon(cx, cz, rad, rot=0.0):
    return [(cx + rad * math.cos(rot + i * 2 * math.pi / 5),
             cz + rad * math.sin(rot + i * 2 * math.pi / 5)) for i in range(5)]


def main():
    a, href = load_dem()
    ring_data = find_palace_ring()
    # данные (восток,север) → движок (X=восток, Z=−север), без замыкающей
    eng = [(p[0], -p[1]) for p in ring_data[:-1]]
    base = min(ground(a, href, x, z) for x, z in eng) - 0.4

    walls = Surface()
    roofs = Surface()

    # основной массив: реальный контур, переменная высота (h_field в данных)
    add_prism(walls, roofs, eng, base, lambda x, z: height_field(x, -z))

    # две башни над корпусом (садовая сторона, симметрично оси дворца)
    cx, cy = PALACE_XY
    for dx in (-24.0, 24.0):
        tx, ty = cx + dx, cy + 20.0            # данные: чуть к северу (корпус)
        pen = pentagon(tx, -ty, 7.0, rot=math.radians(18))
        tb = base + H_CORPS - 1.0              # растут из крыши корпуса
        add_prism(walls, roofs, pen, tb, lambda x, z: H_TOWER - H_CORPS + 1.0)

    with open(OUT, "wb") as f:
        f.write(b"CITY")
        f.write(struct.pack("<II", 1, 2))
        for s in (walls, roofs):
            f.write(struct.pack("<II", s.vcount(), s.icount()))
            f.write(s.v)
            f.write(s.idx)

    xs = [x for x, z in eng]
    zs = [z for x, z in eng]
    print("== ДВОРЕЦ (массинг по реальному контуру 44-вершинного следа) ==")
    print("след            : %.0f м²  габарит X=%.0f Z=%.0f" % (
        abs(shoelace(eng)), max(xs) - min(xs), max(zs) - min(zs)))
    print("цоколь (мир Y)  : %.1f м" % base)
    print("высоты массы    : галереи %.0f · корпус %.0f · каре %.0f · башни %.0f м" % (
        H_GALLERY, H_CORPS, H_CARE, H_TOWER))
    print("стены  △=%d  верш=%d" % (walls.icount() // 3, walls.vcount()))
    print("кровли △=%d  верш=%d" % (roofs.icount() // 3, roofs.vcount()))
    print("буфер           : %s (%.1f КБ)" % (os.path.basename(OUT), os.path.getsize(OUT) / 1024))


if __name__ == "__main__":
    main()
