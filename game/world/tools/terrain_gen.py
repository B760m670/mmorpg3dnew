#!/usr/bin/env python3
# Рельеф Гатчины — большой квадрат под город (по умолчанию 6×6 км). Считает поле
# высот и сохраняет heights.json; сам меш строит Godot в движке (scripts/world.gd)
# с правильными нормалями. Гатчинский комплекс — в центре, вокруг — естественная
# равнина Ижорского плато с мягким рельефом.
import json, os, sys
import numpy as np

ARGS = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
ROOT = ARGS[0] if ARGS else "/home/user/mmorpg3dnew"
LAYOUT = os.path.join(ROOT, "game/world/gatchina/layout.json")
OUTDIR = os.path.join(ROOT, "game/world/gatchina")
with open(LAYOUT) as f:
    L = json.load(f)

T = L["terrain"]
SIZE = float(T["size"])
RES = int(T["resolution"])
half = SIZE / 2.0
xs = np.linspace(-half, half, RES)
GX, GZ = np.meshgrid(xs, xs)
H = np.full((RES, RES), float(T.get("base_height", 0.0)), np.float32)

def fbm(res, base, octaves, seed):
    rng = np.random.default_rng(seed)
    out = np.zeros((res, res), np.float32); amp, freq, norm = 1.0, int(base), 0.0
    for _ in range(octaves):
        g = rng.random((freq, freq)).astype(np.float32)
        t = np.linspace(0, freq, res, endpoint=False)
        i0 = np.floor(t).astype(int) % freq; i1 = (i0+1) % freq
        f = t-np.floor(t); f = (f*f*(3-2*f)).astype(np.float32)
        gx = (g[np.ix_(i0,i0)]*(1-f)[None,:]*(1-f)[:,None] + g[np.ix_(i1,i1)]*f[None,:]*f[:,None]
              + g[np.ix_(i0,i1)]*f[None,:]*(1-f)[:,None] + g[np.ix_(i1,i0)]*(1-f)[None,:]*f[:,None])
        out += amp*gx; norm += amp; amp *= 0.5; freq *= 2
    out /= norm; return (out-out.min())/(out.max()-out.min()+1e-6)

# мягкий естественный рельеф всей равнины (крупная волна + мелкая)
H += (fbm(RES, 4, 4, 101) - 0.5) * 9.0     # пологие возвышенности до ~5 м
H += (fbm(RES, 12, 4, 102) - 0.5) * 2.5

def bump(cx, cz, rx, rz, amp):
    r = ((GX-cx)/rx)**2 + ((GZ-cz)/rz)**2
    return amp*np.exp(-r*2.2)
H += bump(0, 0, 200, 130, 7.0)             # дворцовый холм

# котловины озёр
for lk in L.get("lakes", []):
    cx, cz = lk["center"]; rx, rz = lk["radius"]
    r = np.sqrt(((GX-cx)/rx)**2 + ((GZ-cz)/rz)**2)
    H -= (np.clip(1.0-r, 0, 1)**1.5) * float(lk["depth"])

# лёгкая просадка дорог
def seg_d(px, pz, ax, az, bx, bz):
    vx, vz = bx-ax, bz-az; wx, wz = px-ax, pz-az
    t = np.clip((wx*vx+wz*vz)/(vx*vx+vz*vz+1e-6), 0, 1)
    return np.sqrt((px-(ax+t*vx))**2 + (pz-(az+t*vz))**2)
for rd in L.get("roads", []):
    pts = rd["points"]; hw = rd["width"]/2.0
    dmin = np.full((RES, RES), 1e9, np.float32)
    for i in range(len(pts)-1):
        dmin = np.minimum(dmin, seg_d(GX, GZ, pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1]))
    H -= np.clip((hw-dmin)/hw, 0, 1) * 0.2

# heights.json (129/257 — из него Godot строит меш и сажает объекты)
K = int(T.get("heights_res", 257))
idx = np.linspace(0, RES-1, K).astype(int)
Hd = H[np.ix_(idx, idx)]
with open(os.path.join(OUTDIR, "heights.json"), "w") as f:
    json.dump({"res": K, "size": SIZE, "h": [round(float(x), 3) for x in Hd.reshape(-1)]}, f)
print("[terrain] heights.json %dx%d, size %.0f м, отметки %.1f..%.1f м" %
      (K, K, SIZE, float(H.min()), float(H.max())))
