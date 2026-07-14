"""Полное тело Николая II: MPFB2 + сегментация по весам скелета.

Выход:
  nicholas_body.obj    — тело (антропометрия, кожа, лицо, бельё)
  nicholas_uniform.obj — в преображенском мундире (китель, воротник, обшлага,
                         ремень, брюки, сапоги, погоны, пуговицы, фуражка)
  joints.json          — координаты суставов для игрового рига (оси OBJ)
  nicholas_skin.png / nicholas_eyes.png
Каждый OBJ содержит 13 именованных кусков: head, torso, upperarm_l/r,
forearm_l/r, hand_l/r, thigh_l/r, shin_l/r — куски пересекаются на один ряд
граней, чтобы швы не светились при анимации.
"""
import bpy, sys, os, importlib, json, math, mathutils
import numpy as np
import addon_utils

SCRATCH = "/tmp/claude-0/-home-user-mmorpg3dnew/45dce9e0-e4bb-550f-b915-c58072470dda/scratchpad"
OUT = os.path.join(SCRATCH, "nicholas_glb_out")
MH_DATA = os.path.join(SCRATCH, "makehuman", "makehuman", "data")
os.makedirs(OUT, exist_ok=True)

addon_utils.enable("bl_ext.user_default.mpfb", default_set=True, persistent=True)

def dyn(pkg, key):
    for amod in list(sys.modules):
        if amod.endswith(pkg):
            return getattr(importlib.import_module(amod), key)
    raise ValueError(pkg)

HumanService = dyn("mpfb.services.humanservice", "HumanService")
TargetService = dyn("mpfb.services.targetservice", "TargetService")
LocationService = dyn("mpfb.services.locationservice", "LocationService")
ObjectService = dyn("mpfb.services.objectservice", "ObjectService")
ExportService = dyn("mpfb.services.exportservice", "ExportService")

# ---------- 1. Человек ----------
macro = TargetService.get_default_macro_info_dict()
for k, v in [("gender", 1.0), ("age", 0.45), ("muscle", 0.50),
             ("weight", 0.46), ("height", 0.5), ("proportions", 0.65)]:
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
    else:
        print("MISSING", sub, name)

T("nose", "nose-curve-concave", 0.12)
T("nose", "nose-volume-incr", 0.18)
T("nose", "nose-width1-decr", 0.15)
T("chin", "chin-bones-incr", 0.30)
T("chin", "chin-prominent-incr", 0.15)
T("cheek", "l-cheek-bones-incr", 0.25)
T("cheek", "r-cheek-bones-incr", 0.25)
T("forehead", "forehead-scale-vert-incr", 0.15)
T("eyes", "l-eye-height2-decr", 0.1)
T("eyes", "r-eye-height2-decr", 0.1)
T("head", "head-oval", 0.3)
T("mouth", "mouth-scale-horiz-decr", 0.1)
# по фотографиям молодого Николая II: оттопыренные уши, мужской V-торс
T("ears", "l-ear-flap-incr", 0.5)
T("ears", "r-ear-flap-incr", 0.5)
T("ears", "l-ear-scale-incr", 0.25)
T("ears", "r-ear-scale-incr", 0.25)
T("torso", "torso-vshape-incr", 0.25)
T("torso", "measure-shoulder-dist-incr", 0.20)
T("torso", "torso-muscle-pectoral-incr", 0.15)
T("torso", "torso-muscle-dorsi-incr", 0.12)

# глаза
eyes_path = os.path.join(MH_DATA, "eyes", "low-poly", "low-poly.mhclo")
HumanService.add_mhclo_asset(eyes_path, human, asset_type="Eyes", material_type="MAKESKIN")

# риг — источник весов для сегментации
HumanService.add_builtin_rig(human, "default")

# ---------- 2. Работаем с оригиналом (без копий — иначе два наложенных
# тела пачкают запекание AO самопересечениями) ----------
mesh = human
ExportService.bake_modifiers_remove_helpers(mesh, bake_masks=True, bake_subdiv=True,
                                            remove_helpers=True, also_proxy=True)
eyes_obj = None
for o in bpy.data.objects:
    if o.type == 'MESH' and "low-poly" in o.name.lower():
        eyes_obj = o
print("MESH", mesh.name, len(mesh.data.vertices), "EYES", eyes_obj.name if eyes_obj else None)

# Модификаторы Armature ОСТАВЛЯЕМ — экспортируем скиннинг в GLB

mw = mesh.matrix_world

# ---------- 3. Суставы из рига ----------
arm_rig = None
for o in bpy.data.objects:
    if o.type == 'ARMATURE':
        arm_rig = o
arm_rig.hide_render = True
amw = arm_rig.matrix_world
def bone_head(name):
    b = arm_rig.data.bones.get(name)
    if b is None:
        raise RuntimeError("no bone " + name)
    h = amw @ b.head_local
    return (h.x, h.y, h.z)

J = {
    "neck": bone_head("neck01"),   # ОСНОВАНИЕ шеи (neck02 — верхний позвонок, уровень рта!)
    "shoulder_l": bone_head("upperarm01.L"), "shoulder_r": bone_head("upperarm01.R"),
    "elbow_l": bone_head("lowerarm01.L"),   "elbow_r": bone_head("lowerarm01.R"),
    "wrist_l": bone_head("wrist.L"),        "wrist_r": bone_head("wrist.R"),
    "hip_l": bone_head("upperleg01.L"),     "hip_r": bone_head("upperleg01.R"),
    "knee_l": bone_head("lowerleg01.L"),    "knee_r": bone_head("lowerleg01.R"),
    "pelvis": bone_head("root"),
}
print("JOINTS", {k: tuple(round(v,3) for v in J[k]) for k in J})

