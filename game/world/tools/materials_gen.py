#!/usr/bin/env python3
# Библиотека настоящих PBR-материалов (тайловые albedo+normal+rough).
# Камень-руст (ашлар), кровельный металл, черепица, доски, штукатурка.
import bpy, os, sys
import numpy as np

A = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
ROOT = A[0] if A else "/home/user/mmorpg3dnew"
TEX = os.path.join(ROOT, "game/world/textures")
os.makedirs(TEX, exist_ok=True)
S = 1024

def fbm(size, base, octaves, seed):
    rng = np.random.default_rng(seed)
    out = np.zeros((size, size), np.float32); amp, freq, norm = 1.0, int(base), 0.0
    for _ in range(octaves):
        g = rng.random((freq, freq)).astype(np.float32)
        xs = np.linspace(0, freq, size, endpoint=False)
        x0 = np.floor(xs).astype(int) % freq; x1 = (x0+1) % freq
        fx = xs-np.floor(xs); fx = (fx*fx*(3-2*fx)).astype(np.float32)
        gx = (g[np.ix_(x0,x0)]*(1-fx)[None,:]*(1-fx)[:,None] + g[np.ix_(x1,x1)]*fx[None,:]*fx[:,None]
              + g[np.ix_(x0,x1)]*fx[None,:]*(1-fx)[:,None] + g[np.ix_(x1,x0)]*(1-fx)[None,:]*fx[:,None])
        out += amp*gx; norm += amp; amp *= 0.5; freq *= 2
    out /= norm; return (out-out.min())/(out.max()-out.min()+1e-6)

def save(arr, path):
    h, w = arr.shape[:2]
    if arr.shape[2] == 3:
        arr = np.concatenate([arr, np.ones((h,w,1),np.float32)], -1)
    img = bpy.data.images.new(os.path.basename(path), width=w, height=h, alpha=True)
    img.pixels.foreach_set(np.ascontiguousarray(arr[::-1], np.float32).reshape(-1))
    img.file_format = 'PNG'; img.filepath_raw = path; img.save()
    bpy.data.images.remove(img)

def nrm(height, strength):
    gy, gx = np.gradient(height.astype(np.float32))
    nx, ny, nz = -gx*strength, -gy*strength, np.ones_like(height)
    ln = np.sqrt(nx*nx+ny*ny+nz*nz)+1e-6
    return (np.stack([nx/ln, ny/ln, nz/ln], -1)*0.5+0.5)

def save_rough(r, path): save(np.repeat(r[...,None],3,axis=2), path)

YY, XX = np.mgrid[0:S, 0:S] / S  # 0..1

# ---------- АШЛАР (тёсаный камень, коврами по фасаду) ----------
def ashlar(courses, stagger, mortar, seed, base_rgb, tone_var, chamfer):
    row = np.floor(YY*courses).astype(int)
    off = (row % 2) * stagger
    col = np.floor((XX + off) * courses*2).astype(int)  # блоки шире, чем выше
    # расстояние до шва
    ry = np.minimum(YY*courses % 1.0, 1.0 - (YY*courses % 1.0))
    cxv = (XX+off)*courses*2 % 1.0
    rx = np.minimum(cxv, 1.0-cxv)
    joint = np.minimum(ry, rx)
    seam = np.clip(joint/mortar, 0, 1)          # 0 в шве, 1 на камне
    # рустовка: скошенная фаска у краёв блока
    face = np.clip((joint-mortar)/chamfer, 0, 1)
    height = seam*0.6 + face*0.4
    # тон блока
    rng = np.random.default_rng(seed)
    ntone = rng.random((courses*2+2, courses+2))
    bt = ntone[np.clip(col,0,courses*2+1), np.clip(row,0,courses+1)]
    grain = fbm(S, 32, 4, seed+7)
    weather = fbm(S, 6, 4, seed+9)
    tone = 0.75 + tone_var*(bt-0.5)*2 + 0.12*(grain-0.5)
    tone *= (0.9 + 0.2*weather)
    alb = np.array(base_rgb)[None,None]*tone[...,None]
    alb = alb*(0.55+0.45*seam[...,None])         # швы темнее
    dirt = np.clip((weather-0.6)*2,0,1)*0.15
    alb *= (1-dirt[...,None])
    return np.clip(alb,0,1), height, np.clip(0.72+0.18*(1-seam)+0.1*grain,0,1)

