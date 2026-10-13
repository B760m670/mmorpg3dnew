#!/usr/bin/env python3
"""СМОТР ВСЕЙ ВОДЫ НА КАРТЕ — не там, куда показали пальцем, а везде.

ЗАЧЕМ ЭТОТ ФАЙЛ. Вода ставится по 166 полигонам и 330 линиям из внешних данных
(Overture), а рельеф у нас СВОЙ. Никто ни разу не проверил, согласны ли они
между собой — правки шли по одному месту за раз, по снимку с телефона. Так
дефекты будут находиться ещё год.

Здесь считается ОДНО И ТО ЖЕ ЧИСЛО для КАЖДОГО водоёма: толща воды = урез минус
высота земли, посчитанная ТЕМ ЖЕ способом, что и в игре (terrain.height:
билинейная выборка общей сетки 32 м, в окне парка — метровая карта с плавным
весом по краю). И раскладывается по случаям:
  ВОДА     — толща больше 5 см: водоём настоящий;
  ПЛЁНКА   — толща от 0 до 5 см: гладь лежит на земле, на кадре это «жидкость
             на траве»; именно её видно на снимках с устройства;
  ПОД ЗЕМЛЁЙ — толща отрицательная: рельеф выше уреза, воду не видно совсем.

Отдельно проверяются РЕКИ. Они строятся лентой шириной 6 м на высоте
«земля минус 10 см» ПО ОСИ. Лента плоская поперёк, а берег наклонный, поэтому
на любом косогоре её край неизбежно вылезает над землёй. Здесь меряется, на
сколько.

Запуск: python3 tools/audit_water.py
"""
import json
import os

import numpy as np

ROOT = os.path.join(os.path.dirname(__file__), "..")
G2 = os.path.join(ROOT, "game2")

N = 513
STEP = 32.0
HALF = (N - 1) * STEP / 2.0
NO_WATER = -32768


def load():
    dem = np.fromfile(os.path.join(G2, "assets/dem/gatchina_cm.bin"),
                      dtype="<i2").reshape(N, N).astype(float) / 100.0
    lvl = np.fromfile(os.path.join(G2, "assets/dem/water_level_cm.bin"),
                      dtype="<i2").reshape(N, N)
    meta = json.load(open(os.path.join(G2, "assets/dem/park_dem.json")))
    pn = int(meta["n"])
    park = np.fromfile(os.path.join(G2, "assets/dem/park_dem_cm.bin"),
                       dtype="<i2").reshape(pn, pn).astype(float) / 100.0
    pw = np.fromfile(os.path.join(G2, "assets/dem/park_water_cm.bin"),
                     dtype="<i2").reshape(pn, pn)
    return dem, lvl, park, pw, meta


