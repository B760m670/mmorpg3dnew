#!/usr/bin/env python3
"""ПОЧВА — фундамент под жизнью. Не текстура, а СЛЕДСТВИЕ геологии, рельефа и
влаги (как Солнце из астрономии, трава из влаги). Реальная педология района
Гатчины: край Ижорского ордовикского известнякового плато, ледниковые/озёрные
наносы → дерново-подзолистые почвы; в низинах — торфяно-глеевые; на лугах/пойме
— дерновые гумусные; ближе к известняку — карбонатное влияние (плодороднее).

Из реальных входов (DEM, water.json, landcover.json, класс среза) вычисляются
числами: материнская порода, тип почвы, гумус, влагоёмкость, ПЛОДОРОДИЕ, цвет,
мощность. Плодородие затем питает поле жизни (почва → флора) — настоящая петля.

Выход: game2/assets/life/slice_soilfield.bin (R8×3: fertility, moisture_ret,
type) + meta + превью. Запуск: python3 tools/build_soilfield.py
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

# типы почв района (индекс → имя, цвет влажной почвы)
SOIL = {
    0: ("нет/скала", np.array([0.34, 0.32, 0.30])),
    1: ("скелетная",  np.array([0.40, 0.37, 0.31])),   # тонкая на склонах
    2: ("подзол",     np.array([0.30, 0.28, 0.25])),   # лес: осветлённый горизонт
    3: ("дерновая",   np.array([0.20, 0.15, 0.10])),   # луг: гумус, плодородная
    4: ("торф-глей",  np.array([0.12, 0.11, 0.10])),   # низина/болото: органика, сырость
    5: ("карбонат.",  np.array([0.27, 0.22, 0.16])),   # у известняка: pH выше, плодородна
}


def rasterize(items, cx, cy, half, classes=None):
    img = Image.new("L", (RES, RES), 0)
    dr = ImageDraw.Draw(img)
    for it in items:
        if classes is not None and it.get("class") not in classes:
            continue
        for poly in it.get("polys", []):
            if not poly:
                continue
            pts = [(( x - (cx - half)) / (2 * half) * RES,
                    ((cy + half) - y) / (2 * half) * RES) for x, y in poly[0]]
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
    ys = np.linspace(cy + half, cy - half, RES)
    X, Y = np.meshgrid(xs, ys); Z = -Y

    def demh(x, z):
        u = np.clip((x + DEM_HALF) / DEM_STEP, 0, DEM_N - 1.001)
        v = np.clip((z + DEM_HALF) / DEM_STEP, 0, DEM_N - 1.001)
        i = u.astype(int); j = v.astype(int); fx = u - i; fy = v - j
        a = dem[j, i]; b = dem[j, i + 1]; c = dem[j + 1, i]; d = dem[j + 1, i + 1]
        return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy
    H = demh(X, Z)
    e = cell_m
    gx = (demh(X + e, Z) - demh(X - e, Z)) / (2 * e)
    gn = (demh(X, -(Y + e)) - demh(X, -(Y - e))) / (2 * e)
    slope_deg = np.degrees(np.arctan(np.hypot(gx, gn)))
    lo, hi = np.percentile(H, 5), np.percentile(H, 95)
    elev = np.clip((H - lo) / max(hi - lo, 1e-3), 0, 1)       # 0 низина .. 1 плато
    lowness = 1.0 - elev

    # --- влага (как в поле жизни) ---
    water_mask = rasterize(water, cx, cy, half) > 0.5
    dist_water = distance_transform_edt(~water_mask) * cell_m
    wetland = rasterize(cover, cx, cy, half, {"wetland"})
    forest = rasterize(cover, cx, cy, half, {"forest"})
    wet = np.clip(np.exp(-dist_water / 45.0) + 0.7 * wetland + 0.35 * lowness, 0, 1)

    # --- карбонатное влияние: выше на плато (ближе к известняку) ---
    carb = np.clip(elev * 0.8, 0, 1)

    # класс среза — авторитетнее покрова внутри среза (газон/луг vs роща/лес)
    si = np.clip(((X - cx) / (2 * half) + 0.5) * sn, 0, sn - 1).astype(int)
    sj = np.clip((1 - ((Y - cy) / (2 * half) + 0.5)) * sn, 0, sn - 1).astype(int)
    sc = smap[sj, si]
    wooded = (sc == 2) | (sc == 3) | ((forest > 0.5) & (sc == 0))

    # --- тип почвы (следствие) ---
    soil = np.full((RES, RES), 3, np.uint8)          # по умолчанию дерновая (луг/газон)
    soil[wooded] = 2                                  # роща/лес → подзол
    soil[slope_deg > 22] = 1                          # крутой склон → скелетная
    soil[(wet > 0.6) & (lowness > 0.4)] = 4           # сырая низина → торф-глей
    soil[(wetland > 0.5) | (sc == 7)] = 4             # болото/берег → торф-глей
    soil[(carb > 0.55) & ((sc == 0) | (sc == 1))] = 5  # плато + луг/газон → карбонатная дерновая
    soil[water_mask | (sc == 6)] = 0                 # вода — нет почвы (дно)

    # --- гумус и плодородие (следствие) ---
    organic = np.select(
        [soil == 4, soil == 3, soil == 5, soil == 2, soil == 1],
        [0.85, 0.65, 0.60, 0.25, 0.10], default=0.0)
    moist_ok = 1.0 - np.abs(wet - 0.5) * 1.3          # и не сушь, и не топь
    moist_ok = np.clip(moist_ok, 0, 1)
    waterlog = np.clip((wet - 0.75) * 4, 0, 1)        # переувлажнение душит
    fert = np.clip(organic * (0.4 + 0.6 * moist_ok) * (1 + 0.3 * carb)
                   * (1 - 0.6 * waterlog) * (1 - 0.5 * (slope_deg > 22)), 0, 1)
    moisture_ret = np.clip(0.3 + 0.5 * organic + 0.4 * (soil == 4), 0, 1)

    # --- ДЕФОРМИРУЕМОСТЬ: мокрая органика — вязкая грязь (нога тонет, колея),
    # сухой карбонат/скелет — твёрдо. Меняется с влагой: дождь размягчит, сушь
    # затвердит (данные для рантайм-деформации земли — след, колея, лужи). ---
    deform_base = np.select([soil == 4, soil == 3, soil == 2, soil == 5, soil == 1],
                            [1.00, 0.70, 0.50, 0.35, 0.20], default=0.05)
    deform = np.clip(deform_base * (0.40 + 0.60 * wet), 0, 1)

    # --- запись поля почвы (RGBA: fertility, moisture_ret, deformability, type) ---
    field = np.stack([(fert * 255).astype(np.uint8),
                      (moisture_ret * 255).astype(np.uint8),
                      (deform * 255).astype(np.uint8),
                      soil], -1)
    field.tofile(os.path.join(OUTDIR, "slice_soilfield.bin"))
    json.dump({"n": RES, "cx": cx, "cy": cy, "half_m": half,
               "channels": ["fertility", "moisture_ret", "deformability", "soil_type"],
               "soil_types": {str(k): v[0] for k, v in SOIL.items()}},
              open(os.path.join(OUTDIR, "slice_soilfield.json"), "w"),
              ensure_ascii=False, indent=1)

    # --- превью: цвет почвы, темнее — плодороднее/органика ---
    prev = np.zeros((RES, RES, 3), np.float32)
    for k, (_, col) in SOIL.items():
        m = soil == k
        prev[m] = col
    prev *= (0.75 + 0.5 * fert)[..., None]           # плодородные — насыщеннее
    prev[water_mask] = np.array([0.09, 0.13, 0.16])
    Image.fromarray((np.clip(prev ** (1 / 2.2), 0, 1) * 255).astype(np.uint8)).save(
        os.path.join(ROOT, "..", "soilfield_preview.png"))

    # --- проверка числами ---
    names = {k: v[0] for k, v in SOIL.items()}
    u, c = np.unique(soil, return_counts=True)
    print("== ПОЧВА среза (следствие геологии/рельефа/влаги) ==")
    for k, n in sorted(zip(u, c), key=lambda x: -x[1]):
        print("  %-10s %5.1f%%  плодородие=%.2f" % (
            names[int(k)], 100 * n / soil.size, fert[soil == k].mean()))
    print("плодородие: луг-дерновая %.2f > подзол(лес) %.2f > торф-глей(сыро) %.2f" % (
        fert[soil == 3].mean() if (soil == 3).any() else 0,
        fert[soil == 2].mean() if (soil == 2).any() else 0,
        fert[soil == 4].mean() if (soil == 4).any() else 0))
    hard = (soil == 5) | (soil == 1)
    print("деформируемость: торф-глей(мокро) %.2f > дерновая %.2f > карбонат/скелет(твёрдо) %.2f" % (
        deform[soil == 4].mean() if (soil == 4).any() else 0,
        deform[soil == 3].mean() if (soil == 3).any() else 0,
        deform[hard].mean() if hard.any() else 0))
    print("поле почвы → assets/life/slice_soilfield.bin  превью → soilfield_preview.png")


if __name__ == "__main__":
    main()
