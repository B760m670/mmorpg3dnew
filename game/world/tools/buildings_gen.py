#!/usr/bin/env python3
# Здания Гатчины — каждое отдельным GLB (реальная геометрия, эпоха ~1894).
# Дворец, Приорат, собор, обелиск Коннетабль, вокзал, типовые дома.
import bpy, bmesh, math, os, sys
import numpy as np

ARGS = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
ROOT = ARGS[0] if ARGS else "/home/user/mmorpg3dnew"
OUT = os.path.join(ROOT, "game/world/buildings")
os.makedirs(OUT, exist_ok=True)

def clear():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)

def mat(name, rgb, rough=0.85, metal=0.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    return m

M = dict(
    stone=mat("stone", (0.64, 0.60, 0.48), 0.9),      # пудостский известняк — тёплый серо-жёлтый
    plinth=mat("plinth", (0.38, 0.36, 0.33), 0.9),
    roof=mat("roof", (0.16, 0.30, 0.25), 0.55, 0.2),
    roof_red=mat("roof_red", (0.46, 0.20, 0.15), 0.7),
    gold=mat("gold", (0.80, 0.62, 0.18), 0.30, 1.0),
    green_dome=mat("green_dome", (0.14, 0.36, 0.27), 0.5, 0.1),
    glass=mat("glass", (0.09, 0.12, 0.17), 0.12, 0.0),
    brick=mat("brick", (0.48, 0.26, 0.21), 0.85),
    ochre=mat("ochre", (0.74, 0.60, 0.36), 0.85),
    white=mat("white", (0.76, 0.74, 0.68), 0.85),
    wood=mat("wood", (0.30, 0.21, 0.14), 0.8),
    cross=mat("cross", (0.88, 0.72, 0.28), 0.3, 1.0),
)

_objs = []
def box(cx, cy, cz, sx, sy, sz, material, name="box"):
    m = bpy.data.meshes.new(name); o = bpy.data.objects.new(name, m)
    bpy.context.collection.objects.link(o)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= sx; v.co.y *= sy; v.co.z *= sz
    bm.to_mesh(m); bm.free()
    o.location = (cx, cy, cz)
    o.data.materials.append(material)
    _objs.append(o); return o

def cyl(cx, cy, cz, r, h, material, name="cyl", verts=24, r2=None):
    m = bpy.data.meshes.new(name); o = bpy.data.objects.new(name, m)
    bpy.context.collection.objects.link(o)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=verts,
        radius1=r, radius2=(r if r2 is None else r2), depth=h)
    bm.to_mesh(m); bm.free()
    o.location = (cx, cy, cz)
    o.data.materials.append(material)
    _objs.append(o); return o

def dome(cx, cy, cz, r, material, name="dome"):
    # луковичная главка: сфера, приплюснутая снизу, с вытянутым верхом
    m = bpy.data.meshes.new(name); o = bpy.data.objects.new(name, m)
    bpy.context.collection.objects.link(o)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=20, v_segments=16, radius=r)
    for v in bm.verts:
        z = v.co.z
        if z < 0: v.co.z = z*0.3          # приплюснуть низ
        else:
            k = (z/r)
            v.co.x *= (1.0-0.35*k); v.co.y *= (1.0-0.35*k)  # заострить верх (лук)
            v.co.z = z*1.35
    bm.to_mesh(m); bm.free()
    o.location = (cx, cy, cz)
    o.data.materials.append(material)
    _objs.append(o); return o

def facade_windows(cx, cy, base_z, length, floors, floor_h, depth_y, spacing, material, along_x=True):
    n = max(int(length/spacing), 1)
    for f in range(floors):
        z = base_z + floor_h*0.6 + f*floor_h
        for i in range(n):
            t = (i+0.5)/n
            pos = -length/2 + t*length
            if along_x:
                box(cx+pos, cy, z, spacing*0.4, depth_y, floor_h*0.55, material, "win")
            else:
                box(cx, cy+pos, z, depth_y, spacing*0.4, floor_h*0.55, material, "win")

def export(name):
    global _objs
    for o in bpy.context.selected_objects: o.select_set(False)
    for o in _objs: o.select_set(True)
    if _objs: bpy.context.view_layer.objects.active = _objs[0]
    path = os.path.join(OUT, name)
    bpy.ops.export_scene.gltf(filepath=path, use_selection=True,
        export_format='GLB', export_yup=True, export_apply=True)
    print("[bld] ->", path, "(", len(_objs), "parts )")
    _objs = []
    clear()

# ---------- Большой Гатчинский дворец ----------
# Дворец вынесен в отдельный детальный генератор palace_gen.py (настоящие
# PBR-материалы, наличники, карниз, балюстрада, башни, портик). Здесь не строим.

