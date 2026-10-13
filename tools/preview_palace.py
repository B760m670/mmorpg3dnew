#!/usr/bin/env python3
"""Офлайн-превью массинга (Godot в песочнице нет): читает .bin формата CITY,
рендерит простым пайплайном (пинхол-камера + ламберт + сортировка по глубине,
без отсечения изнанки) в PNG. Только для проверки СИЛУЭТА — не финальный вид.

Запуск: python3 tools/preview_palace.py [file.bin] [out.png]
"""
import math
import os
import struct
import sys

import numpy as np
from PIL import Image

ROOT = os.path.join(os.path.dirname(__file__), "..")


def load(path):
    d = open(path, "rb").read()
    assert d[:4] == b"CITY"
    _, nsurf = struct.unpack_from("<II", d, 4)
    off = 12
    tris = []          # (v0,v1,v2, surf)
    for si in range(nsurf):
        vc, ic = struct.unpack_from("<II", d, off); off += 8
        v = np.frombuffer(d, "<f4", vc * 8, off).reshape(vc, 8); off += vc * 32
        idx = np.frombuffer(d, "<u4", ic, off); off += ic * 4
        pos = v[:, 0:3]
        for k in range(0, ic, 3):
            a, b, c = idx[k], idx[k + 1], idx[k + 2]
            tris.append((pos[a], pos[b], pos[c], si))
    return tris


def render(tris, out, eye, target, up=(0, 1, 0), sun=(-0.4, -0.8, 0.5),
           W=1200, H=800, fov=45.0):
    eye = np.array(eye, float); target = np.array(target, float); up = np.array(up, float)
    fwd = target - eye; fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, up); right /= np.linalg.norm(right)
    upv = np.cross(right, fwd)
    sun = np.array(sun, float); sun /= np.linalg.norm(sun)
    f = 1.0 / math.tan(math.radians(fov) / 2)
    img = np.zeros((H, W, 3), np.float32)
    zbuf = np.full((H, W), 1e9, np.float32)
    # цвет поверхности: 0 стены (камень), 1 кровли (тёмная жесть)
    base_col = {0: np.array([0.78, 0.72, 0.60]), 1: np.array([0.30, 0.29, 0.31])}
    sky = np.array([0.55, 0.63, 0.74])

    def project(p):
        rel = p - eye
        cx = np.dot(rel, right); cy = np.dot(rel, upv); cz = np.dot(rel, fwd)
        if cz <= 0.05:
            return None
        sx = (cx / cz) * f
        sy = (cy / cz) * f
        px = int((sx * (H / W) + 0.5) * W)   # аспект по высоте
        py = int((0.5 - sy) * H)
        return px, py, cz

    order = []
    for i, (a, b, c, s) in enumerate(tris):
        zc = np.dot((a + b + c) / 3 - eye, fwd)
        if zc > 0:
            order.append((zc, i))
    order.sort(reverse=True)   # дальние первыми (художник)

    for _, i in order:
        a, b, c, s = tris[i]
        pa, pb, pc = project(a), project(b), project(c)
        if not (pa and pb and pc):
            continue
        n = np.cross(b - a, c - a)
        nl = np.linalg.norm(n)
        if nl < 1e-9:
            continue
        n /= nl
        lam = abs(np.dot(n, -sun))
        shade = 0.28 + 0.72 * lam            # ambient + diffuse
        col = base_col[s] * shade
        # растеризация треугольника
        xs = [pa[0], pb[0], pc[0]]; ys = [pa[1], pb[1], pc[1]]
        x0, x1 = max(min(xs), 0), min(max(xs), W - 1)
        y0, y1 = max(min(ys), 0), min(max(ys), H - 1)
        if x1 < x0 or y1 < y0:
            continue
        ax, ay = pa[0], pa[1]; bx, by = pb[0], pb[1]; cx2, cy2 = pc[0], pc[1]
        den = (by - cy2) * (ax - cx2) + (cx2 - bx) * (ay - cy2)
        if abs(den) < 1e-6:
            continue
        zc = (pa[2] + pb[2] + pc[2]) / 3
        for yy in range(y0, y1 + 1):
            for xx in range(x0, x1 + 1):
                w0 = ((by - cy2) * (xx - cx2) + (cx2 - bx) * (yy - cy2)) / den
                w1 = ((cy2 - ay) * (xx - cx2) + (ax - cx2) * (yy - cy2)) / den
                w2 = 1 - w0 - w1
                if w0 >= -0.01 and w1 >= -0.01 and w2 >= -0.01:
                    if zc < zbuf[yy, xx]:
                        zbuf[yy, xx] = zc
                        img[yy, xx] = col
    # небо там, где ничего не нарисовано
    mask = (zbuf > 1e8)
    img[mask] = sky
    Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(out)
    print("превью →", out)


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "game2/assets/city/gatchina_palace.bin")
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "..", "palace_preview.png")
    tris = load(src)
    # камера от плаца (юг, +Z) с подъёмом — парадный кадр золотого часа
    render(tris, out, eye=(19, 95, 360), target=(19, 14, 4), sun=(-0.5, -0.5, 0.35))
