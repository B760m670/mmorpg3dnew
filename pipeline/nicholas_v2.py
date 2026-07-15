"""Персонаж V2 — С НУЛЯ, правильным подходом (не «раздутая кукла»).

Тело: MPFB (оцифрованная антропометрия) + subdivision — гладкая поверхность.
Одежда: НАСТОЯЩИЙ КРОЙ — обмер сечений фигуры по высотам → выкройка-труба с
припуском → СИМУЛЯЦИЯ ТКАНИ (драпировка, естественные складки) → подгибка.
Сапоги: лофт по колодке (как шьют обувь), пальцы закрыты формой, не «кубики».
Воротник/фуражка/ремень: по обмерам, со скруглением. Кожа: анатомические зоны
+ подповерхностное рассеивание (SSS). Экспорт: skinned GLB + idle/walk/jump.
"""
import bpy, bmesh, sys, os, importlib, math, mathutils
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
ExportService = dyn("mpfb.services.exportservice", "ExportService")

# ================= 1. ТЕЛО (антропометрия Николая II: 1.70, сухощавый) ========
macro = TargetService.get_default_macro_info_dict()
for k, v in [("gender", 1.0), ("age", 0.45), ("muscle", 0.48),
             ("weight", 0.44), ("height", 0.5), ("proportions", 0.7)]:
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

# черты по фотографиям (нос прямой, скулы, оттопыренные уши, овал)
T("nose", "nose-curve-concave", 0.10)
T("nose", "nose-volume-incr", 0.14)
T("nose", "nose-width1-decr", 0.12)
T("chin", "chin-bones-incr", 0.25)
T("cheek", "l-cheek-bones-incr", 0.22)
T("cheek", "r-cheek-bones-incr", 0.22)
T("head", "head-oval", 0.3)
T("ears", "l-ear-flap-incr", 0.45)
T("ears", "r-ear-flap-incr", 0.45)
T("torso", "torso-vshape-incr", 0.18)

eyes_path = os.path.join(MH_DATA, "eyes", "low-poly", "low-poly.mhclo")
HumanService.add_mhclo_asset(eyes_path, human, asset_type="Eyes", material_type="MAKESKIN")
HumanService.add_builtin_rig(human, "default")

mesh = human
ExportService.bake_modifiers_remove_helpers(mesh, bake_masks=True, bake_subdiv=True,
                                            remove_helpers=True, also_proxy=True)
eyes_obj = None
for o in bpy.data.objects:
    if o.type == 'MESH' and "low-poly" in o.name.lower():
        eyes_obj = o
arm_rig = None
for o in bpy.data.objects:
    if o.type == 'ARMATURE':
        arm_rig = o
arm_rig.hide_render = True
mw = mesh.matrix_world
amw = arm_rig.matrix_world
print("BODY", len(mesh.data.vertices), "verts")

def bone_head(name):
    b = arm_rig.data.bones.get(name)
    h = amw @ b.head_local
    return mathutils.Vector((h.x, h.y, h.z))

J = {n: bone_head(b) for n, b in [
    ("neck", "neck01"), ("shoulder_l", "upperarm01.L"), ("shoulder_r", "upperarm01.R"),
    ("elbow_l", "lowerarm01.L"), ("elbow_r", "lowerarm01.R"),
    ("wrist_l", "wrist.L"), ("wrist_r", "wrist.R"),
    ("hip_l", "upperleg01.L"), ("hip_r", "upperleg01.R"),
    ("knee_l", "lowerleg01.L"), ("knee_r", "lowerleg01.R"),
    ("ankle_l", "foot.L"), ("ankle_r", "foot.R"), ("pelvis", "root")]}
z_neck = J["neck"].z; z_knee = J["knee_l"].z; z_hip = J["hip_l"].z
z_pelvis = J["pelvis"].z
z_hem = z_hip * 0.52 + z_knee * 0.48
z_belt = z_pelvis + 0.05

WORLD_V = [mw @ v.co for v in mesh.data.vertices]
H0 = max(v.z for v in WORLD_V)

# ================= 2. ОБМЕР ФИГУРЫ И КРОЙ =====================================
def section_ring(z, pad, bins=36, xlim=0.30, zslab=0.018, cxy=None):
    """Сечение тела на высоте z: замер радиуса по углам + припуск pad (крой)."""
    pts = [(v.x, v.y) for v in WORLD_V if abs(v.z - z) < zslab and abs(v.x) < xlim]
    if cxy is None:
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
    else:
        cx, cy = cxy
    rad = [0.0] * bins
    for px, py in pts:
        a = math.atan2(py - cy, px - cx) % (2 * math.pi)
        i = int(a / (2 * math.pi) * bins) % bins
        rad[i] = max(rad[i], math.hypot(px - cx, py - cy))
    # заполнить пустые сектора соседями (между ног и т.п.)
    for _ in range(bins):
        for i in range(bins):
            if rad[i] == 0.0:
                rad[i] = max(rad[(i - 1) % bins], rad[(i + 1) % bins]) * 0.98
    # сгладить
    rad = [(rad[(i - 1) % bins] + rad[i] * 2 + rad[(i + 1) % bins]) / 4 for i in range(bins)]
    ring = []
    for i in range(bins):
        a = (i + 0.5) / bins * 2 * math.pi
        ring.append((cx + math.cos(a) * (rad[i] + pad), cy + math.sin(a) * (rad[i] + pad), z))
    return ring

