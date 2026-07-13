#!/usr/bin/env python3
# Генерация мира Гатчины: тайловые PBR-материалы грунта + рельеф terrain.glb.
# Рельеф строится из layout.json (источник истины): равнина, холм под дворцом,
# котловины озёр, дороги. Вершинные цвета кодируют смесь материалов
# (R=трава, G=грунт/дорога, B=брусчатка), Godot-шейдер по ним смешивает тайлы.
import bpy, bmesh, json, math, os, sys
import numpy as np

ARGS = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
ROOT = ARGS[0] if ARGS else "/home/user/mmorpg3dnew"
LAYOUT = os.path.join(ROOT, "game/world/gatchina/layout.json")
TEXDIR = os.path.join(ROOT, "game/world/textures")
OUTDIR = os.path.join(ROOT, "game/world/gatchina")
os.makedirs(TEXDIR, exist_ok=True)

with open(LAYOUT) as f:
    L = json.load(f)

# ---------- 1. Тайловые PBR-текстуры грунта (периодические, бесшовные) ----------
def periodic_fbm(size, base, octaves, seed):
    rng = np.random.default_rng(seed)
    out = np.zeros((size, size), np.float32)
    amp, freq, norm = 1.0, int(base), 0.0
    for _ in range(octaves):
        g = rng.random((freq, freq)).astype(np.float32)
        # билинейная интерполяция с оборачиванием => бесшовный тайл
        xs = np.linspace(0, freq, size, endpoint=False)
        x0 = np.floor(xs).astype(int) % freq
        x1 = (x0 + 1) % freq
        fx = (xs - np.floor(xs)).astype(np.float32)
        fx = fx*fx*(3-2*fx)
        gx = g[x0][:, x0]*(1-fx)[None, :]*(1-fx)[:, None] + \
             g[x1][:, x1]*fx[None, :]*fx[:, None] + \
             g[x0][:, x1]*fx[None, :]*(1-fx)[:, None] + \
             g[x1][:, x0]*(1-fx)[None, :]*fx[:, None]
        out += amp*gx
        norm += amp; amp *= 0.5; freq *= 2
    out /= norm
    return (out-out.min())/(out.max()-out.min()+1e-6)

def normal_from_height(h, strength):
    gy, gx = np.gradient(h.astype(np.float32))
    nx, ny, nz = -gx*strength, -gy*strength, np.ones_like(h)
    ln = np.sqrt(nx*nx+ny*ny+nz*nz)+1e-6
    n = np.stack([nx/ln, ny/ln, nz/ln], -1)*0.5+0.5
    return n

def save_png(arr, path):
    # arr: HxWx(3|4) float 0..1 -> PNG через bpy
    h, w = arr.shape[:2]
    if arr.shape[2] == 3:
        arr = np.concatenate([arr, np.ones((h, w, 1), np.float32)], -1)
    img = bpy.data.images.new(os.path.basename(path), width=w, height=h, alpha=True)
    flat = np.ascontiguousarray(arr[::-1], np.float32).reshape(-1)  # Blender снизу-вверх
    img.pixels.foreach_set(flat)
    img.file_format = 'PNG'
    img.filepath_raw = path
    img.save()
    bpy.data.images.remove(img)

def mix(c0, c1, t):
    return c0[None, None]*(1-t)[..., None]+c1[None, None]*t[..., None]

S = 512
# ТРАВА — газон парка, вариации зелёного, редкие сухие пятна
gh = periodic_fbm(S, 8, 5, 11)
gfine = periodic_fbm(S, 32, 3, 12)
grass = mix(np.array([0.20, 0.34, 0.12]), np.array([0.34, 0.47, 0.18]), gh)
grass = grass*(0.85+0.3*gfine[..., None])
dry = np.clip((periodic_fbm(S, 6, 4, 13)-0.62)*4, 0, 1)
a = (dry*0.5)[..., None]
grass = grass*(1-a) + np.array([0.45, 0.42, 0.22])[None, None]*a
save_png(np.clip(grass, 0, 1), os.path.join(TEXDIR, "grass_albedo.png"))
save_png(normal_from_height(gh*0.4+gfine*0.6, 2.2), os.path.join(TEXDIR, "grass_normal.png"))