# ---------- 4. Классификация вершинных групп по кускам ----------
def classify_group(name):
    n = name.lower()
    side = "l" if n.endswith(".l") else ("r" if n.endswith(".r") else None)
    if "upperleg" in n or "pelvis" in n and False:
        return "thigh_" + side if side else "torso"
    if "lowerleg" in n or n.startswith("foot") or "toe" in n:
        return "shin_" + side if side else "torso"
    if "upperarm" in n:
        return "upperarm_" + side if side else "torso"
    if "lowerarm" in n:
        return "forearm_" + side if side else "torso"
    if n.startswith("wrist") or "finger" in n or "thumb" in n or "metacarpal" in n or n.startswith("palm"):
        return "hand_" + side if side else "torso"
    if n.startswith(("spine", "shoulder", "clavicle", "breast", "root", "pelvis", "neck01", "hip")):
        return "torso"
    return "head_or_torso"  # решаем по высоте кости

PIECES = ["head", "torso", "upperarm_l", "upperarm_r", "forearm_l", "forearm_r",
          "hand_l", "hand_r", "thigh_l", "thigh_r", "shin_l", "shin_r"]

def resolve_head_or_torso(name):
    b = arm_rig.data.bones.get(name)
    if b is not None:
        return "head" if (amw @ b.head_local).z > 1.40 else "torso"
    return "torso"

# ---------- 5. Запекание кожи (до одежды) ----------
# Собственная UV-развёртка: у штатной развёртки MakeHuman перекрываются
# острова, из-за чего AO пачкает кожу. Smart UV даёт уникальные острова.
bpy.ops.object.select_all(action='DESELECT')
mesh.select_set(True)
bpy.context.view_layer.objects.active = mesh
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.normals_make_consistent(inside=False)  # AO чернеет на перевёрнутых нормалях
bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.02)
bpy.ops.object.mode_set(mode='OBJECT')

scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 32

# --- Кожа по скан-методике: запекаем AO и ПОЗИЦИИ поверхности в UV, затем
# красим по анатомическим зонам (как распределён цвет на реальных сканах). ---
TS = 2048
smat = bpy.data.materials.new("SkinBake")
smat.use_nodes = True
tn = smat.node_tree.nodes.new("ShaderNodeTexImage")
smat.node_tree.nodes.active = tn
mesh.data.materials.clear()
mesh.data.materials.append(smat)
bpy.ops.object.select_all(action='DESELECT')
mesh.select_set(True)
bpy.context.view_layer.objects.active = mesh

ao_img = bpy.data.images.new("ao_bake", TS, TS)
tn.image = ao_img
bpy.ops.object.bake(type='AO')
_buf = np.empty(TS * TS * 4, np.float32)
ao_img.pixels.foreach_get(_buf)
ao = _buf.reshape(-1, 4)[:, 0].copy()

pos_img = bpy.data.images.new("pos_bake", TS, TS, float_buffer=True)
tn.image = pos_img
bpy.context.scene.cycles.samples = 4   # позиции детерминированы — сэмплы не нужны
bpy.ops.object.bake(type='POSITION')
pos_img.pixels.foreach_get(_buf)
P = _buf.reshape(-1, 4)[:, :3].copy()
M = np.array(mw)
P = P @ M[:3, :3].T + M[:3, 3][None, :]
print("POS/AO BAKED")

# ориентиры головы (до одежды): персонаж смотрит в -Y.
# Якорь — реальный центр ГЛАЗ (bbox объекта глаз), а не доли от макушки:
# так брови/нос/рот не съезжают при смене пропорций головы.
H0 = max((mw @ v.co).z for v in mesh.data.vertices)
hv0 = [mw @ v.co for v in mesh.data.vertices if (mw @ v.co).z > H0 - 0.26]
cx0 = sum(v.x for v in hv0) / len(hv0)
cy0 = sum(v.y for v in hv0) / len(hv0)
if eyes_obj is not None:
    _e = [eyes_obj.matrix_world @ mathutils.Vector(c) for c in eyes_obj.bound_box]
    z_eyes = sum(v.z for v in _e) / 8.0
else:
    z_eyes = H0 - 0.125
zb0 = z_eyes + 0.024          # линия бровей
zn0 = z_eyes - 0.045          # основание носа
zm0 = z_eyes - 0.078          # рот
nose_ys = [v.y for v in hv0 if abs(v.x - cx0) < 0.012 and abs(v.z - zn0) < 0.012]
nose_y = min(nose_ys) if nose_ys else cy0 - 0.11
ear_xs = [abs(v.x - cx0) for v in hv0 if abs(v.z - (zn0 + 0.02)) < 0.02]
ear_x = max(ear_xs) if ear_xs else 0.075

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
        gg = g[np.ix_(idx, idx)]
        out += amp * gg; tot += amp; amp *= 0.55; c *= 2
    return (out / tot).reshape(-1)

# базовый светлый тёплый тон + пятнистость (3 октавы)
alb = np.tile(np.array([0.842, 0.658, 0.552], np.float32), (P.shape[0], 1))
mott = fbm_uv(96, 3, 77)
alb[:, 0] *= 0.965 + 0.075 * mott
alb[:, 1] *= 0.975 + 0.05 * mott
alb[:, 2] *= 0.985 + 0.03 * mott

RED = np.array([0.115, -0.015, -0.035], np.float32)
def add_red(mask, k=1.0):
    global alb
    alb = alb + RED[None, :] * (mask * k)[:, None]

# подкожная краснота: щёки, нос, уши, шея; суставы: запястья, локти, колени
add_red(sph((cx0 - 0.046, cy0 - 0.038, zn0 + 0.008), 0.038, 0.030), 0.55)
add_red(sph((cx0 + 0.046, cy0 - 0.038, zn0 + 0.008), 0.038, 0.030), 0.55)
add_red(sph((cx0, nose_y + 0.006, zn0 - 0.004), 0.015, 0.014), 0.30)
add_red(sph((cx0 - ear_x, cy0 + 0.008, zn0 + 0.02), 0.030, 0.022), 0.7)
add_red(sph((cx0 + ear_x, cy0 + 0.008, zn0 + 0.02), 0.030, 0.022), 0.7)
for jn, rr, kk in [("wrist_l", 0.085, 0.4), ("wrist_r", 0.085, 0.4),
                   ("elbow_l", 0.07, 0.35), ("elbow_r", 0.07, 0.35),
                   ("knee_l", 0.08, 0.4), ("knee_r", 0.08, 0.4)]:
    add_red(sph(J[jn], rr, 0.05), kk)

