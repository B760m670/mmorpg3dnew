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
  ОГНИ      — число раздельных ярких пятен (локальные максимумы ярче 0.75,
              разнесённые на 6 пикселей). ВОТ ЭТО ЧЕСТНО РАЗДЕЛЯЕТ: у GTA в сухую
              ночь 51 источник в кадре, у нас 0.
  ЦВЕТОВ    — сколько различимых цветов (квантование до 5 бит на канал).
  ДЕТАЛИ    — сколько контраста теряется на каждом удвоении масштаба. Показывает,
              где живёт информация: в крупной форме или в мелочи.

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


def count_lights(L, thr=0.75, r=6):
    m = L > thr
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