# ГРУНТ — утоптанная земля/грунтовая дорога
dh = periodic_fbm(S, 10, 5, 21)
druts = periodic_fbm(S, 24, 3, 22)
dirt = mix(np.array([0.28, 0.20, 0.13]), np.array([0.42, 0.31, 0.20]), dh)
dirt = dirt*(0.8+0.35*druts[..., None])
save_png(np.clip(dirt, 0, 1), os.path.join(TEXDIR, "dirt_albedo.png"))
save_png(normal_from_height(dh*0.5+druts*0.5, 3.0), os.path.join(TEXDIR, "dirt_normal.png"))

# БРУСЧАТКА — булыжная мостовая проспекта (сетка камней)
xx, yy = np.meshgrid(np.linspace(0, 1, S, endpoint=False), np.linspace(0, 1, S, endpoint=False))
cell = 14.0
jx = periodic_fbm(S, 14, 2, 31)*0.5
jy = periodic_fbm(S, 14, 2, 32)*0.5
cx = (xx*cell + jx*0.3) % 1.0
cy = (yy*cell + jy*0.3) % 1.0
d = np.minimum(np.minimum(cx, 1-cx), np.minimum(cy, 1-cy))
stone_mask = np.clip(d*6, 0, 1)  # 0 в швах, 1 в центре камня
stone_tone = periodic_fbm(S, cell*2, 2, 33)
cob = mix(np.array([0.30, 0.30, 0.31]), np.array([0.52, 0.51, 0.49]), stone_tone)
cob = cob*(0.35+0.65*stone_mask[..., None])
save_png(np.clip(cob, 0, 1), os.path.join(TEXDIR, "cobble_albedo.png"))
save_png(normal_from_height(stone_mask*0.8+stone_tone*0.2, 3.5), os.path.join(TEXDIR, "cobble_normal.png"))
print("[tex] grass/dirt/cobble albedo+normal ->", TEXDIR)

# ---------- 2. Рельеф из layout.json ----------
T = L["terrain"]
SIZE = T["size"]; RES = T["resolution"]
half = SIZE/2.0
xs = np.linspace(-half, half, RES)
zs = np.linspace(-half, half, RES)
GX, GZ = np.meshgrid(xs, zs)          # мировые координаты каждой вершины
H = np.full((RES, RES), T["base_height"], np.float32)
# материалы: слои весов
W_grass = np.ones((RES, RES), np.float32)
W_dirt = np.zeros((RES, RES), np.float32)
W_cob = np.zeros((RES, RES), np.float32)

# лёгкий рельеф равнины
plain = periodic_fbm(RES, 6, 4, 101)
H += (plain-0.5)*2.2

# холм под дворцом
def bump(cx, cz, rx, rz, amp):
    r = ((GX-cx)/rx)**2 + ((GZ-cz)/rz)**2
    return amp*np.exp(-r*2.2)
H += bump(0, 0, 180, 120, 6.0)      # дворцовый холм

# котловины озёр
lake_depth = np.zeros((RES, RES), np.float32)
for lk in L["lakes"]:
    cx, cz = lk["center"]; rx, rz = lk["radius"]
    r = np.sqrt(((GX-cx)/rx)**2 + ((GZ-cz)/rz)**2)
    basin = np.clip(1.0-r, 0, 1)
    d = (basin**1.5)*lk["depth"]
    lake_depth = np.maximum(lake_depth, d)
    # берег: у воды меньше травы, больше грунта
    shore = np.clip(1.2-r, 0, 1)*np.clip(r, 0, 1)
    W_dirt += shore*0.6
H -= lake_depth

# дороги: понижают траву, поднимают грунт/брусчатку вдоль полилиний
def seg_dist(px, pz, ax, az, bx, bz):
    vx, vz = bx-ax, bz-az
    wx, wz = px-ax, pz-az
    t = np.clip((wx*vx+wz*vz)/(vx*vx+vz*vz+1e-6), 0, 1)
    dx, dz = px-(ax+t*vx), pz-(az+t*vz)
    return np.sqrt(dx*dx+dz*dz)

