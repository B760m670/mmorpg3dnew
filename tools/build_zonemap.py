#!/usr/bin/env python3
"""Карта зон поверхности из РЕАЛЬНОГО землепользования (шаг 2 генплана).

Растеризует полигоны game2/data/real/landuse.json (+вода) в сетку классов
1024×1024 на территорию 12288 м (12 м/пиксель):
  0 луг (по умолчанию) · 1 парк · 2 лес · 3 поля · 4 город · 5 вода/берег
Выход: game2/assets/dem/zones_1024.bin (raw u8) — террейн-шейдер красит по ней.

Запуск: python3 tools/build_zonemap.py
"""
import json
import os

import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.join(os.path.dirname(__file__), "..")
REAL = os.path.join(ROOT, "game2", "data", "real")
OUT = os.path.join(ROOT, "game2", "assets", "dem", "zones_1024.bin")

N = 1024
SIZE_M = 12288.0
HALF = SIZE_M / 2.0

CLASS_ZONE = {
    "park": 1, "garden": 1, "grass": 1, "meadow": 1, "recreation_ground": 1,
    "cemetery": 1,
    "forest": 2, "wood": 2,
    "farmland": 3, "orchard": 3,
    "residential": 4, "military": 4,
}


def to_px(p):
    # данные: x=восток, y=север; строка 0 растра = северный край
    return ((p[0] + HALF) / SIZE_M * N, (HALF - p[1]) / SIZE_M * N)


def draw_layer(d, rec, zone_id):
    for poly in rec.get("polys", []):
        for k, ring in enumerate(poly):
            if len(ring) < 3:
                continue
            d.polygon([to_px(q) for q in ring], fill=(0 if k > 0 else zone_id))


def main():
    img = Image.new("L", (N, N), 0)
    d = ImageDraw.Draw(img)

    landuse = json.load(open(os.path.join(REAL, "landuse.json")))
    # порядок: сперва крупные общие (поля/лес), потом парки/город поверх
    for target in (3, 2, 1, 4):
        for z in landuse:
            zid = CLASS_ZONE.get(z["class"])
            if zid == target:
                draw_layer(d, z, zid)

    water = json.load(open(os.path.join(REAL, "water.json")))
    for w in water:
        draw_layer(d, w, 5)

    arr = np.asarray(img, dtype=np.uint8)
    arr.tofile(OUT)
    total = arr.size
    print("зоны:", OUT, f"({os.path.getsize(OUT)/1e6:.1f} МБ)")
    names = {0: "луг", 1: "парк", 2: "лес", 3: "поля", 4: "город", 5: "вода"}
    for zid, nm in names.items():
        share = (arr == zid).sum() / total * 100.0
        print("  %d %-6s %5.1f%%" % (zid, nm, share))


if __name__ == "__main__":
    main()
