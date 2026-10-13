#!/usr/bin/env python3
"""Настоящая поверхность Луны: реальная эквидистантная карта альбедо
(NASA/USGS-производная, public domain) → чистый PNG для сферы Луны.

Ближняя сторона (моря Imbrium/Serenitatis/Tranquillitatis — «лицо») отцентрована
на селенографической долготе 0 (центр карты). Ориентацию (какие детали смотрят
на Землю), либрацию и наклон оси задаёт night_sky.gd по числам из world_clock
(гл. 47+53, сверено tools/verify_moon.py). Здесь — только подготовка пикселей.

Проверка числами: размер, среднее альбедо, что центр ближней стороны темнее
краёв (моря — тёмный базальт).
"""
from pathlib import Path
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tools" / "_moon_src.jpg"
OUT = ROOT / "game2" / "assets" / "sky" / "moon_albedo.png"


def main():
    im = Image.open(SRC).convert("RGB")
    # нормализуем размер (эквидистанта 2:1). 1024×512 — достаточно для диска 0.5°.
    if im.size != (1024, 512):
        im = im.resize((1024, 512), Image.LANCZOS)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    im.save(OUT, "PNG")

    a = np.asarray(im.convert("L"), float) / 255.0
    h, w = a.shape
    near = a[h // 4:3 * h // 4, w // 2 - 120:w // 2 + 120].mean()   # центр ближней стороны
    limb = np.concatenate([a[:, :80], a[:, -80:]], axis=1).mean()   # края (дальняя сторона)
    print("[moon] %s  %dx%d  %d Б" % (OUT.name, w, h, OUT.stat().st_size))
    print("[moon] среднее альбедо %.3f" % a.mean())
    print("[moon] центр ближней стороны %.3f < края %.3f  → %s (моря темнее)"
          % (near, limb, "OK" if near < limb else "ПРОВЕРЬ ориентацию"))


if __name__ == "__main__":
    main()
