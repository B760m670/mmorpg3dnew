#!/usr/bin/env python3
"""Настоящий звёздный каталог (Yale Bright Star, BSC5, ~9096 звёзд до 6.5m —
предел невооружённого глаза) → компактный бинарник для купола ночного неба.

Каждая звезда: реальные RA/Dec (J2000) → единичный ЭКВАТОРИАЛЬНЫЙ вектор
(на устройстве его крутит матрица экватор→горизонт по звёздному времени),
реальная видимая величина V (→ яркость/размер) и ЦВЕТ из настоящей
цветовой температуры K через Планка → CIE XYZ → sRGB (та же физика, что у
Солнца в world_clock.gd). Ничего «на глаз».

Формат stars.bin (little-endian):
  'STAR', uint32 count, затем count× [f32 x,y,z, f32 mag, u8 r,g,b, u8 _]
Проверка — tools/verify_night_sky.py (небесная механика) + сводка ниже.
"""
import json
import math
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tools" / "_bsc5.json"
OUT = ROOT / "game2" / "data" / "real" / "stars.bin"
MAG_LIMIT = 6.5

RA_RE = re.compile(r"(\d+)h\s*(\d+)m\s*([\d.]+)s")
DEC_RE = re.compile(r"([+-]?\d+)[^\d-]+(\d+)[^\d]+([\d.]+)")


def parse_ra(s):
    m = RA_RE.match(s.strip())
    h, mi, se = float(m.group(1)), float(m.group(2)), float(m.group(3))
    return (h + mi / 60.0 + se / 3600.0) * 15.0 * math.pi / 180.0


def parse_dec(s):
    m = DEC_RE.match(s.strip())
    dd, mm, ss = m.group(1), float(m.group(2)), float(m.group(3))
    sgn = -1.0 if dd.strip().startswith("-") else 1.0
    return sgn * (abs(float(dd)) + mm / 60.0 + ss / 3600.0) * math.pi / 180.0


# --- цвет звезды из температуры: Планк → CIE XYZ (аналитич. CMF) → sRGB ---
def planck(lam_nm, T):
    lam = lam_nm * 1e-9
    return 1.0 / (lam ** 5 * (math.exp(0.0143877688 / (lam * T)) - 1.0))


def _lobe(l, mu, s1, s2):
    s = s1 if l < mu else s2
    return math.exp(-0.5 * ((l - mu) / s) ** 2)


def cmf(l):
    x = 1.056 * _lobe(l, 599.8, 37.9, 31.0) + 0.362 * _lobe(l, 442.0, 16.0, 26.7) \
        - 0.065 * _lobe(l, 501.1, 20.4, 26.2)
    y = 0.821 * _lobe(l, 568.8, 46.9, 40.5) + 0.286 * _lobe(l, 530.9, 16.3, 31.1)
    z = 1.217 * _lobe(l, 437.0, 11.8, 36.0) + 0.681 * _lobe(l, 459.0, 26.0, 13.8)
    return x, y, z


def star_rgb(T):
    T = max(1800.0, min(40000.0, T))
    X = Y = Z = 0.0
    for k in range(41):
        lam = 380.0 + 10.0 * k
        s = planck(lam, T)
        cx, cy, cz = cmf(lam)
        X += cx * s; Y += cy * s; Z += cz * s
    r = 3.2406 * X - 1.5372 * Y - 0.4986 * Z
    g = -0.9689 * X + 1.8758 * Y + 0.0415 * Z
    b = 0.0557 * X - 0.2040 * Y + 1.0570 * Z
    r, g, b = max(r, 0.0), max(g, 0.0), max(b, 0.0)
    mx = max(r, g, b) or 1.0
    r, g, b = r / mx, g / mx, b / mx
    # звёзды глазу почти белые — лёгкая десатурация тона (тинт остаётся)
    des = 0.45
    r = r + (1.0 - r) * des; g = g + (1.0 - g) * des; b = b + (1.0 - b) * des
    return int(round(r * 255)), int(round(g * 255)), int(round(b * 255))


def main():
    data = json.load(open(SRC))
    rgb_cache = {}
    rows = []
    for e in data:
        v = e.get("V")
        if v in (None, "", "-"):
            continue
        try:
            mag = float(v)
        except ValueError:
            continue
        if mag > MAG_LIMIT:
            continue
        try:
            ra = parse_ra(e["RA"]); dec = parse_dec(e["Dec"])
        except (AttributeError, KeyError, ValueError):
            continue
        try:
            k = int(float(e.get("K") or 0))
        except ValueError:
            k = 0
        if k < 1800:
            k = 6000                       # нет K → солнцеподобный по умолчанию
        kq = (k // 250) * 250
        if kq not in rgb_cache:
            rgb_cache[kq] = star_rgb(kq)
        r, g, b = rgb_cache[kq]
        x = math.cos(dec) * math.cos(ra)
        y = math.cos(dec) * math.sin(ra)
        z = math.sin(dec)
        rows.append((x, y, z, mag, r, g, b))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "wb") as f:
        f.write(b"STAR")
        f.write(struct.pack("<I", len(rows)))
        for x, y, z, mag, r, g, b in rows:
            f.write(struct.pack("<ffffBBBB", x, y, z, mag, r, g, b, 0))

    mags = [r[3] for r in rows]
    print("[stars] %d звёзд ≤ %.1fm → %s (%d Б)" % (len(rows), MAG_LIMIT, OUT, OUT.stat().st_size))
    print("[stars] величины: ярчайшая %.2f, слабейшая %.2f" % (min(mags), max(mags)))
    for name, hr_ra, hr_dec in [("Сириус", 101.287, -16.716), ("Вега", 279.235, 38.784)]:
        # найдём ближайшую по вектору — sanity, что каталог на месте
        tr = hr_ra * math.pi / 180.0; td = hr_dec * math.pi / 180.0
        tv = (math.cos(td) * math.cos(tr), math.cos(td) * math.sin(tr), math.sin(td))
        best = min(rows, key=lambda s: (s[0] - tv[0]) ** 2 + (s[1] - tv[1]) ** 2 + (s[2] - tv[2]) ** 2)
        print("  %-8s ближайшая V=%.2f rgb=(%d,%d,%d)" % (name, best[3], best[4], best[5], best[6]))


if __name__ == "__main__":
    main()
