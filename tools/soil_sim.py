#!/usr/bin/env python3
"""Прототип ЗЕРНИСТОЙ ПОЧВЫ (DEM) — путь «частицы + связность + влага», как MPM
в кино. Частицы = материальные точки (комки), не микрозёрна (их 10^10 —
невозможно; см. расчёт). Физика: гравитация, контактное отталкивание, СВЯЗНОСТЬ
∝ ВЛАГЕ, трение-затухание, пол. Демонстрация числами: колонна почвы оседает —
СУХАЯ растекается в плоскую кучу (слабая связность), МОКРАЯ держит холм (влага
даёт когезию). Это и есть «зерно ведёт себя как настоящая почва».

R&D-прототип модели (офлайн). Реалтайм-зона под лопатой — на устройстве отдельно.
Запуск: python3 tools/soil_sim.py
"""
import numpy as np
from PIL import Image
from scipy.spatial import cKDTree

OUT = "/tmp/soil_sim.png"
R = 0.011
BOX_W, BOX_H = 1.2, 0.75
G = 1.0
K_REP = 6.0
K_COH = 0.22                # связность как поверхностное натяжение (влага=1); слабее отталкивания
FRIC = 0.35                 # тангенциальное затухание (трение зёрен)
DT = 0.010
STEPS = 1100


def column(rng):
    """узкая высокая колонна частиц в центре — ей и предстоит осесть."""
    xs, ys = [], []
    step = 2.02 * R
    y = R
    row = 0
    while y < 0.7:
        x = 0.5 - 0.08
        while x < 0.5 + 0.08:
            xs.append(x + rng.uniform(-0.08, 0.08) * R)
            ys.append(y)
            x += step
        y += step * 0.9
        row += 1
    return np.stack([np.array(xs), np.array(ys)], 1)


def step(p, v, moisture):
    n = len(p)
    F = np.zeros((n, 2))
    F[:, 1] -= G
    r_coh = 2.8 * R
    pairs = np.array(list(cKDTree(p).query_pairs(r_coh)), dtype=int)
    if len(pairs):
        i, j = pairs[:, 0], pairs[:, 1]
        d = p[i] - p[j]
        dist = np.linalg.norm(d, axis=1) + 1e-9
        nrm = d / dist[:, None]
        overlap = 2 * R - dist
        f_rep = np.where(overlap > 0, K_REP * overlap, 0.0)
        coh_zone = np.clip((r_coh - dist) / (r_coh - 2 * R), 0, 1)
        f_coh = -K_COH * moisture * coh_zone * (dist > 2 * R)
        fn = (f_rep + f_coh)[:, None] * nrm
        np.add.at(F, i, fn)
        np.add.at(F, j, -fn)
        # трение: гасим относительную скорость по касательной у контактов
        dv = v[i] - v[j]
        tang = dv - (dv * nrm).sum(1)[:, None] * nrm
        ft = -FRIC * tang * (overlap > -R)[:, None]
        np.add.at(F, i, ft)
        np.add.at(F, j, -ft)
    v = (v + F * DT) * 0.98            # глобальное затухание — устойчивость
    p = p + v * DT
    below = p[:, 1] < R
    p[below, 1] = R
    v[below, 1] *= -0.1
    v[below, 0] *= (1 - FRIC)          # трение о пол
    p[:, 0] = np.clip(p[:, 0], R, BOX_W - R)
    return p, v


def run(moisture, rng):
    p = column(rng)
    v = np.zeros_like(p)
    for _ in range(STEPS):
        p, v = step(p, v, moisture)
    return p


def measure(p):
    base = p[p[:, 1] < 0.06]
    half_w = (base[:, 0].max() - base[:, 0].min()) / 2 if len(base) else 0
    peak = p[:, 1].max()
    return half_w, peak


def draw(p, color):
    S = 520
    view_w, view_h = 0.9, 0.22          # приблизить к почве (низ бокса)
    x0 = 0.15
    H = int(S * view_h / view_w)
    img = np.full((H, S, 3), 208, np.uint8)
    rad = max(2, int(R / view_w * S))
    for x, y in p:
        px = int((x - x0) / view_w * S); py = int(H - y / view_h * H)
        img[max(py - rad, 0):min(py + rad, H - 1) + 1,
            max(px - rad, 0):min(px + rad, S - 1) + 1] = color
    return img


def main():
    n = len(column(np.random.default_rng(1)))
    print("DEM: частиц %d, шагов %d" % (n, STEPS))
    dry = run(0.08, np.random.default_rng(1894))
    wet = run(1.00, np.random.default_rng(1894))
    dw, dh = measure(dry)
    ww, wh = measure(wet)
    print("СУХАЯ (влага 0.08): полуширина кучи=%.2f  высота=%.2f" % (dw, dh))
    print("МОКРАЯ(влага 1.00): полуширина кучи=%.2f  высота=%.2f" % (ww, wh))
    print("угол насыпи ~ atan(h/полуш): сухая %.0f°, мокрая %.0f° (влага→круче)" % (
        np.degrees(np.arctan2(dh, dw + 1e-6)), np.degrees(np.arctan2(wh, ww + 1e-6))))
    a = draw(dry, (150, 120, 85)); b = draw(wet, (92, 66, 42))
    gap = np.full((a.shape[0], 8, 3), 240, np.uint8)
    Image.fromarray(np.concatenate([a, gap, b], 1)).save(OUT)
    print("рендер (слева СУХАЯ растеклась / справа МОКРАЯ холм) →", OUT)


if __name__ == "__main__":
    main()