def loft(rings, name, mat, close_top=False, close_bottom=False):
    bm = bmesh.new()
    rows = []
    for ring in rings:
        rows.append([bm.verts.new(p) for p in ring])
    for r0, r1 in zip(rows, rows[1:]):
        n = len(r0)
        for i in range(n):
            bm.faces.new((r0[i], r0[(i + 1) % n], r1[(i + 1) % n], r1[i]))
    if close_bottom:
        bm.faces.new(tuple(reversed(rows[0])))
    if close_top:
        bm.faces.new(tuple(rows[-1]))
    for f in bm.faces:
        f.smooth = True
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    ob.data.materials.append(mat)
    return ob

def plain_mat(name, color, rough=0.8, metal=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (*color, 1.0)
    p.inputs["Roughness"].default_value = rough
    p.inputs["Metallic"].default_value = metal
    return m

green = plain_mat("TunicMat", (0.052, 0.095, 0.062), 0.88)      # преображенское сукно
green2 = plain_mat("BreechMat", (0.060, 0.080, 0.062), 0.9)
red_mat = plain_mat("CollarMat", (0.42, 0.055, 0.06), 0.85)
gold_mat = plain_mat("GoldMat", (0.75, 0.57, 0.16), 0.32, 1.0)
leather_mat = plain_mat("LeatherMat", (0.042, 0.036, 0.033), 0.32)
belt_mat = plain_mat("BeltMat", (0.11, 0.065, 0.032), 0.5)
hair_mat = plain_mat("HairMat", (0.13, 0.075, 0.035), 0.72)
dark_mat = plain_mat("VisorMat", (0.04, 0.04, 0.045), 0.28)
cap_green = plain_mat("CapMat", (0.052, 0.095, 0.062), 0.85)

# --- КИТЕЛЬ: выкройка-труба по сечениям, потом драпируется физикой ткани ---
tunic_zs = [z_neck + 0.015, z_neck - 0.02, z_neck - 0.07, z_neck - 0.13,
            z_belt + 0.10, z_belt + 0.03, z_belt - 0.03,
            z_hem + 0.06, z_hem + 0.02, z_hem - 0.02]
tunic_pads = [0.011, 0.012, 0.014, 0.018, 0.020, 0.022, 0.022, 0.024, 0.024, 0.024]
tunic_rings = []
for i, z in enumerate(tunic_zs):
    xl = 0.165 if i < 4 else 0.185     # сверху по фигуре, к подолу свободнее
    tunic_rings.append(section_ring(z, tunic_pads[i], bins=40, xlim=xl))
tunic = loft(tunic_rings, "tunic", green)
# группа закрепа: верхние два кольца (плечи) не падают при симуляции
pin = tunic.vertex_groups.new(name="pin")
# закреп только горловины: широкий пин рвёт ткань на границе (дыры на груди)
pin.add([i for i, v in enumerate(tunic.data.vertices) if v.co.z > z_neck - 0.05], 1.0, 'REPLACE')

# РУКАВА кроятся от поверхности руки ПОСЛЕ сглаживания тела (секция 5):
# лофт-трубы нельзя скиннить «ближайшей вершиной» — интерьер цепляется к торсу.
sleeve_l = sleeve_r = None

# манжеты: красные кольца по оси предплечья, жёстко на кость предплечья
def cuff_for(sh, wr, name):
    axis = (wr - sh).normalized()
    bpy.ops.mesh.primitive_cylinder_add(radius=0.047, depth=0.075, vertices=16,
        location=tuple(wr - axis * 0.045), end_fill_type='NOTHING')
    cuff = bpy.context.active_object
    cuff.name = "cuff_" + name
    cuff.data.materials.append(red_mat)
    cuff.rotation_euler = mathutils.Vector((0, 0, 1)).rotation_difference(axis).to_euler()
    so2 = cuff.modifiers.new("solid", 'SOLIDIFY'); so2.thickness = 0.005
    bpy.context.view_layer.objects.active = cuff
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    bpy.ops.object.modifier_apply(modifier="solid")
    cuff["bind_bone"] = "lowerarm02." + name
    return cuff

cuff_l = cuff_for(J["shoulder_l"], J["wrist_l"], "L")
cuff_r = cuff_for(J["shoulder_r"], J["wrist_r"], "R")

# --- БРЮКИ: две штанины по сечениям ноги ---
def leg_tube(hip, knee, side):
    rings = []
    for t, pad in [(0.15, 0.018), (0.35, 0.015), (0.6, 0.012), (0.85, 0.010), (1.03, 0.009)]:
        z = hip.z + (knee.z - hip.z) * t
        x0 = hip.x + (knee.x - hip.x) * t
        y0 = hip.y + (knee.y - hip.y) * t
        pts = [(v.x, v.y) for v in WORLD_V if abs(v.z - z) < 0.02
               and (v.x - x0) ** 2 + (v.y - y0) ** 2 < 0.02
               and (v.x > 0.01 if side == "L" else v.x < -0.01)]
        if not pts:
            pts = [(x0, y0)]
        cx = sum(p[0] for p in pts) / len(pts); cy = sum(p[1] for p in pts) / len(pts)
        r = max((math.hypot(p[0] - cx, p[1] - cy) for p in pts), default=0.07) + pad
        ring = []
        for i in range(16):
            a = i / 16 * 2 * math.pi
            ring.append((cx + math.cos(a) * r, cy + math.sin(a) * r, z))
        rings.append(ring)
    return loft(rings, "breech_" + side, green2)

breech_l = leg_tube(J["hip_l"], J["knee_l"], "L")
breech_r = leg_tube(J["hip_r"], J["knee_r"], "R")

# --- СИМУЛЯЦИЯ ТКАНИ: китель драпируется по телу (настоящие складки) ---
col_mod = mesh.modifiers.new("col", 'COLLISION')
mesh.collision.thickness_outer = 0.004
scene = bpy.context.scene
scene.frame_start = 1
scene.frame_end = 36
cl = tunic.modifiers.new("cloth", 'CLOTH')
cl.settings.quality = 6
cl.settings.mass = 0.32
cl.settings.tension_stiffness = 28.0      # сукно жёстче — меньше сползает с плеч
cl.settings.compression_stiffness = 24.0
cl.settings.shear_stiffness = 14.0
cl.settings.bending_stiffness = 0.55
cl.settings.vertex_group_mass = "pin"
cl.collision_settings.collision_quality = 3
cl.collision_settings.distance_min = 0.005
cl.collision_settings.use_self_collision = False
scene.frame_end = 30
for f in range(1, 31):
    scene.frame_set(f)
bpy.ops.object.select_all(action='DESELECT')
tunic.select_set(True)
bpy.context.view_layer.objects.active = tunic
bpy.ops.object.modifier_apply(modifier="cloth")
scene.frame_set(1)
mesh.modifiers.remove(col_mod)
print("CLOTH SIM DONE")

# лёгкие складки на брюках/кителе (ткань, не воздушный шар)
fold_tex = bpy.data.textures.new("folds", 'CLOUDS')
fold_tex.noise_scale = 0.10
for ob, s in [(breech_l, 0.004), (breech_r, 0.004), (tunic, 0.002)]:
    sub = ob.modifiers.new("subd", 'SUBSURF'); sub.levels = 1
    dp = ob.modifiers.new("disp", 'DISPLACE')
    dp.texture = fold_tex; dp.strength = s; dp.mid_level = 0.5
    so = ob.modifiers.new("solid", 'SOLIDIFY'); so.thickness = 0.004
    bpy.context.view_layer.objects.active = ob
    for mname in ("subd", "disp", "solid"):
        bpy.ops.object.modifier_apply(modifier=mname)

garments = [tunic, breech_l, breech_r]

# ================= 3. САПОГИ ПО КОЛОДКЕ =======================================
def boot(side):
    ankle = J["ankle_" + side.lower()]
    # голенище: сечения голени с припуском
    shin_rings = []
    for t, pad in [(0.0, 0.014), (0.35, 0.013), (0.7, 0.011), (1.0, 0.010)]:
        z = (z_knee - 0.05) + (ankle.z + 0.01 - (z_knee - 0.05)) * t
        pts = [(v.x, v.y) for v in WORLD_V if abs(v.z - z) < 0.02
               and (v.x - ankle.x) ** 2 + (v.y - ankle.y) ** 2 < 0.012]
        cx = sum(p[0] for p in pts) / len(pts) if pts else ankle.x
        cy = sum(p[1] for p in pts) / len(pts) if pts else ankle.y
        r = max((math.hypot(p[0] - cx, p[1] - cy) for p in pts), default=0.05) + pad
        ring = []
        for i in range(16):
            a = i / 16 * 2 * math.pi
            ring.append((cx + math.cos(a) * r, cy + math.sin(a) * r, z))
        shin_rings.append(ring)
    shaft = loft(shin_rings, "bootshaft_" + side, leather_mat)
    # колодка стопы: heel→toe, сечения поперёк стопы, скруглённый нос
    toe_y = min(v.y for v in WORLD_V if v.z < 0.08 and abs(v.x - ankle.x) < 0.07) - 0.012
    heel_y = ankle.y + 0.055
    Lf = heel_y - toe_y
    foot_rings = []
    prof = [(0.0, 0.035, 0.052), (0.22, 0.048, 0.065), (0.5, 0.050, 0.056),
            (0.78, 0.047, 0.042), (0.95, 0.032, 0.030), (1.0, 0.012, 0.018)]
    for t, rx, rz in prof:
        y = heel_y - Lf * t
        ring = []
        for i in range(16):
            a = i / 16 * 2 * math.pi
            ring.append((ankle.x + math.cos(a) * rx, y, 0.012 + rz + math.sin(a) * rz))
        foot_rings.append(ring)
    last = loft(foot_rings, "bootlast_" + side, leather_mat, close_top=True, close_bottom=True)
    # подошва: плоская пластина по колодке
    sole_rings = []
    for zz in (0.0, 0.014):
        ring = []
        for i in range(16):
            a = i / 16 * 2 * math.pi
            ring.append((ankle.x + math.cos(a) * 0.054, (heel_y + toe_y) / 2 + math.sin(a) * (Lf / 2 + 0.006), zz))
        sole_rings.append(ring)
    sole = loft(sole_rings, "bootsole_" + side, leather_mat, close_top=True, close_bottom=True)
    return [shaft, last, sole]

boots = boot("L") + boot("R")

# ================= 4. ВОРОТНИК, РЕМЕНЬ, ФУРАЖКА, ДЕТАЛИ ======================
collar_rings = [section_ring(z_neck + dz, 0.006, bins=20, xlim=0.06, zslab=0.010)
                for dz in (0.020, 0.036, 0.052)]
collar = loft(collar_rings, "collar", red_mat)
so = collar.modifiers.new("solid", 'SOLIDIFY'); so.thickness = 0.006
bpy.context.view_layer.objects.active = collar
bpy.ops.object.modifier_apply(modifier="solid")

belt_rings = [section_ring(z_belt + dz, 0.008, bins=28, xlim=0.17, zslab=0.014)
              for dz in (-0.018, 0.018)]
belt = loft(belt_rings, "belt", belt_mat)
so = belt.modifiers.new("solid", 'SOLIDIFY'); so.thickness = 0.007
bpy.context.view_layer.objects.active = belt
bpy.ops.object.modifier_apply(modifier="solid")

extras = []
def prim(name, mat, bone="spine03"):
    o = bpy.context.active_object
    o.name = name
    o.data.materials.clear(); o.data.materials.append(mat)
    o["bind_bone"] = bone
    extras.append(o)
    return o

def front_y(z, dx=0.03):
    ys = [v.y for v in WORLD_V if abs(v.x) < dx and abs(v.z - z) < 0.02]
    return min(ys) if ys else -0.12

for i, z in enumerate(np.linspace(z_belt + 0.055, z_neck - 0.02, 6)):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.0085, segments=12, ring_count=8,
        location=(0.0, front_y(float(z)) - 0.030, float(z)))
    prim(f"button{i}", gold_mat)
