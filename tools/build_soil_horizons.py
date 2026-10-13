#!/usr/bin/env python3
"""ГОРИЗОНТЫ НА ПОВЕРХНОСТЬ: какой почвенный слой обнажён в каждой точке.

Почему земля разная: профиль (tools/soil_profile.py) везде один и тот же ПО
ПОРЯДКУ, но сверху он СРЕЗАН по-разному — это настоящая педология, КАТЕНА
(закономерная смена почв вдоль склона):
  крутой склон  -> смыв (эрозия) -> верх сорван, обнажается бурый B, ниже морена C;
  ровное плато  -> профиль целый -> сверху подстилка O и гумус A;
  вогнутая низина -> намыв (аккумуляция) -> гумус МОЩНЕЕ, темнее, сырее.

Считаем из НАСТОЯЩЕГО рельефа (DEM Гатчины) три величины:
  slope     — уклон (градусы): чем круче, тем сильнее смыв;
  curvature — кривизна: выпуклая (бугор) смывается, вогнутая (ложбина) намывается;
  twi       — топографический индекс влажности: где копится вода.
Из них — «срез профиля» (м): сколько сорвано сверху, минус намыв.

Выход: game2/assets/dem/soil_horizons.bin (R8: индекс горизонта на поверхности)
     + soil_cut_cm.bin (int16: срез профиля, см — для мощности слоёв в шейдере)
Проверка — числами: доли горизонтов, связь со склоном, что на крутых склонах
обнажается глубокий слой, а в низинах — гумус.
"""
import json
import os
import struct

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEM = os.path.join(ROOT, "game2/assets/dem/gatchina_cm.bin")
PROFILE = os.path.join(ROOT, "game2/data/real/soil_profile.json")
OUT_H = os.path.join(ROOT, "game2/assets/dem/soil_horizons.bin")
OUT_CUT = os.path.join(ROOT, "game2/assets/dem/soil_cut_cm.bin")
OUT_WET = os.path.join(ROOT, "game2/assets/dem/soil_drain.bin")
META = os.path.join(ROOT, "game2/assets/dem/meta_soil.json")

DEM_N = 513
DEM_STEP = 32.0


def load_dem():
    a = np.fromfile(DEM, dtype="<i2").astype(np.float64) / 100.0
    return a.reshape(DEM_N, DEM_N)


def terrain_metrics(h, step):
    """Уклон (град), кривизна (1/м, + выпуклая), индекс влажности."""
    # градиенты (np.gradient учитывает края корректно)
    dzdy, dzdx = np.gradient(h, step)
    slope_rad = np.arctan(np.hypot(dzdx, dzdy))
    slope_deg = np.degrees(slope_rad)

    # кривизна: лапласиан высоты (выпуклость > 0 = бугор/гребень)
    d2y, d2x = np.gradient(dzdy, step)[0], np.gradient(dzdx, step)[1]
    curv = d2x + d2y

    # индекс влажности TWI = ln(a / tan(slope)); a — площадь сбора (упрощ.:
    # чем ниже точка относительно окрестности, тем больше сбор)
    from scipy.ndimage import uniform_filter
    local_mean = uniform_filter(h, size=15)
    rel = local_mean - h                      # >0 = точка ниже окрестности
    twi = rel / (np.tan(slope_rad) + 0.02)
    return slope_deg, curv, twi


def soil_cut_m(slope_deg, curv, twi, cover=None):
    """СРЕЗ ПРОФИЛЯ (м): сколько верха сорвано (+) или намыто (−).

    Физика: смыв растёт с уклоном (нелинейно — как в USLE, ~slope^1.3),
    усиливается на выпуклостях (гребни оголяются), а в вогнутых сырых
    ложбинах идёт накопление (отрицательный срез = мощнее гумус).
    """
    # потенциальный смыв от уклона (голая почва): до ~1.5 м на крутых склонах
    erosion = 0.30 * np.power(np.maximum(slope_deg, 0.0), 1.30)
    # выпуклость оголяет, вогнутость копит (curv нормируем на характерный масштаб)
    cn = np.clip(curv / 0.004, -1.5, 1.5)
    erosion += 0.9 * np.maximum(cn, 0.0)
    # ПОКРОВ (C-фактор USLE) гасит смыв: под лесом почти нет, на пашне/в городе полный
    if cover is not None:
        erosion = erosion * cover
    # намыв в сырых ложбинах (мощнее гумус)
    accum = 0.30 * np.clip(twi / 12.0, 0.0, 1.5)
    return erosion - accum


ZONES = os.path.join(ROOT, "game2/assets/dem/zones_1024.bin")
ZONES_N = 1024
ZONE_SIZE_M = 12288.0
# 0 луг, 1 парк, 2 лес, 3 поля, 4 город, 5 берег/дно, 6 кустарник, 7 болото, 8 дорога


