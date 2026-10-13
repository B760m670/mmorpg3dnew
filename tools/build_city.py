#!/usr/bin/env python3
"""Город Гатчины из РЕАЛЬНЫХ контуров (data/real/buildings.json → 35 853 здания).

Данные несут только план (полигоны в метрах, x=восток y=север); высота и класс
в источнике = null. Поэтому ВЫСОТА ВЫВОДИТСЯ принципиально (эпоха 1894): по
площади следа и удалению от дворца — число этажей × высота этажа + кровля.
Ничего «на глаз»: правило детерминировано и печатает гистограмму.

Здание СТАВИТСЯ НА РЕЛЬЕФ: цоколь = минимум DEM под следом (тот же
gatchina_cm.bin и та же билинейная выборка, что в terrain.gd height()), чуть
утоплен — на склоне не парит и не отрывается. Стены и кровля триангулируются
здесь (стены — квадами по рёбрам, кровля — ear-clipping), выводятся в
res://assets/city/gatchina.citymesh (две поверхности: 0 стены, 1 кровли).
GDScript (city.gd) только грузит буфер и вешает материалы — на устройстве.

Запуск: python3 tools/build_city.py
"""
import json
import os
import struct
import hashlib

ROOT = os.path.join(os.path.dirname(__file__), "..")
SRC = os.path.join(ROOT, "game2", "data", "real", "buildings.json")
DEM = os.path.join(ROOT, "game2", "assets", "dem", "gatchina_cm.bin")
OUT_DIR = os.path.join(ROOT, "game2", "assets", "city")
OUT = os.path.join(OUT_DIR, "gatchina_city.bin")  # *.bin — попадает в экспорт IPA

# --- рельеф (зеркало terrain.gd: int16 см, 513², шаг 32 м, ноль = дворец) ---
DEM_N = 513
DEM_STEP = 32.0
DEM_HALF = (DEM_N - 1) * DEM_STEP * 0.5  # 8192 м
BOUND_M = 8100.0                          # за краем DEM не строим (как дороги)

# --- модель высоты эпохи (провинциальная резиденция, 1894) ---
FLOOR_H = 3.4        # высокий этаж XIX в., м
ROOF_H = 3.0         # плоская «шапка» v1 (скатную кровлю добавит инкремент 2)
PALACE_AREA = 3000.0  # след дворцового масштаба, м²


