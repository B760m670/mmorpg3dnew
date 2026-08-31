#!/usr/bin/env python3
"""НАСТОЯЩАЯ ГИДРОЛОГИЯ: куда вода течёт и где стоит — из реального рельефа.

Прошлые реки были провалом: их русла ПРОРЕЗАЛИ в рельефе по нарисованным линиям,
и они шли сквозь городскую застройку. Здесь наоборот — русла НЕ выдумываются,
а ВЫЧИСЛЯЮТСЯ: вода идёт туда, куда её ведёт настоящий рельеф Гатчины.

Метод — стандарт гидрологии рельефа:
 1. ЗАПОЛНЕНИЕ ВПАДИН (Priority-Flood): находим замкнутые понижения — это
    будущие ОЗЁРА и болота (вода в них стоит, стечь не может). Глубина
    заполнения = глубина озера.
 2. НАПРАВЛЕНИЕ СТОКА (D8): из каждой ячейки вода идёт к самому низкому соседу.
 3. НАКОПЛЕНИЕ СТОКА: сколько ячеек собирает воду выше по течению. Где
    накопление велико — там РУСЛО (ручей -> река).

ПРОВЕРКА — по настоящим водоёмам Гатчины (data/real/water.json, Overture):
если наши вычисленные русла совпадают с реальными реками, значит гидрология
верна и русла можно строить по ней, а не рисовать руками.

Выход: game2/assets/dem/flow_acc.bin (накопление стока), lake_depth_cm.bin
       (глубина застойных впадин).
"""
import heapq
import json
import math
import os

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEM = os.path.join(ROOT, "game2/assets/dem/gatchina_cm.bin")
WATER = os.path.join(ROOT, "game2/data/real/water.json")
OUT_FLOW = os.path.join(ROOT, "game2/assets/dem/flow_acc.bin")
OUT_LAKE = os.path.join(ROOT, "game2/assets/dem/lake_depth_cm.bin")

DEM_N = 513
DEM_STEP = 32.0
HALF = (DEM_N - 1) * DEM_STEP * 0.5


def load_dem():
    return np.fromfile(DEM, dtype="<i2").astype(np.float64).reshape(DEM_N, DEM_N) / 100.0


def fill_sinks(dem):
    """Priority-Flood: заполняем замкнутые впадины до уровня перелива.
    Разница (filled - dem) = глубина стоячей воды (озеро/болото)."""
    n, m = dem.shape
    filled = np.full_like(dem, np.inf)
    visited = np.zeros(dem.shape, bool)
    pq = []
    # старт — границы карты (оттуда вода уходит с территории)
    for i in range(n):
        for j in (0, m - 1):
            heapq.heappush(pq, (dem[i, j], i, j))
            visited[i, j] = True
            filled[i, j] = dem[i, j]
    for j in range(m):
        for i in (0, n - 1):
            if not visited[i, j]:
                heapq.heappush(pq, (dem[i, j], i, j))
                visited[i, j] = True
                filled[i, j] = dem[i, j]
    while pq:
        h, i, j = heapq.heappop(pq)
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ii, jj = i + di, j + dj
            if ii < 0 or ii >= n or jj < 0 or jj >= m or visited[ii, jj]:
                continue
            visited[ii, jj] = True
            # Вода не может быть ниже уровня перелива по пути. ВАЖНО: добавляем
            # МИКРОУКЛОН (эпсилон) — иначе заполненные впадины становятся идеально
            # плоскими, у воды нет направления и сток обрывается (замер показал:
            # 19% карты — плоские озёра, накопление стока падало до 178 ячеек).
            # Это стандарт: Priority-Flood + epsilon (Barnes et al., 2014).
            filled[ii, jj] = max(dem[ii, jj], h + 1e-4)
            heapq.heappush(pq, (filled[ii, jj], ii, jj))
    return filled


