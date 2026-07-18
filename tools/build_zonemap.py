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

# полоса «дорога+обочины» в карте зон, м (сама лента дороги — уже, мешем)
ROAD_HALO_M = {
    "trunk": 16.0, "primary": 14.0, "secondary": 12.0, "tertiary": 10.0,
    "residential": 9.0, "living_street": 9.0, "unclassified": 9.0,
    "unknown": 8.0, "pedestrian": 5.0, "standard_gauge": 10.0,
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
    landcover = json.load(open(os.path.join(REAL, "landcover.json")))
    # порядок: поля → кустарник → ЛЕС (land_cover: Зверинец и массивы) →
    # парки → город → болота → вода
    for z in landuse:
        if CLASS_ZONE.get(z["class"]) == 3:
            draw_layer(d, z, 3)
    for z in landcover:
        if z["class"] == "shrub":
            draw_layer(d, z, 6)
    for z in landcover:
        if z["class"] == "forest":
            draw_layer(d, z, 2)
    for target in (1, 4):
        for z in landuse:
            if CLASS_ZONE.get(z["class"]) == target:
                draw_layer(d, z, target)
    for z in landcover:
        if z["class"] == "wetland":
            draw_layer(d, z, 7)

    # дороги/ж-д ПОВЕРХ зон: полоса «дорога+обочина» — по ней трава не сеется,
    # террейн красит утоптанную полосу под лентой дороги (сама лента — меш)
    roads = json.load(open(os.path.join(REAL, "roads.json")))
    for r in roads:
        wpx = max(1, round(ROAD_HALO_M.get(r["class"], 8.0) / (SIZE_M / N)))
        for line in r.get("lines", []):
            if len(line) < 2:
                continue
            d.line([to_px(q) for q in line], fill=8, width=wpx, joint="curve")

    water = json.load(open(os.path.join(REAL, "water.json")))
    for w in water:
        draw_layer(d, w, 5)

    arr = np.asarray(img, dtype=np.uint8)
    arr.tofile(OUT)
    total = arr.size
    print("зоны:", OUT, f"({os.path.getsize(OUT)/1e6:.1f} МБ)")
    names = {0: "луг", 1: "парк", 2: "лес", 3: "поля", 4: "город", 5: "вода",
             6: "кустарник", 7: "болото", 8: "дорога"}
    for zid, nm in names.items():
        share = (arr == zid).sum() / total * 100.0
        print("  %d %-6s %5.1f%%" % (zid, nm, share))


if __name__ == "__main__":
    main()
