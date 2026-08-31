#!/usr/bin/env python3
"""ПОВЕРХНОСТЬ ВОДЫ ПО НАШЕЙ БАТИМЕТРИИ — печётся один раз, здесь.

ПОЧЕМУ ЭТО ПЕРЕДЕЛАНО ЦЕЛИКОМ, А НЕ ПОДПРАВЛЕНО.
Раньше вода строилась в игре по 166 контурам и 330 линиям из внешних данных
(Overture), а рельеф у нас свой. Никто не сверял их между собой, и правки шли по
одному месту за раз — по снимку с телефона. Смотр всей карты (tools/audit_water.py)
показал, сколько это стоило:
    настоящая вода (толща > 5 см)   1 450 416 м²   94.1%
    ГЛАДЬ НА СУШЕ                      48 208 м²    3.1%
    под землёй (рельеф выше уреза)     39 520 м²    2.6%
    реки: 88.8% ленты закопано в землю, 11.2% торчит краем до 1.06 м
То есть 3.1% воды по всей карте лежало плёнкой на траве, а 330 речных лент
рисовались, чтобы в основном быть невидимыми.

ПРАВИЛО ТЕПЕРЬ ОДНО: вода есть ровно там, где у НАС есть чаша ниже уреза.
  толща = урез (растр) − высота земли (тот же расчёт, что в terrain.height)
  ячейка воды принимается, если толща > 5 см
Чужой контур используется только чтобы знать, ГДЕ ИСКАТЬ, и какой водоём это.

ГЕОМЕТРИЯ. Сетка 2 м, дальше жадное слияние в прямоугольники: середина озера
сливается в несколько крупных плит, дробность остаётся только у берега. Из 363k
ячеек выходит порядка тысячи прямоугольников — и ОДНА сетка на все озёра вместо
483 отдельных.

РЕКИ НЕ ПЕКУТСЯ. Русел в рельефе нет: их не вырезали, и лента на «земле минус
10 см» может быть только закопанной или плавающей. Пока русла не вырезаны,
честнее не рисовать реки вовсе, чем рисовать плёнку.

Выход: game2/assets/dem/water_surface.bin
  uint32 N, затем N записей: float32 x0, z0, x1, z1, y  (мировые метры)

Запуск: python3 tools/build_water_mesh.py
"""
import json
import os
import struct

import numpy as np

ROOT = os.path.join(os.path.dirname(__file__), "..")
G2 = os.path.join(ROOT, "game2")
OUT = os.path.join(G2, "assets", "dem", "water_surface.bin")

CELL = 2.0            # м, шаг сетки воды
MIN_DEPTH = 0.05      # м, тоньше этого — не вода, а плёнка

N = 513
STEP = 32.0
HALF = (N - 1) * STEP / 2.0
NO_WATER = -32768

DEM = np.fromfile(os.path.join(G2, "assets/dem/gatchina_cm.bin"),
                  dtype="<i2").reshape(N, N).astype(float) / 100.0
LVL = np.fromfile(os.path.join(G2, "assets/dem/water_level_cm.bin"),
                  dtype="<i2").reshape(N, N)
META = json.load(open(os.path.join(G2, "assets/dem/park_dem.json")))
PN = int(META["n"])
PHALF = float(META["half_m"])
PCX = float(META["cx"])
PCY = float(META["cy"])
PARK = np.fromfile(os.path.join(G2, "assets/dem/park_dem_cm.bin"),
                   dtype="<i2").reshape(PN, PN).astype(float) / 100.0
PW = np.fromfile(os.path.join(G2, "assets/dem/park_water_cm.bin"),
                 dtype="<i2").reshape(PN, PN)