bpy.ops.mesh.primitive_cube_add(size=1, location=(0.0, front_y(z_belt) - 0.028, z_belt))
bk = prim("buckle", gold_mat); bk.scale = (0.027, 0.006, 0.020)

for side, nm in [(1, "board_l"), (-1, "board_r")]:
    zs = [v.z for v in WORLD_V if abs(v.x - side * 0.105) < 0.02 and abs(v.y + 0.02) < 0.06
          and z_neck - 0.10 < v.z < z_neck + 0.02]
    ztop = max(zs) if zs else z_neck - 0.03
    bpy.ops.mesh.primitive_cube_add(size=1, location=(side * 0.105, -0.02, ztop + 0.016))
    b = prim(nm, gold_mat)
    b.scale = (0.052, 0.026, 0.006)
    b.rotation_euler = (0, side * 0.20, 0)

# фуражка по обмеру головы
hv0 = [v for v in WORLD_V if v.z > H0 - 0.26]
cx0 = sum(v.x for v in hv0) / len(hv0)
cy0 = sum(v.y for v in hv0) / len(hv0)
head_top = [v for v in WORLD_V if v.z > H0 - 0.085]
hw = max(abs(v.x - cx0) for v in head_top) + 0.004
hd = (max(v.y for v in head_top) - min(v.y for v in head_top)) / 2 + 0.004
cap_rings = []
for dz, k in [(-0.012, 1.00), (0.006, 1.05), (0.024, 1.10), (0.040, 1.02), (0.050, 0.72), (0.056, 0.3)]:
    ring = []
    for i in range(24):
        a = i / 24 * 2 * math.pi
        ring.append((cx0 + math.cos(a) * hw * k, cy0 + math.sin(a) * hd * 1.02 * k, H0 + dz))
    cap_rings.append(ring)
