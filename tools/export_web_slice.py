#!/usr/bin/env python3
"""СРЕЗ ИГРОВОГО МЕСТА ДЛЯ БРАУЗЕРА.

Снимает квадрат вокруг заданной точки и кладёт в один файл ДВА слоя:
высоту земли и урез воды. Читает ровно те же данные, что читает игра на
телефоне, и повторяет ту же выборку:

  высота  = terrain.height(x, z)  — общая сетка 32 м, а в окне парка метровая
            карта с плавным весом у края (game2/scripts/world/terrain.gd);
  урез    = water_real.level_at(x, z) — в окне парка ТОЛЬКО метровый растр,
            снаружи общий (game2/scripts/world/water_real.gd).

ЗАЧЕМ ТАК СТРОГО. Если браузерная версия возьмёт другую землю, это будет
другая игра, а не та же на другом экране: игрок пойдёт по одному рельефу, а
увидит другой, и вода встанет не на своём уровне. Расхождение проверяется
числами — скрипт печатает свои итоги, и их можно сверить с tools/audit_water.py.

Формат GSL1 (мало и без разбора на клиенте):
  'GSL1' | n:u32 | cell:f32 | ox:f32 | oz:f32 | hMin:f32 | hMax:f32
  n*n u16  высота, линейно от hMin до hMax
  n*n i16  урез в сантиметрах ОТ hMin; -32768 = воды нет
Один узел стоит 4 байта; 513x513 с шагом 1 м это 1028 КБ.
"""
import json
import os
import struct
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
G2 = os.path.join(ROOT, "game2")
DEM_N = 513
DEM_STEP = 32.0
DEM_HALF = (DEM_N - 1) * DEM_STEP * 0.5
NO_WATER = -32768


def load():
    dem = np.fromfile(os.path.join(G2, "assets/dem/gatchina_cm.bin"),
                      dtype="<i2").reshape(DEM_N, DEM_N).astype(np.float64) / 100.0
    lvl = np.fromfile(os.path.join(G2, "assets/dem/water_level_cm.bin"),
                      dtype="<i2").reshape(DEM_N, DEM_N)
    meta = json.load(open(os.path.join(G2, "assets/dem/park_dem.json")))
    pn = int(meta["n"])
    park = np.fromfile(os.path.join(G2, "assets/dem/park_dem_cm.bin"),
                       dtype="<i2").reshape(pn, pn).astype(np.float64) / 100.0
    pw = np.fromfile(os.path.join(G2, "assets/dem/park_water_cm.bin"),
                     dtype="<i2").reshape(pn, pn)
    return dem, lvl, park, pw, meta


