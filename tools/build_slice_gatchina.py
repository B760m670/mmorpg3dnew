#!/usr/bin/env python3
"""Вертикальный срез №1 — ДВОРЦОВЫЙ ПАРК (дом Николая II).

Карта поверхностей ВЫСОКОГО разрешения (1 м/пиксель) для района дворца —
против 12 м/пиксель у общей карты зон. Здесь «земля везде разная»: партер
у дворца, песчаный плац, гравийные аллеи, рощи с подстилкой, камышовые
берега озёр, открытый луг, вода. Классы (свой богатый набор среза):
  0 луг · 1 газон/партер · 2 роща · 3 лес плотный · 4 аллея (гравий) ·
  5 плац (песок) · 6 вода · 7 берег/камыш · 8 мощёная улица
Контуры — реальные (Overture): вода, парки, аллеи; лес — land_cover.
Плац — исторический полукруг парадного двора у главного фасада.

Выход: game2/assets/dem/slice_palace.bin (R8) + slice_palace.json (границы).
Террейн-шейдер читает карту в границах среза поверх грубой зоны.
Запуск: python3 tools/build_slice_gatchina.py
"""
import json
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.join(os.path.dirname(__file__), "..")
REAL = os.path.join(ROOT, "game2", "data", "real")
OUT_BIN = os.path.join(ROOT, "game2", "assets", "dem", "slice_palace.bin")
OUT_META = os.path.join(ROOT, "game2", "assets", "dem", "slice_palace.json")

# срез вокруг дворца: центр смещён на север (парк и Белое озеро выше дворца)
CX, CY = 0.0, 400.0          # центр среза, м (локальные: x=восток, y=север)
HALF = 950.0                 # полупролёт, м → квадрат 1900 м
MPP = 1.0                    # метр на пиксель
N = int(HALF * 2 / MPP)      # 1900 пикселей

L_MEADOW, L_LAWN, L_GROVE, L_FOREST = 0, 1, 2, 3
L_ALLEY, L_PLAZA, L_WATER, L_SHORE, L_PAVED = 4, 5, 6, 7, 8


def to_px(p):
    # данные x=восток,y=север; строка 0 = север (верх)
    px = (p[0] - CX + HALF) / MPP
    py = (CY + HALF - p[1]) / MPP
    return (px, py)


def draw_polys(d, rec, val):
    for poly in rec.get("polys", []):
        for k, ring in enumerate(poly):
            if len(ring) < 3:
                continue
            d.polygon([to_px(q) for q in ring], fill=(L_MEADOW if k > 0 else val))


def main():
    img = Image.new("L", (N, N), L_MEADOW)
    d = ImageDraw.Draw(img)

    landuse = json.load(open(os.path.join(REAL, "landuse.json")))
    landcover = json.load(open(os.path.join(REAL, "landcover.json")))
    water = json.load(open(os.path.join(REAL, "water.json")))
    roads = json.load(open(os.path.join(REAL, "roads.json")))

    # 1) лес/кустарник (land_cover) → плотный лес как база (внешние массивы,
    #    Зверинец-стиль). Орнаментальный парк ниже перекроет его газоном.
    for z in landcover:
        if z.get("class") in ("forest", "shrub"):
            draw_polys(d, z, L_FOREST)
    # 2) парки/сады → ухоженный газон (партер у дворца, стриженые поляны)
    park_img = Image.new("L", (N, N), 0)
    dp = ImageDraw.Draw(park_img)
    for z in landuse:
        if z.get("class") in ("park", "garden", "recreation_ground"):
            draw_polys(d, z, L_LAWN)
            draw_polys(dp, z, 255)          # маска «внутри орнам. парка»
    # 3) купы деревьев внутри парка: низкочастотный шум ломает сплошной
    #    газон на мозаику поляна/роща (реальный ландшафтный парк, ~40% рощ)
    park_mask = np.asarray(park_img, dtype=np.uint8) > 127
    rng = np.random.default_rng(1894)
    grid = rng.random((40, 40))
    clump = np.asarray(Image.fromarray((grid * 255).astype(np.uint8))
        .resize((N, N), Image.BICUBIC), dtype=np.float32) / 255.0
    arr0 = np.asarray(img, dtype=np.uint8).copy()
    grove = park_mask & (clump > 0.62)
    arr0[grove] = L_GROVE
    img = Image.fromarray(arr0)
    d = ImageDraw.Draw(img)

    # 4) плац — парадный двор у главного фасада дворца (исторический полукруг,
    #    к городу/востоку от дворца). Полукруг радиусом 95 м у (35, 20).
    pcx, pcy = to_px((35.0, 20.0))
    r = 95.0 / MPP
    d.pieslice([pcx - r, pcy - r, pcx + r, pcy + r], 300, 60, fill=L_PLAZA)

    # 5) аллеи/улицы (реальные линии): узкие в парке — гравийные аллеи,
    #    магистрали — мощёные. Ширина из класса.
    def road_style(cls):
        if cls in ("primary", "secondary", "trunk"):
            return L_PAVED, 8.0
        if cls in ("tertiary", "residential", "living_street"):
            return L_PAVED, 6.0
        if cls == "standard_gauge":
            return None, 0.0            # ж/д не в парке-срезе
        return L_ALLEY, 3.5             # пешеходные/прочие → аллея
    for rd in roads:
        val, wm = road_style(rd.get("class", ""))
        if val is None:
            continue
        wpx = max(1, round(wm / MPP))
        for line in rd.get("lines", []):
            if len(line) < 2:
                continue
            d.line([to_px(q) for q in line], fill=val, width=wpx, joint="curve")

    # 6) вода с камышовым берегом: сначала расширенная вода → камыш,
    #    затем сама вода поверх (кольцо шириной ~5 м = берег)
    shore = Image.new("L", (N, N), 0)
    ds = ImageDraw.Draw(shore)
    for w in water:
        for poly in w.get("polys", []):
            for k, ring in enumerate(poly):
                if len(ring) < 3:
                    continue
                ds.polygon([to_px(q) for q in ring], fill=(0 if k > 0 else 255))
    water_mask = np.asarray(shore, dtype=np.uint8) > 127
    shore_band = np.asarray(shore.filter(ImageFilter.MaxFilter(11)),
        dtype=np.uint8) > 127
    arr = np.asarray(img, dtype=np.uint8).copy()
    arr[shore_band] = L_SHORE
    arr[water_mask] = L_WATER

    arr.tofile(OUT_BIN)
    meta = {"cx": CX, "cy": CY, "half_m": HALF, "n": N, "mpp": MPP,
        "classes": {"0": "луг", "1": "газон", "2": "роща", "3": "лес",
            "4": "аллея", "5": "плац", "6": "вода", "7": "берег", "8": "мостовая"}}
    json.dump(meta, open(OUT_META, "w"), ensure_ascii=False, indent=1)

    names = ["луг", "газон", "роща", "лес", "аллея", "плац", "вода", "берег", "мостовая"]
    total = arr.size
    print("срез:", OUT_BIN, f"({N}×{N}, {MPP} м/пкс, {os.path.getsize(OUT_BIN)/1e6:.1f} МБ)")
    for i, nm in enumerate(names):
        share = (arr == i).sum() / total * 100.0
        if share > 0.01:
            print("  %d %-9s %5.1f%%" % (i, nm, share))


if __name__ == "__main__":
    main()
