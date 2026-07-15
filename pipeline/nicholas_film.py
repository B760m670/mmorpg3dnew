"""КИНО-ПЕРСОНАЖ (стадия A: портрет — анатомия, кожа, волосы, глаза).

Без лимитов полигонов. Станки: MPFB (анатомия) → true displacement (поры,
микрорельеф как реальная геометрия) → Random Walk SSS кожа → пряди волос
(particle hair: скальп/брови/усы, Principled Hair BSDF) → трёхслойные глаза
(склера/радужка/роговица) → кино-свет (3 точки, 85мм, DOF) → Cycles 2K/4K.
"""
import bpy, sys, os, importlib, math, mathutils
import numpy as np
import addon_utils

SCRATCH = "/tmp/claude-0/-home-user-mmorpg3dnew/45dce9e0-e4bb-550f-b915-c58072470dda/scratchpad"
OUT = os.path.join(SCRATCH, "film")
MH_DATA = os.path.join(SCRATCH, "makehuman", "makehuman", "data")
os.makedirs(OUT, exist_ok=True)
QUICK = "--quick" in sys.argv     # быстрый прогон для итераций
NAKED = "--naked" in sys.argv     # стадия A0: голая анатомия, ни одного волоса

addon_utils.enable("bl_ext.user_default.mpfb", default_set=True, persistent=True)

def dyn(pkg, key):
    for amod in list(sys.modules):
        if amod.endswith(pkg):
            return getattr(importlib.import_module(amod), key)
    raise ValueError(pkg)

HumanService = dyn("mpfb.services.humanservice", "HumanService")
TargetService = dyn("mpfb.services.targetservice", "TargetService")
LocationService = dyn("mpfb.services.locationservice", "LocationService")
ExportService = dyn("mpfb.services.exportservice", "ExportService")

# ============ СТАНОК 1: анатомическая база =====================
macro = TargetService.get_default_macro_info_dict()
for k, v in [("gender", 1.0), ("age", 0.46), ("muscle", 0.5),
             ("weight", 0.45), ("height", 0.5), ("proportions", 0.72)]:
    if k in macro:
        macro[k] = v
if "race" in macro:
    for k in macro["race"]:
        macro["race"][k] = 1.0 if k == "caucasian" else 0.0
human = HumanService.create_human(macro_detail_dict=macro)
targets_root = LocationService.get_mpfb_data("targets")
def T(sub, name, w):
    p = os.path.join(targets_root, sub, name + ".target.gz")
    if os.path.exists(p):
        TargetService.load_target(human, p, weight=w)

# лицо по фотографиям Николая II (~1894)
T("nose", "nose-curve-concave", 0.10)
T("nose", "nose-volume-incr", 0.16)
T("nose", "nose-width1-decr", 0.14)
T("nose", "nose-point-width-decr", 0.15)
T("chin", "chin-bones-incr", 0.28)
T("chin", "chin-prominent-incr", 0.10)
T("cheek", "l-cheek-bones-incr", 0.25)
T("cheek", "r-cheek-bones-incr", 0.25)
T("cheek", "l-cheek-inner-decr", 0.42)
T("cheek", "r-cheek-inner-decr", 0.42)
T("head", "head-oval", 0.18)
T("ears", "l-ear-flap-incr", 0.4)
T("ears", "r-ear-flap-incr", 0.4)
# губы: объём, лук Купидона, фильтрум — рот не «щель»
T("mouth", "mouth-lowerlip-volume-incr", 0.55)
T("mouth", "mouth-upperlip-volume-incr", 0.45)
T("mouth", "mouth-cupidsbow-incr", 0.4)
T("mouth", "mouth-cupidsbow-width-incr", 0.2)
T("mouth", "mouth-philtrum-volume-incr", 0.45)
T("mouth", "mouth-scale-depth-incr", 0.15)

eyes_path = os.path.join(MH_DATA, "eyes", "low-poly", "low-poly.mhclo")
HumanService.add_mhclo_asset(eyes_path, human, asset_type="Eyes", material_type="MAKESKIN")

mesh = human
ExportService.bake_modifiers_remove_helpers(mesh, bake_masks=True, bake_subdiv=True,
                                            remove_helpers=True, also_proxy=True)
mh_eyes = None
for o in bpy.data.objects:
    if o.type == 'MESH' and "low-poly" in o.name.lower():
        mh_eyes = o
for o in list(bpy.data.objects):
    if o.type == 'ARMATURE':
        bpy.data.objects.remove(o, do_unlink=True)   # портрету риг не нужен