H_REF = DEM[N // 2, N // 2]


def _bilin(A, u, v, n):
    i = np.clip(u.astype(int), 0, n - 2)
    j = np.clip(v.astype(int), 0, n - 2)
    fx = u - i
    fy = v - j
    return (A[j, i] * (1 - fx) * (1 - fy) + A[j, i + 1] * fx * (1 - fy)
            + A[j + 1, i] * (1 - fx) * fy + A[j + 1, i + 1] * fx * fy)


def _smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def park_weight(x, z):
    u = (x - PCX + PHALF) / (2.0 * PHALF)
    v = (PCY + PHALF + z) / (2.0 * PHALF)
    ins = (u > 0) & (v > 0) & (u < 1) & (v < 1)
    e = np.minimum(np.minimum(u, 1 - u), np.minimum(v, 1 - v))
    return np.where(ins, _smoothstep(0.0, 60.0 / (2.0 * PHALF), e), 0.0)


def height(x, z):
    """Та же высота, что видит игрок и физика (terrain.height)."""
    base = _bilin(DEM, (x + HALF) / STEP, (z + HALF) / STEP, N) - H_REF
    kw = park_weight(x, z)
    pu = np.clip(x - PCX + PHALF, 0, PN - 2)
    pv = np.clip(PCY + PHALF + z, 0, PN - 2)
    ph = _bilin(PARK, pu, pv, PN) - H_REF
    return np.where(kw > 0, base * (1 - kw) + ph * kw, base)


def level_at(x, z):
    out = np.full(np.shape(x), np.nan, dtype=float)
    kw = park_weight(x, z)
    pi = np.round(x - PCX + PHALF).astype(int)
    pj = np.round(PCY + PHALF + z).astype(int)
    ok = (kw > 0) & (pi >= 0) & (pj >= 0) & (pi < PN) & (pj < PN)
    v = PW[np.clip(pj, 0, PN - 1), np.clip(pi, 0, PN - 1)]
    out = np.where(ok & (v != NO_WATER), v / 100.0 - H_REF, out)
    ci = np.round((x + HALF) / STEP).astype(int)
    cj = np.round((z + HALF) / STEP).astype(int)
    ok2 = (kw <= 0) & (ci >= 0) & (cj >= 0) & (ci < N) & (cj < N)
    v2 = LVL[np.clip(cj, 0, N - 1), np.clip(ci, 0, N - 1)]
    out = np.where(ok2 & (v2 != NO_WATER), v2 / 100.0 - H_REF, out)
    return out


def poly_inside(P, X, Z):
    inside = np.zeros(np.shape(X), bool)
    n = len(P)
    j = n - 1
    for i in range(n):
        dz = P[j, 1] - P[i, 1]
        c = ((P[i, 1] > Z) != (P[j, 1] > Z)) & \
            (X < (P[j, 0] - P[i, 0]) * (Z - P[i, 1]) / (dz + 1e-12) + P[i, 0])
        inside ^= c
        j = i
    return inside


def greedy_rects(mask, ycm):
    """Жадное слияние ячеек в прямоугольники с ОДИНАКОВЫМ урезом.

    Середина водоёма — это одна большая плита, дробность нужна только у берега.
    Без слияния каждая ячейка 2 м давала бы свои два треугольника.
    """
    m = mask.copy()
    h, w = m.shape
    rects = []
    for j in range(h):
        i = 0
        while i < w:
            if not m[j, i]:
                i += 1
                continue
            y0 = ycm[j, i]
            # тянем вправо, пока тот же урез
            i2 = i
            while i2 + 1 < w and m[j, i2 + 1] and ycm[j, i2 + 1] == y0:
                i2 += 1
            # тянем вниз, пока вся строка такая же
            j2 = j
            while j2 + 1 < h and m[j2 + 1, i:i2 + 1].all() \
                    and (ycm[j2 + 1, i:i2 + 1] == y0).all():
                j2 += 1
            m[j:j2 + 1, i:i2 + 1] = False
            rects.append((i, j, i2 + 1, j2 + 1, y0))
            i = i2 + 1
    return rects


def main():
    data = json.load(open(os.path.join(G2, "data/real/water.json")))
    print("== ПОВЕРХНОСТЬ ВОДЫ ПО НАШЕЙ БАТИМЕТРИИ ==")
    print("правило: вода там, где урез выше земли больше чем на %.0f см" % (MIN_DEPTH * 100))
    all_rects = []
    cells_total = 0
    area_kept = 0.0
    area_dropped = 0.0
    bodies = 0
    for it in data:
        for poly in it.get("polys", []):
            r = np.array(poly[0], dtype=float)
            P = np.column_stack([r[:, 0], -r[:, 1]])
            if np.abs(P).max() > HALF:
                continue
            x0 = np.floor(P[:, 0].min() / CELL) * CELL
            x1 = np.ceil(P[:, 0].max() / CELL) * CELL
            z0 = np.floor(P[:, 1].min() / CELL) * CELL
            z1 = np.ceil(P[:, 1].max() / CELL) * CELL
            xs = np.arange(x0, x1 + CELL, CELL)
            zs = np.arange(z0, z1 + CELL, CELL)
            if len(xs) < 2 or len(zs) < 2:
                continue
            # центры ячеек
            cx = (xs[:-1] + xs[1:]) * 0.5
            cz = (zs[:-1] + zs[1:]) * 0.5
            X, Z = np.meshgrid(cx, cz)
            ins = poly_inside(P, X, Z)
            L = level_at(X, Z)
            T = L - height(X, Z)
            keep = ins & ~np.isnan(L) & (T > MIN_DEPTH)
            area_kept += keep.sum() * CELL * CELL
            area_dropped += (ins & ~keep).sum() * CELL * CELL
            cells_total += int(keep.sum())
            if not keep.any():
                continue
            bodies += 1
            # урез квантуем до сантиметра, чтобы плиты сливались
            ycm = np.where(keep, np.round(np.nan_to_num(L) * 100.0), 0).astype(np.int32)
            for (i0, j0, i1, j1, yv) in greedy_rects(keep, ycm):
                all_rects.append((xs[i0], zs[j0], xs[i1], zs[j1], yv / 100.0))
    print("  водоёмов с настоящей чашей: %d из 166" % bodies)
    print("  оставлено воды: %9.0f м² (%d ячеек по %.0f м)" % (area_kept, cells_total, CELL))
    print("  ОТБРОШЕНО как плёнка/подземное: %9.0f м² (%.1f%% контуров)"
          % (area_dropped, 100.0 * area_dropped / max(area_kept + area_dropped, 1)))
    print("  прямоугольников после слияния: %d (△ %d) — было 483 отдельных сетки"
          % (len(all_rects), len(all_rects) * 2))
    with open(OUT, "wb") as f:
        f.write(struct.pack("<I", len(all_rects)))
        for r in all_rects:
            f.write(struct.pack("<5f", *r))
    print("  записано:", OUT, "%.1f КБ" % (os.path.getsize(OUT) / 1024.0))
    print("  РЕКИ НЕ ПЕКУТСЯ: русел в рельефе нет, лента может быть только")
    print("  закопанной или плавающей (замер: 88.8%% / 11.2%%)")


if __name__ == "__main__":
    main()