for rd in L["roads"]:
    pts = rd["points"]; hw = rd["width"]/2.0
    dmin = np.full((RES, RES), 1e9, np.float32)
    for i in range(len(pts)-1):
        ax, az = pts[i]; bx, bz = pts[i+1]
        dmin = np.minimum(dmin, seg_dist(GX, GZ, ax, az, bx, bz))
    onroad = np.clip((hw-dmin)/2.0+0.5, 0, 1)  # 1 на дороге, мягкий край
    onroad = np.where(dmin < hw+1.5, onroad, 0.0)
    if rd["material"] == "cobble":
        W_cob = np.maximum(W_cob, onroad)
    else:
        W_dirt = np.maximum(W_dirt, onroad)
    H -= onroad*0.15  # дорога чуть врезана
    W_grass *= (1.0-onroad)

# нормализация весов
W_grass = np.clip(W_grass, 0, 1)
W_dirt = np.clip(W_dirt*(1.0-W_cob), 0, 1)
W_cob = np.clip(W_cob, 0, 1)
tot = W_grass+W_dirt+W_cob+1e-6
W_grass, W_dirt, W_cob = W_grass/tot, W_dirt/tot, W_cob/tot

# ---------- 3. Меш рельефа ----------
mesh = bpy.data.meshes.new("terrain")
obj = bpy.data.objects.new("terrain", mesh)
bpy.context.collection.objects.link(obj)
bm = bmesh.new()
verts = [[None]*RES for _ in range(RES)]
col_layer = bm.loops.layers.color.new("Col")
for j in range(RES):
    for i in range(RES):
        verts[j][i] = bm.verts.new((GX[j, i], H[j, i], GZ[j, i]))
bm.verts.ensure_lookup_table()
uv_layer = bm.loops.layers.uv.new("UVMap")
for j in range(RES-1):
    for i in range(RES-1):
        v00, v10, v11, v01 = verts[j][i], verts[j][i+1], verts[j+1][i+1], verts[j+1][i]
        # порядок обхода даёт нормали ВВЕРХ (+Y) — иначе поверхность неосвещена
        for tri in ((v00, v11, v10), (v00, v01, v11)):
            face = bm.faces.new(tri)
            for loop in face.loops:
                vx, vz = loop.vert.co.x, loop.vert.co.z
                # индекс вершины -> вес
                ii = int(round((vx+half)/SIZE*(RES-1)))
                jj = int(round((vz+half)/SIZE*(RES-1)))
                ii = min(max(ii, 0), RES-1); jj = min(max(jj, 0), RES-1)
                loop[col_layer] = (float(W_grass[jj, ii]), float(W_dirt[jj, ii]), float(W_cob[jj, ii]), 1.0)
                loop[uv_layer].uv = ((vx+half)/8.0, (vz+half)/8.0)  # тайлинг ~8м
bm.normal_update()
bm.to_mesh(mesh)
bm.free()

# материал-заглушка (реальный шейдер назначается в Godot)
matmesh = bpy.data.materials.new("ground")
matmesh.use_nodes = True
obj.data.materials.append(matmesh)

# экспорт
for o in bpy.context.selected_objects:
    o.select_set(False)
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
out = os.path.join(OUTDIR, "terrain.glb")
bpy.ops.export_scene.gltf(filepath=out, use_selection=True,
    export_format='GLB', export_vertex_color='ACTIVE',
    export_yup=True, export_apply=True)
print("[terrain] ->", out, "verts", RES*RES)

# heights.json — облегчённая высотная карта (129×129), из неё Godot строит
# меш рельефа прямо в движке (scripts/world.gd), плюс размещает объекты и карту.
K = 129
idx = np.linspace(0, RES - 1, K).astype(int)
Hd = H[np.ix_(idx, idx)]
with open(os.path.join(OUTDIR, "heights.json"), "w") as f:
    json.dump({"res": K, "size": SIZE, "h": [round(float(x), 3) for x in Hd.reshape(-1)]}, f)
print("[terrain] heights.json saved (%dx%d)" % (K, K))
