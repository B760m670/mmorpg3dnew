#!/usr/bin/env python3
"""СРАВНЕНИЕ ДВУХ КАДРОВ ЧИСЛАМИ — вместо «посмотри, видно или нет».

Зачем: раньше проверка «видна ли вода» стоила полного рендера всего мира и
заканчивалась разглядыванием PNG. Здесь два снимка одной сцены (с объектом и
без него) сравниваются попиксельно, и ответ становится замером: какая доля
кадра изменилась и насколько сильно.

Порог заметности взят не с потолка: разница светлоты меньше ~2/255 на глаз в
кадре не видна (порог различения яркости ~1%). Всё, что выше, — видимое.

Запуск: python3 tools/img_diff.py A.png B.png [--mask]
        --mask сохранит A_diff.png: белым отмечено изменившееся.
"""
import sys

import numpy as np
from PIL import Image

THRESH = 2.0 / 255.0      # порог заметности изменения (~1% яркости)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    a_path, b_path = sys.argv[1], sys.argv[2]
    a = np.asarray(Image.open(a_path).convert("RGB"), np.float32) / 255.0
    b = np.asarray(Image.open(b_path).convert("RGB"), np.float32) / 255.0
    if a.shape != b.shape:
        print("кадры разного размера: %s против %s" % (a.shape, b.shape))
        return 1

    d = np.abs(a - b).max(axis=2)
    changed = d > THRESH
    frac = changed.mean()
    print("== СРАВНЕНИЕ КАДРОВ ==")
    print("A: %s" % a_path)
    print("B: %s" % b_path)
    print("изменилось пикселей: %.2f%% (%d из %d)"
          % (frac * 100.0, int(changed.sum()), d.size))
    if changed.any():
        print("сила изменения там, где оно есть: сред %.3f  макс %.3f (0..1)"
              % (d[changed].mean(), d.max()))
        ys, xs = np.nonzero(changed)
        print("область изменения: x %d..%d, y %d..%d (кадр %dx%d)"
              % (xs.min(), xs.max(), ys.min(), ys.max(), a.shape[1], a.shape[0]))
        ca = a[changed].mean(axis=0)
        cb = b[changed].mean(axis=0)
        print("средний цвет там: A(%.3f %.3f %.3f) → B(%.3f %.3f %.3f)"
              % (ca[0], ca[1], ca[2], cb[0], cb[1], cb[2]))
    print("ВЫВОД:", "видимое отличие есть" if frac > 0.001 else "кадры практически одинаковы")

    if "--mask" in sys.argv:
        out = a_path.rsplit(".", 1)[0] + "_diff.png"
        Image.fromarray((changed * 255).astype(np.uint8)).save(out)
        print("маска изменений →", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
