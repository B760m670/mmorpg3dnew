#!/usr/bin/env python3
"""Офлайн-прувф поверхности среза РЕАЛЬНЫМИ материалами по классам (Godot в
песочнице нет). Читает карту классов slice_palace.bin, реальный DEM и
скачанные CC0-текстуры (albedo/normal/AO), компонует землю: каждый класс —
свой настоящий материал, тайлится по миру, освещается солнцем золотого часа
(нормаль рельефа × нормаль материала × AO). Вид сверху, окно вокруг дворца.

Это проверка ДИЗАЙНА поверхности (где какой материал, как выглядит вживую) —
финальный вид даёт GDShader на устройстве. Запуск: python3 tools/preview_slice.py
"""
import json
import os

import numpy as np
from PIL import Image

from build_city import load_dem, DEM_N, DEM_STEP, DEM_HALF

ROOT = os.path.join(os.path.dirname(__file__), "..")
REAL = os.path.join(ROOT, "game2", "assets", "materials", "real")
OUT = os.path.join(ROOT, "..", "slice_surface_preview.png")

TILE_M = 2.0        # период тайла материала, м
WIN_HALF = 320.0    # полуокно рендера вокруг центра, м
CENTER = (0.0, 300.0)  # центр окна в данных (восток, север) — парк у дворца
RES = 1000

# класс среза → (папка материала | None для воды, тон-множитель)
MAT = {
    0: ("grass004", (1.06, 1.00, 0.80)),   # луг — суше
    1: ("grass004", (0.90, 1.06, 0.84)),   # газон — сочный, стриженый
    2: ("grass004", (0.70, 0.78, 0.62)),   # роща — тень
    3: ("grass004", (0.55, 0.62, 0.50)),   # лес — плотная тень
    4: ("gravel011", (1.02, 1.00, 0.96)),  # аллея — гравий
    5: ("gravel011", (1.10, 1.07, 1.00)),  # плац — светлее, суше
    6: (None, None),                        # вода — заливка
    7: ("rock030", (1.10, 1.02, 0.86)),    # берег — камень/галька
    8: ("tiles049", (1.00, 1.00, 1.00)),   # мостовая — плитняк
}
WATER = np.array([0.09, 0.13, 0.16])


def load_map(mat, name):
    p = os.path.join(REAL, mat, name + ".jpg")
    if not os.path.exists(p):
        return None
    return np.asarray(Image.open(p).convert("RGB"), np.float32) / 255.0


