#!/usr/bin/env python3
"""РУСЛА РЕК — вода как следствие рельефа: канал вдоль реальной оси реки, идущий
МОНОТОННО ПОД УКЛОН (вода течёт вниз), который вода и заполняет. Магистральные
реки Гатчины: Парица, Колпанская/Колпанка, парковые каналы. Осевые линии —
реальные (Overture, water.json). Мелкие ручьи/канавы (тоньше клетки DEM 32 м)
пока пропускаем — им нужна более мелкая геометрия.

Что делает:
  1. вдоль оси считает рельеф; определяет НИЗ по течению (к более низкому концу);
  2. строит МОНОТОННО убывающую поверхность воды (ws[k]=min(ws[k-1], релеф-запас))
     — река нигде не течёт вверх; где рельеф поднимается, вода стоит заводью;
  3. вырезает канал (bed=ws-глубина) в DEM по ширине класса;
  4. пишет rivers_carved.json — ленты воды (осевые точки: мир x,y,z + полуширина +
     направление течения) для меша воды.

Данные: gatchina_cm.bin (уже с озёрными днами; + backup .prerivers), water.json →
game2/assets/dem/rivers_carved.json. Проверка числами: уклон русла (убывает),
глубины. Запуск: python3 tools/carve_rivers.py
"""
import json
import os
import shutil

import numpy as np

ROOT = os.path.join(os.path.dirname(__file__), "..")
DEM = os.path.join(ROOT, "game2/assets/dem/gatchina_cm.bin")
WATER = os.path.join(ROOT, "game2/data/real/water.json")
OUT = os.path.join(ROOT, "game2/assets/dem/rivers_carved.json")
N = 513
STEP = 32.0
HALF = (N - 1) * STEP / 2.0
BOUND = 7200.0
# класс → (полуширина м, глубина м, запас над водой до бровки м)
CLASS = {
    "river": (22.0, 2.4, 0.3),
    "canal": (14.0, 1.6, 0.25),
}
MAXDROP = 3.0     # вода не ниже локального рельефа больше чем на столько (иначе
                  # монотонность прорезала бы глубокие щели через подъёмы) →
                  # на подъёмах — мелкий перекат, а не 16-метровая прорезь


def main():
    dem = np.frombuffer(open(DEM, "rb").read(), "<i2").astype(np.float64).reshape(N, N) / 100.0
    orig = dem.copy()
    href = dem[N // 2, N // 2]
    data = json.load(open(WATER))

    def hpx(wx, wz):
        i = int(np.clip((wx + HALF) / STEP, 0, N - 1))
        j = int(np.clip((wz + HALF) / STEP, 0, N - 1))
        return dem[j, i]

    ribbons = []
    carved_cells = 0
    slopes_ok = 0
    slopes_tot = 0

    for r in data:
        spec = CLASS.get(r.get("class"))
        if spec is None:
            continue
        half_w, depth, freeboard = spec
        for line in r.get("lines", []):
            # в мир: x=восток, z=-север; отфильтровать в пределах
            pts = []
            for p in line:
                wx, wz = float(p[0]), -float(p[1])
                if abs(wx) > BOUND or abs(wz) > BOUND:
                    if len(pts) >= 2:
                        break
                    pts = []
                    continue
                pts.append((wx, wz))
            if len(pts) < 2:
                continue
            # уплотнить до ~STEP/2
            dense = [pts[0]]
            for k in range(1, len(pts)):
                a = np.array(dense[-1]); b = np.array(pts[k])
                d = np.linalg.norm(b - a)
                m = max(1, int(d / (STEP * 0.5)))
                for s in range(1, m + 1):
                    dense.append(tuple(a + (b - a) * s / m))
            dense = np.array(dense)
            hs = np.array([hpx(x, z) for x, z in dense])
            # низ по течению — к более низкому концу; идём сверху вниз
            if hs[0] < hs[-1]:
                dense = dense[::-1]; hs = hs[::-1]
            # монотонно убывающая поверхность воды
            ws = np.empty(len(hs))
            ws[0] = hs[0] - freeboard
            for k in range(1, len(hs)):
                ws[k] = max(min(ws[k - 1], hs[k] - freeboard), hs[k] - MAXDROP)
            bed = ws - depth
            # проверка уклона
            slopes_tot += 1
            if ws[-1] <= ws[0] + 1e-6:
                slopes_ok += 1
            # вырезать канал: клетки в радиусе half_w от осевых точек
            rad = int(np.ceil(half_w / STEP)) + 1
            for k, (wx, wz) in enumerate(dense):
                ci = int((wx + HALF) / STEP); cj = int((wz + HALF) / STEP)
                for dj in range(-rad, rad + 1):
                    for di in range(-rad, rad + 1):
                        i = ci + di; j = cj + dj
                        if not (0 <= i < N and 0 <= j < N):
                            continue
                        cx = -HALF + i * STEP; cz = -HALF + j * STEP
                        dist2 = (cx - wx) ** 2 + (cz - wz) ** 2
                        if dist2 <= half_w * half_w:
                            # чаша: по оси глубоко (ws-depth), к краю — к урезу (ws)
                            prof = 1.0 - dist2 / (half_w * half_w)
                            cell_bed = ws[k] - depth * prof
                            if cell_bed < dem[j, i]:
                                dem[j, i] = cell_bed
                                carved_cells += 1
            # лента воды: точки мира (y в мировой системе = abs-href), направление
            ribbon = []
            for k, (wx, wz) in enumerate(dense):
                t = dense[min(k + 1, len(dense) - 1)] - dense[max(k - 1, 0)]
                tn = t / (np.linalg.norm(t) + 1e-6)
                ribbon.append([round(wx, 1), round(ws[k] - href, 2), round(wz, 1),
                               half_w, round(float(tn[0]), 3), round(float(tn[1]), 3)])
            ribbons.append({"name": r.get("name"), "class": r.get("class"), "pts": ribbon})

    changed_land = np.abs(dem - orig) > 0.01
    print("== РУСЛА РЕК ==")
    print("рек-лент: %d, клеток русла вырезано: %d" % (len(ribbons), int(changed_land.sum())))
    print("уклон вниз (русел монотонных): %d/%d" % (slopes_ok, slopes_tot))
    if changed_land.any():
        d = (orig - dem)[changed_land]
        print("врезка русла (м): сред %.2f  макс %.2f" % (d.mean(), d.max()))

    json.dump(ribbons, open(OUT, "w"), ensure_ascii=False)
    print("ленты воды → %s (%d рек)" % (OUT, len(ribbons)))
    if not os.path.exists(DEM + ".prerivers"):
        shutil.copy(DEM, DEM + ".prerivers")
    # DEM уже мутирован in-memory — запишем
    np.clip(np.round(dem * 100.0), -32768, 32767).astype("<i2").tofile(DEM)
    print("DEM с руслами записан")


if __name__ == "__main__":
    main()
