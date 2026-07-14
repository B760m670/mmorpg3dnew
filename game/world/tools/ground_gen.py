#!/usr/bin/env python3
# Библиотека НАСТОЯЩИХ грунтов и мощения — тайловые PBR-текстуры (albedo+normal+rough).
# Земля везде разная: луг, лесная подстилка, пашня, садовая земля, суглинок — и
# мощёная дорога (брусчатка). Реалистичность даёт клеточная (worley) структура:
# камни/комья/галька как настоящие, а не «шумовое пятно».
import bpy, os, sys, json
import numpy as np

A = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
ROOT = A[0] if A else "/home/user/mmorpg3dnew"
GD = os.path.join(ROOT, "game/world/textures/ground")
os.makedirs(GD, exist_ok=True)
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

# Бесшовная клеточная (worley) текстура: F1/F2 расстояния и id ячейки.
def worley(size, cells, seed):
    rng = np.random.default_rng(seed)
    fx = rng.random((cells, cells)).astype(np.float32)
    fy = rng.random((cells, cells)).astype(np.float32)
    cid = rng.random((cells, cells)).astype(np.float32)
    lin = ((np.arange(size)+0.5)/size*cells).astype(np.float32)
    GX, GY = np.meshgrid(lin, lin)
    ix = np.floor(GX).astype(int); iy = np.floor(GY).astype(int)
    F1 = np.full((size, size), 9.9, np.float32)
    F2 = np.full((size, size), 9.9, np.float32)
    ID = np.zeros((size, size), np.float32)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            cxg = (ix+dx) % cells; cyg = (iy+dy) % cells
            fpx = (ix+dx) + fx[cyg, cxg]; fpy = (iy+dy) + fy[cyg, cxg]
            d = (GX-fpx)**2 + (GY-fpy)**2
            closer = d < F1
            F2 = np.where(closer, F1, np.minimum(F2, d))
            ID = np.where(closer, cid[cyg, cxg], ID)
            F1 = np.where(closer, d, F1)
    return np.sqrt(F1), np.sqrt(F2), ID

def save(arr, path):
    h, w = arr.shape[:2]
    if arr.ndim == 2: arr = np.repeat(arr[...,None], 3, axis=2)
    if arr.shape[2] == 3: arr = np.concatenate([arr, np.ones((h,w,1),np.float32)], -1)
    img = bpy.data.images.new(os.path.basename(path), width=w, height=h, alpha=True)
    img.pixels.foreach_set(np.ascontiguousarray(arr[::-1], np.float32).reshape(-1))
    img.file_format = 'PNG'; img.filepath_raw = path; img.save()
    bpy.data.images.remove(img)

def nrm(height, strength):
    gy, gx = np.gradient(height.astype(np.float32))
    nx, ny, nz = -gx*strength, -gy*strength, np.ones_like(height)
    ln = np.sqrt(nx*nx+ny*ny+nz*nz)+1e-6
    return np.stack([nx/ln, ny/ln, nz/ln], -1)*0.5+0.5

def patches(field, lo, hi):
    return np.clip((field-lo)/(hi-lo), 0, 1)

def ss(x):  # smoothstep 0..1
    x = np.clip(x, 0, 1); return x*x*(3-2*x)

FINE=None
def emit(name, alb, height, rough, nstr):
    global FINE
    if FINE is None:
        FINE=fbm(S,150,4,999)
    alb=alb*(0.85+0.3*FINE[...,None])            # мелкое зерно (резкость)
    height=height*0.72+FINE*0.28                 # мелкий рельеф в нормали
    save(np.clip(alb, 0, 1), os.path.join(GD, name+"_albedo.png"))
    save(nrm(height, nstr*1.9), os.path.join(GD, name+"_normal.png"))
    if np.isscalar(rough):
        rough = np.full((S, S), rough, np.float32)
    save(np.clip(rough, 0, 1), os.path.join(GD, name+"_rough.png"))

LIB = {}

# ---- НАСТОЯЩАЯ ЗЕМЛЯ: тёмный суглинок + галька + комья + органика ----
# Реализм даёт worley-структура комьев и рассыпанные камешки, а не плоский шум.
def soil(name, base, dry, seed, pebble_amt=0.10, moist=0.30, tile=6.0, rough=0.9):
    clods_d, clods_e, clods_id = worley(S, 26, seed)      # комья (агрегаты почвы)
    peb_d, _pf2, peb_id = worley(S, 90, seed+5)           # мелкая галька
    grain = fbm(S, 60, 5, seed+1)
    macro = fbm(S, 7, 4, seed+2)
    t = np.clip(macro*0.7 + grain*0.3, 0, 1)[...,None]
    alb = base[None,None]*(1-t) + dry[None,None]*t
    clod_face = ss(1.0 - clods_d/0.7)
    crack = ss(1.0 - (clods_e-clods_d)/0.06)              # тёмные швы между комьями
    alb = alb*(0.9+0.22*clod_face[...,None])
    alb = alb*(1-0.35*crack[...,None])
    wet = patches(fbm(S,12,4,seed+3), 0.5, 0.85)          # влажные тёмные участки
    alb = alb*(1-moist*wet[...,None])
    org = patches(fbm(S,110,2,seed+4), 0.72, 0.9)         # органика — тёмные крапины
    alb = alb*(1-0.5*org[...,None])
    stones = ss(1.0 - peb_d/0.32)                          # рассыпанная галька
    smask = ((stones > 0.5) & (peb_id < pebble_amt)).astype(np.float32)
    scol = np.array([0.34,0.32,0.30])[None,None] + (peb_id[...,None]-0.5)*0.12
    alb = alb*(1-smask[...,None]) + scol*smask[...,None]
    height = clod_face*0.5 + stones*smask*0.9 - crack*0.4 + grain*0.25
    r = np.full((S,S), rough, np.float32) - 0.12*wet + 0.04*stones*smask
    emit(name, alb, height, np.clip(r,0,1), 3.2)
    LIB[name] = {"name":name, "tile":tile, "rough":rough}

