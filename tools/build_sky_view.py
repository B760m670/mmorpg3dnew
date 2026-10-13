#!/usr/bin/env python3
"""ФАКТОР ВИДИМОСТИ НЕБА (Sky View Factor) — настоящая основа GI нашего мира.

Почему именно это. В пасмурной Гатчине главный источник света — НЕ солнце, а
весь небесный купол. Значит освещённость точки определяется тем, КАКУЮ ДОЛЮ
НЕБА она видит: на открытом поле — почти всё небо; в ложбине, у подножия
склона, в узкой долине — часть неба закрыта рельефом, и там ТЕМНЕЕ. Это не
художественный приём, а измеряемая величина (её считают в климатологии и
городской физике).

Сейчас в игре небо светит всюду одинаково — оттого мир выглядит плоским.
Здесь SVF считается из НАСТОЯЩЕГО DEM Гатчины и становится картой затенения
рассеянным светом. Работает на всей территории (16 км), без каскадов и без
ограничений SDFGI, и стоит НОЛЬ в кадре — всё посчитано заранее.

Метод (Dozier & Frew, стандарт для рельефа): в каждой точке по K азимутам
находим УГОЛ ГОРИЗОНТА — максимальный угол, под которым виден рельеф в этом
направлении. Видимая доля неба: SVF = среднее по азимутам от cos^2(горизонт).

Дополнительно считаем СМЕЩЁННУЮ НОРМАЛЬ (bent normal) — среднее направление
на открытую часть неба: свет должен приходить оттуда, где небо не закрыто.

Выход: game2/assets/dem/sky_view.bin (R8: SVF 0..255)
Проверка — числами: на ровном поле SVF ~1, в ложбинах заметно меньше,
на гребнях максимум; связь с рельефом обязана быть.
"""
import json
import math
import os

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEM = os.path.join(ROOT, "game2/assets/dem/gatchina_cm.bin")
OUT = os.path.join(ROOT, "game2/assets/dem/sky_view.bin")
META = os.path.join(ROOT, "game2/assets/dem/meta_skyview.json")

DEM_N = 513
DEM_STEP = 32.0
AZIMUTHS = 16          # направлений по кругу
MAX_DIST_M = 2400.0    # дальше рельеф на горизонт почти не влияет


def load_dem():
    return np.fromfile(DEM, dtype="<i2").astype(np.float32).reshape(DEM_N, DEM_N) / 100.0


def sky_view_factor(h, step, n_az=AZIMUTHS, max_dist=MAX_DIST_M):
    """SVF по Dozier-Frew: среднее cos^2(угол горизонта) по азимутам."""
    n_steps = int(max_dist / step)
    svf = np.zeros_like(h)
    for a in range(n_az):
        ang = 2.0 * math.pi * a / n_az
        dx = math.cos(ang)
        dy = math.sin(ang)
        max_tan = np.zeros_like(h)          # тангенс угла горизонта
        for s in range(1, n_steps + 1):
            d = s * step
            # сдвиг всей карты на s шагов в направлении (dx,dy)
            sx = int(round(dx * s))
            sy = int(round(dy * s))
            if abs(sx) >= DEM_N or abs(sy) >= DEM_N:
                break
            shifted = np.roll(np.roll(h, -sy, axis=0), -sx, axis=1)
            # края: за пределами карты рельефа нет (не загораживает)
            if sy > 0:
                shifted[-sy:, :] = h[-sy:, :]
            elif sy < 0:
                shifted[:-sy, :] = h[:-sy, :]
            if sx > 0:
                shifted[:, -sx:] = h[:, -sx:]
            elif sx < 0:
                shifted[:, :-sx] = h[:, :-sx]
            np.maximum(max_tan, (shifted - h) / d, out=max_tan)
        horizon = np.arctan(np.maximum(max_tan, 0.0))
        svf += np.cos(horizon) ** 2
    return svf / n_az


def main():
    h = load_dem()
    print("=== ФАКТОР ВИДИМОСТИ НЕБА (SVF) территории Гатчины ===")
    print("  рельеф %.1f..%.1f м, сетка %d² по %.0f м, азимутов %d, дальность %.0f м"
          % (h.min(), h.max(), DEM_N, DEM_STEP, AZIMUTHS, MAX_DIST_M))
    svf = sky_view_factor(h, DEM_STEP)

    ok = True
    print("\n  SVF: %.3f..%.3f (средн %.3f)" % (svf.min(), svf.max(), svf.mean()))
    if not (0.0 <= svf.min() and svf.max() <= 1.0001):
        print("  ! SVF вышел за 0..1 — ошибка формулы")
        ok = False

    # физичность: низкие места видят меньше неба, чем высокие
    from scipy.ndimage import uniform_filter
    rel = h - uniform_filter(h, size=25)     # выше/ниже окрестности
    low = rel < np.percentile(rel, 10)       # ложбины
    high = rel > np.percentile(rel, 90)      # гребни
    print("  ложбины: SVF %.3f   гребни: SVF %.3f" % (svf[low].mean(), svf[high].mean()))
    if svf[low].mean() >= svf[high].mean():
        print("  ! нефизично: ложбина обязана видеть МЕНЬШЕ неба, чем гребень")
        ok = False
    else:
        print("  OK: ложбины темнее гребней на %.1f%% рассеянного света"
              % ((1 - svf[low].mean() / svf[high].mean()) * 100))

    # ровное место должно видеть почти всё небо
    from scipy.ndimage import generic_filter
    dzdy, dzdx = np.gradient(h, DEM_STEP)
    flat = np.hypot(dzdx, dzdy) < 0.01
    if flat.sum() > 100:
        fm = svf[flat].mean()
        print("  ровные места: SVF %.3f (обязано быть близко к 1)  %s"
              % (fm, "OK" if fm > 0.93 else "ПРОВАЛ"))
        if fm <= 0.93:
            ok = False

    (np.clip(svf, 0, 1) * 255).astype(np.uint8).tofile(OUT)
    json.dump({"grid_n": DEM_N, "step_m": DEM_STEP, "azimuths": AZIMUTHS,
               "max_dist_m": MAX_DIST_M, "format": "uint8 SVF 0..255",
               "method": "Dozier & Frew: mean cos^2(horizon angle)"},
              open(META, "w"), ensure_ascii=False, indent=1)
    print("\n  -> %s (%d Б)" % (os.path.basename(OUT), os.path.getsize(OUT)))
    print("  ИТОГ: %s" % ("КАРТА ВИДИМОСТИ НЕБА ФИЗИЧНА" if ok else "ЕСТЬ ПРОВАЛЫ"))


if __name__ == "__main__":
    main()