cap = loft(cap_rings, "cap_crown", cap_green, close_top=True)
cap["bind_bone"] = "head"; extras.append(cap)
band_rings = []
for dz in (-0.016, 0.012):
    ring = []
    for i in range(24):
        a = i / 24 * 2 * math.pi
        ring.append((cx0 + math.cos(a) * hw * 1.015, cy0 + math.sin(a) * hd * 1.03, H0 + dz))
    band_rings.append(ring)
band = loft(band_rings, "cap_band", red_mat)
band["bind_bone"] = "head"; extras.append(band)
so = band.modifiers.new("solid", 'SOLIDIFY'); so.thickness = 0.005
bpy.context.view_layer.objects.active = band
bpy.ops.object.modifier_apply(modifier="solid")
# козырёк: дуга-пластина вперёд
bmv = bmesh.new()
rows = []
for rr in (0.0, 0.062):
    row = []
    for i in range(13):
        a = math.pi * (0.18 + 0.64 * i / 12)          # сектор спереди
        px = cx0 + math.cos(a + math.pi / 2 * 0 - math.pi / 2) * 0  # заглушка
        row.append(None)
    rows.append(row)
bmv.free()
# строим козырёк проще: два кольцевых сегмента (внутренний у околыша, внешний вперёд)
vis_rows = []
for rr, drop in ((0.0, 0.0), (0.065, 0.020)):
    row = []
    for i in range(13):
        t = i / 12.0
        a = -math.pi / 2 + (t - 0.5) * 1.7            # сектор вокруг лица (-Y)
        row.append((cx0 + math.sin(a) * (hw * 1.015 + rr),
                    cy0 - math.cos(a) * (hd * 1.03 + rr),
                    H0 - 0.014 - drop))
    vis_rows.append(row)
bmv = bmesh.new()
r0 = [bmv.verts.new(p) for p in vis_rows[0]]
r1 = [bmv.verts.new(p) for p in vis_rows[1]]
for i in range(12):
    bmv.faces.new((r0[i], r0[i + 1], r1[i + 1], r1[i]))
for f in bmv.faces:
    f.smooth = True
vme = bpy.data.meshes.new("cap_visor")
bmv.to_mesh(vme); bmv.free()
visor = bpy.data.objects.new("cap_visor", vme)
bpy.context.collection.objects.link(visor)
visor.data.materials.append(dark_mat)
so = visor.modifiers.new("solid", 'SOLIDIFY'); so.thickness = 0.004
bpy.context.view_layer.objects.active = visor
bpy.ops.object.modifier_apply(modifier="solid")
visor["bind_bone"] = "head"; extras.append(visor)
bpy.ops.mesh.primitive_cylinder_add(radius=0.008, depth=0.006, vertices=12,
    location=(cx0, cy0 - hd * 1.06, H0 - 0.002))
ck = prim("cockade", gold_mat, "head")
ck.rotation_euler = (math.pi / 2, 0, 0)