# 1. ЛУГ — тёмная травяная ПОЧВА (пышность даёт геометрия травы сверху)
soil("meadow", np.array([0.10,0.09,0.06]), np.array([0.20,0.17,0.11]),
     11, pebble_amt=0.06, moist=0.35, tile=6.0)
# 3. ЛЕСНАЯ ПОДСТИЛКА — очень тёмная земля, больше органики/камней
soil("forest_floor", np.array([0.09,0.07,0.05]), np.array([0.17,0.13,0.08]),
     31, pebble_amt=0.12, moist=0.4, tile=6.0)
# 5. САДОВАЯ / ОГОРОДНАЯ — рыхлая тёмная, влажная
soil("garden_soil", np.array([0.11,0.08,0.055]), np.array([0.19,0.14,0.09]),
     51, pebble_amt=0.14, moist=0.42, tile=4.0)
# 6. ГРУНТОВАЯ ТРОПА — утоптанная светловатая земля, больше камешков
soil("dirt_path", np.array([0.13,0.10,0.07]), np.array([0.26,0.20,0.13]),
     61, pebble_amt=0.2, moist=0.2, tile=6.0)

# 2. СУХАЯ ТРАВА — степная, желтовато-бурая (травяной тон)
d1 = fbm(S, 10, 5, 21); d2 = fbm(S, 32, 3, 22)
alb = np.array([0.34,0.30,0.15])[None,None]*(0.8+0.4*d1[...,None])
alb = alb*(1-0.2*d2[...,None]) + np.array([0.22,0.26,0.11])[None,None]*(0.15*d2[...,None])
emit("dry_grass", alb, d1*0.5+d2*0.5, 0.92, 2.0)
LIB["dry_grass"] = {"name":"Сухая трава","tile":8.0,"rough":0.92}

# 4. ПАШНЯ — вспаханная тёмная земля с бороздами
xx, yy = np.mgrid[0:S, 0:S] / S
furrow = (np.sin(yy*np.pi*2*20 + fbm(S,8,2,41)*3.0)*0.5+0.5)
clods = fbm(S, 48, 3, 42)
alb = np.array([0.16,0.11,0.07])[None,None]*(0.7+0.6*(furrow[...,None]*0.55+clods[...,None]*0.45))
alb = alb*(1-0.25*patches(fbm(S,12,3,43),0.5,0.85)[...,None])
emit("field", alb, furrow*0.7+clods*0.3, 0.95, 4.5)
LIB["field"] = {"name":"Пашня","tile":5.0,"rough":0.95}

# 7. МОЩЕНИЕ / БРУСЧАТКА — настоящие камни-сетты со швами (дороги у дворца)
cells = 15
F1, F2, CID = worley(S, cells, 700)
edge = F2 - F1
mortar = 1.0 - ss(edge/0.05)                       # тёмные швы между камнями
dome = ss(1.0 - F1/0.62)                            # выпуклость камня
wear = fbm(S, 80, 4, 701)                           # износ/зерно на камнях
stone = np.array([0.40,0.38,0.35])[None,None] + (CID[...,None]-0.5)*np.array([0.14,0.12,0.10])[None,None]
stone = stone*(0.82+0.3*wear[...,None])
mortar_col = np.array([0.16,0.15,0.14])[None,None]
cob = stone*(1-mortar[...,None]) + mortar_col*mortar[...,None]
cob = cob*(0.9+0.16*fbm(S,10,3,702)[...,None])
cob_h = dome*(1-mortar) - mortar*0.6 + wear*0.15
save(np.clip(cob,0,1), os.path.join(GD,"cobblestone_albedo.png"))
save(nrm(cob_h*0.85 + fbm(S,150,4,999)*0.15, 5.5), os.path.join(GD,"cobblestone_normal.png"))
save(np.clip(np.full((S,S),0.6,np.float32) + 0.2*mortar - 0.1*dome,0,1),
     os.path.join(GD,"cobblestone_rough.png"))
LIB["cobblestone"] = {"name":"Брусчатка","tile":2.8,"rough":0.6}

# 8. ПЕСОК и СУГЛИНОК — запас библиотеки
sand_r = (np.sin(xx*np.pi*2*40 + fbm(S,10,2,71)*4)*0.5+0.5)*0.4 + fbm(S,50,3,72)*0.6
alb = np.array([0.66,0.58,0.42])[None,None]*(0.9+0.15*sand_r[...,None])
emit("sand", alb, sand_r, 0.85, 1.5)
LIB["sand"] = {"name":"Песок","tile":5.0,"rough":0.85}
c1 = fbm(S, 14, 5, 81); cracks = patches(fbm(S,30,3,82), 0.0, 0.12)
alb = np.array([0.34,0.22,0.15])[None,None]*(0.85+0.3*c1[...,None])
alb = alb*(1-cracks[...,None]*0.6)
emit("clay", alb, c1*0.7+(1-cracks)*0.3, 0.88, 2.5)
LIB["clay"] = {"name":"Суглинок","tile":5.0,"rough":0.88}

with open(os.path.join(GD, "ground_library.json"), "w") as f:
    json.dump({"note":"Библиотека грунтов и мощения: тайловые PBR-материалы. albedo/normal/rough рядом.",
               "types": LIB}, f, ensure_ascii=False, indent=2)
print("[ground] library ->", GD, "types:", len(LIB))