def sample_zones():
    """Карта землепользования в узлах DEM (та же выборка, что в шейдере)."""
    if not os.path.exists(ZONES):
        return None
    z = np.fromfile(ZONES, dtype=np.uint8).reshape(ZONES_N, ZONES_N)
    half = (DEM_N - 1) * DEM_STEP * 0.5
    i = np.arange(DEM_N)
    east = -half + i * DEM_STEP                 # по столбцам
    north = half - i * DEM_STEP                 # по строкам
    zx = np.clip(((east + ZONE_SIZE_M * 0.5) / ZONE_SIZE_M * ZONES_N).astype(int), 0, ZONES_N - 1)
    zy = np.clip(((-north + ZONE_SIZE_M * 0.5) / ZONE_SIZE_M * ZONES_N).astype(int), 0, ZONES_N - 1)
    return z[np.ix_(zy, zx)]


# C-фактор USLE: во сколько раз покров СНИЖАЕТ смыв (реальные справочные
# величины). Лес и парк защищают почву корнями и опадом — смыв почти нулевой;
# луг слабее; пашня открыта; в городе почва вскрыта стройкой и подсыпана.
COVER_C = {
    0: 0.05,   # луг (задернован)
    1: 0.01,   # парк (деревья + газон)
    2: 0.004,  # лес (опад + корни — почти нет смыва)
    3: 0.35,   # поля (пашня открыта)
    4: 1.00,   # город (грунт вскрыт/нарушен)
    5: 0.50,   # берег (подмывается)
    6: 0.02,   # кустарник
    7: 0.01,   # болото
    8: 1.00,   # дорога (полотно, срезано)
}


def cover_factor(zone):
    c = np.full(zone.shape, 0.05, dtype=np.float64)
    for k, v in COVER_C.items():
        c[zone == k] = v
    return c


def apply_landcover(idx, zone):
    """ПОКРОВ решает, что лежит СВЕРХУ (настоящая педология):
      лес/парк/кустарник -> есть подстилка O (опад);
      луг/поля           -> подстилки НЕТ, сверху дернина/пахотный гумус A;
      город/дорога       -> почва нарушена, срезана до B (насыпь/подсыпка);
      болото             -> торфянистый верх (считаем как O, но сырой);
      берег/дно          -> оглеенный, верх смыт до E/B.
    """
    out = idx.copy()
    litter = np.isin(zone, [1, 2, 6, 7])        # парк, лес, кустарник, болото
    grass = np.isin(zone, [0, 3])               # луг, поля
    urban = np.isin(zone, [4, 8])               # город, дороги
    shore = zone == 5
    # там, где подстилки быть не может — поднимаем минимум до A (индекс 1)
    out[(grass | urban | shore) & (out < 1)] = 1
    # город/дорога: грунт нарушен и подсыпан — не мельче B (индекс 3)
    out[urban & (out < 3)] = 3
    # берег: верх смыт — не мельче E (индекс 2)
    out[shore & (out < 2)] = 2
    # под лесом подстилка сохраняется даже на умеренном склоне (корни держат)
    out[litter & (out == 1)] = 0
    return out


