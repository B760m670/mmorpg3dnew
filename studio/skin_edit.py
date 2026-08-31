#!/usr/bin/env python3
"""ПРАВКА САМОЙ КОЖИ. Сосок — это краска, и двигать его надо в краске.

ПОЧЕМУ НЕ РАЗВЁРТКОЙ, хотя это была первая мысль и она казалась чище: правка
развёртки не трогает форму тела, но ТЯНЕТ РИСУНОК. Проверено кадром с
разделением причин — только правка развёртки, ключи формы выключены: ареола
превратилась в размазанный завиток, волосы вокруг закрутились воронкой.
Причина видна из математики: сдвиг с радиальным затуханием даёт и сдвиг, и
поворот (ротор поля не ноль), а ареола — мелкая деталь, она этого не терпит.

ЧТО ЗДЕСЬ ВМЕСТО ЭТОГО. Ареола вырезается и вклеивается на новое место ЖЁСТКО,
без единого пикселя растяжения. Старое место залечивается размытой копией
ТОЙ ЖЕ картинки: размытая копия сходится с окружением ровно на границе маски,
поэтому шва нет по построению. Заплата из другого места кожи шов давала —
там иначе лежат волосы и другой тон, и в кадре была видна прямоугольная
нашлёпка.

Теряется рисунок волос в пятне около 38 текселей, и почти всё это пятно
накрывается перенесённой ареолой.
"""
import numpy as np


def _blurred(a, r=16, passes=2):
    """Размытие складыванием бегущих сумм: без scipy, только numpy."""
    out = a.astype(np.float32)
    for _ in range(passes):
        for axis in (0, 1):
            n = out.shape[axis]
            k = min(2 * r + 1, n if n % 2 else n - 1)
            if k < 3:
                continue
            pad = [(0, 0)] * out.ndim
            pad[axis] = (k // 2, k // 2)
            p = np.pad(out, pad, mode='edge')
            # НОЛЬ ВПЕРЕДИ ОБЯЗАТЕЛЕН: сумма окна это c[i+k] − c[i], и без
            # приписанного нуля правый край вылезает за массив на единицу.
            zpad = [(0, 0)] * out.ndim
            zpad[axis] = (1, 0)
            c = np.pad(np.cumsum(p, axis=axis), zpad, mode='constant')
            lo = np.take(c, np.arange(0, n), axis=axis)
            hi = np.take(c, np.arange(k, k + n), axis=axis)
            out = (hi - lo) / float(k)
    return out


def _alpha(h, w, cy, cx, r, feather):
    y, x = np.ogrid[:h, :w]
    d = np.sqrt((y - cy) ** 2 + (x - cx) ** 2)
    t = np.clip((r - d) / max(1e-6, feather), 0.0, 1.0)
    return (t * t * (3.0 - 2.0 * t)).astype(np.float32)


def move_spot(img, moves, r_heal=38, r_spot=30, feather=13, verbose=True):
    """Перенести пятна в картинке Блендера. moves: [((sx,sy),(dx,dy)), ...]
    в текселях, считая СВЕРХУ, как принято у картинок."""
    W, H = img.size
    buf = np.empty(W * H * 4, dtype=np.float32)
    img.pixels.foreach_get(buf)
    a = buf.reshape(H, W, 4)

    def row(y):
        return H - 1 - int(y)

    # окно вокруг обоих пятен, чтобы не размывать всю картинку
    ys = [row(p[1]) for m in moves for p in m]
    xs = [int(p[0]) for m in moves for p in m]
    pad = r_heal + 3 * feather + 40
    y0, y1 = max(0, min(ys) - pad), min(H, max(ys) + pad)
    x0, x1 = max(0, min(xs) - pad), min(W, max(xs) + pad)
    win = a[y0:y1, x0:x1, :3]
    # СНИМОК ДО ЛЕЧЕНИЯ. Первый раз я копировал исходник ПОСЛЕ засыпки, и
    # переносил на новое место уже замытое пятно: ареола пропадала вовсе,
    # оставалась бледная клякса. Ошибка тихая — работает, но не то.
    src = win.copy()
    smooth = _blurred(win, r=16, passes=2)

    # 1. залечить старые места размытой копией
    heal = np.zeros(win.shape[:2], dtype=np.float32)
    for (sx, sy), _ in moves:
        heal = np.maximum(heal, _alpha(win.shape[0], win.shape[1],
                                       row(sy) - y0, sx - x0, r_heal, feather))
    win[:] = win * (1.0 - heal[..., None]) + smooth * heal[..., None]

    # 2. вклеить пятно на новое место — жёстко, из ИСХОДНОЙ картинки
    for (sx, sy), (dx, dy) in moves:
        sy0, sx0 = row(sy) - y0, sx - x0
        dy0, dx0 = row(dy) - y0, dx - x0
        m = _alpha(win.shape[0], win.shape[1], dy0, dx0, r_spot, feather)
        shifted = np.roll(np.roll(src, dy0 - sy0, axis=0), dx0 - sx0, axis=1)
        win[:] = win * (1.0 - m[..., None]) + shifted * m[..., None]

    a[y0:y1, x0:x1, :3] = win
    img.pixels.foreach_set(a.reshape(-1))
    img.update()
    if verbose:
        print("[кожа] пятен перенесено %d, окно %dx%d текселей"
              % (len(moves), x1 - x0, y1 - y0))
    return len(moves)


def find_skin_image(body, name_hint="sss"):
    """Картинка цвета кожи в материале тела.

    ИСКАТЬ НАДО ВНУТРИ ГРУПП УЗЛОВ, и на этом первый заход молча провалился:
    шейдер кожи MPFB (ENHANCED_SSS) прячет обе картинки — цвет и подповерхностное
    рассеяние — в группе, а на верхнем уровне материала всего два узла. Обход
    только верхнего уровня возвращал None, правка не происходила, и я принял
    за неё сдвиг вершин, который двигает краску вместе с кожей.
    Картинка рассеяния (sss.png) того же размера, поэтому отбрасывается по имени.
    """
    seen, best = set(), None
    def walk(tree):
        nonlocal best
        if tree is None or tree.name in seen:
            return
        seen.add(tree.name)
        for n in tree.nodes:
            if n.type == 'TEX_IMAGE' and n.image is not None:
                im = n.image
                if (im.size[0] >= 1024 and im.size[1] >= 1024
                        and name_hint not in im.name.lower()):
                    best = im
            elif n.type == 'GROUP':
                walk(n.node_tree)
    for m in body.data.materials:
        if m is not None and m.use_nodes:
            walk(m.node_tree)
    return best