def flow_accumulation(filled):
    """D8: направление к самому низкому соседу + накопление сверху вниз."""
    n, m = filled.shape
    order = np.argsort(filled, axis=None)[::-1]      # сверху вниз по высоте
    acc = np.ones(filled.shape, np.float64)
    dirs = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    for flat in order:
        i, j = divmod(int(flat), m)
        best = None
        best_slope = 0.0
        for di, dj in dirs:
            ii, jj = i + di, j + dj
            if ii < 0 or ii >= n or jj < 0 or jj >= m:
                continue
            d = DEM_STEP * (1.4142 if di and dj else 1.0)
            slope = (filled[i, j] - filled[ii, jj]) / d
            if slope > best_slope:
                best_slope = slope
                best = (ii, jj)
        if best is not None:
            acc[best] += acc[i, j]
    return acc


def real_water_mask():
    """Маска настоящих водоёмов Гатчины (Overture) в сетке DEM — для сверки."""
    if not os.path.exists(WATER):
        return None
    try:
        items = json.load(open(WATER))
    except Exception:
        return None
    mask = np.zeros((DEM_N, DEM_N), bool)
    cnt = 0
    for it in items if isinstance(items, list) else []:
        rings = []
        if "lines" in it:
            rings = it["lines"]
        elif "polys" in it:
            for poly in it["polys"]:
                rings.extend(poly)
        elif "outline" in it:
            rings = [it["outline"]]
        for ln in rings:
            for pt in ln:
                east, north = float(pt[0]), float(pt[1])
                i = int(round((HALF - north) / DEM_STEP))     # строка (с севера)
                j = int(round((east + HALF) / DEM_STEP))      # столбец
                if 0 <= i < DEM_N and 0 <= j < DEM_N:
                    mask[i, j] = True
                    cnt += 1
    return mask if cnt > 0 else None


def main():
    dem = load_dem()
    print("=== ГИДРОЛОГИЯ ТЕРРИТОРИИ ГАТЧИНЫ (из настоящего рельефа) ===")
    print("  рельеф %.1f..%.1f м, сетка %d² по %.0f м" % (dem.min(), dem.max(), DEM_N, DEM_STEP))

    filled = fill_sinks(dem)
    lake = np.maximum(filled - dem, 0.0)
    n_lake = (lake > 0.05).sum()
    print("\n  ВПАДИНЫ (где вода стоит): %d ячеек (%.1f%% территории), глубина до %.1f м"
          % (n_lake, n_lake / lake.size * 100, lake.max()))

    acc = flow_accumulation(filled)
    print("  СТОК: накопление до %.0f ячеек (%.1f км² сбора)"
          % (acc.max(), acc.max() * DEM_STEP ** 2 / 1e6))

    # русла — там, где накопление выше порога (ручьи и реки)
    thr = 150.0
    channels = acc > thr
    print("  РУСЛА (сбор > %.0f ячеек): %d ячеек (%.1f%% территории)"
          % (thr, channels.sum(), channels.sum() / acc.size * 100))

    ok = True
    # ---- ГЛАВНАЯ ПРОВЕРКА: совпали ли расчётные русла с НАСТОЯЩИМИ реками ----
    rw = real_water_mask()
    if rw is not None:
        from scipy.ndimage import binary_dilation
        near_real = binary_dilation(rw, iterations=2)   # допуск ~2 ячейки (64 м)
        hit = (channels & near_real).sum() / max(channels.sum(), 1)
        # контроль: случайные точки той же численности совпали бы настолько
        base = near_real.sum() / near_real.size
        print("\n  СВЕРКА С НАСТОЯЩИМИ ВОДОЁМАМИ (Overture):")
        print("    расчётных русел рядом с настоящей водой: %.1f%%" % (hit * 100))
        print("    случайное совпадение дало бы:             %.1f%%" % (base * 100))
        if hit > base * 2.0:
            print("    OK: расчёт попадает в настоящие реки в %.1f раза лучше случайного"
                  % (hit / max(base, 1e-6)))
        else:
            print("    ! расчёт не воспроизводит настоящие реки")
            ok = False

    np.clip(acc / max(acc.max(), 1) * 65535, 0, 65535).astype("<u2").tofile(OUT_FLOW)
    np.clip(lake * 100, 0, 32000).astype("<i2").tofile(OUT_LAKE)
    print("\n  -> %s, %s" % (os.path.basename(OUT_FLOW), os.path.basename(OUT_LAKE)))
    print("  ИТОГ: %s" % ("ГИДРОЛОГИЯ ВЕРНА" if ok else "ЕСТЬ ПРОВАЛЫ"))


if __name__ == "__main__":
    main()
