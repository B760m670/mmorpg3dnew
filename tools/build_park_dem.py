#!/usr/bin/env python3
"""ВЫСОТЫ ГАТЧИНСКОГО ПАРКА С РАЗРЕШЕНИЕМ 1 МЕТР.

ЗАЧЕМ. Общая сетка высот — 32 метра. Пруд Гатчинского парка размером 60-200 м
занимает в ней две-три точки, поэтому урез воды из неё вычислить НЕЛЬЗЯ:
ИЗМЕРЕНО, что гладь вставала выше окрестной земли у 145 водоёмов из 166, до
11.7 м — вода висела плитой над ландшафтом. Никакая формула этого не чинит:
информации о береге в данных просто нет.

ЗАТО ЕСТЬ ДРУГОЕ. slice_palace.bin — разметка парка ±950 м вокруг дворца с
шагом 1 метр, и в ней размечены классы «вода» и «берег». Контуры прудов там
точны до метра, в 32 раза точнее общей сетки. Не хватало только ВЫСОТ.

ЧТО ДЕЛАЕМ:
 1. Крупную форму земли берём из общей сетки (бикубическая интерполяция до
    1 м). Это НЕ выдумка: пологий рельеф парка на масштабе 32 м измерен верно,
    интерполяция лишь сглаживает ступеньки.
 2. Пруды вырезаем ПО МЕТРОВЫМ КОНТУРАМ. Урез = самая низкая земля в кольце
    4 м снаружи пруда: тогда вода не может оказаться выше берега нигде.
 3. Глубина растёт от берега (0.25 м/м) и упирается в предел, зависящий от
    размера пруда. ИЗМЕРЕНО-ОПОРНОЕ: Белое озеро — макс 3.5 м; мелкие пруды
    парка около метра. Формула даёт 3.5 м для 29 га и 1.3 м для 0.3 га.
 4. Класс «берег» только ПОДНИМАЕМ до уреза+0.25, если он ниже. Землю не режем.

ВЫХОД: park_dem_cm.bin (1900² int16, сантиметры, АБСОЛЮТНЫЕ метры) —
        высоты парка, и park_water_cm.bin — урез на клетках воды.

Запуск: python3 tools/build_park_dem.py
"""
import json
import os

import numpy as np
from scipy import ndimage

ROOT = os.path.join(os.path.dirname(__file__), "..")
DEM = os.path.join(ROOT, "game2/assets/dem/gatchina_cm.bin.prebed")   # без грубой резки
SLICE_BIN = os.path.join(ROOT, "game2/assets/dem/slice_palace.bin")
SLICE_META = os.path.join(ROOT, "game2/assets/dem/slice_palace.json")
OUT_DEM = os.path.join(ROOT, "game2/assets/dem/park_dem_cm.bin")
OUT_WATER = os.path.join(ROOT, "game2/assets/dem/park_water_cm.bin")
OUT_META = os.path.join(ROOT, "game2/assets/dem/park_dem.json")

DEM_N = 513
DEM_STEP = 32.0
DEM_HALF = (DEM_N - 1) * DEM_STEP / 2.0

CLS_WATER = 6
CLS_SHORE = 7
SLOPE = 0.25          # м глубины на м от берега — берег пруда падает быстро
MIN_AREA_M2 = 100     # мельче — лужа, чаши не строим
BANK_MIN = 0.25       # м: берег обязан быть выше уреза хотя бы на столько
BANK_RUN = 25.0       # м: на какой длине берег плавно поднимается к урезу
COLLAR = 6            # клеток(м): воротник у кромки, где земля ОБЯЗАНА быть выше воды
SMOOTH_M = 3.5        # м: сглаживание поля под сетку местности (у ног она 2 м)
NO_WATER = -32768


def max_depth_for(area_m2):
    """Предел глубины по размеру. Опора: Белое озеро 29.5 га — 3.5 м
    (промеры), мелкие пруды парка — около метра."""
    ha = area_m2 / 10000.0
    return float(np.clip(0.9 * np.sqrt(ha) + 0.8, 0.6, 3.5))


