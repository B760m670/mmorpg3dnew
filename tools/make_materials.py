#!/usr/bin/env python3
"""Синтез PBR-материалов поверхности («скан без сканера», аудит v3 п.1).

Библиотеки сканов недоступны (Megascans — лицензия Epic; CC0-сайты закрыты
сетью среды), поэтому материалы синтезируются по референсам эпохи:
дернина луга, грунт просёлка, макадам шоссе (щебень), булыжник мостовой.
Каждый материал — пара текстур 1024², бесшовных по построению
(периодический шум/вороной):
  <имя>_alb.png — albedo (нормирован к среднему 0.5: шейдер умножает
                  зонный цвет на 2×albedo — тон зоны сохраняется)
  <имя>_nr.png  — RGBA: RG = наклон нормали (x,z), B=1, A = roughness

Проверка числами: средние/разбросы каналов печатаются при генерации.
Запуск: python3 tools/make_materials.py
"""
import os

import numpy as np
from PIL import Image

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(ROOT, "game2", "assets", "materials")
N = 1024
RNG = np.random.default_rng(1894)


# ---------------------------------------------------------------- шумы (тайл)
def value_noise(cells: int) -> np.ndarray:
    """Периодический value-шум NxN от решётки cells×cells."""
    lat = RNG.random((cells, cells))
    x = np.linspace(0.0, cells, N, endpoint=False)
    i0 = np.floor(x).astype(int) % cells
    i1 = (i0 + 1) % cells
    f = x - np.floor(x)
    f = f * f * (3.0 - 2.0 * f)
    a = lat[np.ix_(i0, i0)]
    b = lat[np.ix_(i0, i1)]
    c = lat[np.ix_(i1, i0)]
    d = lat[np.ix_(i1, i1)]
    fx = f[None, :]
    fy = f[:, None]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def fbm(cells: int, octaves: int) -> np.ndarray:
    out = np.zeros((N, N))
    amp, tot = 1.0, 0.0
    for k in range(octaves):
        out += amp * value_noise(cells << k)
        tot += amp
        amp *= 0.5
    return out / tot


def voronoi(cells: int):
    """Периодический вороной: F1, F2-F1, случайный тон ячейки, вектор до центра."""
    jit = RNG.random((cells, cells, 2)) * 0.85 + 0.075
    tone = RNG.random((cells, cells))
    x = np.linspace(0.0, cells, N, endpoint=False)
    X, Y = np.meshgrid(x, x)               # (row=y, col=x)
    ci = np.floor(X).astype(int)
    cj = np.floor(Y).astype(int)
    d1 = np.full((N, N), 9.0)
    d2 = np.full((N, N), 9.0)
    t = np.zeros((N, N))
    vx = np.zeros((N, N))
    vy = np.zeros((N, N))
    for dj in (-1, 0, 1):
        for di in (-1, 0, 1):
            pi = ci + di
            pj = cj + dj
            px = pi + jit[pj % cells, pi % cells, 0]
            py = pj + jit[pj % cells, pi % cells, 1]
            dx = px - X
            dy = py - Y
            d = np.hypot(dx, dy)
            closer = d < d1
            d2 = np.where(closer, d1, np.minimum(d2, d))
            t = np.where(closer, tone[pj % cells, pi % cells], t)
            vx = np.where(closer, dx, vx)
            vy = np.where(closer, dy, vy)
            d1 = np.minimum(d1, d)
    return d1, d2 - d1, t, vx, vy


# ---------------------------------------------------------------- сборка pbr
def normal_rg(h: np.ndarray, strength: float):
    dhx = (np.roll(h, -1, axis=1) - np.roll(h, 1, axis=1)) * strength
    dhy = (np.roll(h, -1, axis=0) - np.roll(h, 1, axis=0)) * strength
    return -dhx, -dhy