# губы
lips = band(zm0 - 0.008, zm0 + 0.010, 0.006) * front * (np.abs(P[:, 0] - cx0) < 0.028)
lip_col = np.array([0.70, 0.34, 0.32], np.float32)
alb = alb * (1 - (lips * 0.6)[:, None]) + lip_col[None, :] * (lips * 0.6)[:, None]

# лёгкая синева выбритой щетины (только подбородок/челюсть, слабая)
beard = band(zm0 - 0.075, zm0 + 0.010, 0.012) * front * (np.abs(P[:, 0] - cx0) < 0.062)
beard = beard * (1 - lips)
grey = np.array([0.62, 0.63, 0.68], np.float32)
alb = alb * (1 - (beard * 0.10)[:, None]) + (alb * grey[None, :]) * (beard * 0.10)[:, None]

# глазницы едва заметно темнее и теплее
for sx in (-1, 1):
    m = sph((cx0 + sx * 0.032, cy0 - 0.048, z_eyes), 0.017, 0.015)
    alb = alb * (1 - (m * 0.05)[:, None] * np.array([[0.2, 0.55, 0.7]], np.float32))

# AO мягко (не в лоб)
alb = alb * (0.80 + 0.20 * ao)[:, None]

px4 = np.ones((P.shape[0], 4), np.float32)
px4[:, :3] = np.clip(alb, 0, 1)
skin_img = bpy.data.images.new("skin_final", TS, TS)
skin_img.pixels.foreach_set(px4.reshape(-1))
skin_png = os.path.join(OUT, "nicholas_skin.png")
skin_img.filepath_raw = skin_png
skin_img.file_format = 'PNG'
skin_img.save()

# roughness: T-зона и губы более гладкие/жирные, остальное матовое
rgh = np.full(P.shape[0], 0.58, np.float32)
tzone = band(zb0 - 0.01, H0 - 0.055, 0.01) * front
nose_strip = band(zn0 - 0.02, zb0, 0.01) * front * (np.abs(P[:, 0] - cx0) < 0.014)
rgh = rgh - 0.12 * np.clip(tzone + nose_strip, 0, 1) - 0.20 * lips + 0.06 * (mott - 0.5)
rpx = np.ones((P.shape[0], 4), np.float32)
rpx[:, 0] = rpx[:, 1] = rpx[:, 2] = np.clip(rgh, 0.2, 0.9)
rgh_img = bpy.data.images.new("skin_rough", TS, TS)
rgh_img.pixels.foreach_set(rpx.reshape(-1))
rgh_img.filepath_raw = os.path.join(OUT, "nicholas_rough.png")
rgh_img.file_format = 'PNG'
rgh_img.save()

# поры: высокочастотная нормаль
pore_h = fbm_uv(512, 2, 41).reshape(TS, TS)
gy, gx = np.gradient(pore_h)
nstr = 1.4
nx, ny, nz = -gx * nstr, -gy * nstr, np.ones_like(pore_h)
ln = np.sqrt(nx * nx + ny * ny + nz * nz)
npx = np.stack([nx / ln, ny / ln, nz / ln], -1) * 0.5 + 0.5
npx4 = np.concatenate([npx.astype(np.float32), np.ones((TS, TS, 1), np.float32)], -1)
pore_img = bpy.data.images.new("skin_pore", TS, TS)
pore_img.pixels.foreach_set(npx4.reshape(-1))
pore_img.filepath_raw = os.path.join(OUT, "nicholas_pore.png")
pore_img.file_format = 'PNG'
pore_img.save()

# финальный материал кожи: цвет + roughness + поры
for n in list(smat.node_tree.nodes):
    if n.type not in ('OUTPUT_MATERIAL',):
        smat.node_tree.nodes.remove(n)
out_n = [n for n in smat.node_tree.nodes if n.type == 'OUTPUT_MATERIAL'][0]
bsdf = smat.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
ti = smat.node_tree.nodes.new("ShaderNodeTexImage")
ti.image = skin_img
smat.node_tree.links.new(ti.outputs["Color"], bsdf.inputs["Base Color"])
tr = smat.node_tree.nodes.new("ShaderNodeTexImage")
tr.image = rgh_img
tr.image.colorspace_settings.name = 'Non-Color'
smat.node_tree.links.new(tr.outputs["Color"], bsdf.inputs["Roughness"])
tp = smat.node_tree.nodes.new("ShaderNodeTexImage")
tp.image = pore_img
tp.image.colorspace_settings.name = 'Non-Color'
nm = smat.node_tree.nodes.new("ShaderNodeNormalMap")
nm.inputs["Strength"].default_value = 0.45
smat.node_tree.links.new(tp.outputs["Color"], nm.inputs["Color"])
smat.node_tree.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
smat.node_tree.links.new(bsdf.outputs["BSDF"], out_n.inputs["Surface"])
print("SKIN BAKED (anatomical zones)")

# перекраска глаз
eye_img = bpy.data.images.load(os.path.join(MH_DATA, "eyes", "materials", "brown_eye.png"))
ep = np.array(eye_img.pixels[:]).reshape(-1, 4)
r, g, b = ep[:, 0], ep[:, 1], ep[:, 2]
mask = (r > b * 1.05) & (r > 0.08) & (r < 0.9)
lum = (r + g + b) / 3.0
ep[mask, 0] = lum[mask] * 0.62
ep[mask, 1] = lum[mask] * 0.80
ep[mask, 2] = lum[mask] * 1.00
eye_img.pixels = ep.ravel().tolist()
eye_png = os.path.join(OUT, "nicholas_eyes.png")
eye_img.filepath_raw = eye_png
eye_img.file_format = 'PNG'
eye_img.save()
if eyes_obj is not None:
    emat = bpy.data.materials.new("EyeBlue")
    emat.use_nodes = True
    eb = emat.node_tree.nodes["Principled BSDF"]
    et = emat.node_tree.nodes.new("ShaderNodeTexImage")
    et.image = eye_img
    emat.node_tree.links.new(et.outputs["Color"], eb.inputs["Base Color"])
    eb.inputs["Roughness"].default_value = 0.15
    eyes_obj.data.materials.clear()
    eyes_obj.data.materials.append(emat)

