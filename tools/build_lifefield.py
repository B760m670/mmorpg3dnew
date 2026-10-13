#!/usr/bin/env python3
"""ПОЛЕ ЖИЗНИ — растительность НЕ подбирается «чтобы походило», а ВЫРАСТАЕТ из
реальных условий (как Солнце в проекте — из астрономии, а не «на глаз»).

Для каждой точки среза вычисляются числами:
  влага   = близость к РЕАЛЬНОЙ воде (water.json) + низины DEM + болота (landcover)
  свет    = экспозиция склона к настоящему Солнцу (Гатчина, полдень солнцестояния
            53.9°) − полог леса (landcover forest)
  вид     = реальный land-cover + класс среза (газон/луг/подлесок/камыш/куст)
Из них СЛЕДУЮТ высота, плотность и сочность покрова: у воды — выше и гуще, на
сухих крутых склонах — голо, под пологом — редкий подлесок. Ничего не задано
вручную, кроме ботанических черт видов (стриженый газон низкий, камыш высокий).

Выход: game2/assets/life/slice_lifefield.bin (R8×3: density,height,lushness) +
meta + превью. Его читает grass.gd, заменяя захардкоженные правила. Проверка —
числами (эмерджентные зависимости печатаются). Запуск: python3 tools/build_lifefield.py
"""
import json
import os

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import distance_transform_edt

from build_city import load_dem, DEM_N, DEM_STEP, DEM_HALF

ROOT = os.path.join(os.path.dirname(__file__), "..")
REAL = os.path.join(ROOT, "game2", "data", "real")
OUTDIR = os.path.join(ROOT, "game2", "assets", "life")
RES = 768
SUN_EL = np.radians(53.9)      # полдень солнцестояния, Гатчина (сверено в проекте)


