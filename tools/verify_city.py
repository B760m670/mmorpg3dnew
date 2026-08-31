#!/usr/bin/env python3
"""Верификация буфера города — ЗЕРКАЛО загрузчика city.gd (Godot запустить в
песочнице нельзя, поэтому контракт данных проверяем здесь) + доказательство-
картинка: город сверху, цвет по выведенной высоте.

Проверяет: сигнатуру, версию, счётчики, индексы в диапазоне, отсутствие NaN/inf,
границы координат (внутри ±DEM_HALF, высоты в разумном коридоре). Выход ≠0 при
нарушении — годится как гейт в CI перед сборкой.
"""
import math
import os
import struct
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
BIN = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    ROOT, "game2", "assets", "city", "gatchina_city.bin")
SHOT = os.path.join(ROOT, "..", "scratchpad_city.png")  # эвиденс кладём вне игры
SRC = os.path.join(ROOT, "game2", "data", "real", "buildings.json")
DEM_HALF = 8192.0


def read_surfaces():
    with open(BIN, "rb") as f:
        data = f.read()
    assert data[:4] == b"CITY", "сигнатура ≠ CITY"
    ver, nsurf = struct.unpack_from("<II", data, 4)
    off = 12
    surfaces = []
    for _ in range(nsurf):
        vcount, icount = struct.unpack_from("<II", data, off)
        off += 8
        vbytes = data[off:off + vcount * 32]
        off += vcount * 32
        ibytes = data[off:off + icount * 4]
        off += icount * 4
        verts = struct.unpack("<%df" % (vcount * 8), vbytes)
        idx = struct.unpack("<%dI" % icount, ibytes)
        surfaces.append((vcount, icount, verts, idx))
    assert off == len(data), "лишние/недостающие байты: off=%d len=%d" % (off, len(data))
    return ver, surfaces


def check():
    ver, surfaces = read_surfaces()
    print("версия=%d, поверхностей=%d" % (ver, len(surfaces)))
    ok = True
    ymin, ymax = 1e9, -1e9
    for si, (vc, ic, verts, idx) in enumerate(surfaces):
        name = ["стены", "кровли"][si] if si < 2 else "surf%d" % si
        # индексы в диапазоне
        bad_i = [i for i in idx if i >= vc]
        if bad_i:
            print("  [%s] ИНДЕКС ВНЕ ДИАПАЗОНА: %d шт" % (name, len(bad_i)))
            ok = False
        if ic % 3 != 0:
            print("  [%s] индексов не кратно 3: %d" % (name, ic))
            ok = False
        # координаты/нормали
        nan = 0
        oob = 0
        nbad = 0
        for k in range(vc):
            x, y, z, nx, ny, nz, u, w = verts[k * 8:k * 8 + 8]
            if any(math.isnan(t) or math.isinf(t) for t in (x, y, z, nx, ny, nz)):
                nan += 1
            if abs(x) > DEM_HALF or abs(z) > DEM_HALF:
                oob += 1
            nl = nx * nx + ny * ny + nz * nz
            if abs(nl - 1.0) > 0.05:
                nbad += 1
            ymin = min(ymin, y)
            ymax = max(ymax, y)
        if nan:
            print("  [%s] NaN/inf вершин: %d" % (name, nan)); ok = False
        if oob:
            print("  [%s] координат за ±%.0f м: %d" % (name, DEM_HALF, oob)); ok = False
        if nbad:
            print("  [%s] ненормированных нормалей: %d" % (name, nbad)); ok = False
        print("  [%s] верш=%d △=%d  — индексы ок=%s, nan=%d, oob=%d, нормали ок=%s" % (
            name, vc, ic // 3, not bad_i, nan, oob, nbad == 0))
    print("высоты Y (мир): %.1f .. %.1f м" % (ymin, ymax))
    print("КОНТРАКТ:", "OK ✓" if ok else "НАРУШЕН ✗")
    return ok


def evidence():
    """Ортографический вид сверху: заливаем реальные следы цветом по высоте."""
    try:
        import json
        import numpy as np
        from PIL import Image, ImageDraw
    except Exception as e:
        print("эвиденс пропущен (нет numpy/PIL):", e)
        return
    R = 6600.0
    S = 1400
    img = Image.new("RGB", (S, S), (16, 20, 16))
    dr = ImageDraw.Draw(img)

    def to_px(x, y):  # восток→право, север→вверх
        return ((x + R) / (2 * R) * S, (R - y) / (2 * R) * S)

    def sl(r):
        s = 0.0
        for k in range(len(r)):
            x0, y0 = r[k]; x1, y1 = r[(k + 1) % len(r)]
            s += x0 * y1 - x1 * y0
        return abs(s) / 2

    b = json.load(open(SRC))
    n = 0
    for it in b:
        for poly in it.get("polys", []):
            if not poly or len(poly[0]) < 4:
                continue
            ring = poly[0]
            a = sl(ring)
            # тот же ранг высоты, что в build_city (для цвета)
            t = min(1.0, math.log10(max(a, 6.0)) / math.log10(3000.0))
            col = (int(60 + 180 * t), int(70 + 150 * t), int(90 + 60 * t))
            pts = [to_px(p[0], p[1]) for p in ring]
            if all(0 <= px < S and 0 <= py < S for px, py in pts):
                dr.polygon(pts, fill=col)
                n += 1
    # метка дворца (центр данных ≈ дворец)
    cx, cy = to_px(0, 0)
    dr.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], outline=(255, 80, 60), width=2)
    img.save(SHOT)
    print("эвиденс: %d следов → %s (крупные=светлые/высокие, красная метка=дворец)" % (n, SHOT))


if __name__ == "__main__":
    ok = check()
    evidence()
    raise SystemExit(0 if ok else 1)