# ---------- 6. Оболочки (волосы/борода + одежда) ----------
H = max((mw @ v.co).z for v in mesh.data.vertices)
head_vs = [mw @ v.co for v in mesh.data.vertices if (mw @ v.co).z > H - 0.26]
cx = sum(v.x for v in head_vs) / len(head_vs)
cy = sum(v.y for v in head_vs) / len(head_vs)
# лицевые ориентиры — от якоря глаз (см. секцию кожи), не от макушки
z_brow, z_nose, z_mouth = zb0, zn0, zm0

def plain_mat(name, color, rough=0.8):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (*color, 1.0)
    p.inputs["Roughness"].default_value = rough
    return m

def make_shell(name, face_filter, thickness, material, grow=0):
    bpy.ops.object.select_all(action='DESELECT')
    mesh.select_set(True)
    bpy.context.view_layer.objects.active = mesh
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='FACE')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')
    count = 0
    for poly in mesh.data.polygons:
        c = mw @ poly.center
        if face_filter(c):
            poly.select = True
            count += 1
    if count == 0:
        print("SHELL", name, "EMPTY")
        return None
    bpy.ops.object.mode_set(mode='EDIT')
    for _ in range(grow):
        bpy.ops.mesh.select_more()
    bpy.ops.mesh.duplicate()
    bpy.ops.mesh.separate(type='SELECTED')
    bpy.ops.object.mode_set(mode='OBJECT')
    shell = [o for o in bpy.context.selected_objects if o != mesh][-1]
    shell.name = name
    solid = shell.modifiers.new("solid", 'SOLIDIFY')
    solid.thickness = thickness
    solid.offset = 1.0
    shell.data.materials.clear()
    shell.data.materials.append(material)
    print("SHELL", name, count, "faces")
    return shell

hair_col = (0.13, 0.075, 0.035)
beard_col = (0.16, 0.09, 0.04)
green = (0.055, 0.10, 0.065)     # преображенский тёмно-зелёный
red = (0.45, 0.06, 0.06)
dark = (0.045, 0.045, 0.05)
leather = (0.12, 0.07, 0.035)
gold = (0.72, 0.55, 0.16)

def hair_filter(c):
    if c.y < cy - 0.02:
        return c.z > H - 0.048
    if c.y > cy + 0.02:
        return c.z > H - 0.165
    return c.z > H - 0.088

hair = make_shell("hairsh", hair_filter, 0.008, plain_mat("HairMat", hair_col), grow=1)
beard = None  # по фотографиям молодого Николая — только усы, без бороды
# усы строим ОБЪЕКТОМ в секции 7 (выборка граней лица ненадёжна: липнет к носу)
mustache = None
brows = make_shell("browssh",
    lambda c: (c.y < cy - 0.025) and (z_brow - 0.005 < c.z < z_brow + 0.007) and 0.014 < abs(c.x - cx) < 0.042,
    0.004, plain_mat("BrowsMat", hair_col))

import mathutils

face_shells = [s for s in [hair, beard, mustache, brows] if s]

# суставы-ориентиры для кроя (никаких абсолютных высот)
zsh = J["shoulder_l"][2]
xw = abs(J["wrist_l"][0])
z_neck = J["neck"][2]
z_hip = J["hip_l"][2]
z_knee = J["knee_l"][2]
z_pelvis = J["pelvis"][2]
z_hem = z_hip * 0.55 + z_knee * 0.45          # низ кителя — середина бедра
z_belt = z_pelvis + 0.050

briefs = make_shell("briefs",
    lambda c: z_hip - 0.06 < c.z < z_pelvis + 0.03 and abs(c.x) < 0.16,
    0.004, plain_mat("BriefsMat", (0.25, 0.25, 0.27)), grow=1)

def bisect_shell(obj, plane_co, plane_no):
    """Ровный срез: удаляем всё с внешней стороны плоскости (никаких зигзагов)."""
    if obj is None:
        return
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.bisect(plane_co=plane_co, plane_no=plane_no,
                        use_fill=False, clear_inner=False, clear_outer=True)
    bpy.ops.object.mode_set(mode='OBJECT')

# ---- КИТЕЛЬ: торс + рукава; подол/горловина/рукава срезаны ровно ----
def tunic_filter(c):
    if z_hem - 0.04 < c.z < z_neck + 0.03 and abs(c.x) < 0.24:
        return True
    if c.z > z_hem and 0.13 <= abs(c.x) < xw + 0.03:
        return True
    return False

tunic = make_shell("tunic", tunic_filter, 0.006, plain_mat("TunicMat", green), grow=1)
bisect_shell(tunic, (0.0, 0.0, z_hem), (0.0, 0.0, -1.0))            # подол
bisect_shell(tunic, (0.0, 0.0, z_neck + 0.015), (0.0, 0.0, 1.0))    # горловина
sh_l = mathutils.Vector(J["shoulder_l"]); wr_l = mathutils.Vector(J["wrist_l"])
ax_l = (wr_l - sh_l).normalized()
bisect_shell(tunic, tuple(wr_l - ax_l * 0.02), tuple(ax_l))         # конец рукава L
sh_r = mathutils.Vector(J["shoulder_r"]); wr_r = mathutils.Vector(J["wrist_r"])
ax_r = (wr_r - sh_r).normalized()
bisect_shell(tunic, tuple(wr_r - ax_r * 0.02), tuple(ax_r))         # конец рукава R

# ---- БРЮКИ: только ноги (|x| ограничен — кисти НЕ трогаем), ровный низ ----
breeches = make_shell("breeches",
    lambda c: z_knee - 0.08 < c.z < z_hem + 0.06 and abs(c.x) < 0.30,
    0.005, plain_mat("BreechesMat", (0.075, 0.095, 0.08)), grow=1)
