#!/usr/bin/env python3
"""Реальный рельеф ТЕРРИТОРИИ ГАТЧИНЫ из настоящих измерений (E3-конвейер).

Берёт terrarium-тайлы высокого зума (z13, ~10 м/пиксель на этой широте) вокруг
Гатчины и строит локальную сетку высот в МЕТРАХ на регулярном шаге:
513×513 узлов × 32 м = территория 16384×16384 м, хранение int16 в САНТИМЕТРАХ
(точность 1 см; высоты Гатчины ~60–130 м — в int16-см помещаются с запасом).

Выход: game2/assets/dem/gatchina_cm.bin + meta.json.
Проверка числами: высота у дворца, у Белого озера, диапазон по территории.

Запуск: python3 tools/fetch_dem_gatchina.py
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
TMP = "/tmp/claude-0/-home-user-mmorpg3dnew/45dce9e0-e4bb-550f-b915-c58072470dda/scratchpad/dem_tiles"

CENTER_LAT = 59.5648            # центр территории (дворец) — контент-координата,
CENTER_LON = 30.1282            # применяется ТОЛЬКО в конвейере данных
Z = 13                          # ~9.7 м/пиксель на этой широте
GRID_N = 513                    # узлов на сторону
STEP_M = 32.0                   # шаг сетки, м  → территория 16384 м
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
        """высота (м) билинейно из мозаики тайлов"""
        x, y = merc_px(lat, lon, self.z)
        h = 0.0
        # билинейная интерполяция по 4 соседним пикселям
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
        h = (vals[0] * (1 - fx) + vals[1] * fx) * (1 - fy) \
            + (vals[2] * (1 - fx) + vals[3] * fx) * fy
        return h


def main():
    os.makedirs(ASSET_DIR, exist_ok=True)
    os.makedirs(TMP, exist_ok=True)
    cache = TileCache(Z)
    half = (GRID_N - 1) * STEP_M / 2.0
    m_per_deg_lon = M_PER_DEG_LAT * math.cos(math.radians(CENTER_LAT))

    grid = np.zeros((GRID_N, GRID_N), dtype=np.float64)
    for j in range(GRID_N):                      # j: 0 = северный край
        north = half - j * STEP_M
        lat = CENTER_LAT + north / M_PER_DEG_LAT
        for i in range(GRID_N):
            east = -half + i * STEP_M
            lon = CENTER_LON + east / m_per_deg_lon
            grid[j, i] = cache.sample(lat, lon)
        if j % 64 == 0:
            print(f"  строка {j}/{GRID_N}  (широта {lat:.4f})")

    cm = np.clip(np.round(grid * 100.0), -32768, 32767).astype("<i2")
    out = os.path.join(ASSET_DIR, "gatchina_cm.bin")
    cm.tofile(out)
    meta = {
        "format": "raw int16 LE, row-major, сантиметры",
        "grid_n": GRID_N, "step_m": STEP_M, "size_m": (GRID_N - 1) * STEP_M,
        "center_lat": CENTER_LAT, "center_lon": CENTER_LON,
        "row0": "северный край; x=восток, строки к югу",
        "source": f"terrarium z{Z} (SRTM/ASTER), билинейно",
    }
    json.dump(meta, open(os.path.join(ASSET_DIR, "meta_gatchina.json"), "w"),
              indent=2, ensure_ascii=False)

    # --- проверка числами ---
    print(f"сетка {GRID_N}×{GRID_N}, шаг {STEP_M} м, территория {(GRID_N-1)*STEP_M:.0f} м")
    print(f"файл {out} ({os.path.getsize(out)/1e6:.2f} МБ), тайлов скачано: {len(cache.tiles)}")
    print("=== проверка высот (м) ===")
    print(f"  мин/макс по территории: {grid.min():.1f} / {grid.max():.1f}")
    c = GRID_N // 2
    print(f"  центр (дворец): {grid[c, c]:.1f}")
    # Белое озеро (~600 м СВ от дворца): east=+350, north=+450
    jj = int(round((half - 450) / STEP_M)); ii = int(round((half + 350) / STEP_M))
    print(f"  Белое озеро (~59.5688,30.1344): {grid[jj, ii]:.1f}")
    # край территории на юге (должен быть в разумных пределах 50..150)
    print(f"  южный край (центр): {grid[-1, c]:.1f}")
    ok = 40.0 < grid.min() and grid.max() < 180.0 and grid[c, c] > grid[jj, ii] - 1.0
    print("  ИТОГ:", "правдоподобно (Гатчинская равнина 60–130 м)" if ok else "ПРОВЕРИТЬ!")


if __name__ == "__main__":
    main()