# ================= 5. ТЕЛО: сглаживание сеткой (после симуляции) =============
bpy.ops.object.select_all(action='DESELECT')
mesh.select_set(True)
bpy.context.view_layer.objects.active = mesh
if mesh.data.shape_keys:                     # таргеты MPFB — запечь в базовую сетку
    bpy.ops.object.shape_key_remove(all=True, apply_mix=True)
sub = mesh.modifiers.new("subd", 'SUBSURF'); sub.levels = 1; sub.render_levels = 1
bpy.ops.object.modifier_apply(modifier="subd")
WORLD_V = [mw @ v.co for v in mesh.data.vertices]
print("BODY SUBDIVIDED:", len(mesh.data.vertices))

# волосы + брови оболочкой по подразделённой голове (аккуратные)
def shell(name, face_filter, thickness, material, grow=0):
    bpy.ops.object.select_all(action='DESELECT')
    mesh.select_set(True)
    bpy.context.view_layer.objects.active = mesh
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='FACE')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')
    cnt = 0
    for poly in mesh.data.polygons:
        c = mw @ poly.center
        if face_filter(c):
            poly.select = True; cnt += 1
    if cnt == 0:
        return None
    bpy.ops.object.mode_set(mode='EDIT')
    for _ in range(grow):
        bpy.ops.mesh.select_more()
    bpy.ops.mesh.duplicate()
    bpy.ops.mesh.separate(type='SELECTED')
    bpy.ops.object.mode_set(mode='OBJECT')
    sh = [o for o in bpy.context.selected_objects if o != mesh][-1]
    sh.name = name
    so2 = sh.modifiers.new("solid", 'SOLIDIFY'); so2.thickness = thickness; so2.offset = 1.0
    sh.data.materials.clear(); sh.data.materials.append(material)
    return sh

if eyes_obj is not None:
    _e = [eyes_obj.matrix_world @ mathutils.Vector(c) for c in eyes_obj.bound_box]
    z_eyes = sum(v.z for v in _e) / 8.0
else:
    z_eyes = H0 - 0.125
zb0 = z_eyes + 0.024
zn0 = z_eyes - 0.045
zm0 = z_eyes - 0.078
nose_ys = [v.y for v in hv0 if abs(v.x - cx0) < 0.012 and abs(v.z - zn0) < 0.012]
nose_y = min(nose_ys) if nose_ys else cy0 - 0.11

def hair_filter(c):
    if c.y < cy0 - 0.02:
        return c.z > H0 - 0.048
    if c.y > cy0 + 0.02:
        return c.z > H0 - 0.165
    return c.z > H0 - 0.088

hair = shell("hair", hair_filter, 0.010, hair_mat, grow=1)
brows = shell("brows",
    lambda c: (c.y < cy0 - 0.025) and (zb0 - 0.004 < c.z < zb0 + 0.007) and 0.014 < abs(c.x - cx0) < 0.042,
    0.004, hair_mat)

# --- РУКАВА: крой от поверхности руки (наследуют правильные веса скелета) ---
xw = abs(J["wrist_l"].x)
sleeve_l = shell("sleeve_l",
    lambda c: c.z > z_hem and 0.15 <= c.x < xw - 0.015, 0.006, green, grow=1)
sleeve_r = shell("sleeve_r",
    lambda c: c.z > z_hem and -(xw - 0.015) < c.x <= -0.15, 0.006, green, grow=1)

def bisect_obj(obj, plane_co, plane_no):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.bisect(plane_co=plane_co, plane_no=plane_no,
                        use_fill=False, clear_inner=False, clear_outer=True)
    bpy.ops.object.mode_set(mode='OBJECT')

for sv, shj, wrj in ((sleeve_l, J["shoulder_l"], J["wrist_l"]),
                     (sleeve_r, J["shoulder_r"], J["wrist_r"])):
    if sv is None:
        continue
    axl = (wrj - shj).normalized()
    bisect_obj(sv, tuple(wrj - axl * 0.02), tuple(axl))    # ровный конец рукава
    dpm = sv.modifiers.new("disp", 'DISPLACE')
    dpm.texture = fold_tex; dpm.strength = 0.0035; dpm.mid_level = 0.5
    bpy.context.view_layer.objects.active = sv
    bpy.ops.object.modifier_apply(modifier="disp")

# усы: изогнутая труба-«подкова» под носом (одним куском, не шарики)
must_pts = []
for i in range(9):
    t = i / 8.0
    a = math.pi * (0.18 + 0.64 * t)
    mx = cx0 + math.cos(a) * 0.024
    mz = zn0 - 0.009 - 0.006 * abs(math.cos(a))
    face_ys = [v.y for v in hv0 if abs(v.x - mx) < 0.012 and abs(v.z - mz) < 0.01]
    my = (min(face_ys) if face_ys else nose_y + 0.01) - 0.002
    must_pts.append((mx, my, mz))
crv = bpy.data.curves.new("mustache", 'CURVE')
crv.dimensions = '3D'
sp = crv.splines.new('NURBS')
sp.points.add(len(must_pts) - 1)
for i, p in enumerate(must_pts):
    sp.points[i].co = (*p, 1.0)
sp.use_endpoint_u = True
crv.bevel_depth = 0.0068
crv.bevel_resolution = 3
must = bpy.data.objects.new("mustache", crv)
bpy.context.collection.objects.link(must)
bpy.ops.object.select_all(action='DESELECT')
must.select_set(True)
bpy.context.view_layer.objects.active = must
bpy.ops.object.convert(target='MESH')
must = bpy.context.active_object
must.data.materials.append(hair_mat)
must["bind_bone"] = "head"; extras.append(must)