DEM, LVL, PARK, PW, META = load()
H_REF = DEM[DEM_N // 2, DEM_N // 2]
PN = int(META["n"])
PHALF = float(META["half_m"])
PCX = float(META["cx"])
PCY = float(META["cy"])


def dem_height(x, z):
    """Общая сетка, билинейно — как Terrain._dem_height."""
    u = np.clip((x + DEM_HALF) / DEM_STEP, 0, DEM_N - 1.001)
    v = np.clip((z + DEM_HALF) / DEM_STEP, 0, DEM_N - 1.001)
    i = u.astype(int)
    j = v.astype(int)
    fx = u - i
    fy = v - j
    a = DEM[j, i] * (1 - fx) + DEM[j, i + 1] * fx
    b = DEM[j + 1, i] * (1 - fx) + DEM[j + 1, i + 1] * fx
    return a * (1 - fy) + b * fy


def park_uv(x, z):
    """Столбец/строка в метровой карте парка — как Terrain.park_height_abs.
    Строка считается от СЕВЕРА, поэтому здесь -z, а не z: перепутать эти знаки
    значит отразить парк, и пруд уедет на другой берег."""
    return (x - PCX + PHALF), (PCY + PHALF - (-z))


def park_height_abs(x, z):
    u, v = park_uv(x, z)
    ok = (u >= 0) & (v >= 0) & (u < PN - 1) & (v < PN - 1)
    uu = np.clip(u, 0, PN - 1.001)
    vv = np.clip(v, 0, PN - 1.001)
    i = uu.astype(int)
    j = vv.astype(int)
    fx = uu - i
    fy = vv - j
    a = PARK[j, i] * (1 - fx) + PARK[j, i + 1] * fx
    b = PARK[j + 1, i] * (1 - fx) + PARK[j + 1, i + 1] * fx
    return np.where(ok, a * (1 - fy) + b * fy, np.nan)


def park_weight(x, z):
    u, v = park_uv(x, z)
    u = u / (2.0 * PHALF)
    v = v / (2.0 * PHALF)
    inside = (u > 0) & (v > 0) & (u < 1) & (v < 1)
    e = np.minimum(np.minimum(u, 1 - u), np.minimum(v, 1 - v))
    t = np.clip(e / (60.0 / (2.0 * PHALF)), 0, 1)
    return np.where(inside, t * t * (3 - 2 * t), 0.0)


def height(x, z):
    """Высота мира; 0 — уровень дворца. Точно как Terrain.height."""
    base = dem_height(x, z) - H_REF
    kw = park_weight(x, z)
    ph = park_height_abs(x, z) - H_REF
    use = (kw > 0) & ~np.isnan(ph)
    return np.where(use, base + (np.nan_to_num(ph) - base) * kw, base)


def level(x, z):
    """Урез; NaN — воды нет. Точно как WaterReal.level_at."""
    out = np.full(x.shape, np.nan)
    # в окне парка — только метровый растр
    u, v = park_uv(x, z)
    kw = park_weight(x, z)
    pi = np.rint(u).astype(int)
    pj = np.rint(v).astype(int)
    inpark = (kw > 0) & (pi >= 0) & (pj >= 0) & (pi < PN) & (pj < PN)
    pv = PW[np.clip(pj, 0, PN - 1), np.clip(pi, 0, PN - 1)]
    out = np.where(inpark & (pv != NO_WATER), pv / 100.0 - H_REF, out)
    # снаружи — общая сетка 32 м
    gi = np.rint((x + DEM_HALF) / DEM_STEP).astype(int)
    gj = np.rint((z + DEM_HALF) / DEM_STEP).astype(int)
    okg = (~inpark) & (gi >= 0) & (gj >= 0) & (gi < DEM_N) & (gj < DEM_N)
    gv = LVL[np.clip(gj, 0, DEM_N - 1), np.clip(gi, 0, DEM_N - 1)]
    out = np.where(okg & (gv != NO_WATER), gv / 100.0 - H_REF, out)
    return out


def main():
    cx = float(sys.argv[1]) if len(sys.argv) > 1 else -16.0
    cz = float(sys.argv[2]) if len(sys.argv) > 2 else -640.0
    size = float(sys.argv[3]) if len(sys.argv) > 3 else 512.0
    cell = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0
    out = sys.argv[5] if len(sys.argv) > 5 else os.path.join(ROOT, "web/data/slice.bin")

    n = int(round(size / cell)) + 1
    ox = cx - size / 2.0
    oz = cz - size / 2.0
    xs = ox + np.arange(n) * cell
    zs = oz + np.arange(n) * cell
    X, Z = np.meshgrid(xs, zs)

    H = height(X, Z)
    L = level(X, Z)

    h_min = float(H.min())
    h_max = float(H.max())
    span = (h_max - h_min) / 65535.0
    hq = np.rint((H - h_min) / span).astype(np.uint16)

    lq = np.full((n, n), NO_WATER, dtype=np.int16)
    wet = ~np.isnan(L)
    # урез хранится в сантиметрах ОТ h_min: диапазон int16 это +-327 м, чего
    # хватает любому месту, а точность 1 см — вдесятеро мельче ряби
    lq[wet] = np.rint((L[wet] - h_min) * 100.0).astype(np.int16)

    depth = np.where(wet, L - H, np.nan)
    real_wet = wet & (depth > 0.02)
    area = float(real_wet.sum()) * cell * cell
    vol = float(np.nansum(np.where(real_wet, depth, 0.0))) * cell * cell

    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "wb") as f:
        f.write(b"GSL1")
        f.write(struct.pack("<Ifffff", n, cell, ox, oz, h_min, h_max))
        f.write(hq.tobytes())
        f.write(lq.tobytes())

    print("срез %s: %d x %d узлов, шаг %g м, охват %g м" % (out, n, n, cell, size))
    print("  начало X %.1f  Z %.1f" % (ox, oz))
    print("  высоты %.2f .. %.2f м (шаг квантования %.1f мм)" % (h_min, h_max, span * 1000))
    print("  воды %.0f м² глубже 2 см, объём %.0f м³, средняя глубина %.2f м"
          % (area, vol, vol / max(area, 1e-9)))
    if real_wet.any():
        print("  урез %.2f .. %.2f м" % (float(L[real_wet].min()), float(L[real_wet].max())))
    print("  файл %.0f КБ" % (os.path.getsize(out) / 1024.0))


if __name__ == "__main__":
    main()