mw = mesh.matrix_world
# запечь shape keys, сгладить базу ×2 (кино: плотная сетка)
bpy.ops.object.select_all(action='DESELECT')
mesh.select_set(True)
bpy.context.view_layer.objects.active = mesh
if mesh.data.shape_keys:
    bpy.ops.object.shape_key_remove(all=True, apply_mix=True)
sub = mesh.modifiers.new("subd", 'SUBSURF'); sub.levels = 2
bpy.ops.object.modifier_apply(modifier="subd")
print("[film] body verts:", len(mesh.data.vertices))
WORLD_V = [mw @ v.co for v in mesh.data.vertices]
H0 = max(v.z for v in WORLD_V)
hv0 = [v for v in WORLD_V if v.z > H0 - 0.26]
cx0 = sum(v.x for v in hv0) / len(hv0)
cy0 = sum(v.y for v in hv0) / len(hv0)

# центры глаз — из mhclo глаз (точная анатомическая привязка)
eye_c = {}
if mh_eyes is not None:
    for side, sgn in (("l", 1), ("r", -1)):
        vs = [mh_eyes.matrix_world @ v.co for v in mh_eyes.data.vertices
              if (mh_eyes.matrix_world @ v.co).x * sgn > 0]
        eye_c[side] = mathutils.Vector((sum(v.x for v in vs) / len(vs),
                                        sum(v.y for v in vs) / len(vs),
                                        sum(v.z for v in vs) / len(vs)))
z_eyes = (eye_c["l"].z + eye_c["r"].z) / 2 if eye_c else H0 - 0.125
zb0 = z_eyes + 0.024
zn0 = z_eyes - 0.045
zm0 = z_eyes - 0.078
nose_ys = [v.y for v in hv0 if abs(v.x - cx0) < 0.012 and abs(v.z - zn0) < 0.012]
nose_y = min(nose_ys) if nose_ys else cy0 - 0.11

# ---------- АУДИТ АНАТОМИИ: замеры против канонов пластической анатомии ------
def _menton():   # нижняя точка подбородка
    cand = [v.z for v in WORLD_V if abs(v.x - cx0) < 0.015 and v.y < cy0 - 0.03
            and H0 - 0.32 < v.z < zm0]
    return min(cand) if cand else zm0 - 0.05

def _width_at(z, dz=0.008, ymax=None):
    vs = [abs(v.x - cx0) for v in WORLD_V if abs(v.z - z) < dz and v.z > H0 - 0.32
          and (ymax is None or v.y < ymax)]
    return 2 * max(vs) if vs else 0.0

menton = _menton()
ipd = (eye_c["l"] - eye_c["r"]).length if eye_c else 0.0
crown_chin = H0 - menton
mid_third = zb0 - zn0            # бровь → основание носа
low_third = zn0 - menton         # основание носа → подбородок
eye_mid_ratio = (z_eyes - menton) / max(crown_chin, 1e-6)   # глаза на середине черепа ≈ 0.5
bizygo = _width_at(z_eyes - 0.012, ymax=cy0 - 0.005)   # скуловая ширина (БЕЗ ушей)
bigonial = _width_at(zm0 - 0.038)                 # челюстная ширина (углы)
alar_vs = [abs(v.x - cx0) for v in hv0 if abs(v.z - (zn0 + 0.004)) < 0.006 and v.y < nose_y + 0.018]
alar = 2 * max(alar_vs) if alar_vs else 0.0       # ширина крыльев носа
eye_ball_d = 2 * 0.0108
K = 0.063 / max(ipd, 1e-6)                        # перевод в «реальные метры» по IPD=63мм
print("[audit] ---- ГОЛАЯ АНАТОМИЯ: замеры (в мм реального масштаба) ----")
print(f"[audit] IPD={ipd*1000:.1f} модельных мм (норма-якорь 63мм, K={K:.3f})")
print(f"[audit] crown-chin={crown_chin*K*1000:.0f} (норма 230-250)")
print(f"[audit] глаза на высоте {eye_mid_ratio:.2f} черепа (канон 0.50)")
print(f"[audit] средняя треть (бровь-нос) ={mid_third*K*1000:.0f} vs нижняя (нос-подбородок)={low_third*K*1000:.0f} (канон: равны)")
print(f"[audit] скуловая ширина={bizygo*K*1000:.0f} (норма муж 130-145)")
print(f"[audit] челюстная ширина={bigonial*K*1000:.0f} (канон ≈0.75-0.8 скуловой: {bizygo*0.77*K*1000:.0f})")
print(f"[audit] крылья носа={alar*K*1000:.0f} (канон ≈ межслёзное ≈ 32-36)")
print(f"[audit] лицевой индекс (бровь-подбородок)/скуловая = {(zb0-menton)/max(bizygo,1e-6):.2f} (канон 0.9-1.0)")