def main():
    dem, href = load_dem()
    dem = np.frombuffer(bytes(dem), np.int16).reshape(DEM_N, DEM_N).astype(np.float32) / 100.0 - href
    meta = json.load(open(os.path.join(ROOT, "game2/assets/dem/slice_palace.json")))
    sn = meta["n"]; scx, scy, shalf = meta["cx"], meta["cy"], meta["half_m"]
    smap = np.frombuffer(open(os.path.join(ROOT, "game2/assets/dem/slice_palace.bin"), "rb").read(sn * sn), np.uint8).reshape(sn, sn)

    tex = {}
    for cls, (mat, _) in MAT.items():
        if mat and mat not in tex:
            tex[mat] = {
                "c": load_map(mat, "Color"),
                "n": load_map(mat, "Normal"),
                "ao": load_map(mat, "AmbientOcclusion"),
            }

    # сетка мира окна (восток x, север y)
    xs = np.linspace(CENTER[0] - WIN_HALF, CENTER[0] + WIN_HALF, RES)
    ys = np.linspace(CENTER[1] + WIN_HALF, CENTER[1] - WIN_HALF, RES)  # север вверх
    X, Y = np.meshgrid(xs, ys)

    # класс из карты среза (данные: строка 0 = север)
    su = ((X - scx) / (2 * shalf) + 0.5) * sn
    sv = (1.0 - ((Y - scy) / (2 * shalf) + 0.5)) * sn
    si = np.clip(su.astype(int), 0, sn - 1)
    sj = np.clip(sv.astype(int), 0, sn - 1)
    cls = smap[sj, si]

    # рельеф: высота и нормаль (движок z=-север)
    Z = -Y
    def demh(x, z):
        u = np.clip((x + DEM_HALF) / DEM_STEP, 0, DEM_N - 1.001)
        v = np.clip((z + DEM_HALF) / DEM_STEP, 0, DEM_N - 1.001)
        i = u.astype(int); j = v.astype(int)
        fx = u - i; fy = v - j
        a = dem[j, i]; b = dem[j, i + 1]; c = dem[j + 1, i]; d = dem[j + 1, i + 1]
        return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy
    e = 4.0
    gx = demh(X + e, Z) - demh(X - e, Z)
    gz = demh(X, Z + e) - demh(X, Z - e)
    dem_n = np.stack([-gx, 2 * e * np.ones_like(gx), -gz], -1)
    dem_n /= np.linalg.norm(dem_n, axis=2, keepdims=True)

    # тайл-uv материала
    tu = ((X / TILE_M) % 1.0)
    tv = ((Z / TILE_M) % 1.0)

    albedo = np.zeros((RES, RES, 3), np.float32)
    matn = np.zeros((RES, RES, 3), np.float32); matn[..., 1] = 1.0
    ao = np.ones((RES, RES), np.float32)

    for c, (mat, tint) in MAT.items():
        mask = cls == c
        if not mask.any():
            continue
        if mat is None:
            albedo[mask] = WATER
            continue
        t = tex[mat]
        h, w = t["c"].shape[:2]
        pu = (tu[mask] * (w - 1)).astype(int)
        pv = (tv[mask] * (h - 1)).astype(int)
        col = t["c"][pv, pu] * np.array(tint)
        albedo[mask] = np.clip(col, 0, 1)
        if t["n"] is not None:
            nn = t["n"][pv, pu] * 2.0 - 1.0
            # tangent(x)->world x, tangent(y)->world z, tangent(z)->up
            matn[mask] = np.stack([nn[:, 0], nn[:, 2], nn[:, 1]], -1)
        if t["ao"] is not None:
            ao[mask] = t["ao"][pv, pu, 0]

    # смешиваем нормаль рельефа и материала
    N = dem_n + np.stack([matn[..., 0], np.zeros_like(matn[..., 0]), matn[..., 2]], -1) * 0.7
    N /= np.linalg.norm(N, axis=2, keepdims=True) + 1e-6

    L = np.array([-0.45, 0.40, 0.79]); L /= np.linalg.norm(L)   # низкое солнце
    ndl = np.clip((N * L).sum(2), 0, 1)
    sun = np.array([1.02, 0.87, 0.62]); sky = np.array([0.34, 0.44, 0.60])
    lit = albedo * ao[..., None] * (sky * 0.55 + sun * ndl[..., None])
    # вода бликует к солнцу
    water_mask = cls == 6
    lit[water_mask] = (WATER * 0.6 + sun * (ndl[water_mask, None] ** 3) * 0.5)

    img = np.clip(lit ** (1 / 2.2), 0, 1)
    Image.fromarray((img * 255).astype(np.uint8)).save(OUT)

    names = {0: "луг", 1: "газон", 2: "роща", 3: "лес", 4: "аллея", 5: "плац", 6: "вода", 7: "берег", 8: "мостовая"}
    u, cc = np.unique(cls, return_counts=True)
    print("окно %.0f×%.0f м @ (%.0f,%.0f), реальные материалы по классам:" % (
        2 * WIN_HALF, 2 * WIN_HALF, *CENTER))
    for k, v in sorted(zip(u, cc), key=lambda x: -x[1]):
        mat = MAT[int(k)][0] or "—(вода)"
        print("  %-9s %5.1f%%  → %s" % (names.get(int(k), "?"), 100 * v / cls.size, mat))
    print("прувф →", OUT)


if __name__ == "__main__":
    main()