bisect_shell(breeches, (0.0, 0.0, z_knee - 0.065), (0.0, 0.0, -1.0))

uniform_shells = [s for s in [tunic, breeches] if s]

# ---------- 7. Построенные детали: воротник, манжеты, ремень, САПОГИ,
# погоны, пуговицы, пряжка, фуражка. Каждая деталь знает свою кость. ----------
accessories = []
def pick_bone(*names):
    for n in names:
        if arm_rig.data.bones.get(n) is not None:
            return n
    return "spine03"

def add_prim(name, mat, bone="spine03"):
    o = bpy.context.active_object
    o.name = name
    o.data.materials.clear()
    o.data.materials.append(mat)
    o["bind_bone"] = bone
    accessories.append(o)
    return o

gold_mat = plain_mat("GoldMat", gold, rough=0.35)
green_mat = plain_mat("CapMat", green)
dark_mat = plain_mat("VisorMat", dark, rough=0.3)
red_mat = plain_mat("BandMat", red)

# грудь: передний y на данной высоте
def front_y(z, dx=0.03):
    ys = [(mw @ v.co).y for v in mesh.data.vertices
          if abs((mw @ v.co).x) < dx and abs((mw @ v.co).z - z) < 0.02]
    return min(ys) if ys else -0.12

leather_mat = plain_mat("LeatherMat", (0.045, 0.038, 0.035), rough=0.35)

# --- ВОРОТНИК-СТОЙКА: обмер только самой ШЕИ (узкий столбик), не плеч ---
neck_vs = [mw @ v.co for v in mesh.data.vertices
           if z_neck + 0.015 < (mw @ v.co).z < z_neck + 0.05 and abs((mw @ v.co).x) < 0.07]
ncx = sum(v.x for v in neck_vs) / len(neck_vs)
ncy = sum(v.y for v in neck_vs) / len(neck_vs)
nrad = min(max(math.hypot(v.x - ncx, v.y - ncy) for v in neck_vs) + 0.006, 0.058)
bpy.ops.mesh.primitive_cylinder_add(radius=nrad, depth=0.036, vertices=20,
    location=(ncx, ncy, z_neck + 0.028), end_fill_type='NOTHING')
collar = add_prim("collar", red_mat, pick_bone("neck01", "neck02"))
collar.modifiers.new("solid", 'SOLIDIFY').thickness = 0.006

# --- МАНЖЕТЫ: красные кольца по оси предплечья ---
for ax, wr, side in [(ax_l, wr_l, "L"), (ax_r, wr_r, "R")]:
    loc = wr - ax * 0.045
    bpy.ops.mesh.primitive_cylinder_add(radius=0.047, depth=0.075, vertices=14,
        location=tuple(loc), end_fill_type='NOTHING')
    cuff = add_prim("cuff_" + side, red_mat, pick_bone("lowerarm02." + side, "lowerarm01." + side))
    cuff.rotation_euler = mathutils.Vector((0, 0, 1)).rotation_difference(ax).to_euler()
    cuff.modifiers.new("solid", 'SOLIDIFY').thickness = 0.005

# --- РЕМЕНЬ: обмер только ТУЛОВИЩА (|x| ограничен — в A-позе на этой высоте
# висят предплечья, без фильтра ремень превращался в «доску» на всю ширину) ---
waist_vs = [mw @ v.co for v in mesh.data.vertices
            if z_belt - 0.02 < (mw @ v.co).z < z_belt + 0.02 and abs((mw @ v.co).x) < 0.16]
wcx = sum(v.x for v in waist_vs) / len(waist_vs)
wcy = sum(v.y for v in waist_vs) / len(waist_vs)
wrx = max(abs(v.x - wcx) for v in waist_vs) + 0.012
wry = max(abs(v.y - wcy) for v in waist_vs) + 0.012
bpy.ops.mesh.primitive_cylinder_add(radius=1.0, depth=0.035, vertices=24,
    location=(wcx, wcy, z_belt), end_fill_type='NOTHING')
belt = add_prim("belt", plain_mat("BeltMat", leather, rough=0.45), pick_bone("spine02", "spine03"))
belt.scale = (wrx, wry, 1.0)
belt.modifiers.new("solid", 'SOLIDIFY').thickness = 0.007

# --- САПОГИ: голенище + ступня + подошва (пальцы ЗАКРЫТЫ) ---
for side in ("L", "R"):
    ankle = mathutils.Vector(bone_head("foot." + side))
    top_z = z_knee - 0.05
    shaft_h = top_z - (ankle.z - 0.02)
    bpy.ops.mesh.primitive_cone_add(radius1=0.052, radius2=0.066, depth=shaft_h, vertices=16,
        location=(ankle.x, ankle.y, (top_z + ankle.z - 0.02) * 0.5))
    add_prim("bootshaft_" + side, leather_mat, pick_bone("lowerleg02." + side, "lowerleg01." + side))
    # ступня: эллипсоид накрывает ВСЮ стопу с запасом (пальцы закрыты) + подошва + каблук
    toe_y = min((mw @ v.co).y for v in mesh.data.vertices
                if (mw @ v.co).z < 0.08 and abs((mw @ v.co).x - ankle.x) < 0.07)
    fl = (ankle.y + 0.055) - (toe_y - 0.015)      # длина стопы с запасом
    fc = (ankle.y + 0.055 + toe_y - 0.015) * 0.5  # центр по Y
    parts = []
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, segments=16, ring_count=10,
        location=(ankle.x, fc, 0.055))
    ell = bpy.context.active_object; ell.scale = (0.058, fl * 0.52, 0.058); parts.append(ell)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(ankle.x, fc, 0.011))
    sole = bpy.context.active_object; sole.scale = (0.105, fl * 0.98, 0.022); parts.append(sole)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(ankle.x, ankle.y + 0.040, 0.020))
    heel = bpy.context.active_object; heel.scale = (0.095, 0.09, 0.040); parts.append(heel)
    # тупой носок сапога: закрывает клин между сужением эллипсоида и подошвой
    bpy.ops.mesh.primitive_cube_add(size=1, location=(ankle.x, toe_y + 0.030, 0.036))
    toe = bpy.context.active_object; toe.scale = (0.112, 0.105, 0.072); parts.append(toe)
    bpy.ops.object.select_all(action='DESELECT')
    for p in parts:
        p.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    foot_obj = bpy.context.active_object
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    foot_obj.name = "bootfoot_" + side
    foot_obj.data.materials.clear()
    foot_obj.data.materials.append(leather_mat)
    foot_obj["bind_bone"] = pick_bone("foot." + side)
    accessories.append(foot_obj)