# ================= 6. КОЖА: анатомические зоны + SSS ==========================
TS = 2048
smat = bpy.data.materials.new("SkinMat")
smat.use_nodes = True
tn = smat.node_tree.nodes.new("ShaderNodeTexImage")
smat.node_tree.nodes.active = tn
mesh.data.materials.clear()
mesh.data.materials.append(smat)
bpy.ops.object.select_all(action='DESELECT')
mesh.select_set(True)
bpy.context.view_layer.objects.active = mesh
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.normals_make_consistent(inside=False)
bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.02)
bpy.ops.object.mode_set(mode='OBJECT')
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 24
scene.render.bake.margin = 2   # иначе margin размазывает зоны через швы UV-островов
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

alb = np.tile(np.array([0.845, 0.660, 0.555], np.float32), (P.shape[0], 1))
mott = fbm_uv(96, 3, 77)
alb[:, 0] *= 0.965 + 0.075 * mott
alb[:, 1] *= 0.975 + 0.05 * mott
alb[:, 2] *= 0.985 + 0.03 * mott
# подкожная краснота — ЕДВА заметная (иначе читается как грязь на коже)
RED = np.array([0.055, -0.008, -0.018], np.float32)
def add_red(mask, k):
    global alb
    alb = alb + RED[None, :] * (mask * k)[:, None]
add_red(sph((cx0 - 0.046, cy0 - 0.038, zn0 + 0.008), 0.038, 0.05), 0.35)
add_red(sph((cx0 + 0.046, cy0 - 0.038, zn0 + 0.008), 0.038, 0.05), 0.35)
add_red(sph((cx0, nose_y + 0.006, zn0 - 0.004), 0.014, 0.02), 0.25)
ear_xs = [abs(v.x - cx0) for v in hv0 if abs(v.z - (zn0 + 0.02)) < 0.02]
ear_x = max(ear_xs) if ear_xs else 0.075
add_red(sph((cx0 - ear_x, cy0 + 0.008, zn0 + 0.02), 0.024, 0.03), 0.3)
add_red(sph((cx0 + ear_x, cy0 + 0.008, zn0 + 0.02), 0.024, 0.03), 0.3)
for jn, rr, kk in [("wrist_l", 0.08, 0.18), ("wrist_r", 0.08, 0.18),
                   ("knee_l", 0.08, 0.18), ("knee_r", 0.08, 0.18)]:
    add_red(sph(tuple(J[jn]), rr, 0.07), kk)
lips = band(zm0 - 0.008, zm0 + 0.010, 0.006) * front * (np.abs(P[:, 0] - cx0) < 0.028)
lip_col = np.array([0.70, 0.34, 0.32], np.float32)
alb = alb * (1 - (lips * 0.55)[:, None]) + lip_col[None, :] * (lips * 0.55)[:, None]
beard = band(zm0 - 0.075, zm0 + 0.010, 0.012) * front * (np.abs(P[:, 0] - cx0) < 0.062) * (1 - lips)
grey = np.array([0.62, 0.63, 0.68], np.float32)
alb = alb * (1 - (beard * 0.09)[:, None]) + (alb * grey[None, :]) * (beard * 0.09)[:, None]
alb = alb * (0.82 + 0.18 * ao)[:, None]
px4 = np.ones((P.shape[0], 4), np.float32)
px4[:, :3] = np.clip(alb, 0, 1)
skin_img = bpy.data.images.new("skin_final", TS, TS)
skin_img.pixels.foreach_set(px4.reshape(-1))
skin_img.filepath_raw = os.path.join(OUT, "nicholas_skin.png")
skin_img.file_format = 'PNG'
skin_img.save()
rgh = np.full(P.shape[0], 0.56, np.float32)
tz = band(zb0 - 0.01, H0 - 0.055, 0.01) * front
rgh = rgh - 0.12 * tz - 0.2 * lips + 0.05 * (mott - 0.5)
rpx = np.ones((P.shape[0], 4), np.float32)
rpx[:, 0] = rpx[:, 1] = rpx[:, 2] = np.clip(rgh, 0.2, 0.9)
rgh_img = bpy.data.images.new("skin_rough", TS, TS)
rgh_img.pixels.foreach_set(rpx.reshape(-1))
pore_h = fbm_uv(512, 2, 41).reshape(TS, TS)
gy, gx = np.gradient(pore_h)
nx, ny, nz = -gx * 1.4, -gy * 1.4, np.ones_like(pore_h)
ln = np.sqrt(nx * nx + ny * ny + nz * nz)
npx = np.stack([nx / ln, ny / ln, nz / ln], -1) * 0.5 + 0.5
npx4 = np.concatenate([npx.astype(np.float32), np.ones((TS, TS, 1), np.float32)], -1)
pore_img = bpy.data.images.new("skin_pore", TS, TS)
pore_img.pixels.foreach_set(npx4.reshape(-1))
for n in list(smat.node_tree.nodes):
    if n.type != 'OUTPUT_MATERIAL':
        smat.node_tree.nodes.remove(n)
