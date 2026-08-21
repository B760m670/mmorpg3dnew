#!/usr/bin/env python3
"""НАСЫЩЕННОСТЬ КАДРА В ЧИСЛАХ.

«Насыщенно» — это впечатление, и спорить о нём бесполезно. Здесь оно разложено
на величины, которые можно померить у чужого кадра и у своего, и сравнить.

ВСЁ СВОДИТСЯ К ОДНОМУ РАЗМЕРУ (640x360). Иначе край и детали меряются на разных
сетках, и числа несравнимы — а сравнение тут единственная цель.

  КРАЙ      — доля пикселей, где градиент яркости больше порога. Осторожно: его
              легко надуть шумом и ступеньками, он НЕ равен «богатству». У нашего
              кадра Гатчины он вышел 0.117 против 0.142 у GTA — почти поровну,
              хотя в кадре у нас четыре объекта, а у них сотни. Разницу делал
              зубчатый край воды, а не содержание.
  ОГНИ      — число раздельных источников света. ПЕРВАЯ ВЕРСИЯ ВРАЛА: она брала
              абсолютный порог 0.75, и на светлом кадре считала за «огни» блики
              на бетоне (56 штук у плоской таблички) и засветки облаков (58 у
              нашего дневного поля). Источник — это не «яркий пиксель», а
              ЛОКАЛЬНЫЙ ПИК НА ТЁМНОМ ФОНЕ: лампа в кадре ярче своего окружения
              в разы, а освещённая стена — нет. Поэтому теперь пятно считается,
              только если оно ярче кольца вокруг себя втрое и само ярче 0.55.
  ЦВЕТОВ    — сколько различимых цветов (квантование до 5 бит на канал).
  ДЕТАЛИ    — сколько контраста теряется на каждом удвоении масштаба. Показывает,
              где живёт информация: в мелочи или в крупной форме. ВАЖЕН НАКЛОН,
              а не сами числа. У хорошего кадра ряд РАСТЁТ (0.028 0.033 ... 0.048)
              — структура есть на всех размерах. У нашего крупного плана травы он
              ПАДАЕТ (0.023 0.018 ... 0.011) — вся информация в текселях, а между
              10 см и 3 м не происходит ничего. Это шум, а не содержание.

Запуск: python3 studio/density.py кадр.png [ещё.png ...]
        python3 studio/density.py --label "GTA" папка/*.png
"""
import sys

import numpy as np
from PIL import Image

W, H = 640, 360


def rgb_of(path):
    return np.asarray(Image.open(path).convert('RGB').resize((W, H), Image.LANCZOS)
                      ).astype(float) / 255.0


def sobel(g):
    gx = np.zeros_like(g)
    gy = np.zeros_like(g)
    gx[:, 1:-1] = g[:, 2:] - g[:, :-2]
    gy[1:-1, :] = g[2:, :] - g[:-2, :]
    return np.hypot(gx, gy)


def detail_spectrum(L, levels=5):
    out, cur = [], L
    for _ in range(levels):
        h, w = cur.shape
        h -= h % 2
        w -= w % 2
        cur = cur[:h, :w]
        small = cur.reshape(h // 2, 2, w // 2, 2).mean(axis=(1, 3))
        up = np.repeat(np.repeat(small, 2, 0), 2, 1)
        out.append(float(np.std(cur - up)))
        cur = small
    return out


def _boxblur(a, r):
    """Среднее в окне (2r+1)² через интегральную сумму — фон вокруг пятна."""
    p = np.pad(a, r + 1, mode='edge')
    s = p.cumsum(0).cumsum(1)
    s = np.pad(s, ((1, 0), (1, 0)))
    h, w = a.shape
    k = 2 * r + 1
    y0 = np.arange(h)
    x0 = np.arange(w)
    Y0, X0 = np.meshgrid(y0, x0, indexing='ij')
    tot = (s[Y0 + k, X0 + k] - s[Y0, X0 + k] - s[Y0 + k, X0] + s[Y0, X0])
    return tot / (k * k)


def count_lights(L, thr=0.55, r=6, ratio=3.0):
    """Источники света: локальные пики, ярче своего ОКРУЖЕНИЯ в `ratio` раз.

    Освещённая стена ярка, но её окружение ярко ровно так же — она не пик.
    Лампа ярче фона в разы. Это и есть разница, и на ней держится вся мера.
    """
    bg = _boxblur(L, 4 * r)                    # фон: среднее по широкому окну
    m = (L > thr) & (L > ratio * (bg + 0.02))
    ys, xs = np.nonzero(m)
    if len(ys) == 0:
        return 0
    seen = np.zeros_like(m)
    n = 0
    for k in np.argsort(-L[ys, xs]):
        y, x = ys[k], xs[k]
        if seen[y, x]:
            continue
        n += 1
        seen[max(0, y - r):y + r + 1, max(0, x - r):x + r + 1] = True
    return n


def measure(paths, label=""):
    E, D, C, Lt = [], [], [], []
    for p in paths:
        rgb = rgb_of(p)
        L = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
        E.append(float(np.mean(sobel(L) > 0.06)))
        D.append(detail_spectrum(L))
        C.append(len(set(map(tuple, (rgb * 31).astype(int).reshape(-1, 3)[::5]))))
        Lt.append(count_lights(L))
    D = np.mean(np.array(D), axis=0)
    print("%-22s край %.3f | цветов %4d | огней %5.1f | детали %s"
          % (label or paths[0].split('/')[-1], np.mean(E), np.mean(C), np.mean(Lt),
             " ".join("%.3f" % v for v in D)))
    return dict(edge=float(np.mean(E)), colors=float(np.mean(C)),
                lights=float(np.mean(Lt)), detail=list(D))


if __name__ == "__main__":
    args = sys.argv[1:]
    label = ""
    if args and args[0] == "--label":
        label = args[1]
        args = args[2:]
    if not args:
        print(__doc__)
        sys.exit(1)
    measure(args, label)