def load_dem():
    with open(DEM, "rb") as f:
        raw = f.read()
    import array
    a = array.array("h")
    a.frombytes(raw[:DEM_N * DEM_N * 2])
    href = a[(DEM_N // 2) * DEM_N + (DEM_N // 2)] / 100.0
    return a, href


def dem_at(a, i, j):
    i = 0 if i < 0 else DEM_N - 1 if i > DEM_N - 1 else i
    j = 0 if j < 0 else DEM_N - 1 if j > DEM_N - 1 else j
    return a[j * DEM_N + i] / 100.0


def ground(a, href, x, z):
    """Высота мира (м, ноль = дворец) в точке движка (x, z). Билинейно."""
    u = (x + DEM_HALF) / DEM_STEP
    v = (z + DEM_HALF) / DEM_STEP
    i = int(u // 1)
    j = int(v // 1)
    fx = u - i
    fy = v - j
    a00 = dem_at(a, i, j)
    a10 = dem_at(a, i + 1, j)
    a01 = dem_at(a, i, j + 1)
    a11 = dem_at(a, i + 1, j + 1)
    return (a00 * (1 - fx) + a10 * fx) * (1 - fy) + (a01 * (1 - fx) + a11 * fx) * fy - href


def shoelace(ring):
    s = 0.0
    n = len(ring)
    for k in range(n):
        x0, y0 = ring[k]
        x1, y1 = ring[(k + 1) % n]
        s += x0 * y1 - x1 * y0
    return 0.5 * s


def infer_height(area, cx, cy):
    """Число этажей из площади следа + удаления от дворца; детерминированный
    разброс конька из хеша центра (крыши не строятся под одну линейку)."""
    dist = (cx * cx + cy * cy) ** 0.5
    if area >= PALACE_AREA:
        storeys, fh = 3, 4.6          # дворцовый масштаб — высокие залы
    elif area >= 1000.0:
        storeys, fh = 3, FLOOR_H      # крупное городское/казённое
    elif area >= 300.0:
        storeys, fh = (3 if dist < 1500.0 else 2), FLOOR_H
    elif area >= 90.0:
        storeys, fh = 2, FLOOR_H      # типовой дом
    elif area >= 30.0:
        storeys, fh = (2 if dist < 900.0 else 1), FLOOR_H
    else:
        storeys, fh = 1, 3.0          # службы/сараи
    h = struct.unpack("<I", hashlib.md5(b"%d_%d" % (int(cx * 10), int(cy * 10))).digest()[:4])[0]
    jitter = (h / 2**32 - 0.5) * 0.8  # ±0.4 м
    return storeys * fh + ROOF_H + jitter


def ear_clip(poly):
    """Триангуляция простого полигона (без дыр) ушами. poly: список (x,z),
    CCW. Возвращает список индексов-троек в исходный poly."""
    n = len(poly)
    if n < 3:
        return []
    idx = list(range(n))
    tris = []

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def in_tri(p, a, b, c):
        d1 = cross(a, b, p)
        d2 = cross(b, c, p)
        d3 = cross(c, a, p)
        neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
        pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
        return not (neg and pos)

    guard = 0
    while len(idx) > 3 and guard < 4 * n:
        guard += 1
        ear = False
        m = len(idx)
        for k in range(m):
            ia, ib, ic = idx[(k - 1) % m], idx[k], idx[(k + 1) % m]
            a, b, c = poly[ia], poly[ib], poly[ic]
            if cross(a, b, c) <= 0:            # выпуклая вершина (CCW)
                continue
            bad = False
            for jj in idx:
                if jj in (ia, ib, ic):
                    continue
                if in_tri(poly[jj], a, b, c):
                    bad = True
                    break
            if bad:
                continue
            tris.append((ia, ib, ic))
            idx.pop(k)
            ear = True
            break
        if not ear:
            break                              # вырожденный контур — что смогли
    if len(idx) == 3:
        tris.append((idx[0], idx[1], idx[2]))
    return tris


class Surface:
    __slots__ = ("v", "idx", "_n")

    def __init__(self):
        self.v = bytearray()   # интерливд: 3 pos + 3 nrm + 2 uv (float32)
        self.idx = bytearray()
        self._n = 0

    def add(self, x, y, z, nx, ny, nz, u, w):
        self.v += struct.pack("<8f", x, y, z, nx, ny, nz, u, w)
        i = self._n
        self._n += 1
        return i

    def tri(self, a, b, c):
        self.idx += struct.pack("<3I", a, b, c)

    def vcount(self):
        return self._n

    def icount(self):
        return len(self.idx) // 4


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    a, href = load_dem()
    with open(SRC) as f:
        buildings = json.load(f)

    walls = Surface()
    roofs = Surface()
    n_built = n_skip_far = n_skip_small = n_skip_hero = 0
    hist = {}
    total_footprint = 0.0
    hmin, hmax = 1e9, -1e9

    for b in buildings:
        for poly in b.get("polys", []):
            if not poly:
                continue
            ring = poly[0]                     # внешнее кольцо (дыры — инкремент 2)
            if len(ring) < 4:
                continue
            # площадь и центр в данных (восток, север)
            area = abs(shoelace(ring))
            if area < 6.0:                     # мусорные микрополигоны
                n_skip_small += 1
                continue
            cx = sum(p[0] for p in ring) / len(ring)
            cy = sum(p[1] for p in ring) / len(ring)
            if abs(cx) > BOUND_M or abs(cy) > BOUND_M:
                n_skip_far += 1
                continue
            # HERO-объекты строятся отдельно (build_palace.py) — их след из фона
            # убираем, чтобы под детальным дворцом не осталось коробки-дубля
            if area > 10000.0 and (cx - 19.0) ** 2 + (cy - 37.0) ** 2 < 60.0 ** 2:
                n_skip_hero += 1
                continue

            # данные → движок: X=восток, Z=-север
            eng = [(p[0], -p[1]) for p in ring[:-1]]  # без повтора замыкающей
            # ориентация CCW в координатах движка (для внешних нормалей/ear-clip)
            if shoelace([(x, z) for x, z in eng]) < 0:
                eng.reverse()

            h = infer_height(area, cx, cy)
            base = min(ground(a, href, x, z) for x, z in eng) - 0.4  # цоколь утоплен
            top = base + h
            hmin = min(hmin, h)
            hmax = max(hmax, h)
            total_footprint += area
            hist[round(h)] = hist.get(round(h), 0) + 1
            n_built += 1

            # --- стены: квад на ребро, внешняя нормаль, UV (периметр, высота) ---
            m = len(eng)
            perim = 0.0
            for k in range(m):
                x0, z0 = eng[k]
                x1, z1 = eng[(k + 1) % m]
                ex, ez = x1 - x0, z1 - z0
                el = (ex * ex + ez * ez) ** 0.5
                if el < 1e-4:
                    continue
                # внешняя нормаль CCW-контура: (dz, -dx)/|..|  (левая сторона — внутрь)
                nx, nz = ez / el, -ex / el
                u0, u1 = perim, perim + el
                perim += el
                b0 = walls.add(x0, base, z0, nx, 0.0, nz, u0, 0.0)
                b1 = walls.add(x1, base, z1, nx, 0.0, nz, u1, 0.0)
                t0 = walls.add(x0, top, z0, nx, 0.0, nz, u0, h)
                t1 = walls.add(x1, top, z1, nx, 0.0, nz, u1, h)
                walls.tri(b0, t0, b1)
                walls.tri(b1, t0, t1)

            # --- кровля: ear-clip внешнего кольца на высоте top, нормаль вверх ---
            tris = ear_clip(eng)
            ridx = [roofs.add(x, top, z, 0.0, 1.0, 0.0, x * 0.25, z * 0.25) for x, z in eng]
            for ia, ib, ic in tris:
                roofs.tri(ridx[ia], ridx[ib], ridx[ic])

    # --- запись citymesh ---
    with open(OUT, "wb") as f:
        f.write(b"CITY")
        f.write(struct.pack("<II", 1, 2))               # версия, число поверхностей
        for s in (walls, roofs):
            f.write(struct.pack("<II", s.vcount(), s.icount()))
            f.write(s.v)
            f.write(s.idx)

    size_mb = os.path.getsize(OUT) / 1e6
    print("== ГОРОД ГАТЧИНЫ (реальные следы, высота выведена) ==")
    print("построено зданий : %d" % n_built)
    print("отсеяно: далеко=%d  мелочь=%d  hero=%d" % (n_skip_far, n_skip_small, n_skip_hero))
    print("след суммарный   : %.0f м² (%.2f га)" % (total_footprint, total_footprint / 1e4))
    print("высоты           : %.1f .. %.1f м" % (hmin, hmax))
    print("стены  △=%d  верш=%d" % (walls.icount() // 3, walls.vcount()))
    print("кровли △=%d  верш=%d" % (roofs.icount() // 3, roofs.vcount()))
    print("буфер citymesh   : %.2f МБ" % size_mb)
    print("гистограмма высот (м → зданий):")
    for k in sorted(hist):
        bar = "#" * min(60, hist[k] * 60 // max(hist.values()))
        print("  %2d  %5d  %s" % (k, hist[k], bar))


if __name__ == "__main__":
    main()