out_n = [n for n in smat.node_tree.nodes if n.type == 'OUTPUT_MATERIAL'][0]
bsdf = smat.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
ti = smat.node_tree.nodes.new("ShaderNodeTexImage"); ti.image = skin_img
smat.node_tree.links.new(ti.outputs["Color"], bsdf.inputs["Base Color"])
tr2 = smat.node_tree.nodes.new("ShaderNodeTexImage"); tr2.image = rgh_img
tr2.image.colorspace_settings.name = 'Non-Color'
smat.node_tree.links.new(tr2.outputs["Color"], bsdf.inputs["Roughness"])
tp = smat.node_tree.nodes.new("ShaderNodeTexImage"); tp.image = pore_img
tp.image.colorspace_settings.name = 'Non-Color'
nmn = smat.node_tree.nodes.new("ShaderNodeNormalMap")
nmn.inputs["Strength"].default_value = 0.4
smat.node_tree.links.new(tp.outputs["Color"], nmn.inputs["Color"])
smat.node_tree.links.new(nmn.outputs["Normal"], bsdf.inputs["Normal"])
# ПОДПОВЕРХНОСТНОЕ РАССЕИВАНИЕ — «живая» кожа, не пластик
for key, val in [("Subsurface Weight", 0.10)]:
    if key in bsdf.inputs:
        bsdf.inputs[key].default_value = val
if "Subsurface Radius" in bsdf.inputs:
    bsdf.inputs["Subsurface Radius"].default_value = (0.46, 0.17, 0.09)
if "Subsurface Scale" in bsdf.inputs:
    bsdf.inputs["Subsurface Scale"].default_value = 0.012
smat.node_tree.links.new(bsdf.outputs["BSDF"], out_n.inputs["Surface"])
print("SKIN V2 DONE")

# глаза
eye_img = bpy.data.images.load(os.path.join(MH_DATA, "eyes", "materials", "brown_eye.png"))
ep = np.array(eye_img.pixels[:]).reshape(-1, 4)
r, g, b = ep[:, 0], ep[:, 1], ep[:, 2]
mask = (r > b * 1.05) & (r > 0.08) & (r < 0.9)
lum = (r + g + b) / 3.0
ep[mask, 0] = lum[mask] * 0.62
ep[mask, 1] = lum[mask] * 0.80
ep[mask, 2] = lum[mask] * 1.00
eye_img.pixels = ep.ravel().tolist()
eye_img.filepath_raw = os.path.join(OUT, "nicholas_eyes.png")
eye_img.file_format = 'PNG'
eye_img.save()
if eyes_obj is not None:
    emat = bpy.data.materials.new("EyeMat")
    emat.use_nodes = True
    eb = emat.node_tree.nodes["Principled BSDF"]
    et = emat.node_tree.nodes.new("ShaderNodeTexImage")
    et.image = eye_img
    emat.node_tree.links.new(et.outputs["Color"], eb.inputs["Base Color"])
    eb.inputs["Roughness"].default_value = 0.12
    eyes_obj.data.materials.clear()
    eyes_obj.data.materials.append(emat)

# ================= 7. ПРИВЯЗКА К СКЕЛЕТУ ======================================
def transfer_weights(dst):
    dt = dst.modifiers.new("dt", 'DATA_TRANSFER')
    dt.object = mesh
    dt.use_vert_data = True
    dt.data_types_verts = {'VGROUP_WEIGHTS'}
    dt.vert_mapping = 'NEAREST'
    bpy.context.view_layer.objects.active = dst
    bpy.ops.object.datalayout_transfer(modifier="dt")
    bpy.ops.object.modifier_apply(modifier="dt")

def bind(obj, solo_bone=None):
    if solo_bone is not None:
        vg = obj.vertex_groups.get(solo_bone) or obj.vertex_groups.new(name=solo_bone)
        vg.add(range(len(obj.data.vertices)), 1.0, 'REPLACE')
    if not any(m.type == 'ARMATURE' for m in obj.modifiers):
        am = obj.modifiers.new("arm", 'ARMATURE')
        am.object = arm_rig

for ob in garments + boots + [collar, belt]:
    transfer_weights(ob)
    bind(ob)
# оболочки-крои уже унаследовали веса тела — только модификатор
for ob in [s for s in (hair, brows, sleeve_l, sleeve_r) if s]:
    bind(ob)
for ob in (cuff_l, cuff_r):
    bind(ob, solo_bone=str(ob.get("bind_bone", "spine03")))
if eyes_obj is not None:
    bind(eyes_obj, solo_bone="head")
for ob in extras:
    bind(ob, solo_bone=str(ob.get("bind_bone", "spine03")))

# ================= 8. НОРМИРОВКА РОСТА 1.70 ==================================
H_body = max((mesh.matrix_world @ v.co).z for v in mesh.data.vertices)
s_norm = 1.70 / H_body
all_exp = [mesh, arm_rig, eyes_obj] + garments + boots + [collar, belt, cuff_l, cuff_r] + extras \
    + [s for s in (hair, brows, sleeve_l, sleeve_r) if s]
bpy.ops.object.select_all(action='DESELECT')
for o in all_exp:
    if o is None:
        continue
    o.location = [c * s_norm for c in o.location]
    o.scale = [c * s_norm for c in o.scale]
    o.select_set(True)
bpy.context.view_layer.objects.active = arm_rig
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
print("HEIGHT ->", 1.70)

# ================= 9. АНИМАЦИИ (автопроба осей) ==============================
def probe_axis(bone, marker, want):
    pb = arm_rig.pose.bones[bone]
    mk = arm_rig.pose.bones[marker]
    pb.rotation_mode = 'XYZ'
    best = (0, 1, -1e9)
    for axis in range(3):
        for sign in (1, -1):
            pb.rotation_euler = (0, 0, 0)
            bpy.context.view_layer.update()
            before = (arm_rig.matrix_world @ mk.tail).copy()
            e = [0.0, 0.0, 0.0]; e[axis] = sign * 0.5
            pb.rotation_euler = e
            bpy.context.view_layer.update()
            after = (arm_rig.matrix_world @ mk.tail).copy()
            score = (after - before).dot(mathutils.Vector(want))
            if score > best[2]:
                best = (axis, sign, score)
    pb.rotation_euler = (0, 0, 0)
    bpy.context.view_layer.update()
    return best