# ============ СТАНОК 3: кожа (карты по анатомии + Random Walk SSS) ============
TS = 4096 if not QUICK else 2048
smat = bpy.data.materials.new("SkinFilm")
smat.use_nodes = True
tn = smat.node_tree.nodes.new("ShaderNodeTexImage")
smat.node_tree.nodes.active = tn
mesh.data.materials.clear()
mesh.data.materials.append(smat)
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.normals_make_consistent(inside=False)
bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.015)
bpy.ops.object.mode_set(mode='OBJECT')
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 16
scene.render.bake.margin = 2
ao_img = bpy.data.images.new("ao", TS, TS)
tn.image = ao_img
bpy.ops.object.bake(type='AO')
_buf = np.empty(TS * TS * 4, np.float32)
ao_img.pixels.foreach_get(_buf)
ao = _buf.reshape(-1, 4)[:, 0].copy()
pos_img = bpy.data.images.new("pos", TS, TS, float_buffer=True)
tn.image = pos_img
scene.cycles.samples = 4
bpy.ops.object.bake(type='POSITION')
pos_img.pixels.foreach_get(_buf)
P = _buf.reshape(-1, 4)[:, :3].copy()
M = np.array(mw)
P = P @ M[:3, :3].T + M[:3, 3][None, :]
print("[film] bakes done")

def sph(center, r, soft):
    d = np.linalg.norm(P - np.array(center, np.float32)[None, :], axis=1)
    return np.clip((r - d) / max(soft, 1e-5), 0, 1).astype(np.float32)

def band(zlo, zhi, soft=0.01):
    return (np.clip((P[:, 2] - zlo) / soft, 0, 1) * np.clip((zhi - P[:, 2]) / soft, 0, 1)).astype(np.float32)

front = np.clip((cy0 - 0.02 - P[:, 1]) / 0.03, 0, 1)