alb,h,r = ashlar(6, 0.5, 0.02, 3, (0.66,0.62,0.50), 0.10, 0.05)
save(alb, TEX+"/stone_albedo.png"); save(nrm(h,3.5), TEX+"/stone_normal.png"); save_rough(r, TEX+"/stone_rough.png")

# рустованный цоколь — грубее, глубже швы, крупнее блоки
alb,h,r = ashlar(4, 0.5, 0.03, 15, (0.60,0.56,0.45), 0.12, 0.09)
save(alb, TEX+"/rustic_albedo.png"); save(nrm(h,5.5), TEX+"/rustic_normal.png"); save_rough(r, TEX+"/rustic_rough.png")

# ---------- КРОВЕЛЬНЫЙ МЕТАЛЛ (фальцевая кровля, патина) ----------
seams = np.clip((np.abs((XX*16 % 1.0)-0.5)*2-0.86)/0.14, 0, 1)  # вертикальные фальцы
patina = fbm(S, 8, 4, 41)
streak = fbm(S, 4, 3, 42)
base = np.array([0.20,0.34,0.30])   # позеленевшая медь/крашеный металл
alb = base[None,None]*(0.8+0.4*patina[...,None])
alb = alb*(1-0.25*seams[...,None])
alb = alb*(0.9+0.2*streak[...,None])
h = seams*0.7 + 0.05*patina
save(np.clip(alb,0,1), TEX+"/roofmetal_albedo.png"); save(nrm(h,4.0), TEX+"/roofmetal_normal.png")
save_rough(np.clip(0.35+0.3*patina,0,1), TEX+"/roofmetal_rough.png")

# ---------- ЧЕРЕПИЦА (для домов) ----------
rows = 22
ry2 = YY*rows % 1.0
tile_row = np.floor(YY*rows).astype(int)
off = (tile_row % 2)*0.5
cx2 = (XX*rows*0.9+off) % 1.0
overlap = np.clip((0.75-ry2)/0.75,0,1)  # нижний край черепицы выступает
round_tile = 1-np.clip((np.abs(cx2-0.5)*2-0.6)/0.4,0,1)
h = overlap*0.6 + round_tile*0.4
tone = fbm(S, 16, 4, 51)
alb = np.array([0.52,0.24,0.18])[None,None]*(0.8+0.4*tone[...,None])
alb = alb*(0.7+0.3*overlap[...,None])
save(np.clip(alb,0,1), TEX+"/rooftile_albedo.png"); save(nrm(h,4.5), TEX+"/rooftile_normal.png")
save_rough(np.full((S,S),0.8,np.float32), TEX+"/rooftile_rough.png")

# ---------- ДОСКИ (дерево) ----------
planks = 10
py = YY*planks % 1.0
pl_row = np.floor(YY*planks).astype(int)
gap = np.clip(np.minimum(py,1-py)/0.03,0,1)
grain = fbm(S, 64, 3, 61)*0.5 + fbm(S, 8, 3, 62)*0.5
rng = np.random.default_rng(63); pt = rng.random(planks+1)[np.clip(pl_row,0,planks)]
alb = np.array([0.34,0.24,0.15])[None,None]*(0.7+0.5*(0.5*pt[...,None]+0.5*grain[...,None]))
alb = alb*(0.6+0.4*gap[...,None])
save(np.clip(alb,0,1), TEX+"/wood_albedo.png"); save(nrm(gap*0.3+grain*0.7,2.5), TEX+"/wood_normal.png")
save_rough(np.full((S,S),0.75,np.float32), TEX+"/wood_rough.png")

# ---------- ШТУКАТУРКА (стены домов, красится цветом материала) ----------
bump = fbm(S, 48, 4, 71)*0.6 + fbm(S,10,3,72)*0.4
alb = np.full((S,S,3),0.86,np.float32)*(0.9+0.15*bump[...,None])
save(np.clip(alb,0,1), TEX+"/plaster_albedo.png"); save(nrm(bump,1.5), TEX+"/plaster_normal.png")
save_rough(np.full((S,S),0.9,np.float32), TEX+"/plaster_rough.png")

print("[mat] library ->", TEX)