FWD = (0, -1, 0); DOWN = (0, 0, -1); BACK = (0, 1, 0)
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
ax_foot_L = probe_axis("foot.L", "foot.L", (0, -0.6, -0.8))
ax_foot_R = probe_axis("foot.R", "foot.R", (0, -0.6, -0.8))

def probe_root_up():
    pb = arm_rig.pose.bones["root"]
    best = (1, 1, -1e9)
    for axis in range(3):
        for sign in (1, -1):
            pb.location = (0, 0, 0)
            bpy.context.view_layer.update()
            before = (arm_rig.matrix_world @ pb.head).z
            l = [0.0, 0.0, 0.0]; l[axis] = sign * 0.05
            pb.location = l
            bpy.context.view_layer.update()
            best = max(best, (axis, sign, (arm_rig.matrix_world @ pb.head).z - before),
                       key=lambda t: t[2])
    pb.location = (0, 0, 0)
    bpy.context.view_layer.update()
    return best

ax_root_up = probe_root_up()

def euler_for(*components):
    e = [0.0, 0.0, 0.0]
    for (axis, sign, _), ang in components:
        e[axis] += sign * ang
    return tuple(e)

ARMS_DOWN = 0.85
ELBOW_REST = 0.28
TAU = 2 * math.pi

def make_action(name, frames_poses):
    act = bpy.data.actions.new(name)
    if arm_rig.animation_data is None:
        arm_rig.animation_data_create()
    arm_rig.animation_data.action = act
    for frame, poses in frames_poses:
        scene.frame_set(frame)
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
    s = math.sin(phase * TAU)
    sw = 0.48 * s
    kneeL = 0.10 + 0.72 * max(0.0, math.sin((phase + 0.70) * TAU))
    kneeR = 0.10 + 0.72 * max(0.0, math.sin((phase + 0.20) * TAU))
    footL = -0.30 * math.sin((phase + 0.55) * TAU) - 0.08
    footR = -0.30 * math.sin((phase + 0.05) * TAU) - 0.08
    arm = 0.32 * s
    elbL = ELBOW_REST + 0.20 * max(0.0, -s)
    elbR = ELBOW_REST + 0.20 * max(0.0, s)
    return {
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
        "__bob": -0.022 * (0.5 + 0.5 * math.cos(phase * 2 * TAU)),
    }

walk = make_action("walk", [(1 + i * 2, walk_pose(i / 12.0)) for i in range(13)])

def idle_pose(t):
    b = 0.5 + 0.5 * math.sin(t * TAU)
    return {
        "upperarm01.L": euler_for((ax_down_L, ARMS_DOWN - 0.015 * b)),
        "upperarm01.R": euler_for((ax_down_R, ARMS_DOWN - 0.015 * b)),
        "lowerarm01.L": euler_for((ax_elb_L, ELBOW_REST)),
        "lowerarm01.R": euler_for((ax_elb_R, ELBOW_REST)),
        "lowerleg01.L": euler_for((ax_knee_L, 0.04)),
        "lowerleg01.R": euler_for((ax_knee_R, 0.04)),
        "__bob": -0.003 * b,
    }

idle = make_action("idle", [(1 + i * 12, idle_pose(i / 4.0)) for i in range(5)])

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

jump = make_action("jump", [
    (1, jump_pose(0.0, 0.06, 0.0, 0.0, 0.0)),
    (5, jump_pose(0.55, 1.05, -0.25, -0.30, -0.11)),
    (9, jump_pose(-0.12, 0.06, 0.35, 0.20, 0.02)),
    (14, jump_pose(0.25, 0.55, 0.0, 0.05, -0.03)),
    (19, jump_pose(0.0, 0.06, 0.0, 0.0, 0.0)),
])

arm_rig.animation_data.action = None
for act in (idle, walk, jump):
    tr = arm_rig.animation_data.nla_tracks.new()
    tr.name = act.name
    strip = tr.strips.new(act.name, 1, act)
    strip.name = act.name
scene.render.fps = 24

# shape keys в базовую сетку
for o in [x for x in all_exp if x is not None and x.type == 'MESH']:
    if o.data.shape_keys:
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.shape_key_remove(all=True, apply_mix=True)

# ================= 10. ЭКСПОРТ ================================================
uni_set = [mesh, eyes_obj] + garments + boots + [collar, belt, cuff_l, cuff_r] + extras \
    + [s for s in (hair, brows, sleeve_l, sleeve_r) if s]
uni_set = [o for o in uni_set if o is not None]
body_set = [o for o in [mesh, eyes_obj, hair, brows] if o is not None]
keep = {o.name for o in uni_set + body_set}
for o in list(bpy.data.objects):
    if o.type == 'MESH' and o.name not in keep:
        bpy.data.objects.remove(o, do_unlink=True)

def export_glb(objects, path):
    bpy.ops.object.select_all(action='DESELECT')
    for o in objects:
        o.select_set(True)
    arm_rig.select_set(True)
    bpy.context.view_layer.objects.active = arm_rig
    bpy.ops.export_scene.gltf(filepath=path, export_format='GLB',
                              use_selection=True, export_animations=True,
                              export_animation_mode='NLA_TRACKS',
                              export_apply=True, export_yup=True)
    print("GLB EXPORTED", path)

export_glb(uni_set, os.path.join(OUT, "nicholas_uniform.glb"))
export_glb(body_set, os.path.join(OUT, "nicholas_body.glb"))
print("DONE V2")
