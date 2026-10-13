#!/usr/bin/env python3
"""РЕГИОНАЛЬНЫЙ рельеф для ДАЛЬНЕГО ФОНА — настоящий, не фейк-шум. Тот же
источник и та же локальная система координат (ENU от Гатчинского дворца), что у
основного DEM (fetch_dem_gatchina.py), только КРУПНО и ДАЛЕКО: сетка 257×257 ×
512 м = территория 131 км (±65.5 км). По ней строится «дальний фон» — реальный
силуэт региона до горизонта (залив на СЗ, низины Петербурга на С, Ижорское плато
на Ю), а не бесконечная плоская плита.

Совпадает с основным DEM в центре (тот же ENU, тот же источник terrarium) →
стык фон↔детальный клипмап на ~8 км сходится по высоте.

Выход: game2/assets/dem/gatchina_region_cm.bin + meta. Проверка числами: залив ~0,
плато на юге выше центра. Запуск: python3 tools/build_regional_dem.py
"""
import json
import math
import os
import subprocess

import numpy as np
from PIL import Image

ROOT = os.path.join(os.path.dirname(__file__), "..")
ASSET_DIR = os.path.join(ROOT, "game2", "assets", "dem")
TILE = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
TMP = "/tmp/claude-0/-home-user-mmorpg3dnew/283ce6a4-bcad-5286-9fb2-0f049fba2e1d/scratchpad/region_tiles"

CENTER_LAT = 59.563446           # тот же центр, что у основного DEM (дворец)
CENTER_LON = 30.107487
Z = 9                            # ~155 м/пиксель на этой широте — под шаг 512 м
GRID_N = 257                     # узлов на сторону
STEP_M = 512.0                   # шаг сетки, м → территория 131072 м (±65.5 км)
M_PER_DEG_LAT = 111320.0


def fetch_tile(z, x, y):
    p = f"{TMP}/{z}_{x}_{y}.png"
    if os.path.exists(p) and os.path.getsize(p) > 0:
        return p
    r = subprocess.run(["curl", "-sS", "-o", p, "-w", "%{http_code}",
                        TILE.format(z=z, x=x, y=y)], capture_output=True, text=True, timeout=60)
    if r.stdout.strip() != "200":
        raise RuntimeError(f"тайл {z}/{x}/{y}: HTTP {r.stdout.strip()}")
    return p


def merc_px(lat, lon, z):
    n = 256 * (2 ** z)
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    return x, y


class TileCache:
    def __init__(self, z):
        self.z = z
        self.tiles = {}

    def sample(self, lat, lon):
        x, y = merc_px(lat, lon, self.z)
        x0, y0 = math.floor(x - 0.5), math.floor(y - 0.5)
        fx, fy = (x - 0.5) - x0, (y - 0.5) - y0
        vals = []
        for dy in (0, 1):
            for dx in (0, 1):
                px, py = x0 + dx, y0 + dy
                tx, ty = px // 256, py // 256
                key = (tx, ty)
                if key not in self.tiles:
                    self.tiles[key] = np.asarray(
                        Image.open(fetch_tile(self.z, tx, ty)).convert("RGB"), dtype=np.float64)
                t = self.tiles[key]
                r, g, b = t[py % 256, px % 256]
                vals.append(r * 256.0 + g + b / 256.0 - 32768.0)
        return (vals[0] * (1 - fx) + vals[1] * fx) * (1 - fy) \
            + (vals[2] * (1 - fx) + vals[3] * fx) * fy


def main():
    os.makedirs(ASSET_DIR, exist_ok=True)
    os.makedirs(TMP, exist_ok=True)
    cache = TileCache(Z)
    half = (GRID_N - 1) * STEP_M / 2.0
    m_per_deg_lon = M_PER_DEG_LAT * math.cos(math.radians(CENTER_LAT))

    grid = np.zeros((GRID_N, GRID_N), dtype=np.float64)
    for j in range(GRID_N):                      # j=0 северный край
        north = half - j * STEP_M
        lat = CENTER_LAT + north / M_PER_DEG_LAT
        for i in range(GRID_N):
            east = -half + i * STEP_M
            lon = CENTER_LON + east / m_per_deg_lon
            grid[j, i] = cache.sample(lat, lon)
        if j % 32 == 0:
            print(f"  строка {j}/{GRID_N} (широта {lat:.3f})")

    # деспайк: одиночные иглы-артефакты (ASTER) убираем медианой 3×3 там, где
    # пиксель отклоняется от локальной медианы > 40 м (реальные склоны плавные)
    from scipy.ndimage import median_filter
    med = median_filter(grid, size=3, mode="nearest")
    spikes = np.abs(grid - med) > 40.0
    grid = np.where(spikes, med, grid)
    print("деспайк: убрано игл-артефактов: %d" % int(spikes.sum()))
    # дно/море (terrarium даёт отрицательные над водой) — не топим в бездну,
    # прижимаем к 0 (уровень залива), фон не должен зиять чёрной ямой
    grid = np.maximum(grid, -5.0)
    cm = np.clip(np.round(grid * 100.0), -32768, 32767).astype("<i2")
    out = os.path.join(ASSET_DIR, "gatchina_region_cm.bin")
    cm.tofile(out)
    json.dump({
        "format": "raw int16 LE, row-major, сантиметры",
        "grid_n": GRID_N, "step_m": STEP_M, "size_m": (GRID_N - 1) * STEP_M,
        "center_lat": CENTER_LAT, "center_lon": CENTER_LON,
        "row0": "северный край; x=восток, строки к югу",
        "source": f"terrarium z{Z} (SRTM/ASTER+GEBCO), билинейно, тот же ENU что основной DEM",
    }, open(os.path.join(ASSET_DIR, "meta_region.json"), "w"), indent=2, ensure_ascii=False)

    # --- проверка числами (реальная география региона) ---
    c = GRID_N // 2
    def at_km(east_km, north_km):
        jj = int(round((half - north_km * 1000) / STEP_M))
        ii = int(round((half + east_km * 1000) / STEP_M))
        return grid[np.clip(jj, 0, GRID_N-1), np.clip(ii, 0, GRID_N-1)]
    print(f"\nсетка {GRID_N}×{GRID_N}, шаг {STEP_M:.0f} м, территория {(GRID_N-1)*STEP_M/1000:.0f} км")
    print(f"файл {out} ({os.path.getsize(out)/1e6:.2f} МБ), тайлов: {len(cache.tiles)}")
    print("=== проверка высот региона (м) ===")
    print(f"  центр (дворец, ~100 м): {grid[c, c]:.1f}")
    print(f"  залив Финский СЗ (~-40E,+40N, ~0): {at_km(-40, 42):.1f}")
    print(f"  Петербург С (~+5E,+40N, низина): {at_km(5, 40):.1f}")
    print(f"  Ижорское плато Ю (~0E,-45N, выше): {at_km(0, -45):.1f}")
    print(f"  мин/макс по региону: {grid.min():.1f} / {grid.max():.1f}")
    ok = at_km(-40, 42) < 25.0 and at_km(0, -45) > grid[c, c] - 5.0
    print("  ИТОГ:", "правдоподобно (залив низко, плато на юге выше)" if ok else "ПРОВЕРИТЬ!")


if __name__ == "__main__":
    main()