def rasterize(polys_items, cx, cy, half, classes=None):
    """маска класса(ов) покрова на сетке RES² по реальным полигонам (данные)."""
    img = Image.new("L", (RES, RES), 0)
    dr = ImageDraw.Draw(img)
    for it in polys_items:
        if classes is not None and it.get("class") not in classes:
            continue
        for poly in it.get("polys", []):
            if not poly:
                continue
            ring = poly[0]
            pts = [(( x - (cx - half)) / (2 * half) * RES,
                    ((cy + half) - y) / (2 * half) * RES) for x, y in ring]
            if len(pts) >= 3:
                dr.polygon(pts, fill=255)
    return np.asarray(img, np.float32) / 255.0


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    dem, href = load_dem()
    dem = np.frombuffer(bytes(dem), np.int16).reshape(DEM_N, DEM_N).astype(np.float32) / 100.0 - href
    meta = json.load(open(os.path.join(ROOT, "game2/assets/dem/slice_palace.json")))
    sn = meta["n"]; cx, cy, half = meta["cx"], meta["cy"], meta["half_m"]
    smap = np.frombuffer(open(os.path.join(ROOT, "game2/assets/dem/slice_palace.bin"), "rb").read(sn * sn), np.uint8).reshape(sn, sn)
    water = json.load(open(os.path.join(REAL, "water.json")))
    cover = json.load(open(os.path.join(REAL, "landcover.json")))

    cell_m = 2 * half / RES
    xs = np.linspace(cx - half, cx + half, RES)
    ys = np.linspace(cy + half, cy - half, RES)     # север вверх
    X, Y = np.meshgrid(xs, ys)
    Z = -Y                                           # движок

    # --- рельеф: высота, уклон, нормаль ---
    def demh(x, z):
        u = np.clip((x + DEM_HALF) / DEM_STEP, 0, DEM_N - 1.001)
        v = np.clip((z + DEM_HALF) / DEM_STEP, 0, DEM_N - 1.001)
        i = u.astype(int); j = v.astype(int); fx = u - i; fy = v - j
        a = dem[j, i]; b = dem[j, i + 1]; c = dem[j + 1, i]; d = dem[j + 1, i + 1]
        return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy
    H = demh(X, Z)
    e = cell_m
    gx = (demh(X + e, Z) - demh(X - e, Z)) / (2 * e)   # d h / d east
    gn = (demh(X, -(Y + e)) - demh(X, -(Y - e))) / (2 * e)  # d h / d north
    nrm = np.stack([-gx, -gn, np.ones_like(gx)], -1)
    nrm /= np.linalg.norm(nrm, axis=2, keepdims=True)
    slope_deg = np.degrees(np.arccos(np.clip(nrm[..., 2], -1, 1)))
    lowness = np.clip((np.percentile(H, 60) - H) / 8.0, 0, 1)   # низина относительно среза

    # --- влага: реальная вода + болото + низина ---
    water_mask = rasterize(water, cx, cy, half) > 0.5
    dist_water = distance_transform_edt(~water_mask) * cell_m    # метры до воды
    wetland = rasterize(cover, cx, cy, half, {"wetland"})
    moist = np.clip(np.exp(-dist_water / 45.0) + 0.7 * wetland + 0.3 * lowness, 0, 1)

    # --- свет: экспозиция к Солнцу − полог леса ---
    sun = np.array([0.0, -np.cos(SUN_EL), np.sin(SUN_EL)])       # юг, высоко (east,north,up)
    expo = np.clip((nrm * sun).sum(2), 0, 1)                     # склон к солнцу
    forest = rasterize(cover, cx, cy, half, {"forest"})
    light = np.clip((0.35 + 0.65 * expo) * (1.0 - 0.75 * forest), 0, 1)

    # --- почва питает флору (петля geology→soil→flora): плодородие из поля почвы ---
    soilbin = os.path.join(OUTDIR, "slice_soilfield.bin")
    if os.path.exists(soilbin):
        sf = np.frombuffer(open(soilbin, "rb").read(RES * RES * 4), np.uint8).reshape(RES, RES, 4)
        fert = sf[..., 0].astype(np.float32) / 255.0
    else:
        fert = np.full((RES, RES), 0.5, np.float32)     # без поля почвы — нейтрально

    # --- вид: класс среза поверх реального покрова ---
    shrub = rasterize(cover, cx, cy, half, {"shrub"})
    # 0 нет,1 газон,2 луг,3 подлесок,4 камыш,5 куст
    sp = np.full((RES, RES), 2, np.uint8)               # по умолчанию луг
    sp[forest > 0.5] = 3
    sp[shrub > 0.5] = 5
    sp[wetland > 0.5] = 4
    # класс среза (данные строка0=север) — точнее покрова
    si = np.clip(((X - cx) / (2 * half) + 0.5) * sn, 0, sn - 1).astype(int)
    sj = np.clip((1 - ((Y - cy) / (2 * half) + 0.5)) * sn, 0, sn - 1).astype(int)
    sc = smap[sj, si]
    sp[sc == 1] = 1          # газон
    sp[sc == 0] = 2          # луг
    sp[(sc == 2) | (sc == 3)] = 3   # роща/лес → подлесок
    sp[sc == 7] = 4          # берег → камыш
    for empty in (4, 5, 6, 8):      # аллея/плац/вода/мостовая — без травы
        sp[sc == empty] = 0
    sp[water_mask] = 0

    # ботанические черты вида: (высота_м, база_плотности)
    trait_h = np.array([0.0, 0.10, 0.55, 0.30, 1.10, 0.70])
    trait_d = np.array([0.0, 1.00, 0.80, 0.35, 0.70, 0.55])
    base_h = trait_h[sp]; base_d = trait_d[sp]

    # --- СЛЕДСТВИЕ: рост из влаги и света; сухой крутой склон — голо ---
    lush = (np.clip(0.30 + 0.70 * moist, 0, 1) * np.clip(0.30 + 0.70 * light, 0, 1)
            * np.clip(0.35 + 0.65 * fert, 0, 1))          # рост требует и плодородия почвы
    bare_steep = ((slope_deg > 30) & (moist < 0.30)).astype(np.float32)
    height = base_h * (0.5 + 0.5 * lush)
    density = np.clip(base_d * lush * (0.5 + 0.5 * fert) * (1 - bare_steep), 0, 1)
    lushness = np.clip(lush, 0, 1)

    # --- запись поля ---
    HMAX = 1.3
    field = np.stack([
        (density * 255).astype(np.uint8),
        (np.clip(height / HMAX, 0, 1) * 255).astype(np.uint8),
        (lushness * 255).astype(np.uint8)], -1)
    field.tofile(os.path.join(OUTDIR, "slice_lifefield.bin"))
    json.dump({"n": RES, "cx": cx, "cy": cy, "half_m": half, "h_max_m": HMAX,
               "channels": ["density", "height/h_max", "lushness"]},
              open(os.path.join(OUTDIR, "slice_lifefield.json"), "w"),
              ensure_ascii=False, indent=1)

    # --- превью: сочность→цвет, высота→яркость, где нет травы — темно ---
    dry = np.array([0.55, 0.50, 0.22]); wet = np.array([0.10, 0.42, 0.12])
    veg = dry * (1 - lushness[..., None]) + wet * lushness[..., None]
    veg *= (0.35 + 0.65 * np.clip(height / HMAX, 0, 1))[..., None]
    veg[density < 0.05] = np.array([0.08, 0.09, 0.10])
    veg[water_mask] = np.array([0.09, 0.13, 0.16])
    Image.fromarray((np.clip(veg ** (1 / 2.2), 0, 1) * 255).astype(np.uint8)).save(
        os.path.join(ROOT, "..", "lifefield_preview.png"))

    # --- проверка ЧИСЛАМИ: жизнь следует из условий ---
    veg_mask = density > 0.05
    near = veg_mask & (dist_water < 30)
    far = veg_mask & (dist_water > 150) & (wetland < 0.5)
    open_m = veg_mask & (forest < 0.5) & (sp == 2)
    under = veg_mask & (forest > 0.5)
    print("== ПОЛЕ ЖИЗНИ среза (вырастает из реальных условий) ==")
    print("покрытие травой : %.1f%% площади" % (100 * veg_mask.mean()))
    print("высота у воды<30м: %.2f м   на суше>150м: %.2f м   (влага→рост)" % (
        height[near].mean() if near.any() else 0, height[far].mean() if far.any() else 0))
    print("плотность откр.луг: %.2f   подлесок(лес): %.2f   (полог→редко)" % (
        density[open_m].mean() if open_m.any() else 0, density[under].mean() if under.any() else 0))
    print("голо на сухом крутом склоне: %.1f%% таких ячеек" % (
        100 * bare_steep[(slope_deg > 30)].mean() if (slope_deg > 30).any() else 0))
    print("средняя сочность: у воды %.2f / на суше %.2f" % (
        lushness[near].mean() if near.any() else 0, lushness[far].mean() if far.any() else 0))
    print("поле → assets/life/slice_lifefield.bin (%d²)  превью → lifefield_preview.png" % RES)


if __name__ == "__main__":
    main()