def main():
    prof = json.load(open(PROFILE))
    hz = prof["horizons"]
    # верхние границы горизонтов (глубина от исходной поверхности)
    tops = []
    z = 0.0
    for h in hz:
        tops.append(z)
        z += h["thick_m"]
    tops = np.array(tops)

    h = load_dem()
    slope, curv, twi = terrain_metrics(h, DEM_STEP)
    zone = sample_zones()
    # СМЫВ ЗАВИСИТ ОТ ПОКРОВА (C-фактор USLE): под лесом почва защищена корнями
    # и опадом — профиль целый даже на склоне; пашня и город смываются.
    cov = cover_factor(zone) if zone is not None else None
    cut = soil_cut_m(slope, curv, twi, cov)

    # какой горизонт на поверхности: первый, чья НИЖНЯЯ граница глубже среза
    bottoms = np.array([tops[i] + hz[i]["thick_m"] for i in range(len(hz))])
    cut_pos = np.maximum(cut, 0.0)
    idx = np.searchsorted(bottoms, cut_pos, side="right").astype(np.int16)
    idx = np.clip(idx, 0, len(hz) - 1)

    # ПОКРОВ: что лежит сверху — решает не только рельеф, но и растительность/
    # использование земли (подстилка только под лесом, в городе грунт нарушен)
    zone = sample_zones()
    if zone is not None:
        idx_before = idx.copy()
        idx = apply_landcover(idx, zone)
        changed = (idx != idx_before).sum() / idx.size
        print("  покров (реальное землепользование) изменил %.0f%% точек" % (changed * 100))

    print("=== ГОРИЗОНТЫ НА ПОВЕРХНОСТИ (территория Гатчины, %d×%d) ===" % (DEM_N, DEM_N))
    print("  рельеф: уклон %.1f..%.1f° (средн %.1f°)" % (
        slope.min(), slope.max(), slope.mean()))
    print("  срез профиля: %.2f..%.2f м (средн %.2f м)" % (cut.min(), cut.max(), cut.mean()))
    print("\n  %-4s %-34s %8s" % ("код", "горизонт", "доля"))
    total = idx.size
    ok = True
    for i, hh in enumerate(hz):
        frac = (idx == i).sum() / total
        print("  %-4s %-34s %7.1f%%" % (hh["code"], hh["name"], frac * 100))
    # физичность: подавляющая часть территории — целый профиль (O/A сверху)
    top_frac = ((idx == 0) | (idx == 1)).sum() / total
    if top_frac < 0.5:
        print("  ! нефизично: почти вся территория оголена — эрозия завышена")
        ok = False
    else:
        print("\n  OK: %.0f%% территории — целый профиль (подстилка/гумус сверху)" % (top_frac * 100))

    # связь со склоном: на крутых склонах обязан обнажаться более глубокий слой
    steep = slope > np.percentile(slope, 95)
    flat = slope < np.percentile(slope, 20)
    if idx[steep].mean() <= idx[flat].mean():
        print("  ! нефизично: на крутых склонах не обнажаются глубокие горизонты")
        ok = False
    else:
        print("  OK: крутые склоны обнажают слой №%.2f, пологие №%.2f (смыв работает)" % (
            idx[steep].mean(), idx[flat].mean()))

    # ГЛАВНЫЙ признак C-фактора: на ОДИНАКОВО крутых склонах лес обязан
    # сохранить почву, а открытая земля (пашня/город) — потерять
    if zone is not None:
        st = slope > np.percentile(slope, 90)
        forest = st & np.isin(zone, [2, 1])          # лес/парк на склоне
        bare = st & np.isin(zone, [3, 4, 8])         # пашня/город/дорога на склоне
        if forest.sum() > 50 and bare.sum() > 50:
            cf, cb = cut[forest].mean(), cut[bare].mean()
            if cf >= cb:
                print("  ! нефизично: лес не защищает склон от смыва")
                ok = False
            else:
                print("  OK: на равных склонах лес срезан на %.2f м, открытая земля на %.2f м"
                      % (cf, cb))

    # намыв: в сырых ложбинах гумус должен быть МОЩНЕЕ (срез отрицательный)
    wet = twi > np.percentile(twi, 90)
    if cut[wet].mean() >= cut.mean():
        print("  ! нефизично: в ложбинах нет накопления гумуса")
        ok = False
    else:
        print("  OK: в ложбинах срез %.2f м против %.2f м в среднем (намыв гумуса)" % (
            cut[wet].mean(), cut.mean()))

    # ПОЛЕ ДРЕНАЖА (для влаги/луж): куда стекает и где стоит вода.
    # twi — топографический индекс влажности (высокий = ложбина, вода копится),
    # k_sat поверхностного слоя — как быстро впитывает (глина держит, песок пьёт).
    ksat = np.array([h["k_sat"] for h in hz])
    surf_k = ksat[idx]
    # 0 = сухо/дренирует, 255 = мокро/застаивается
    twi_n = np.clip((twi - np.percentile(twi, 5)) /
                    (np.percentile(twi, 98) - np.percentile(twi, 5) + 1e-9), 0, 1)
    slow = np.clip((np.log10(1e-3) - np.log10(surf_k)) / 6.0, 0, 1)   # медленно впитывает
    wetf = np.clip(0.65 * twi_n + 0.35 * slow, 0, 1)
    (wetf * 255).astype(np.uint8).tofile(OUT_WET)
    print("  поле дренажа: ложбины+водоупор -> %s (средн %.2f)" % (
        os.path.basename(OUT_WET), wetf.mean()))

    idx.astype(np.uint8).tofile(OUT_H)
    np.clip(cut * 100.0, -32000, 32000).astype("<i2").tofile(OUT_CUT)
    json.dump({
        "grid_n": DEM_N, "step_m": DEM_STEP,
        "horizons": [h["code"] for h in hz],
        "format_h": "uint8 индекс горизонта на поверхности",
        "format_cut": "int16 срез профиля, см (+ смыто, − намыто)",
        "source": "катена по настоящему DEM Гатчины (уклон/кривизна/влажность)",
    }, open(META, "w"), ensure_ascii=False, indent=1)
    print("\n  -> %s (%d Б)" % (os.path.basename(OUT_H), os.path.getsize(OUT_H)))
    print("  -> %s (%d Б)" % (os.path.basename(OUT_CUT), os.path.getsize(OUT_CUT)))
    print("\n  ИТОГ: %s" % ("ПОЛЕ ГОРИЗОНТОВ ФИЗИЧНО" if ok else "ЕСТЬ ПРОВАЛЫ"))


if __name__ == "__main__":
    main()
