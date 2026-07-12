#!/usr/bin/env python3
# Карта Гатчины из того же layout.json (без рассинхрона с миром).
# Рисует сушу, парки, озёра, дороги, метки зданий. Маркер игрока — в Godot.
import bpy, json, os, sys
import numpy as np

ARGS = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
ROOT = ARGS[0] if ARGS else "/home/user/mmorpg3dnew"
G = os.path.join(ROOT, "game/world/gatchina")
with open(os.path.join(G, "layout.json")) as f:
    L = json.load(f)
SIZE = L["terrain"]["size"]; half = SIZE/2.0
N = 1024
img = np.zeros((N, N, 3), np.float32)

def w2p(x, z):
    # мир (X восток, Z юг) -> пиксель (col, row), север сверху
    px = (x + half) / SIZE * (N-1)
    py = (z + half) / SIZE * (N-1)
    return px, py

YY, XX = np.meshgrid(np.arange(N), np.arange(N), indexing='ij')  # row=YY, col=XX
def to_world(col, row):
    x = col / (N-1) * SIZE - half
    z = row / (N-1) * SIZE - half
    return x, z
WX = XX / (N-1) * SIZE - half
WZ = YY / (N-1) * SIZE - half

# фон — светлая земля (пергамент)
img[:] = np.array([0.86, 0.82, 0.72])

# парки/леса
for fr in L["forests"]:
    cx, cz = fr["center"]; rx, rz = fr["radius"]
    r = np.sqrt(((WX-cx)/rx)**2 + ((WZ-cz)/rz)**2)
    m = (r < 1.0)
    img[m] = np.array([0.45, 0.58, 0.38])

# озёра
for lk in L["lakes"]:
    cx, cz = lk["center"]; rx, rz = lk["radius"]
    r = np.sqrt(((WX-cx)/rx)**2 + ((WZ-cz)/rz)**2)
    m = (r < 1.0)
    img[m] = np.array([0.42, 0.63, 0.74])
    edge = (r < 1.0) & (r > 0.92)
    img[edge] = np.array([0.30, 0.48, 0.60])

# дороги
def draw_line(x0, z0, x1, z1, wpx, col):
    p0 = np.array(w2p(x0, z0)); p1 = np.array(w2p(x1, z1))
    d = p1 - p0; ln = np.hypot(*d)
    if ln < 1e-3: return
    n = int(ln*2)+1
    for t in np.linspace(0, 1, n):
        c, rr = p0 + d*t
        ci, ri = int(round(c)), int(round(rr))
        img[max(ri-wpx,0):ri+wpx+1, max(ci-wpx,0):ci+wpx+1] = col

for rd in L["roads"]:
    pts = rd["points"]
    col = np.array([0.55, 0.55, 0.57]) if rd["material"] == "cobble" else np.array([0.66, 0.55, 0.40])
    wpx = max(int(rd["width"]/SIZE*N/2), 2)
    for i in range(len(pts)-1):
        draw_line(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1], wpx, col)

# здания — золотые метки (квадрат по footprint)
for b in L["buildings"]:
    x, z = b["position"]; fw, fh = b.get("footprint", [20, 20])
    px, py = w2p(x, z)
    rw = max(int(fw/SIZE*N/2), 4); rh = max(int(fh/SIZE*N/2), 4)
    ci, ri = int(px), int(py)
    img[max(ri-rh,0):ri+rh, max(ci-rw,0):ci+rw] = np.array([0.80, 0.66, 0.30])
    # рамка
    img[max(ri-rh,0):ri+rh, max(ci-rw,0):max(ci-rw,0)+1] = np.array([0.4,0.3,0.1])
    img[max(ri-rh,0):ri+rh, min(ci+rw,N-1):min(ci+rw,N-1)+1] = np.array([0.4,0.3,0.1])

# городские кварталы — светлые пятна домов
for blk in L["town"]["blocks"]:
    cx, cz = blk["center"]; bw, bh = blk["size"]
    r = (np.abs(WX-cx) < bw/2) & (np.abs(WZ-cz) < bh/2)
    img[r & (img[:,:,0] > 0.8)] = np.array([0.78, 0.72, 0.60])

# точка спавна
sx, sz = L["spawn"]["position"]
px, py = w2p(sx, sz); ci, ri = int(px), int(py)
img[max(ri-5,0):ri+5, max(ci-5,0):ci+5] = np.array([0.85, 0.20, 0.15])

# рамка карты
img[:6,:] = 0.2; img[-6:,:] = 0.2; img[:,:6] = 0.2; img[:,-6:] = 0.2

out = os.path.join(G, "map.png")
flat = np.concatenate([img, np.ones((N,N,1),np.float32)], -1)
im = bpy.data.images.new("map", width=N, height=N, alpha=True)
im.pixels.foreach_set(np.ascontiguousarray(flat[::-1], np.float32).reshape(-1))
im.file_format = 'PNG'; im.filepath_raw = out; im.save()
print("[map] ->", out)