# --- ПУГОВИЦЫ: ряд от ремня до воротника ---
btn_zs = np.linspace(z_belt + 0.055, z_neck - 0.018, 6)
for i, z in enumerate(btn_zs):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.0085, location=(0.0, front_y(float(z)) - 0.011, float(z)), segments=12, ring_count=8)
    add_prim(f"button{i}", gold_mat)

# --- ПРЯЖКА ---
bpy.ops.mesh.primitive_cube_add(size=1, location=(wcx, wcy - wry - 0.004, z_belt))
buckle = add_prim("buckle", gold_mat)
buckle.scale = (0.026, 0.007, 0.020)

# --- ПОГОНЫ ---
for side, sname in [(1, "board_l"), (-1, "board_r")]:
    zs = [(mw @ v.co).z for v in mesh.data.vertices
          if abs((mw @ v.co).x - side * 0.105) < 0.02 and abs((mw @ v.co).y + 0.02) < 0.06
          and z_neck - 0.10 < (mw @ v.co).z < z_neck + 0.02]
    ztop = max(zs) if zs else z_neck - 0.03
    bpy.ops.mesh.primitive_cube_add(size=1, location=(side * 0.105, -0.02, ztop + 0.012))
    b = add_prim(sname, gold_mat)
    b.scale = (0.052, 0.026, 0.006)
    b.rotation_euler = (0, side * 0.20, 0)

# --- ФУРАЖКА: по форме головы, не «гриб» ---
head_top_vs = [mw @ v.co for v in mesh.data.vertices if (mw @ v.co).z > H - 0.09]
hw = max(abs(v.x - cx) for v in head_top_vs)
hd = (max(v.y for v in head_top_vs) - min(v.y for v in head_top_vs)) / 2
bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, location=(cx, cy, H + 0.016), segments=24, ring_count=12)
crown = add_prim("cap_crown", green_mat, "head")
crown.scale = (hw * 1.08, hd * 1.10, 0.038)
bpy.ops.mesh.primitive_cylinder_add(radius=1.0, depth=0.030, location=(cx, cy, H - 0.004), vertices=24)
band = add_prim("cap_band", red_mat, "head")
band.scale = (hw * 1.03, hd * 1.05, 1.0)
# козырёк заходит ЗАДНИМ краем под околыш (не парит отдельно от фуражки)
bpy.ops.mesh.primitive_cylinder_add(radius=1.0, depth=0.005, location=(cx, cy - hd * 0.80, H - 0.014), vertices=20)
visor = add_prim("cap_visor", dark_mat, "head")
visor.scale = (hw * 0.84, hd * 0.70, 1.0)
visor.rotation_euler = (0.30, 0, 0)
bpy.ops.mesh.primitive_cylinder_add(radius=0.008, depth=0.006, location=(cx, cy - hd * 1.05, H - 0.004), vertices=12)
cockade = add_prim("cockade", gold_mat, "head")
cockade.rotation_euler = (math.pi / 2, 0, 0)

# --- УСЫ: два эллипсоида под носом; фронт лица меряем ПРЯМО на высоте усов ---
must_mat = plain_mat("MustacheMat", beard_col, rough=0.65)
z_must = z_eyes - 0.051
face_ys = [v.y for v in hv0 if abs(v.x - cx0) < 0.02 and abs(v.z - z_must) < 0.008]
face_y = min(face_ys) if face_ys else nose_y + 0.008
for sx in (-1, 1):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, segments=12, ring_count=8,
        location=(cx + sx * 0.0115, face_y - 0.0015, z_must))
    mo = add_prim("mustache_" + ("l" if sx < 0 else "r"), must_mat, "head")
    mo.scale = (0.0155, 0.0075, 0.0062)
    mo.rotation_euler = (math.radians(-12), math.radians(sx * -14), math.radians(sx * -8))

# применить трансформы примитивов
bpy.ops.object.select_all(action='DESELECT')
for o in accessories:
    o.select_set(True)
bpy.context.view_layer.objects.active = accessories[0]
bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

# ---------- нормировка роста: тело ровно 1.70 м (было ~2.7 в GLB) ----------
H_body = max((mesh.matrix_world @ v.co).z for v in mesh.data.vertices)
s_norm = 1.70 / H_body
all_export = [mesh, arm_rig] + face_shells + uniform_shells + accessories \
    + ([briefs] if briefs else []) + ([eyes_obj] if eyes_obj else [])
bpy.ops.object.select_all(action='DESELECT')
for o in all_export:
    if o is None:
        continue
    o.location = [c * s_norm for c in o.location]
    o.scale = [c * s_norm for c in o.scale]
    o.select_set(True)
bpy.context.view_layer.objects.active = arm_rig
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
print("HEIGHT NORMALIZED:", H_body, "->", 1.70)


# ================= GLB: скиннинг, анимации, экспорт =================
import mathutils

def bind_to_armature(obj, solo_bone=None):
    """Привязывает объект к ригу. solo_bone: все вершины на одну кость."""
    if solo_bone is not None:
        vg = obj.vertex_groups.get(solo_bone) or obj.vertex_groups.new(name=solo_bone)
        vg.add(range(len(obj.data.vertices)), 1.0, 'REPLACE')
    has_arm = any(m.type == 'ARMATURE' for m in obj.modifiers)
    if not has_arm:
        am = obj.modifiers.new("arm", 'ARMATURE')
        am.object = arm_rig

