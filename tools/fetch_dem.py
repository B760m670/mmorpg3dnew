#!/usr/bin/env python3
"""E3 — сбор НАСТОЯЩИХ данных высот Земли (не выдумка, не декаль).

Источник: AWS Terrain Tiles (terrarium) — склейка реальных измерений: SRTM/ASTER
(суша) + GEBCO/ETOPO (дно океанов). Кодировка высоты: h = R*256 + G + B/256 - 32768 м.

1) собирает глобальный DEM (Web Mercator мозаика) → game2/assets/dem/earth_z<Z>.png
2) научно проверяет реальность: известные вершины/впадины числами (высокий зум).

Запуск: python3 tools/fetch_dem.py
"""
import json
import math
import os
import subprocess
import sys

from PIL import Image

ROOT = os.path.join(os.path.dirname(__file__), "..")
ASSET_DIR = os.path.join(ROOT, "game2", "assets", "dem")
TILE = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
TMP = "/tmp/claude-0/-home-user-mmorpg3dnew/45dce9e0-e4bb-550f-b915-c58072470dda/scratchpad/dem_tiles"
GLOBAL_Z = 3  # 8×8=64 тайла = 2048×2048 (~20 км/пиксель) — материки/океаны


def fetch_tile(z, x, y, path):
    r = subprocess.run(["curl", "-sS", "-o", path, "-w", "%{http_code}",
                        TILE.format(z=z, x=x, y=y)], capture_output=True, text=True, timeout=60)
    return r.stdout.strip() == "200" and os.path.exists(path) and os.path.getsize(path) > 0


def decode(im, px, py):
    r, g, b = im.getpixel((px, py))[:3]
    return (r * 256 + g + b / 256.0) - 32768.0


def lonlat_to_merc_px(lat, lon, z):
    n = 256 * (2 ** z)
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    return x, y


def build_global():
    os.makedirs(ASSET_DIR, exist_ok=True)
    os.makedirs(TMP, exist_ok=True)
    n = 2 ** GLOBAL_Z
    size = n * 256
    mosaic = Image.new("RGB", (size, size))
    ok = 0
    for ty in range(n):
        for tx in range(n):
            p = f"{TMP}/{GLOBAL_Z}_{tx}_{ty}.png"
            if not os.path.exists(p):
                if not fetch_tile(GLOBAL_Z, tx, ty, p):
                    print(f"  тайл {tx},{ty} НЕ получен")
                    continue
            try:
                mosaic.paste(Image.open(p).convert("RGB"), (tx * 256, ty * 256))
                ok += 1
            except Exception as e:
                print(f"  тайл {tx},{ty} битый: {e}")
    # декодируем terrarium → высоты (м), даунсемпл до OUT_SIZE, сохраняем raw int16
    import numpy as np
    arr = np.asarray(mosaic, dtype=np.float64)
    elev = arr[..., 0] * 256.0 + arr[..., 1] + arr[..., 2] / 256.0 - 32768.0
    out_size = 1024
    f = size // out_size
    elev_ds = elev.reshape(out_size, f, out_size, f).mean(axis=(1, 3))
    elev_i16 = np.clip(np.round(elev_ds), -32768, 32767).astype("<i2")
    out_bin = os.path.join(ASSET_DIR, "earth_i16.bin")
    elev_i16.tofile(out_bin)
    meta = {"format": "raw int16 little-endian, row-major",
            "width": out_size, "height": out_size, "projection": "web_mercator",
            "lat_limit": 85.0511, "unit": "meters (sea level = 0)",
            "sample": "x=(lon+180)/360*W ; y=(1-asinh(tan(lat))/pi)/2*H"}
    json.dump(meta, open(os.path.join(ASSET_DIR, "meta.json"), "w"), indent=2, ensure_ascii=False)
    print(f"глобальный DEM: {ok}/{n*n} тайлов → {out_bin} ({out_size}×{out_size} int16, %.1f МБ)"
          % (os.path.getsize(out_bin) / 1e6))
    return elev_i16, out_size


def verify_point(name, lat, lon, known, z=11):
    """проверка реальности: точечная высота на высоком зуме vs известное значение"""
    x, y = lonlat_to_merc_px(lat, lon, z)
    tx, ty = int(x // 256), int(y // 256)
    px, py = int(x % 256), int(y % 256)
    p = f"{TMP}/v_{z}_{tx}_{ty}.png"
    if not os.path.exists(p) and not fetch_tile(z, tx, ty, p):
        print(f"  {name}: тайл недоступен")
        return
    im = Image.open(p).convert("RGB")
    # берём максимум/минимум в окне 5×5 (пик/дно подпиксельны)
    vals = [decode(im, min(255, max(0, px + dx)), min(255, max(0, py + dy)))
            for dx in range(-2, 3) for dy in range(-2, 3)]
    got = max(vals, key=abs)
    print(f"  {name:22s} расчёт={got:8.0f} м  известно={known:8d} м  разн={got-known:+6.0f} м")


def main():
    print("=== E3: сбор НАСТОЯЩИХ высот Земли (terrarium DEM) ===")
    build_global()
    print("--- научная проверка реальности (высокий зум, точечно) ---")
    verify_point("Эверест", 27.9881, 86.9250, 8849)
    verify_point("Монблан", 45.8326, 6.8652, 4808)
    verify_point("Мёртвое море", 31.5590, 35.4732, -430)
    verify_point("Гатчина (дворец)", 59.5648, 30.1282, 130)
    verify_point("Марианская впадина", 11.3493, 142.1996, -10935, z=8)
    verify_point("середина Тихого океана", 0.0, -160.0, -5200, z=6)


if __name__ == "__main__":
    main()