def save_mat(name: str, alb: np.ndarray, h: np.ndarray, nstr: float,
        rough: np.ndarray, desat: float = 0.65) -> None:
    # цвет в кадре несёт зона/класс — текстура несёт ФАКТУРУ: гасим свой
    # оттенок (desat) и нормируем по светимости (не по каналам — иначе
    # редкие цветные пятна разъезжаются в чужой оттенок)
    lum = alb @ np.array([0.30, 0.55, 0.15])
    alb = alb * (1.0 - desat) + lum[..., None] * desat
    alb = np.clip(alb * (0.5 / max(float(lum.mean()), 1e-4)), 0.0, 1.0)
    Image.fromarray((alb * 255).astype(np.uint8)).save(
        os.path.join(OUT, name + "_alb.png"))
    nx, ny = normal_rg(h, nstr)
    nr = np.zeros((N, N, 4))
    nr[..., 0] = np.clip(nx * 0.5 + 0.5, 0, 1)
    nr[..., 1] = np.clip(ny * 0.5 + 0.5, 0, 1)
    nr[..., 2] = 1.0
    nr[..., 3] = np.clip(rough, 0, 1)
    Image.fromarray((nr * 255).astype(np.uint8)).save(
        os.path.join(OUT, name + "_nr.png"))
    print("  %-8s alb=%.2f/%.2f/%.2f  σh=%.2f  rough=%.2f±%.2f" % (
        name, *alb.reshape(-1, 3).mean(axis=0), h.std(),
        rough.mean(), rough.std()))


def make_sod():
    """Дернина: кочковатый войлок травы с проплешинами земли."""
    h = 0.55 * fbm(8, 5) + 0.45 * fbm(48, 3)
    patch = fbm(6, 3)                       # проплешины
    bare = np.clip((patch - 0.62) * 6.0, 0, 1)
    green = np.stack([0.24 + 0.25 * h, 0.34 + 0.22 * h, 0.10 + 0.10 * h], -1)
    earth = np.array([0.30, 0.24, 0.15])
    alb = green * (1 - bare[..., None]) + earth * bare[..., None]
    alb *= (0.85 + 0.3 * fbm(96, 2))[..., None]
    rough = 0.88 - 0.08 * bare + 0.06 * (fbm(64, 2) - 0.5)
    save_mat("sod", alb, h * (1 - 0.5 * bare), 5.5, rough)


def make_dirt():
    """Грунт просёлка: утоптанная земля с вдавленными камешками."""
    base = fbm(10, 5)
    d1, edge, tone, _, _ = voronoi(64)
    pebble_mask = np.clip((tone - 0.60) * 5.0, 0, 1)   # камешки чаще и крупнее
    dome = np.clip(1.0 - d1 * 1.9, 0, 1) ** 1.4
    h = base * 0.5 + dome * pebble_mask * 0.8
    alb = np.stack([0.34 + 0.16 * base, 0.27 + 0.13 * base,
        0.18 + 0.09 * base], -1)
    grey = np.array([0.55, 0.53, 0.50])
    m = (pebble_mask * dome)[..., None]
    alb = alb * (1 - m) + grey * m
    rough = 0.86 - 0.30 * pebble_mask * dome
    save_mat("dirt", alb, h, 5.0, rough)


def make_macadam():
    """Макадам: плотно укатанный щебень (шоссе 1894)."""
    d1, edge, tone, _, _ = voronoi(72)      # щебень ~3 см при тайле 2 м
    stone = np.clip(edge * 4.0, 0, 1)       # грани щебня
    h = stone * (0.5 + 0.5 * tone) + 0.12 * fbm(20, 3)
    g = 0.42 + 0.16 * tone
    alb = np.stack([g * (1.0 + 0.08 * tone), g, g * (0.94 - 0.05 * tone)], -1)
    alb *= (0.88 + 0.24 * stone)[..., None]
    rough = 0.78 + 0.10 * (1 - stone)
    save_mat("macadam", alb, h, 4.0, rough)


def make_cobble():
    """Булыжник мостовой: окатанные камни, швы с землёй."""
    d1, edge, tone, _, _ = voronoi(14)          # камень ~15 см при тайле 2 м
    dome = np.clip(edge * 3.2, 0, 1) ** 0.6     # купол камня, швы у границ
    h = dome * (0.75 + 0.25 * tone) + 0.06 * fbm(64, 2)
    g = 0.40 + 0.16 * tone                      # серо-бурый гранит, без пестроты
    alb = np.stack([g * (1.0 + 0.06 * (tone - 0.5)), g,
        g * (0.96 - 0.05 * (tone - 0.5))], -1)
    seam = np.array([0.24, 0.19, 0.13])
    alb = alb * dome[..., None] + seam * (1 - dome[..., None])
    rough = 0.55 + 0.30 * (1 - dome)            # темя камней отполировано
    save_mat("cobble", alb, h, 4.2, rough, desat=0.5)


def main():
    os.makedirs(OUT, exist_ok=True)
    print("материалы →", OUT)
    make_sod()
    make_dirt()
    make_macadam()
    make_cobble()


if __name__ == "__main__":
    main()
