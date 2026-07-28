#!/usr/bin/env python3
"""ДНО ВОДОЁМОВ — фундамент настоящей воды.

ИЗМЕРЕНО, зачем это нужно (озеро «Тёплая», 2007 м, самое большое у нас):
    берег по DEM: мин 77.00  макс 86.48  медиана 79.76 м
    «дно» в центре по DEM:   79.95 м
    толща воды при уровне=медиана берега: -0.19 м  → воды НЕ ВИДНО
Причина: SRTM меряет ОТРАЖЕНИЕ ОТ ГЛАДИ. Внутри озера в DEM записан уровень
воды, а не дно. Чаши нет, глубины нет, шейдер красит воду по толще → ALPHA=0.
Разброс берега 9.5 м — это шум радара, а не рельеф: урез озера по определению
горизонтален.

Что делаем (и почему именно так):
 1. УРОВЕНЬ = медиана DEM по контуру. Медиана, а не минимум: минимум ловит
    выброс шума (у «Тёплой» минимум на 2.8 м ниже дна — вода закапывалась).
 2. ВНУТРИ контура высота задаётся ЗАНОВО (не min с исходной): исходные
    значения внутри — это гладь, их сохранять нечего. Дно = уровень минус
    глубина.
 3. ГЛУБИНА растёт от берега вглубь с уклоном SLOPE и упирается в MAX_DEPTH.
    Профиль сам масштабируется: лужа 40 м получит 0.7 м, озеро — предел.
 4. БЕРЕГ (кольцо суши в одну клетку) поджимается так, чтобы он был ВЫШЕ уреза
    на 0.3..3.0 м. Без этого шум ±9 м торчит островами посреди озера.
 5. УРОВЕНЬ ЗАПИСЫВАЕТСЯ В РАСТР water_level_cm.bin — движок берёт его оттуда,
    а не выводит заново из уже прорезанного DEM (иначе уровень уползал бы вниз
    с каждым прогоном).

Идемпотентно: всегда начинаем с бэкапа .prebed (чистый DEM без вмешательств).

Данные: gatchina_cm.bin(.prebed), water.json. Запуск:
    python3 tools/carve_water_beds.py
"""
import json
import os
import shutil

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import binary_dilation, distance_transform_edt

ROOT = os.path.join(os.path.dirname(__file__), "..")
DEM = os.path.join(ROOT, "game2/assets/dem/gatchina_cm.bin")
LEVEL_BIN = os.path.join(ROOT, "game2/assets/dem/water_level_cm.bin")
WATER = os.path.join(ROOT, "game2/data/real/water.json")
N = 513
STEP = 32.0
HALF = (N - 1) * STEP / 2.0
BOUND = 6800.0
MAX_DIM = 3500.0

# ГЛУБИНА. Опора на измеренное: Белое озеро в Гатчинском парке — макс 3.5 м,
# Чёрное ~2 м. Это ледниковая равнина, озёра мелкие. Уклон дна 0.09 м/м —
# пологое ложе, за 40 м от берега 3.5 м (совпадает с промерами Белого).
SLOPE = 0.09
MAX_DEPTH = 3.5
BANK_MIN = 0.3        # м: берег обязан быть выше уреза хотя бы на столько
BANK_MAX = 3.0        # м: и не выше — иначе шум DEM встаёт стеной у воды
NO_WATER = -32768     # маркер «здесь воды нет» в растре уровня


def to_px(x, y):
    """данные (x=восток, y=север) → пиксель DEM (i=восток, j к югу)"""
    i = (x + HALF) / STEP
    j = (-y + HALF) / STEP        # z=-север
    return i, j