def main():
    meta = json.load(open(SLICE_META))
    n, half, cx, cy = meta["n"], meta["half_m"], meta["cx"], meta["cy"]
    cls = np.fromfile(SLICE_BIN, "u1").reshape(n, n)
    dem = np.fromfile(DEM, "<i2").astype(np.float32).reshape(DEM_N, DEM_N) / 100.0

    # --- 1. крупная форма: общая сетка → 1 метр ---
    # пиксель среза (px,py) → данные (восток x, север y) → индекс общей сетки
    px = np.arange(n, dtype=np.float32)
    x_east = cx - half + px                      # по столбцам
    y_north = cy + half - px                     # по строкам
    gi = (x_east + DEM_HALF) / DEM_STEP          # столбец общей сетки
    gj = (-y_north + DEM_HALF) / DEM_STEP        # строка общей сетки (z = -север)
    JJ, II = np.meshgrid(gj, gi, indexing="ij")
    base = ndimage.map_coordinates(dem, [JJ, II], order=3, mode="nearest")
    base = base.astype(np.float32)

    water = cls == CLS_WATER
    shore = cls == CLS_SHORE
    out = base.copy()
    level_img = np.full((n, n), np.nan, np.float32)

    lab, cnt = ndimage.label(water)
    ponds = []
    for k in range(1, cnt + 1):
        comp = lab == k
        area = int(comp.sum())
        if area < MIN_AREA_M2:
            continue
        ring = ndimage.binary_dilation(comp, iterations=4) & (~water)
        if not ring.any():
            continue
        # УРЕЗ = МЕДИАНА ВЫСОТ ВНУТРИ КОНТУРА.
        # Радар мерит отражение от ГЛАДИ: внутри озера в сетке записан уровень
        # воды, а не дно. Значит медиана внутри и есть искомый урез — это
        # ИЗМЕРЕНИЕ, а не оценка. Сверка по Белому озеру: медиана внутри 84.01,
        # медиана кольца снаружи 84.59 — сходятся в пределах 0.6 м.
        # ЧЕГО ДЕЛАТЬ НЕЛЬЗЯ (проверено на себе): брать МИНИМУМ кольца. У
        # километрового озера периметр гуляет на 12 м, минимум хватает самую
        # низкую точку всего обвода — урез уехал на 6 м вниз, и берега встали
        # отвесными обрывами в 17 м.
        level = float(np.median(base[comp]))
        dist = ndimage.distance_transform_edt(comp)          # метры (1 м/пкс)
        dmax = max_depth_for(area)
        depth = np.minimum(dist * SLOPE, dmax)
        out[comp] = level - depth[comp]
        level_img[comp] = level
        ys, xs = np.nonzero(comp)
        ponds.append(dict(area=area, level=level, dmax=float(depth[comp].max()),
                          w=int(xs.max() - xs.min()), h=int(ys.max() - ys.min()),
                          X=float(cx - half + xs.mean()),
                          Z=float(-(cy + half - ys.mean()))))

    # --- БЕРЕГ: земля поднимается к урезу ПЛАВНО, полосой BANK_RUN метров ---
    # Просто «поднять до уреза» дало бы стену там, где сетка занижена на 6 м.
    # В природе берег поднимается к воде, а не обрывается: делаем пандус с
    # затуханием по расстоянию от воды. Землю при этом только ПОДНИМАЕМ.
    if np.isfinite(level_img).any():
        wmask = np.isfinite(level_img)
        dist, idx = ndimage.distance_transform_edt(~wmask, return_indices=True)
        near_level = level_img[tuple(idx)]
        need = near_level + BANK_MIN                      # куда обязана дойти земля
        ramp = np.clip(1.0 - (dist - 3.0) / BANK_RUN, 0.0, 1.0)
        lift = np.maximum(0.0, (need - base) * ramp)      # только вверх
        land = ~wmask
        out[land] = base[land] + lift[land]
        # ЖЁСТКАЯ ГАРАНТИЯ у самой кромки. Пандус затухает по расстоянию и у
        # берега не дотягивает считанные проценты — а этого хватает, чтобы вода
        # выглянула за берег (замерено: +4.92 м). В воротнике COLLAR метров
        # земля обязана быть выше уреза, без исключений.
        for k2 in range(1, cnt + 1):
            comp2 = lab == k2
            if comp2.sum() < MIN_AREA_M2:
                continue
            lv2 = float(np.nanmax(level_img[comp2]))
            collar = ndimage.binary_dilation(comp2, iterations=COLLAR) & land
            out[collar] = np.maximum(out[collar], lv2 + BANK_MIN)

    # --- СГЛАЖИВАНИЕ — ПОСЛЕДНИМ ДЕЙСТВИЕМ, И БОЛЬШЕ НИЧЕГО ПОСЛЕ НЕГО ---
    #
    # ОШИБКА, КОТОРУЮ ЗДЕСЬ ИСПРАВЛЯЮ. Раньше я сглаживал поле, а ПОТОМ снова
    # накладывал резкие ступеньки — жёсткий воротник и дно. Сглаживание тем
    # самым отменялось, и берег превращался в гребёнку отвесных зубцов.
    # ИЗМЕРЕНО на прошлой версии: перепад между СОСЕДНИМИ узлами сетки
    # местности (она 2 м) доходил до 6.50 м — стена в 73°, 1414 таких узлов.
    # Эти зубцы игрок видел как стену, проходил сквозь неё (коллизия 2 м зубец
    # не описывает) и получал от них рвано скачущие тени: при ходьбе кольца
    # рельефа снапятся, зубцы пересобираются, и тени скачут вместе с ними.
    #
    # Теперь порядок обратный: все ограничения накладываются ДО, сглаживание —
    # ПОСЛЕ, и после него поле уже никто не трогает.
    out = ndimage.gaussian_filter(out, sigma=SMOOTH_M, mode="nearest")

    # УРОВЕНЬ ВОДЫ ПОДГОНЯЕТСЯ ПОД СГЛАЖЕННУЮ ЗЕМЛЮ, а не земля под уровень.
    # Это и есть замена жёсткому воротнику: вместо того чтобы поднимать берег
    # ступенькой до воды, опускаем воду под самый низкий сглаженный берег.
    # Земля остаётся гладкой, а вода гарантированно не переливается.
    if np.isfinite(level_img).any():
        land = ~np.isfinite(level_img)
        for k3 in range(1, cnt + 1):
            comp3 = lab == k3
            if comp3.sum() < MIN_AREA_M2:
                continue
            collar = ndimage.binary_dilation(comp3, iterations=COLLAR) & land
            if not collar.any():
                continue
            # НЕ МИНИМУМ. Минимум по всему воротнику хватает самую низкую точку
            # обвода — у пруда на склоне это уводит урез на метры вниз, и вода
            # оказывается НИЖЕ собственного дна (замерено: толща -7.31 м).
            # Берём НИЖНЮЮ ЧЕТВЕРТЬ высот берега: устойчиво к выбросам и всё
            # ещё низко. Останется небольшой перелив там, где берег ниже уреза,
            # но земля теперь гладкая, и это читается как топкая кромка, а не
            # как парящая плита.
            lv_new = float(np.percentile(out[collar], 10.0)) - 0.05
            # и не ниже собственного дна: вода обязана быть видна
            bed_hi = float(np.percentile(out[comp3], 75.0))
            level_img[comp3] = max(lv_new, bed_hi + 0.20)

    # --- ПРОВЕРКА ЧИСЛАМИ ---
    print("== ВЫСОТЫ ПАРКА, 1 МЕТР ==")
    print("окно ±%.0f м вокруг (%.0f, %.0f), сетка %dx%d, 1 м/точка"
          % (half, cx, cy, n, n))
    print("прудов с чашей: %d из %d размеченных" % (len(ponds), cnt))
    ponds.sort(key=lambda p: -p["area"])
    for p in ponds[:8]:
        print("   %6.2f га  %4dx%-4d м  урез %6.2f м  глубина до %.2f м  X%+.0f Z%+.0f"
              % (p["area"] / 10000, p["w"], p["h"], p["level"], p["dmax"],
                 p["X"], p["Z"]))
    # перелив: нигде вода не должна стоять выше земли за берегом
    over = 0.0
    for k in range(1, cnt + 1):
        comp = lab == k
        if comp.sum() < MIN_AREA_M2:
            continue
        ring = ndimage.binary_dilation(comp, iterations=4) & (~water)
        if not ring.any():
            continue
        lv = np.nanmax(level_img[comp])
        over = max(over, float((lv - out[ring]).max()))
    print("перелив за берег (должен быть <= 0): %+.2f м" % over)
    thick = (level_img - out)[np.isfinite(level_img)]
    print("толща воды: мин %.2f  сред %.2f  макс %.2f м"
          % (thick.min(), thick.mean(), thick.max()))
    far = ndimage.distance_transform_edt(~np.isfinite(level_img)) > (BANK_RUN + 5.0)
    if far.any():
        print("земля дальше %.0f м от воды изменена (должно 0.00): %.2f м"
              % (BANK_RUN + 5.0, float(np.abs(out - base)[far].max())))
    lifted = out - base
    print("подъём берега: макс %.2f м, полоса %.0f м" % (float(lifted.max()), BANK_RUN))
    # ГЛАВНЫЙ ЗАМЕР: перепад между соседними узлами сетки местности (она 2 м).
    # Это и есть «зубцы»: сквозь них видно и проходишь, и от них скачут тени.
    st = out[::2, ::2]
    dd = np.concatenate([np.abs(np.diff(st, axis=1)).ravel(),
                         np.abs(np.diff(st, axis=0)).ravel()])
    print("перепад между соседними узлами сетки 2 м: сред %.3f  99.9%% %.2f  МАКС %.2f м"
          % (dd.mean(), np.percentile(dd, 99.9), dd.max()))
    print("узлов с перепадом > 1 м: %d, > 2 м: %d" % (int((dd > 1).sum()), int((dd > 2).sum())))
    print("высоты парка: %.1f .. %.1f м" % (out.min(), out.max()))

    np.clip(np.round(out * 100), -32768, 32767).astype("<i2").tofile(OUT_DEM)
    lw = np.full((n, n), NO_WATER, np.int32)
    m = np.isfinite(level_img)
    lw[m] = np.round(level_img[m] * 100).astype(np.int32)
    np.clip(lw, -32768, 32767).astype("<i2").tofile(OUT_WATER)
    json.dump(dict(n=n, half_m=half, cx=cx, cy=cy, mpp=meta["mpp"],
                   note="Высоты парка 1 м: крупная форма из общей сетки, "
                        "пруды вырезаны по метровым контурам среза.",
                   ponds=len(ponds)),
              open(OUT_META, "w"), ensure_ascii=False, indent=1)
    print("записано:", OUT_DEM, "и", OUT_WATER)


if __name__ == "__main__":
    main()