# ---------- Приоратский дворец ----------
# землебитный корпус, красная черепичная кровля, высокая башня-каланча со шпилем
clear()
box(0, 0, 5.0, 20.0, 14.0, 10.0, M["ochre"], "corps")
box(0, 0, 10.6, 20.4, 14.4, 1.4, M["roof_red"], "cornice")
box(0, 0, 12.5, 18.0, 12.0, 3.0, M["roof_red"], "roof")       # скат упрощён
box(-6, 8, 4.0, 8.0, 6.0, 8.0, M["white"], "annex")
# башня-каланча
cyl(9, -4, 12.0, 3.2, 24.0, M["white"], "tower", verts=16)
cyl(9, -4, 24.2, 3.0, 1.0, M["brick"], "tower_ring", verts=16)
cyl(9, -4, 30.0, 3.0, 10.0, M["roof_red"], "spire", verts=16, r2=0.1)  # шпиль
export("priory.glb")

# ---------- Собор Святого апостола Павла ----------
# пятиглавый, русско-византийский, с колокольней; охристые стены, золочёные главы
clear()
box(0, 0, 9.0, 24.0, 34.0, 18.0, M["ochre"], "nave")
box(0, 0, 18.6, 24.4, 34.4, 1.2, M["stone"], "cornice")
# закомары/аттик
box(0, 0, 20.0, 22.0, 32.0, 3.0, M["ochre"], "attic")
facade_windows(0, 17.2, 4, 30, 2, 6.5, 0.4, 5.0, M["glass"], along_x=True)
facade_windows(12.2, 0, 4, 26, 2, 6.5, 0.4, 5.0, M["glass"], along_x=False)
facade_windows(-12.2, 0, 4, 26, 2, 6.5, 0.4, 5.0, M["glass"], along_x=False)
# центральный барабан + большая глава
cyl(0, 0, 24.0, 7.0, 10.0, M["ochre"], "drum", verts=16)
dome(0, 0, 30.0, 8.0, M["gold"], "dome_c")
cyl(0, 0, 40.0, 0.4, 4.0, M["cross"], "cross_c", verts=6, r2=0.2)
box(0, 0, 43.0, 2.0, 0.3, 0.3, M["cross"], "cross_bar")
# четыре малые главы по углам
for dx, dy in [(8, 11), (-8, 11), (8, -11), (-8, -11)]:
    cyl(dx, dy, 21.0, 2.6, 6.0, M["ochre"], "drum_s", verts=12)
    dome(dx, dy, 25.0, 3.0, M["gold"], "dome_s")
# колокольня над западным входом
box(0, -20, 14.0, 9.0, 9.0, 28.0, M["ochre"], "belltower")
cyl(0, -20, 29.0, 4.0, 5.0, M["ochre"], "bell_drum", verts=12)
dome(0, -20, 33.5, 4.5, M["gold"], "bell_dome")
export("cathedral.glb")

# ---------- Обелиск Коннетабль ----------
clear()
box(0, 0, 2.0, 9.0, 9.0, 4.0, M["plinth"], "base")
box(0, 0, 5.0, 6.0, 6.0, 2.5, M["stone"], "pedestal")
cyl(0, 0, 18.0, 1.6, 24.0, M["stone"], "shaft", verts=4, r2=0.5)  # четырёхгранный сужающийся
cyl(0, 0, 30.6, 0.6, 2.0, M["gold"], "cap", verts=4, r2=0.05)
export("connetable.glb")

# ---------- Балтийский вокзал ----------
clear()
box(0, 0, 5.0, 60.0, 16.0, 10.0, M["brick"], "hall")
box(0, 0, 10.6, 60.4, 16.4, 1.4, M["stone"], "cornice")
box(0, 0, 12.5, 58.0, 14.0, 3.0, M["roof"], "roof")
box(0, 0, 8.0, 12.0, 17.0, 14.0, M["brick"], "clocktower")   # центральный ризалит с часами
box(0, 8.6, 12.0, 3.0, 0.4, 3.0, M["stone"], "clock")
facade_windows(0, 8.2, 2, 56, 2, 4.5, 0.4, 5.0, M["glass"])
box(0, -9.0, 4.0, 56.0, 3.0, 6.0, M["stone"], "platform_canopy")  # навес перрона
export("station.glb")

# ---------- Типовые дома (3 варианта) ----------
def house(name, wall_mat, roof_mat, wx, wy, floors):
    clear()
    h = floors*3.6
    box(0, 0, h/2, wx, wy, h, wall_mat, "walls")
    box(0, 0, h+0.9, wx+0.6, wy+0.6, 1.8, roof_mat, "roof")   # двускатная упрощённо
    box(0, 0, h+2.2, wx*0.7, wy*0.7, 1.2, roof_mat, "ridge")
    facade_windows(0, wy/2+0.1, 0, wx*0.85, floors, 3.6, 0.3, 3.2, M["glass"])
    facade_windows(0, -wy/2-0.1, 0, wx*0.85, floors, 3.6, 0.3, 3.2, M["glass"])
    box(0, wy/2+0.2, 1.6, 1.4, 0.4, 3.2, M["wood"], "door")
    export(name)

house("house_a.glb", M["ochre"], M["roof_red"], 14, 10, 2)
house("house_b.glb", M["stone"], M["roof"], 12, 9, 2)
house("house_c.glb", M["brick"], M["roof_red"], 16, 11, 3)
print("[bld] done")