# оболочки лица/одежды унаследовали веса тела — просто вешаем модификатор
for sh in face_shells + uniform_shells + ([briefs] if briefs else []):
    if sh is not None:
        bind_to_armature(sh)
# глаза и фуражка/пуговицы/погоны — жёстко на кость
if eyes_obj is not None:
    bind_to_armature(eyes_obj, solo_bone="head")
for acc in accessories:
    bind_to_armature(acc, solo_bone=str(acc.get("bind_bone", "spine03")))

# ---------- автопроба осей костей ----------
def probe_axis(bone, marker, want):
    """Подбирает (ось, знак) поворота bone, максимально двигающие marker.tail
    в направлении want (мировой вектор)."""
    pb = arm_rig.pose.bones[bone]
    mk = arm_rig.pose.bones[marker]
    pb.rotation_mode = 'XYZ'
    best = (0, 1, -1e9)
    for axis in range(3):
        for sign in (1, -1):
            pb.rotation_euler = (0, 0, 0)
            bpy.context.view_layer.update()
            before = (arm_rig.matrix_world @ mk.tail).copy()
            e = [0.0, 0.0, 0.0]
            e[axis] = sign * 0.5
            pb.rotation_euler = e
            bpy.context.view_layer.update()
            after = (arm_rig.matrix_world @ mk.tail).copy()
            score = (after - before).dot(mathutils.Vector(want))
            if score > best[2]:
                best = (axis, sign, score)
    pb.rotation_euler = (0, 0, 0)
    bpy.context.view_layer.update()
    return best

FWD = (0, -1, 0)   # персонаж смотрит в -Y
DOWN = (0, 0, -1)
BACK = (0, 1, 0)

ax_hip_L = probe_axis("upperleg01.L", "foot.L", FWD)
ax_hip_R = probe_axis("upperleg01.R", "foot.R", FWD)
ax_knee_L = probe_axis("lowerleg01.L", "foot.L", BACK)
ax_knee_R = probe_axis("lowerleg01.R", "foot.R", BACK)
ax_swing_L = probe_axis("upperarm01.L", "wrist.L", FWD)
ax_swing_R = probe_axis("upperarm01.R", "wrist.R", FWD)
ax_down_L = probe_axis("upperarm01.L", "wrist.L", DOWN)
ax_down_R = probe_axis("upperarm01.R", "wrist.R", DOWN)
ax_elb_L = probe_axis("lowerarm01.L", "wrist.L", FWD)
ax_elb_R = probe_axis("lowerarm01.R", "wrist.R", FWD)
print("AXES hipL", ax_hip_L, "kneeL", ax_knee_L, "swingL", ax_swing_L, "downL", ax_down_L)

def euler_for(*components):
    """components: ((axis, sign, _), angle) -> суммарный эйлер."""
    e = [0.0, 0.0, 0.0]
    for (axis, sign, _), ang in components:
        e[axis] += sign * ang
    return tuple(e)

ARMS_DOWN = 0.85   # A-поза -> руки вдоль тела
ELBOW_REST = 0.28
TAU = 2 * math.pi

# голеностоп: носок вперёд-вниз; вертикаль корпуса: ось локального смещения root
ax_foot_L = probe_axis("foot.L", "foot.L", (0, -0.6, -0.8))
ax_foot_R = probe_axis("foot.R", "foot.R", (0, -0.6, -0.8))

def probe_root_up():
    pb = arm_rig.pose.bones["root"]
    best = (1, 1, -1e9)
    for axis in range(3):
        for sign in (1, -1):
            pb.location = (0.0, 0.0, 0.0)
            bpy.context.view_layer.update()
            before = (arm_rig.matrix_world @ pb.head).z
            l = [0.0, 0.0, 0.0]
            l[axis] = sign * 0.05
            pb.location = l
            bpy.context.view_layer.update()
            after = (arm_rig.matrix_world @ pb.head).z
            score = after - before
            if score > best[2]:
                best = (axis, sign, score)
    pb.location = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()
    return best

ax_root_up = probe_root_up()
print("AXES foot", ax_foot_L, "root_up", ax_root_up)

def make_action(name, frames_poses):
    act = bpy.data.actions.new(name)
    if arm_rig.animation_data is None:
        arm_rig.animation_data_create()
    arm_rig.animation_data.action = act
    for frame, poses in frames_poses:
        bpy.context.scene.frame_set(frame)
        for bname, val in poses.items():
            if bname == "__bob":
                pb = arm_rig.pose.bones["root"]
                l = [0.0, 0.0, 0.0]
                l[ax_root_up[0]] = ax_root_up[1] * val
                pb.location = l
                pb.keyframe_insert('location', frame=frame)
                continue
            pb = arm_rig.pose.bones[bname]
            pb.rotation_mode = 'XYZ'
            pb.rotation_euler = val
            pb.keyframe_insert('rotation_euler', frame=frame)
    return act

def walk_pose(phase):
    """Естественный шаг: бёдра-колени-голеностоп со сдвигом фаз,
    руки в противофазе с локтевой прокачкой, вертикальная пружина корпуса."""
    s = math.sin(phase * TAU)
    sw = 0.48 * s
    kneeL = 0.10 + 0.72 * max(0.0, math.sin((phase + 0.70) * TAU))
    kneeR = 0.10 + 0.72 * max(0.0, math.sin((phase + 0.20) * TAU))
    footL = -0.30 * math.sin((phase + 0.55) * TAU) - 0.08
    footR = -0.30 * math.sin((phase + 0.05) * TAU) - 0.08
    arm = 0.32 * s
    elbL = ELBOW_REST + 0.20 * max(0.0, -s)
    elbR = ELBOW_REST + 0.20 * max(0.0, s)
    pose = {
        "upperleg01.L": euler_for((ax_hip_L, sw)),
        "upperleg01.R": euler_for((ax_hip_R, -sw)),
        "lowerleg01.L": euler_for((ax_knee_L, kneeL)),
        "lowerleg01.R": euler_for((ax_knee_R, kneeR)),
        "foot.L": euler_for((ax_foot_L, footL)),
        "foot.R": euler_for((ax_foot_R, footR)),
        "upperarm01.L": euler_for((ax_down_L, ARMS_DOWN), (ax_swing_L, -arm)),
        "upperarm01.R": euler_for((ax_down_R, ARMS_DOWN), (ax_swing_R, arm)),
        "lowerarm01.L": euler_for((ax_elb_L, elbL)),
        "lowerarm01.R": euler_for((ax_elb_R, elbR)),
        # корпус ниже в моменты двойной опоры, выше в переносе
        "__bob": -0.022 * (0.5 + 0.5 * math.cos(phase * 2 * TAU)),
    }
    return pose

