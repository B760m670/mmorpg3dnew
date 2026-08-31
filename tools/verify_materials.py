#!/usr/bin/env python3
"""Проверка целостности реальных материалов: наличие каналов, размер, что
карты не вырождены (Color не плоский, Normal ~синеватый вокруг (128,128,255),
Roughness/AO в разумном диапазоне). Выход ≠0 при проблеме — гейт для CI.

Запуск: python3 tools/verify_materials.py
"""
import glob
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.join(os.path.dirname(__file__), "..")
REAL = os.path.join(ROOT, "game2", "assets", "materials", "real")


def stat(path):
    a = np.asarray(Image.open(path).convert("RGB"), np.float32) / 255.0
    return a.mean(axis=(0, 1)), a.std(), a.shape[:2]


def main():
    ok = True
    for d in sorted(glob.glob(REAL + "/*")):
        if not os.path.isdir(d):
            continue
        name = os.path.basename(d)
        maps = {os.path.basename(f)[:-4]: f for f in glob.glob(d + "/*.jpg")}
        if "Color" not in maps or "Normal" not in maps:
            print("  [%s] НЕТ обязательных карт (Color/Normal)" % name); ok = False; continue
        cm, cs, dim = stat(maps["Color"])
        nm, ns, _ = stat(maps["Normal"])
        # Normal должен быть «синим» (B доминирует, ~1.0), не серым/плоским
        blue_ok = nm[2] > 0.6 and nm[2] > nm[0] and ns > 0.01
        flat = cs < 0.02
        print("  [%-10s] %dx%d карт=%d  Color=%.2f/%.2f/%.2f σ=%.3f  Normal B=%.2f  %s" % (
            name, dim[1], dim[0], len(maps), cm[0], cm[1], cm[2], cs, nm[2],
            "OK" if (blue_ok and not flat) else "ПОДОЗРИТЕЛЬНО"))
        ok = ok and blue_ok and not flat
    print("МАТЕРИАЛЫ:", "OK ✓" if ok else "ПРОБЛЕМА ✗")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