def fbm_uv(cells, octs, seed):
    rng = np.random.default_rng(seed)
    out = np.zeros((TS, TS), np.float32); amp = 1.0; c = cells; tot = 0.0
    for _ in range(octs):
        g = rng.random((c, c)).astype(np.float32)
        idx = (np.arange(TS) * c // TS)
        out += amp * g[np.ix_(idx, idx)]; tot += amp; amp *= 0.55; c *= 2
    return (out / tot).reshape(-1)

# альбедо: живой светлый тон, мягкая пятнистость, лёгкие зоны
alb = np.tile(np.array([0.875, 0.655, 0.525], np.float32), (P.shape[0], 1))
mott = fbm_uv(128, 4, 77)
alb[:, 0] *= 0.97 + 0.06 * mott
alb[:, 1] *= 0.975 + 0.045 * mott
alb[:, 2] *= 0.985 + 0.03 * mott
RED = np.array([0.05, -0.008, -0.016], np.float32)
def add_red(mask, k):
    global alb
    alb = alb + RED[None, :] * (mask * k)[:, None]
add_red(sph((cx0 - 0.046, cy0 - 0.038, zn0 + 0.008), 0.04, 0.05), 0.4)
add_red(sph((cx0 + 0.046, cy0 - 0.038, zn0 + 0.008), 0.04, 0.05), 0.4)
add_red(sph((cx0, nose_y + 0.006, zn0 - 0.002), 0.016, 0.02), 0.3)
ear_xs = [abs(v.x - cx0) for v in hv0 if abs(v.z - (zn0 + 0.02)) < 0.02]
ear_x = max(ear_xs) if ear_xs else 0.075
add_red(sph((cx0 - ear_x, cy0 + 0.008, zn0 + 0.02), 0.026, 0.03), 0.35)
add_red(sph((cx0 + ear_x, cy0 + 0.008, zn0 + 0.02), 0.026, 0.03), 0.35)
lips = band(zm0 - 0.008, zm0 + 0.010, 0.006) * front * (np.abs(P[:, 0] - cx0) < 0.028)
lip_col = np.array([0.66, 0.33, 0.31], np.float32)
alb = alb * (1 - (lips * 0.5)[:, None]) + lip_col[None, :] * (lips * 0.5)[:, None]
beard = band(zm0 - 0.075, zm0 + 0.012, 0.014) * front * (np.abs(P[:, 0] - cx0) < 0.06) * (1 - lips)
grey = np.array([0.7, 0.71, 0.75], np.float32)
alb = alb * (1 - (beard * 0.07)[:, None]) + (alb * grey[None, :]) * (beard * 0.07)[:, None]
# ноздри — глубокая тень
for sx in (-1, 1):
    nost = sph((cx0 + sx * 0.0105, nose_y + 0.006, zn0 - 0.0035), 0.0045, 0.004)
    alb = alb * (1 - (nost * 0.62)[:, None])
alb = alb * (0.86 + 0.14 * ao)[:, None]
px4 = np.ones((P.shape[0], 4), np.float32)
px4[:, :3] = np.clip(alb, 0, 1)
skin_img = bpy.data.images.new("skinF", TS, TS)
skin_img.pixels.foreach_set(px4.reshape(-1))

# roughness: T-зона/нос — 0.38; щёки 0.5; губы 0.32; тело 0.55
rgh = np.full(P.shape[0], 0.55, np.float32)
tz = band(zb0 - 0.005, H0 - 0.05, 0.012) * front
nose_strip = band(zn0 - 0.02, zb0, 0.012) * front * (np.abs(P[:, 0] - cx0) < 0.016)
cheeks = sph((cx0 - 0.046, cy0 - 0.038, zn0 + 0.008), 0.045, 0.05) \
       + sph((cx0 + 0.046, cy0 - 0.038, zn0 + 0.008), 0.045, 0.05)
rgh = rgh - 0.17 * np.clip(tz + nose_strip, 0, 1) - 0.05 * np.clip(cheeks, 0, 1) - 0.23 * lips
rgh = rgh + 0.05 * (mott - 0.5)
rpx = np.ones((P.shape[0], 4), np.float32)
rpx[:, 0] = rpx[:, 1] = rpx[:, 2] = np.clip(rgh, 0.25, 0.85)
rgh_img = bpy.data.images.new("rghF", TS, TS)
rgh_img.pixels.foreach_set(rpx.reshape(-1))

# ============ СТАНОК 2: микрорельеф — TRUE DISPLACEMENT ============
# карта высот: поры (мелкие) + морщинки лба/у глаз (направленные) + вены тыльные
disp_h = np.zeros(P.shape[0], np.float32)
# поры НЕ здесь: они 3D-шумом в шейдере (в UV — швы и «вязаный» узор);
# тут лишь крупная неровность кожи
pores = fbm_uv(300, 3, 41)
disp_h += (pores - 0.5) * 0.22
# морщины лба: горизонтальные волны, только лоб
forehead = band(zb0 + 0.012, H0 - 0.055, 0.012) * front
waves = (np.sin(P[:, 2] * 900.0 + fbm_uv(60, 2, 55) * 6.0) * 0.5 + 0.5).astype(np.float32)
disp_h += (waves - 0.5) * 0.5 * forehead
# гусиные лапки у глаз
for sx in (-1, 1):
    crow = sph((cx0 + sx * 0.052, cy0 - 0.035, z_eyes - 0.004), 0.02, 0.02)
    disp_h += (np.sin((P[:, 0] - cx0) * 1400.0) * 0.5) * crow * 0.7

# ---------- АНАТОМИЧЕСКИЙ РЕЛЬЕФ: кости черепа и мышцы лица ----------
# (амплитуды крупнее пор — рельеф ДОЛЖЕН читаться на голом лице)
# надбровные дуги (супраорбитальный валик)
disp_h += band(zb0 - 0.003, zb0 + 0.011, 0.006) * front * 1.6
# глабелла (межбровье) — мягкий бугор
disp_h += sph((cx0, nose_y + 0.014, zb0 + 0.002), 0.011, 0.010) * 1.2
# височные впадины (temporalis под фасцией — лёгкая вогнутость)
for sx in (-1, 1):
    disp_h -= sph((cx0 + sx * 0.063, cy0 - 0.004, zb0 + 0.012), 0.020, 0.020) * 1.4
# скуловые дуги: от скуловой кости к уху
for sx in (-1, 1):
    for t in (0.0, 0.33, 0.66, 1.0):
        ax = 0.042 + t * (ear_x - 0.052)
        ay = cy0 - 0.028 + t * 0.030
        disp_h += sph((cx0 + sx * ax, ay, z_eyes - 0.013), 0.011, 0.011) * 1.15
# жевательная мышца (masseter) — объём у угла челюсти
for sx in (-1, 1):
    disp_h += sph((cx0 + sx * 0.051, cy0 + 0.010, zm0 - 0.030), 0.020, 0.018) * 1.1
# носогубная борозда — лёгкая складка от крыла носа к углу рта
for sx in (-1, 1):
    for t in (0.0, 0.5, 1.0):
        nx_ = 0.016 + t * 0.012
        nz_ = zn0 - 0.004 - t * 0.026
        disp_h -= sph((cx0 + sx * nx_, nose_y + 0.010 + t * 0.008, nz_), 0.0045, 0.0045) * 1.0
# губоподбородочная борозда + подбородочный бугор
disp_h -= band(zm0 - 0.021, zm0 - 0.013, 0.004) * front * (np.abs(P[:, 0] - cx0) < 0.015) * 1.2
disp_h += sph((cx0, nose_y + 0.012, zm0 - 0.034), 0.014, 0.012) * 1.4
# ШЕЯ: кивательные мышцы (от сосцевидного отростка к яремной вырезке) + кадык
neck_front_y = cy0 - 0.055
for sx in (-1, 1):
    for t in (0.0, 0.4, 0.8):
        sy = cy0 + 0.015 - t * 0.055
        sz = (H0 - 0.245) - t * 0.055
        sxx = 0.032 - t * 0.012
        disp_h += sph((cx0 + sx * sxx, sy, sz), 0.013, 0.013) * 0.8
disp_h += sph((cx0, neck_front_y, H0 - 0.30), 0.009, 0.008) * 1.0   # кадык
dpx = np.ones((P.shape[0], 4), np.float32)
dval = np.clip(disp_h * 0.5 + 0.5, 0, 1)
dpx[:, 0] = dpx[:, 1] = dpx[:, 2] = dval
disp_img = bpy.data.images.new("dispF", TS, TS)
disp_img.pixels.foreach_set(dpx.reshape(-1))
for im, nm in ((skin_img, "skin"), (rgh_img, "rough"), (disp_img, "disp")):
    im.filepath_raw = os.path.join(OUT, f"film_{nm}.png")
    im.file_format = 'PNG'
    im.save()

# шейдер кожи: Random Walk SSS + двухслойный спекуляр + displacement
nt = smat.node_tree
for n in list(nt.nodes):
    if n.type != 'OUTPUT_MATERIAL':
        nt.nodes.remove(n)
out_n = [n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'][0]
bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
t_alb = nt.nodes.new("ShaderNodeTexImage"); t_alb.image = skin_img
nt.links.new(t_alb.outputs["Color"], bsdf.inputs["Base Color"])
t_r = nt.nodes.new("ShaderNodeTexImage"); t_r.image = rgh_img
t_r.image.colorspace_settings.name = 'Non-Color'
nt.links.new(t_r.outputs["Color"], bsdf.inputs["Roughness"])
# ПОРЫ: 3D-шум → Bump — бесшовно (в UV были швы и «вязаный» узор), ~0.5 мм
ptex = nt.nodes.new("ShaderNodeTexNoise")
ptex.inputs["Scale"].default_value = 950.0
ptex.inputs["Detail"].default_value = 3.0
pbump = nt.nodes.new("ShaderNodeBump")
pbump.inputs["Strength"].default_value = 0.16
pbump.inputs["Distance"].default_value = 0.0005
nt.links.new(ptex.outputs["Fac"], pbump.inputs["Height"])
nt.links.new(pbump.outputs["Normal"], bsdf.inputs["Normal"])
for key, val in [("Subsurface Weight", 1.0), ("IOR", 1.4), ("Coat Weight", 0.12),
                 ("Coat Roughness", 0.28)]:
    if key in bsdf.inputs:
        bsdf.inputs[key].default_value = val
if "Subsurface Radius" in bsdf.inputs:
    bsdf.inputs["Subsurface Radius"].default_value = (0.482, 0.169, 0.109)
if "Subsurface Scale" in bsdf.inputs:
    bsdf.inputs["Subsurface Scale"].default_value = 0.022
if hasattr(bsdf, "subsurface_method"):
    bsdf.subsurface_method = 'RANDOM_WALK'
# displacement
t_d = nt.nodes.new("ShaderNodeTexImage"); t_d.image = disp_img
t_d.image.colorspace_settings.name = 'Non-Color'
dsp = nt.nodes.new("ShaderNodeDisplacement")
dsp.inputs["Scale"].default_value = 0.0021
dsp.inputs["Midlevel"].default_value = 0.5
nt.links.new(t_d.outputs["Color"], dsp.inputs["Height"])
nt.links.new(dsp.outputs["Displacement"], out_n.inputs["Displacement"])
nt.links.new(bsdf.outputs["BSDF"], out_n.inputs["Surface"])
try:
    smat.displacement_method = 'BOTH'
except Exception:
    try:
        smat.cycles.displacement_method = 'BOTH'
    except Exception:
        pass
print("[film] skin shader ready")

# ============ СТАНОК 5: глаза (склера/радужка/роговица) ============
if mh_eyes is not None:
    mh_eyes.hide_render = True
    mh_eyes.hide_viewport = True
eye_objs = []
def make_eye(c, name):
    # ОДНА сфера: зоны зрачок/радужка/склера — по углу нормали от оси взгляда (-Y).
    # Радужка видна всегда, никакой мутной линзы; влажный блеск — покрытием (Coat).
    r = 0.0113
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, segments=32, ring_count=24,
        location=(c.x, c.y + 0.0013, c.z - 0.0011))
    sc = bpy.context.active_object; sc.name = name
    sc.rotation_euler = (math.radians(-4.0), 0, 0)   # взгляд чуть вниз, не «выпучен»
    for p in sc.data.polygons:
        p.use_smooth = True
    m = bpy.data.materials.new("EyeMat_" + name); m.use_nodes = True
    ntw = m.node_tree
    pb = ntw.nodes["Principled BSDF"]
    geo = ntw.nodes.new("ShaderNodeNewGeometry")
    dot = ntw.nodes.new("ShaderNodeVectorMath"); dot.operation = 'DOT_PRODUCT'
    dot.inputs[1].default_value = (0.0, -1.0, 0.0)
    ntw.links.new(geo.outputs["Normal"], dot.inputs[0])
    # зоны: dot>0.945 зрачок; 0.80..0.945 радужка; ниже — склера
    ramp_zone = ntw.nodes.new("ShaderNodeValToRGB")
    ramp_zone.color_ramp.interpolation = 'LINEAR'
    e0 = ramp_zone.color_ramp.elements[0]; e0.position = 0.795; e0.color = (0, 0, 0, 1)
    e1 = ramp_zone.color_ramp.elements[1]; e1.position = 0.81; e1.color = (1, 1, 1, 1)
    ntw.links.new(dot.outputs["Value"], ramp_zone.inputs["Fac"])
    pup = ntw.nodes.new("ShaderNodeValToRGB")
    p0 = pup.color_ramp.elements[0]; p0.position = 0.938; p0.color = (0, 0, 0, 1)
    p1 = pup.color_ramp.elements[1]; p1.position = 0.952; p1.color = (1, 1, 1, 1)
    ntw.links.new(dot.outputs["Value"], pup.inputs["Fac"])
    # узор радужки: кольца
    wav = ntw.nodes.new("ShaderNodeTexWave")
    wav.wave_type = 'RINGS'
    wav.inputs["Scale"].default_value = 260.0
    wav.inputs["Distortion"].default_value = 9.0
    tc = ntw.nodes.new("ShaderNodeTexCoord")
    ntw.links.new(tc.outputs["Object"], wav.inputs["Vector"])
    iris_ramp = ntw.nodes.new("ShaderNodeValToRGB")
    iris_ramp.color_ramp.elements[0].color = (0.05, 0.085, 0.135, 1)   # серо-голубая
    iris_ramp.color_ramp.elements[1].color = (0.30, 0.44, 0.54, 1)
    ntw.links.new(wav.outputs["Fac"], iris_ramp.inputs["Fac"])
    # склера: тёплый белок, к краям розовее
    sk_ramp = ntw.nodes.new("ShaderNodeValToRGB")
    sk_ramp.color_ramp.elements[0].color = (0.62, 0.50, 0.47, 1)
    sk_ramp.color_ramp.elements[1].color = (0.80, 0.77, 0.75, 1)
    ntw.links.new(dot.outputs["Value"], sk_ramp.inputs["Fac"])
    mix_ir = ntw.nodes.new("ShaderNodeMix"); mix_ir.data_type = 'RGBA'
    ntw.links.new(ramp_zone.outputs["Color"], mix_ir.inputs["Factor"])
    ntw.links.new(sk_ramp.outputs["Color"], mix_ir.inputs["A"])
    ntw.links.new(iris_ramp.outputs["Color"], mix_ir.inputs["B"])
    mix_pu = ntw.nodes.new("ShaderNodeMix"); mix_pu.data_type = 'RGBA'
    ntw.links.new(pup.outputs["Color"], mix_pu.inputs["Factor"])
    ntw.links.new(mix_ir.outputs["Result"], mix_pu.inputs["A"])
    mix_pu.inputs["B"].default_value = (0.004, 0.004, 0.005, 1)
    # порядок: зрачок поверх → в Base Color
    ntw.links.new(mix_pu.outputs["Result"], pb.inputs["Base Color"])
    # инвертируем: Factor=1 должен быть зрачком, поэтому меняем A/B местами выше
    pb.inputs["Roughness"].default_value = 0.12
    if "Coat Weight" in pb.inputs:
        pb.inputs["Coat Weight"].default_value = 1.0
    if "Coat Roughness" in pb.inputs:
        pb.inputs["Coat Roughness"].default_value = 0.025
    sc.data.materials.append(m)
    return [sc]

for s in ("l", "r"):
    if s in eye_c:
        eye_objs += make_eye(eye_c[s], "eye_" + s)
print("[film] eyes built")

# ============ СТАНОК 4: ПРЯДИ волос (скальп, брови, усы) ============
def vgroup_from_filter(name, flt):
    vg = mesh.vertex_groups.new(name=name)
    idxs = [v.index for v in mesh.data.vertices if flt(mw @ v.co)]
    if idxs:
        vg.add(idxs, 1.0, 'REPLACE')
    return vg, len(idxs)

def hair_system(name, vgroup, count, length, mat_index, clump=0.9, kink_amp=0.0,
                rough=0.02, radius=0.00065, children=24):
    ps_mod = mesh.modifiers.new(name, 'PARTICLE_SYSTEM')
    psys = ps_mod.particle_system
    st = psys.settings
    st.type = 'HAIR'
    st.count = count
    st.hair_length = length
    st.hair_step = 5
    st.child_type = 'INTERPOLATED'
    st.child_percent = children
    st.rendered_child_count = children
    st.clump_factor = clump
    st.roughness_2 = rough
    st.root_radius = radius / 0.001
    if kink_amp > 0:
        st.kink = 'CURL'
        st.kink_amplitude = kink_amp
        st.kink_frequency = 2.2
    st.material = mat_index + 1
    psys.vertex_group_density = vgroup
    return psys

hair_mat = bpy.data.materials.new("HairFilm")
hair_mat.use_nodes = True
hnt = hair_mat.node_tree
for n in list(hnt.nodes):
    if n.type != 'OUTPUT_MATERIAL':
        hnt.nodes.remove(n)
hout = [n for n in hnt.nodes if n.type == 'OUTPUT_MATERIAL'][0]
hb = hnt.nodes.new("ShaderNodeBsdfHairPrincipled")
# тёмно-русый с рыжиной (по описаниям и портретам)
if "Melanin" in hb.inputs:
    hb.inputs["Melanin"].default_value = 0.72
if "Melanin Redness" in hb.inputs:
    hb.inputs["Melanin Redness"].default_value = 0.55
hnt.links.new(hb.outputs["BSDF"], hout.inputs["Surface"])
mesh.data.materials.append(hair_mat)
hair_mi = len(mesh.data.materials) - 1

# аккуратная короткая стрижка 1890-х: высокая линия лба, коротко и прилизанно
def hf_scalp(c):
    if c.y < cy0 - 0.02:
        return c.z > H0 - 0.038
    if c.y > cy0 + 0.02:
        return c.z > H0 - 0.13
    return c.z > H0 - 0.062

vgroup_from_filter("scalp", hf_scalp)
z_brow_line = z_eyes + 0.019           # брови ближе к глазам, не «на лбу»
vgroup_from_filter("brows_g",
    lambda c: (c.y < cy0 - 0.025) and (z_brow_line - 0.0055 < c.z < z_brow_line + 0.0055) and 0.013 < abs(c.x - cx0) < 0.042)
vgroup_from_filter("must_g",
    lambda c: (c.y < cy0 - 0.05) and (zm0 + 0.012 < c.z < zn0 + 0.002) and abs(c.x - cx0) < 0.032)
# БОРОДА (у Николая II в 1894 — полная борода): подбородок + челюсть + щёки
# до бакенбард; свободна только полоска непосредственно под губой
def beard_filter(c):
    dx = abs(c.x - cx0)
    if c.z < zm0 - 0.085 or c.y > cy0 + 0.01:
        return False
    under_lip = (c.z > zm0 - 0.008 and dx < 0.016)      # ямка под губой
    if under_lip:
        return False
    if c.z < zm0 + 0.004 and dx < 0.060:                 # подбородок и челюсть
        return True
    if c.z < zn0 + 0.004 and 0.030 < dx < 0.075 and c.y < cy0 - 0.005:
        return True                                       # щёки до бакенбард
    return False
vgroup_from_filter("beard_g", beard_filter)

DN = 1 if QUICK else 2
if not NAKED:
    scalp_sys = hair_system("hair_scalp", "scalp", 2300 * DN, 0.024, hair_mi, clump=0.82,
                kink_amp=0.0005, rough=0.010, children=16 * DN)
    hair_system("hair_brows", "brows_g", 240, 0.0042, hair_mi, clump=0.55, rough=0.015, children=8)
    hair_system("hair_must", "must_g", 340, 0.0110, hair_mi, clump=0.9, kink_amp=0.0,
                rough=0.008, children=8)
    hair_system("hair_beard", "beard_g", 1100 * DN, 0.0135, hair_mi, clump=0.75, kink_amp=0.0004,
                rough=0.012, children=10)

    # «ПРИЧЕСАТЬ» физикой: динамика волос + гравитация укладывают пряди (не ёжик)
    scalp_sys.use_hair_dynamics = True
    if scalp_sys.cloth is not None:
        hs = scalp_sys.cloth.settings
        hs.mass = 0.05
        hs.bending_stiffness = 0.15
    scene.frame_start = 1
    scene.frame_end = 18
    for f in range(1, 19):
        scene.frame_set(f)
    print("[film] hair systems ready (groomed by physics)")
else:
    print("[film] NAKED: анатомия без волос — все пряди выключены")

# ============ СТАНОК 7: кино-стейдж (свет, камера, рендер) ============
world = bpy.data.worlds.new("studio")
scene.world = world
world.use_nodes = True
bgn = world.node_tree.nodes["Background"]
bgn.inputs[0].default_value = (0.035, 0.037, 0.042, 1.0)   # тёмный фон портрета
bgn.inputs[1].default_value = 1.0

def area_light(name, loc, rot, size, power, color=(1, 1, 1)):
    ld = bpy.data.lights.new(name, 'AREA')
    ld.size = size
    ld.energy = power
    ld.color = color
    lo = bpy.data.objects.new(name, ld)
    lo.location = loc
    lo.rotation_euler = rot
    bpy.context.collection.objects.link(lo)
    return lo

fy = nose_y - 0.02
# ключевой (тёплый, слева сверху), заполняющий (холодный, справа), контровой
area_light("key", (cx0 - 0.55, fy - 0.75, z_eyes + 0.35),
           (math.radians(70), 0, math.radians(-32)), 0.7, 120.0, (1.0, 0.93, 0.85))
area_light("fill", (cx0 + 0.7, fy - 0.6, z_eyes + 0.05),
           (math.radians(80), 0, math.radians(42)), 1.1, 35.0, (0.85, 0.9, 1.0))
area_light("rim", (cx0 + 0.25, cy0 + 0.75, z_eyes + 0.45),
           (math.radians(-115), 0, math.radians(15)), 0.5, 45.0, (1.0, 0.97, 0.9))

cam_d = bpy.data.cameras.new("cam")
cam_d.lens = 85
cam_d.dof.use_dof = True
cam_d.dof.aperture_fstop = 4.0
cam = bpy.data.objects.new("cam", cam_d)
bpy.context.collection.objects.link(cam)
scene.camera = cam
cam.location = (cx0, fy - 0.80, z_eyes + 0.015)
cam.rotation_euler = (math.radians(90), 0, 0)
cam_d.dof.focus_distance = 0.80

scene.cycles.samples = 64 if QUICK else 192
scene.cycles.use_denoising = True
try:
    scene.cycles.denoiser = 'OPENIMAGEDENOISE'
except Exception:
    pass
scene.render.resolution_x = 1200 if QUICK else 2160
scene.render.resolution_y = 1500 if QUICK else 2700
scene.view_settings.view_transform = 'Filmic' if 'Filmic' else 'Standard'
scene.view_settings.look = 'Medium High Contrast'
if NAKED:
    # три ракурса голой анатомии: анфас / три четверти / профиль
    views = [("front", (cx0, fy - 0.80, z_eyes + 0.015), (math.radians(90), 0, 0)),
             ("threeq", (cx0 - 0.57, fy - 0.57, z_eyes + 0.015), (math.radians(90), 0, math.radians(-45))),
             ("profile", (cx0 - 0.80, cy0 - 0.02, z_eyes + 0.015), (math.radians(90), 0, math.radians(-90)))]
    for nm, loc, rot in views:
        cam.location = loc
        cam.rotation_euler = rot
        scene.render.filepath = os.path.join(OUT, f"anatomy_{nm}.png")
        bpy.ops.render.render(write_still=True)
        print("[film] ANATOMY RENDERED ->", scene.render.filepath)
else:
    scene.render.filepath = os.path.join(OUT, "portrait.png")
    bpy.ops.render.render(write_still=True)
    print("[film] PORTRAIT RENDERED ->", scene.render.filepath)