FPS = 24
walk_frames = [(1 + i * 2, walk_pose(i / 12.0)) for i in range(13)]  # цикл 1 с
walk = make_action("walk", walk_frames)

def idle_pose(t):
    b = 0.5 + 0.5 * math.sin(t * TAU)
    return {
        "upperarm01.L": euler_for((ax_down_L, ARMS_DOWN - 0.015 * b)),
        "upperarm01.R": euler_for((ax_down_R, ARMS_DOWN - 0.015 * b)),
        "lowerarm01.L": euler_for((ax_elb_L, ELBOW_REST)),
        "lowerarm01.R": euler_for((ax_elb_R, ELBOW_REST)),
        "upperleg01.L": (0.0, 0.0, 0.0),
        "upperleg01.R": (0.0, 0.0, 0.0),
        "lowerleg01.L": euler_for((ax_knee_L, 0.04)),
        "lowerleg01.R": euler_for((ax_knee_R, 0.04)),
        "foot.L": (0.0, 0.0, 0.0),
        "foot.R": (0.0, 0.0, 0.0),
        "__bob": -0.003 * b,
    }

idle_frames = [(1 + i * 12, idle_pose(i / 4.0)) for i in range(5)]  # 2 с цикл
idle = make_action("idle", idle_frames)

def jump_pose(hip, knee, foot, arm_sw, bob):
    return {
        "upperleg01.L": euler_for((ax_hip_L, hip)),
        "upperleg01.R": euler_for((ax_hip_R, hip)),
        "lowerleg01.L": euler_for((ax_knee_L, knee)),
        "lowerleg01.R": euler_for((ax_knee_R, knee)),
        "foot.L": euler_for((ax_foot_L, foot)),
        "foot.R": euler_for((ax_foot_R, foot)),
        "upperarm01.L": euler_for((ax_down_L, ARMS_DOWN), (ax_swing_L, arm_sw)),
        "upperarm01.R": euler_for((ax_down_R, ARMS_DOWN), (ax_swing_R, arm_sw)),
        "lowerarm01.L": euler_for((ax_elb_L, ELBOW_REST + 0.15)),
        "lowerarm01.R": euler_for((ax_elb_R, ELBOW_REST + 0.15)),
        "__bob": bob,
    }

jump_frames = [
    (1,  jump_pose(0.0, 0.06, 0.0, 0.0, 0.0)),
    (5,  jump_pose(0.55, 1.05, -0.25, -0.30, -0.11)),   # присед-замах
    (9,  jump_pose(-0.12, 0.06, 0.35, 0.20, 0.02)),     # толчок, носки вытянуты
    (14, jump_pose(0.25, 0.55, 0.0, 0.05, -0.03)),      # подбор ног в полёте
    (19, jump_pose(0.0, 0.06, 0.0, 0.0, 0.0)),
]
jump = make_action("jump", jump_frames)

# NLA: обе анимации как отдельные дорожки (экспортер выдаст их по именам)
arm_rig.animation_data.action = None
for act in (idle, walk, jump):
    tr = arm_rig.animation_data.nla_tracks.new()
    tr.name = act.name
    strip = tr.strips.new(act.name, 1, act)
    strip.name = act.name

bpy.context.scene.render.fps = FPS

# ---------- запечь shape keys в базовую сетку (иначе Godot сбрасывает морфы) ----------
body_set_pre = [mesh] + face_shells + ([eyes_obj] if eyes_obj else []) + ([briefs] if briefs else [])
uni_set_pre = [mesh] + face_shells + ([eyes_obj] if eyes_obj else []) + uniform_shells + accessories
for o in {o.name: o for o in body_set_pre + uni_set_pre}.values():
    if o.type == 'MESH' and o.data.shape_keys:
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.shape_key_remove(all=True, apply_mix=True)
        print("SHAPE KEYS BAKED:", o.name)

# ---------- экспорт двух GLB ----------
def export_glb(objects, path):
    bpy.ops.object.select_all(action='DESELECT')
    for o in objects:
        o.select_set(True)
    arm_rig.select_set(True)
    bpy.context.view_layer.objects.active = arm_rig
    bpy.ops.export_scene.gltf(filepath=path, export_format='GLB',
                              use_selection=True,
                              export_animations=True,
                              export_animation_mode='NLA_TRACKS',
                              export_apply=True,
                              export_yup=True)
    print("GLB EXPORTED", path)

body_set = [mesh] + face_shells + ([eyes_obj] if eyes_obj else []) + ([briefs] if briefs else [])
uni_set = [mesh] + face_shells + ([eyes_obj] if eyes_obj else []) + uniform_shells + accessories

# убрать посторонние меши (виджеты костей и т.п.) — иначе экспортёр тащит их
# как детей арматуры (из-за этого в GLB был Icosphere 1 м и рост 2.75)
keep = {o.name for o in body_set + uni_set if o is not None}
for o in list(bpy.data.objects):
    if o.type == 'MESH' and o.name not in keep:
        print("REMOVED STRAY:", o.name)
        bpy.data.objects.remove(o, do_unlink=True)

export_glb(uni_set, os.path.join(OUT, "nicholas_uniform.glb"))
export_glb(body_set, os.path.join(OUT, "nicholas_body.glb"))
print("DONE")