DEM, LVL, PARK, PW, META = load()
H_REF = DEM[N // 2, N // 2]
PN = int(META["n"])
PHALF = float(META["half_m"])
PCX = float(META["cx"])
PCY = float(META["cy"])


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
    """Тот же вес метровой карты, что в terrain.park_weight."""
    u = (x - PCX + PHALF) / (2.0 * PHALF)
    v = (PCY + PHALF + z) / (2.0 * PHALF)
    ins = (u > 0) & (v > 0) & (u < 1) & (v < 1)
    e = np.minimum(np.minimum(u, 1 - u), np.minimum(v, 1 - v))
    return np.where(ins, _smoothstep(0.0, 60.0 / (2.0 * PHALF), e), 0.0)


def height(x, z):
    """terrain.height(): мировые метры, ноль — дворец."""
    base = _bilin(DEM, (x + HALF) / STEP, (z + HALF) / STEP, N) - H_REF
    kw = park_weight(x, z)
    pu = np.clip(x - PCX + PHALF, 0, PN - 2)
    pv = np.clip(PCY + PHALF + z, 0, PN - 2)
    ph = _bilin(PARK, pu, pv, PN) - H_REF
    return np.where(kw > 0, base * (1 - kw) + ph * kw, base)


def level_at(x, z):
    """water_real.level_at(): в окне парка — только метровый растр."""
    out = np.full(np.shape(x), np.nan, dtype=float)
    kw = park_weight(x, z)
    # парк
    pi = np.round(x - PCX + PHALF).astype(int)
    pj = np.round(PCY + PHALF + z).astype(int)
    ok = (kw > 0) & (pi >= 0) & (pj >= 0) & (pi < PN) & (pj < PN)
    if ok.any():
        v = PW[np.clip(pj, 0, PN - 1), np.clip(pi, 0, PN - 1)]
        out = np.where(ok & (v != NO_WATER), v / 100.0 - H_REF, out)
    # общая сетка
    ci = np.round((x + HALF) / STEP).astype(int)
    cj = np.round((z + HALF) / STEP).astype(int)
    ok2 = (kw <= 0) & (ci >= 0) & (cj >= 0) & (ci < N) & (cj < N)
    if ok2.any():
        v2 = LVL[np.clip(cj, 0, N - 1), np.clip(ci, 0, N - 1)]
        out = np.where(ok2 & (v2 != NO_WATER), v2 / 100.0 - H_REF, out)
    return out


def poly_inside(P, X, Z):
    inside = np.zeros(len(X), bool)
    n = len(P)
    j = n - 1
    for i in range(n):
        dz = P[j, 1] - P[i, 1]
        c = ((P[i, 1] > Z) != (P[j, 1] > Z)) & \
            (X < (P[j, 0] - P[i, 0]) * (Z - P[i, 1]) / (dz + 1e-12) + P[i, 0])
        inside ^= c
        j = i
    return inside


def audit_lakes(data, cell=4.0):
    print("=== ОЗЁРА И ПРУДЫ (полигоны) ===")
    tot = dict(water=0.0, film=0.0, under=0.0, nolevel=0.0)
    bodies = 0
    worst = []
    for it in data:
        for poly in it.get("polys", []):
            r = np.array(poly[0], dtype=float)
            P = np.column_stack([r[:, 0], -r[:, 1]])
            if np.abs(P).max() > HALF:
                continue                       # за краем территории не строится
            bodies += 1
            xs = np.arange(P[:, 0].min(), P[:, 0].max() + cell, cell)
            zs = np.arange(P[:, 1].min(), P[:, 1].max() + cell, cell)
            X, Z = np.meshgrid(xs, zs)
            X = X.ravel()
            Z = Z.ravel()
            m = poly_inside(P, X, Z)
            if m.sum() == 0:
                continue
            X, Z = X[m], Z[m]
            L = level_at(X, Z)
            T = L - height(X, Z)
            a = cell * cell
            no = np.isnan(L)
            wet = (~no) & (T > 0.05)
            film = (~no) & (T > 0.0) & (T <= 0.05)
            und = (~no) & (T <= 0.0)
            tot["water"] += wet.sum() * a
            tot["film"] += film.sum() * a
            tot["under"] += und.sum() * a
            # ПЛЁНКА В ШИРОКОМ СМЫСЛЕ: там, где растр вовсе не знает воды,
            # но полигон лёг выше земли — рисуется гладь на суше
            lv = np.nanmedian(L) if (~no).any() else np.nan
            if not np.isnan(lv):
                spill = no & (lv - height(X, Z) > 0.0)
                tot["nolevel"] += spill.sum() * a
                if spill.sum() * a > 200.0:
                    worst.append((spill.sum() * a, float(np.mean(X)), float(np.mean(Z))))
    s = sum(tot.values())
    print("  водоёмов построено: %d, суммарная площадь контуров %.0f м²" % (bodies, s))
    for k, name in [("water", "ВОДА (толща > 5 см)"),
                    ("film", "ПЛЁНКА (0..5 см)"),
                    ("under", "ПОД ЗЕМЛЁЙ (рельеф выше уреза)"),
                    ("nolevel", "ГЛАДЬ НА СУШЕ (растр воды не знает)")]:
        print("    %-38s %9.0f м²  %5.1f%%" % (name, tot[k], 100.0 * tot[k] / max(s, 1)))
    worst.sort(reverse=True)
    print("  худшие по площади глади на суше:")
    for a, cx, cz in worst[:6]:
        print("    %7.0f м² около (%6.0f, %6.0f)" % (a, cx, cz))
    return tot


def audit_rivers(data, half_w=3.0):
    print("=== РЕКИ (ленты) ===")
    print("  лента плоская поперёк и лежит на «земля − 10 см» ПО ОСИ;")
    print("  на косогоре её край обязан вылезать над землёй — меряем, на сколько")
    above = []
    seg = 0
    for it in data:
        for line in it.get("lines", []):
            r = np.array(line, dtype=float)
            if len(r) < 2:
                continue
            X = r[:, 0]
            Z = -r[:, 1]
            keep = (np.abs(X) <= HALF) & (np.abs(Z) <= HALF)
            X, Z = X[keep], Z[keep]
            if len(X) < 2:
                continue
            seg += 1
            d = np.gradient(np.column_stack([X, Z]), axis=0)
            nrm = np.column_stack([-d[:, 1], d[:, 0]])
            ln = np.hypot(nrm[:, 0], nrm[:, 1]) + 1e-9
            nrm = nrm / ln[:, None] * half_w
            y = height(X, Z) - 0.10
            for sgn in (1.0, -1.0):
                gx = X + sgn * nrm[:, 0]
                gz = Z + sgn * nrm[:, 1]
                above.append(y - height(gx, gz))
    if not above:
        print("  рек нет")
        return
    a = np.concatenate(above)
    print("  лент: %d, замеров по краям: %d" % (seg, len(a)))
    print("  край ленты ВЫШЕ земли: %.1f%% замеров" % (100.0 * (a > 0).mean()))
    print("  превышение: медиана %.2f м, 90%% %.2f м, макс %.2f м"
          % (np.median(a[a > 0]) if (a > 0).any() else 0,
             np.percentile(a[a > 0], 90) if (a > 0).any() else 0,
             a.max()))
    print("  край НИЖЕ земли (лента утоплена): %.1f%%, глубина медиана %.2f м"
          % (100.0 * (a < 0).mean(), -np.median(a[a < 0]) if (a < 0).any() else 0))


def main():
    data = json.load(open(os.path.join(G2, "data/real/water.json")))
    print("== СМОТР ВОДЫ ПО ВСЕЙ КАРТЕ 16.4 × 16.4 км ==")
    audit_lakes(data)
    audit_rivers(data)


if __name__ == "__main__":
    main()
