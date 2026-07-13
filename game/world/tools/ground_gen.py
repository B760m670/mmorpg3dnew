#!/usr/bin/env python3
# Библиотека НАСТОЯЩИХ грунтов — тайловые PBR-текстуры (albedo+normal+rough).
# Земля везде разная: луг, сухая трава, лесная подстилка, пашня, садовая земля,
# грунтовая тропа, песок, суглинок. Сохраняются один раз и применяются к любой
# области (world/textures/ground/), плюс манифест ground_library.json.
import bpy, os, sys, json
import numpy as np

A = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
ROOT = A[0] if A else "/home/user/mmorpg3dnew"
GD = os.path.join(ROOT, "game/world/textures/ground")
os.makedirs(GD, exist_ok=True)
S = 512

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

def emit(name, alb, height, rough, nstr, rgh_range=None):
    save(np.clip(alb, 0, 1), os.path.join(GD, name+"_albedo.png"))
    save(nrm(height, nstr), os.path.join(GD, name+"_normal.png"))
    if np.isscalar(rough):
        rough = np.full((S, S), rough, np.float32)
    save(np.clip(rough, 0, 1), os.path.join(GD, name+"_rough.png"))

xx, yy = np.mgrid[0:S, 0:S] / S
LIB = {}

# 1. ЛУГ — сочная зелёная трава с редкими цветами
g1 = fbm(S, 8, 5, 11); g2 = fbm(S, 40, 3, 12)
alb = np.array([0.19,0.33,0.11])[None,None]*(1-g1[...,None]*0.5) + np.array([0.32,0.46,0.17])[None,None]*(g1[...,None]*0.5)
alb *= (0.85+0.3*g2[...,None])
flowers = patches(fbm(S,60,2,13), 0.82, 0.9)
alb = alb*(1-flowers[...,None]) + np.array([0.9,0.85,0.4])[None,None]*flowers[...,None]
emit("meadow", alb, g1*0.4+g2*0.6, 0.9, 2.0)
LIB["meadow"] = {"name":"Луговая трава","tile":8.0,"rough":0.9}

# 2. СУХАЯ ТРАВА — степная, желтовато-бурая
d1 = fbm(S, 10, 5, 21); d2 = fbm(S, 32, 3, 22)
alb = np.array([0.45,0.40,0.18])[None,None]*(0.8+0.4*d1[...,None])
alb = alb*(1-0.2*d2[...,None]) + np.array([0.30,0.34,0.14])[None,None]*(0.15*d2[...,None])
emit("dry_grass", alb, d1*0.5+d2*0.5, 0.92, 2.0)
LIB["dry_grass"] = {"name":"Сухая трава","tile":8.0,"rough":0.92}

# 3. ЛЕСНАЯ ПОДСТИЛКА — тёмная земля, палая листва, мох, веточки
e = fbm(S, 12, 5, 31); leaves = patches(fbm(S,40,3,32), 0.55, 0.85)
moss = patches(fbm(S,18,4,33), 0.6, 0.85)
alb = np.array([0.17,0.12,0.07])[None,None]*(0.8+0.5*e[...,None])
alb = alb*(1-leaves[...,None]) + np.array([0.42,0.26,0.12])[None,None]*leaves[...,None]
alb = alb*(1-moss[...,None]) + np.array([0.18,0.28,0.12])[None,None]*moss[...,None]
emit("forest_floor", alb, e*0.5+leaves*0.3+moss*0.2, 0.95, 3.0)
LIB["forest_floor"] = {"name":"Лесная подстилка","tile":6.0,"rough":0.95}

# 4. ПАШНЯ — вспаханная земля с бороздами (направленные гряды)
furrow = (np.sin(yy*np.pi*2*22 + fbm(S,8,2,41)*3.0)*0.5+0.5)
clods = fbm(S, 48, 3, 42)
alb = np.array([0.30,0.20,0.12])[None,None]*(0.7+0.5*(furrow[...,None]*0.6+clods[...,None]*0.4))
emit("field", alb, furrow*0.7+clods*0.3, 0.95, 4.5)
LIB["field"] = {"name":"Пашня","tile":5.0,"rough":0.95}

# 5. САДОВАЯ / ОГОРОДНАЯ ЗЕМЛЯ — тёмная рыхлая, влажная, мелкие камешки
s1 = fbm(S, 24, 5, 51); stones = patches(fbm(S,70,2,52), 0.85, 0.94)
alb = np.array([0.16,0.11,0.07])[None,None]*(0.85+0.4*s1[...,None])
alb = alb*(1-stones[...,None]) + np.array([0.4,0.38,0.35])[None,None]*stones[...,None]
emit("garden_soil", alb, s1*0.7+stones*0.3, 0.9, 3.0)
LIB["garden_soil"] = {"name":"Садовая земля","tile":4.0,"rough":0.9}

# 6. ГРУНТОВАЯ ТРОПА — светлый утоптанный грунт
p1 = fbm(S, 10, 5, 61); ruts = fbm(S, 26, 3, 62)
alb = np.array([0.42,0.33,0.22])[None,None]*(0.8+0.35*p1[...,None])*(0.9+0.15*ruts[...,None])
emit("dirt_path", alb, p1*0.5+ruts*0.5, 0.9, 3.0)
LIB["dirt_path"] = {"name":"Грунтовая тропа","tile":6.0,"rough":0.9}

# 7. ПЕСОК — светлый мелкий, лёгкая рябь
sand_r = (np.sin(xx*np.pi*2*40 + fbm(S,10,2,71)*4)*0.5+0.5)*0.4 + fbm(S,50,3,72)*0.6
alb = np.array([0.72,0.63,0.44])[None,None]*(0.9+0.15*sand_r[...,None])
emit("sand", alb, sand_r, 0.85, 1.5)
LIB["sand"] = {"name":"Песок","tile":5.0,"rough":0.85}

# 8. СУГЛИНОК — красновато-бурая плотная глина с трещинами
c1 = fbm(S, 14, 5, 81); cracks = patches(fbm(S,30,3,82), 0.0, 0.12)
alb = np.array([0.40,0.24,0.16])[None,None]*(0.85+0.3*c1[...,None])
alb = alb*(1-cracks[...,None]*0.6)
emit("clay", alb, c1*0.7+(1-cracks)*0.3, 0.88, 2.5)
LIB["clay"] = {"name":"Суглинок","tile":5.0,"rough":0.88}

with open(os.path.join(GD, "ground_library.json"), "w") as f:
    json.dump({"note":"Библиотека грунтов: тайловые PBR-материалы, применяются к любой области через terrain-шейдер. albedo/normal/rough в этой же папке.",
               "types": LIB}, f, ensure_ascii=False, indent=2)
print("[ground] library ->", GD, "types:", len(LIB))