def main():
    # всегда от чистого DEM: инструмент можно гонять сколько угодно раз
    if os.path.exists(DEM + ".prebed"):
        shutil.copy(DEM + ".prebed", DEM)
    else:
        shutil.copy(DEM, DEM + ".prebed")
        print("бэкап исходного DEM → gatchina_cm.bin.prebed")
    orig = np.frombuffer(open(DEM, "rb").read(), "<i2").astype(np.float32).reshape(N, N) / 100.0
    data = json.load(open(WATER))

    mask = Image.new("L", (N, N), 0)
    dm = ImageDraw.Draw(mask)
    level_img = np.zeros((N, N), np.float32)   # уровень воды (абс, м) на клетках воды
    lakes = 0
    biggest = None
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
            hs = []
            px = []
            for p in o:
                i, j = to_px(p[0], p[1])
                px.append((i, j))
                ii = int(np.clip(i, 0, N - 1)); jj = int(np.clip(j, 0, N - 1))
                hs.append(orig[jj, ii])
            one = Image.new("L", (N, N), 0)
            ImageDraw.Draw(one).polygon(px, fill=1)
            om = np.asarray(one, bool)
            if not om.any():
                continue                        # мельче клетки DEM — чаши не будет
            # УРЕЗ. Медиана берега — устойчивая оценка, но её мало: ИЗМЕРЕНО, что
            # так у 145 водоёмов из 166 гладь вставала ВЫШЕ земли сразу за
            # контуром (до 11.7 м). Со стороны это плоская плита, парящая над
            # ландшафтом, — именно её видно с высоты как «воду, накрывшую всё».
            # Причина в данных: пруд 20-100 м меньше клетки DEM (32 м), и сетка
            # просто не знает, где у него урез.
            # Поэтому урез дополнительно ПРИЖИМАЕТСЯ к самой низкой земле в
            # кольце шириной 2 клетки снаружи контура. Вода тогда не может
            # оказаться выше берега ни в одной точке — переливаться некуда.
            ring = binary_dilation(om, iterations=2) & (~om)
            level = float(np.median(hs))
            if ring.any():
                level = min(level, float(orig[ring].min()))
            level_img[om] = level
            dm.polygon(px, fill=1)
            lakes += 1
            if biggest is None or dim > biggest[0]:
                biggest = (dim, r.get("name"), level, om)

    wmask = np.asarray(mask, bool)
    if not wmask.any():
        print("вода не найдена в пределах — дно не вырезано")
        return

    # --- ЧАША: глубина от расстояния до берега (полклетки = сам урез) ---
    dist_m = np.maximum(distance_transform_edt(wmask) - 0.5, 0.0) * STEP
    depth = np.minimum(dist_m * SLOPE, MAX_DEPTH)
    out = orig.copy()
    out[wmask] = (level_img - depth)[wmask]     # внутри — ЗАНОВО: там было не дно

    # --- БЕРЕГ: клетки суши в один шаг от воды поджимаем к урезу ---
    # уровень ближайшей воды для каждой клетки суши
    _, (jy, ix) = distance_transform_edt(~wmask, return_indices=True)
    near_level = level_img[jy, ix]
    dist_land = distance_transform_edt(~wmask)
    # ТОЛЬКО ПОДНИМАЕМ. Раньше здесь стояло clip(orig - level, 0.3, 3.0), и
    # берег, который был выше уреза на 10 м, СРЕЗАЛСЯ до +3 м. Это уничтожало
    # настоящий рельеф и роняло землю ниже уреза СОСЕДНЕГО водоёма — отсюда
    # часть переливов. Берег теперь либо остаётся как есть, либо подтягивается
    # до уреза плюс BANK_MIN, если он оказался ниже воды.
    bank = (~wmask) & (dist_land <= 1.5)
    out[bank] = np.maximum(orig, near_level + BANK_MIN)[bank]

    # --- ПРОВЕРКА ЧИСЛАМИ ---
    thick = (level_img - out)[wmask]            # толща воды в каждой клетке
    land_far = (~wmask) & (~bank)
    print("== ДНО ВОДОЁМОВ ==")
    print("озёр с чашей: %d, клеток воды: %d, клеток берега поджато: %d"
          % (lakes, int(wmask.sum()), int(bank.sum())))
    print("толща воды (м): мин %.2f  сред %.2f  макс %.2f"
          % (thick.min(), thick.mean(), thick.max()))
    print("вода везде выше дна:", "OK" if thick.min() > 0.0 else "ОШИБКА!")
    print("берег над урезом (м): мин %.2f  макс %.2f"
          % ((out - near_level)[bank].min(), (out - near_level)[bank].max()))
    dl = np.abs(out - orig)[land_far].max() if land_far.any() else 0.0
    print("суша вне воды и берега изменена (должно 0.00): %.2f м" % dl)
    if biggest is not None:
        dim, name, lev, om = biggest
        t = (lev - out)[om]
        print("самое большое — «%s» (%.0f м): урез %.2f м, толща мин %.2f сред %.2f макс %.2f м"
              % (name, dim, lev, t.min(), t.mean(), t.max()))

    np.clip(np.round(out * 100.0), -32768, 32767).astype("<i2").tofile(DEM)
    # растр уровня: движок ставит гладь ровно сюда, не пересчитывая из DEM
    lvl = np.full((N, N), NO_WATER, np.int32)
    lvl[wmask] = np.round(level_img[wmask] * 100.0).astype(np.int32)
    np.clip(lvl, -32768, 32767).astype("<i2").tofile(LEVEL_BIN)
    print("DEM с дном записан:", DEM)
    print("растр уровня воды записан:", LEVEL_BIN)


if __name__ == "__main__":
    main()
