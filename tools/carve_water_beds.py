#!/usr/bin/env python3
"""ДНО ВОДОЁМОВ — фундамент настоящей воды. SRTM отдаёт гладь озера как плоскость
(уровень воды), а не дно, поэтому у воды не было ни глубины, ни берега (плита на
плоском рельефе → z-fight у кромки). Здесь в реальный DEM ВЫРЕЗАЮТСЯ котловины
под реальными контурами озёр: глубина растёт от берега к центру (пологий профиль),
у самого берега 0 (мягкий заход), в центре — до предела по размеру озера.

Тогда: у воды есть глубина (шейдер красит по ней — мелко/глубоко), а БЕРЕГ
возникает сам там, где рельеф пересекает уровень воды. Рельеф вне воды не тронут.

Данные: gatchina_cm.bin (+ backup), water.json. Проверка числами: глубины, что
суша не изменилась. Запуск: python3 tools/carve_water_beds.py
"""
import json
import os
import shutil

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import distance_transform_edt

ROOT = os.path.join(os.path.dirname(__file__), "..")
DEM = os.path.join(ROOT, "game2/assets/dem/gatchina_cm.bin")
WATER = os.path.join(ROOT, "game2/data/real/water.json")
N = 513
STEP = 32.0
HALF = (N - 1) * STEP / 2.0
BOUND = 6800.0
MAX_DIM = 3500.0
SLOPE = 0.09          # м глубины на м от берега (пологое дно)
MAX_DEPTH = 4.5       # предел глубины (озёра Гатчины мелкие)


def to_px(x, y):
    """данные (x=восток, y=север) → пиксель DEM (i=восток, j к югу)"""
    i = (x + HALF) / STEP
    j = (-y + HALF) / STEP        # z=-север
    return i, j


def main():
    raw = np.frombuffer(open(DEM, "rb").read(), "<i2").astype(np.float32).reshape(N, N) / 100.0
    orig = raw.copy()
    data = json.load(open(WATER))

    mask = Image.new("L", (N, N), 0)
    dm = ImageDraw.Draw(mask)
    level_img = np.zeros((N, N), np.float32)   # уровень воды (абс, м) на клетках воды
    lakes = 0
    for r in data:
        for poly in r.get("polys", []):
            o = poly[0]
            if len(o) < 3:
                continue
            xs = [p[0] for p in o]; ys = [p[1] for p in o]
            dim = max(max(xs) - min(xs), max(ys) - min(ys))
            cx = (min(xs) + max(xs)) / 2; cy = (min(ys) + max(ys)) / 2
            if dim >= MAX_DIM or abs(cx) > BOUND or abs(cy) > BOUND:
                continue
            # уровень = медиана рельефа по контуру (гладь = уровень)
            hs = []
            px = []
            for p in o:
                i, j = to_px(p[0], p[1])
                px.append((i, j))
                ii = int(np.clip(i, 0, N - 1)); jj = int(np.clip(j, 0, N - 1))
                hs.append(orig[jj, ii])
            level = float(np.median(hs))
            # растеризуем этот полигон в отдельную маску, чтобы вписать его уровень
            one = Image.new("L", (N, N), 0)
            ImageDraw.Draw(one).polygon(px, fill=1)
            om = np.asarray(one, bool)
            level_img[om] = level
            dm.polygon(px, fill=1)
            lakes += 1

    wmask = np.asarray(mask, bool)
    if not wmask.any():
        print("вода не найдена в пределах — дно не вырезано")
        return

    # расстояние до берега (в метрах) внутри воды
    dist = distance_transform_edt(wmask) * STEP
    depth = np.minimum(dist * SLOPE, MAX_DEPTH)
    bed = level_img - depth
    # вырезаем: под водой высота = дно (только опускаем)
    out = orig.copy()
    out[wmask] = np.minimum(orig[wmask], bed[wmask])

    # --- проверка числами ---
    changed = np.abs(out - orig) > 0.01
    land_changed = changed & (~wmask)
    dvals = (level_img - out)[wmask]
    print("== ДНО ВОДОЁМОВ ==")
    print("озёр вырезано: %d, клеток воды: %d" % (lakes, int(wmask.sum())))
    print("глубина под водой (м): сред %.2f  макс %.2f  у берега(мин) %.2f"
          % (dvals.mean(), dvals.max(), dvals.min()))
    print("клеток суши изменено (должно 0): %d" % int(land_changed.sum()))
    print("рельеф вне воды не тронут:", "OK" if land_changed.sum() == 0 else "ОШИБКА!")

    if not os.path.exists(DEM + ".prebed"):
        shutil.copy(DEM, DEM + ".prebed")
        print("бэкап исходного DEM → gatchina_cm.bin.prebed")
    np.clip(np.round(out * 100.0), -32768, 32767).astype("<i2").tofile(DEM)
    print("DEM с дном записан:", DEM)


if __name__ == "__main__":
    main()
