#!/usr/bin/env python3
"""Офлайн-доказательство реальных материалов (Godot в песочнице нет): берёт
скачанные CC0-каналы (Color/Normal/Roughness/AO) и релайтит плитку светом
золотого часа с нормал-маппингом. Показывает, что это НАСТОЯЩИЙ скан, а не
синтетика. Не финальный вид — прувф материала.

Запуск: python3 tools/preview_surface.py
"""
import glob
import os

import numpy as np
from PIL import Image

ROOT = os.path.join(os.path.dirname(__file__), "..")
REAL = os.path.join(ROOT, "game2", "assets", "materials", "real")
OUT = os.path.join(ROOT, "..", "surface_real_preview.png")
N = 512


def load(path):
    im = Image.open(path).convert("RGB").resize((N, N), Image.LANCZOS)
    return np.asarray(im, np.float32) / 255.0


def relight(mat_dir):
    col = load(os.path.join(mat_dir, "Color.jpg"))
    nrm = load(os.path.join(mat_dir, "Normal.jpg")) * 2.0 - 1.0
    nrm /= np.linalg.norm(nrm, axis=2, keepdims=True) + 1e-6
    rf = os.path.join(mat_dir, "Roughness.jpg")
    aof = os.path.join(mat_dir, "AmbientOcclusion.jpg")
    rough = load(rf)[..., 0] if os.path.exists(rf) else np.full((N, N), 0.8)
    ao = load(aof)[..., 0] if os.path.exists(aof) else np.ones((N, N))

    L = np.array([-0.5, 0.35, 0.79])           # низкое солнце (золотой час)
    L /= np.linalg.norm(L)
    V = np.array([0.0, 0.0, 1.0])
    H = (L + V); H /= np.linalg.norm(H)
    ndl = np.clip((nrm * L).sum(2), 0, 1)
    ndh = np.clip((nrm * H).sum(2), 0, 1)
    shin = np.clip((1.0 - rough), 0.02, 1.0) * 60.0
    spec = (ndh ** shin) * (1.0 - rough) * 0.35
    sun = np.array([1.0, 0.86, 0.62])          # тёплый
    sky = np.array([0.32, 0.42, 0.58])         # холодный ambient
    lit = col * ao[..., None] * (sky * 0.5 + sun * ndl[..., None]) + spec[..., None] * sun
    return np.clip(lit ** (1 / 2.2), 0, 1)


def main():
    dirs = sorted(glob.glob(REAL + "/*"))
    tiles = []
    for d in dirs:
        col = load(os.path.join(d, "Color.jpg"))
        lit = relight(d)
        name = os.path.basename(d)
        row = np.concatenate([col ** (1 / 2.2), lit], axis=1)  # albedo | освещённое
        # подпись полосой
        bar = np.zeros((22, row.shape[1], 3), np.float32)
        tiles.append(np.concatenate([bar, row], axis=0))
        print("  %-10s albedo=%.2f  готово" % (name, col.mean()))
    grid = np.concatenate(tiles, axis=0)
    img = Image.fromarray((grid * 255).astype(np.uint8))
    from PIL import ImageDraw
    dr = ImageDraw.Draw(img)
    y = 0
    for d in dirs:
        dr.text((6, y + 5), "%s  (ambientCG CC0)   albedo | свет золотого часа" %
                os.path.basename(d), fill=(230, 230, 210))
        y += 22 + N
    img.save(OUT)
    print("прувф →", OUT)


if __name__ == "__main__":
    main()
