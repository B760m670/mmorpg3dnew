#!/usr/bin/env python3
"""РАСТЕНИЯ — геометрия из ботаники (Blender/bpy).

ЧЕМ ЭТО ОТЛИЧАЕТСЯ ОТ ПРОШЛОЙ ТРАВЫ. Прошлая была «лезвие = плоский
треугольник, 7 штук в кусте». Здесь каждый вид строится из СВОИХ чисел
(tools/vegetation.py): высота побега в июне, ширина листа, сколько побегов
даёт дернина, тип роста. Злак — узкие изогнутые листья от корня и соцветие
сверху; разнотравье — стебель с широкими листьями и цветок; кустарничек —
одревесневшая веточка с мелкими листьями; папоротник — вайя с перьями.
Форма берётся из habit вида, а не одна на всех.

ЧЕСТНО ПРО ЛИСТ. Лист злака — изогнутая сужающаяся лента из 5 сегментов
(дуга, а не прямой треугольник): у настоящего листа есть перегиб, и именно он
читается вблизи. Ширина ленты — leaf_mm из ботаники, длина — h_cm.

ВЫХОД: game2/assets/plants/<латинское имя>.glb (по модели на вид) и общий
лист-превью, чтобы СНАЧАЛА посмотреть на растения, а потом уже сеять их.

Запуск: python3 tools/build_plants.py [--only Phleum] [--no-preview]
"""
import json
import math
import os
import random
import sys

import bpy
import mathutils

ROOT = os.path.join(os.path.dirname(__file__), "..")
VEG = os.path.join(ROOT, "game2", "data", "real", "vegetation.json")
OUTDIR = os.path.join(ROOT, "game2", "assets", "plants")
PREVIEW = os.path.join(ROOT, "plants_preview.png")

SEG_BLADE = 5          # сегментов в листе злака: меньше — лист ломается углом
SEG_LEAF = 3           # сегментов в широком листе разнотравья


def clear():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def mesh_from(name, verts, faces):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate()
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    return ob


def blade(length, width, lean, twist, curve, segs=SEG_BLADE):
    """Изогнутый сужающийся лист. Дуга в вертикальной плоскости, повёрнутая
    на azimuth; кончик уходит вниз тем сильнее, чем длиннее лист — так лист
    и ведёт себя под своим весом."""
    verts, faces = [], []
    for i in range(segs + 1):
        t = i / segs
        # дуга: подъём замедляется, кончик отгибается наружу и вниз
        rise = math.sin(t * math.pi * 0.5)
        out = (1.0 - math.cos(t * math.pi * 0.5)) * curve
        y = length * rise * math.cos(lean)
        r = length * (out + math.sin(lean) * t)
        x = r * math.cos(twist)
        z = r * math.sin(twist)
        w = width * (1.0 - t * 0.92) * 0.5      # сужение к кончику
        # ширина откладывается поперёк направления роста
        px, pz = -math.sin(twist) * w, math.cos(twist) * w
        verts.append((x - px, y, z - pz))
        verts.append((x + px, y, z + pz))
    for i in range(segs):
        a = i * 2
        faces.append((a, a + 1, a + 3, a + 2))
    return verts, faces


def broad_leaf(length, width, angle, twist):
    """Широкий лист разнотравья: ланцет с черешком."""
    verts, faces = [], []
    for i in range(SEG_LEAF + 1):
        t = i / SEG_LEAF
        y = length * math.sin(angle) * t + length * 0.25 * math.sin(t * math.pi) * 0.4
        r = length * math.cos(angle) * t
        x = r * math.cos(twist)
        z = r * math.sin(twist)
        w = width * math.sin(max(t, 0.06) * math.pi) * 0.5   # шире в середине
        px, pz = -math.sin(twist) * w, math.cos(twist) * w
        verts.append((x - px, y, z - pz))
        verts.append((x + px, y, z + pz))
    for i in range(SEG_LEAF):
        a = i * 2
        faces.append((a, a + 1, a + 3, a + 2))
    return verts, faces


def stem(height, thick, tilt, twist):
    """Стебель: узкая лента (две грани крест-накрест дали бы вдвое больше
    треугольников без выигрыша на таком масштабе)."""
    verts, faces = [], []
    segs = 3
    for i in range(segs + 1):
        t = i / segs
        y = height * t
        r = height * math.sin(tilt) * t * t
        x, z = r * math.cos(twist), r * math.sin(twist)
        w = thick * (1.0 - t * 0.5) * 0.5
        verts.append((x - w, y, z))
        verts.append((x + w, y, z))
    for i in range(segs):
        a = i * 2
        faces.append((a, a + 1, a + 3, a + 2))
    return verts, faces


def head(y, size, twist, kind):
    """Соцветие. У злака — вытянутый колос/метёлка, у разнотравья — щиток."""
    verts, faces = [], []
    if kind == "злак" or kind == "осока":
        h, w = size * 3.2, size * 0.55
        for i in range(3):
            a = twist + i * 2.094
            px, pz = math.cos(a) * w, math.sin(a) * w
            base = len(verts)
            verts += [(-px, y, -pz), (px, y, pz), (px, y + h, pz), (-px, y + h, -pz)]
            faces.append((base, base + 1, base + 2, base + 3))
    else:
        r = size
        for i in range(5):
            a = twist + i * 1.2566
            px, pz = math.cos(a) * r, math.sin(a) * r
            base = len(verts)
            verts += [(0, y, 0), (px, y + r * 0.25, pz),
                      (px * 0.7 - pz * 0.7, y + r * 0.25, pz * 0.7 + px * 0.7)]
            faces.append((base, base + 1, base + 2))
    return verts, faces


def build_species(name, sp, rng):
    """Одна ДЕРНИНА вида: столько побегов, сколько даёт вид."""
    verts, faces = [], []
    matslot = []            # 0 = зелень, 1 = соцветие

    def add(v, f, mat):
        base = len(verts)
        verts.extend(v)
        for ff in f:
            faces.append(tuple(b + base for b in ff))
            matslot.append(mat)

    h_lo, h_hi = sp["h_cm"]
    habit = sp["habit"]
    n = int(sp["shoots"])
    lw = sp["leaf_mm"] / 1000.0

    for k in range(n):
        hgt = rng.uniform(h_lo, h_hi) / 100.0
        tw = rng.uniform(0, math.tau)
        if habit in ("злак", "осока"):
            lean = rng.uniform(0.10, 0.55)
            v, f = blade(hgt, lw, lean, tw, rng.uniform(0.25, 0.6))
            add(v, f, 0)
            if k < max(1, n // 3):                    # колосится не каждый побег
                v, f = stem(hgt * 1.05, lw * 0.45, lean * 0.35, tw)
                add(v, f, 0)
                if sp.get("flower"):
                    v, f = head(hgt * 1.02, lw * 1.1, tw, habit)
                    add(v, f, 1)
        elif habit == "папоротник":
            lean = rng.uniform(0.25, 0.7)
            v, f = stem(hgt, lw * 0.25, lean, tw)
            add(v, f, 0)
            for j in range(6):                        # перья вайи
                t = 0.25 + 0.12 * j
                v, f = broad_leaf(hgt * 0.30 * (1.0 - t * 0.5), lw * 0.5,
                                  rng.uniform(-0.1, 0.25), tw + (1 if j % 2 else -1) * 1.4)
                v = [(a, b + hgt * t, c) for a, b, c in v]
                add(v, f, 0)
        elif habit == "кустарничек":
            v, f = stem(hgt, lw * 0.30, rng.uniform(0.05, 0.3), tw)
            add(v, f, 0)
            for j in range(4):
                t = 0.35 + 0.18 * j
                v, f = broad_leaf(lw * 1.6, lw, rng.uniform(0.1, 0.5),
                                  tw + j * 1.7)
                v = [(a, b + hgt * t, c) for a, b, c in v]
                add(v, f, 0)
        else:                                          # разнотравье
            tilt = rng.uniform(0.0, 0.28)
            v, f = stem(hgt, lw * 0.22, tilt, tw)
            add(v, f, 0)
            for j in range(3):
                t = 0.20 + 0.22 * j
                v, f = broad_leaf(lw * 2.4, lw, rng.uniform(-0.05, 0.3), tw + j * 2.1)
                v = [(a, b + hgt * t, c) for a, b, c in v]
                add(v, f, 0)
            if sp.get("flower"):
                v, f = head(hgt, lw * 0.9, tw, habit)
                add(v, f, 1)

    ob = mesh_from(name, verts, faces)
    green = bpy.data.materials.new("green")
    green.diffuse_color = tuple(sp["color"]) + (1.0,)
    ob.data.materials.append(green)
    fl = bpy.data.materials.new("flower")
    fl.diffuse_color = tuple(sp["flower"] or sp["color"]) + (1.0,)
    ob.data.materials.append(fl)
    for i, p in enumerate(ob.data.polygons):
        p.material_index = matslot[i] if i < len(matslot) else 0
    return ob


def render_preview(names, path):
    """Лист-превью: все виды в ряд, ортографически, чтобы СМОТРЕТЬ на растения."""
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 24
    sc.cycles.device = "CPU"
    sc.render.resolution_x = 260 * len(names)
    sc.render.resolution_y = 620
    sc.render.filepath = path
    sc.render.image_settings.file_format = "PNG"
    sc.world = bpy.data.worlds.new("w")
    sc.world.use_nodes = True
    sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.30, 0.34, 0.38, 1)
    sc.world.node_tree.nodes["Background"].inputs[1].default_value = 1.4

    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    span = 0.55 * len(names)
    cam_data.ortho_scale = span
    cam = bpy.data.objects.new("cam", cam_data)
    sc.collection.objects.link(cam)
    cam.location = (span * 0.5 - 0.275, 0.65, 6.0)
    cam.rotation_euler = (math.pi / 2, 0, 0)
    sc.camera = cam

    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 3.0
    sun.rotation_euler = (0.9, 0.2, 0.6)
    sc.collection.objects.link(sun)
    bpy.ops.render.render(write_still=True)


def main():
    only = None
    for a in sys.argv:
        if a.startswith("--only"):
            only = a.split("=", 1)[1] if "=" in a else None
    veg = json.load(open(VEG, encoding="utf-8"))
    os.makedirs(OUTDIR, exist_ok=True)
    clear()
    rng = random.Random(20250621)

    made = []
    print("== РАСТЕНИЯ ИЗ БОТАНИКИ ==")
    for rus, sp in veg["species"].items():
        if only and only.lower() not in sp["lat"].lower():
            continue
        ob = build_species(sp["lat"].replace(" ", "_"), sp, rng)
        tris = sum(len(p.vertices) - 2 for p in ob.data.polygons)
        made.append((rus, sp, ob, tris))
        print("  %-24s %-26s %-12s побегов %2d  высота %3d-%3d см  △=%4d"
              % (rus, sp["lat"], sp["habit"], sp["shoots"],
                 sp["h_cm"][0], sp["h_cm"][1], tris))

    # разложить в ряд для превью
    for i, (_, _, ob, _) in enumerate(made):
        ob.location.x = i * 0.55

    total = sum(t for _, _, _, t in made)
    print("  видов %d, треугольников на дернину: сред %.0f, всего %d"
          % (len(made), total / max(len(made), 1), total))

    # экспорт по одному
    for rus, sp, ob, _ in made:
        for o in bpy.context.scene.objects:
            o.select_set(False)
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        p = os.path.join(OUTDIR, sp["lat"].replace(" ", "_") + ".glb")
        bpy.ops.export_scene.gltf(filepath=p, use_selection=True,
                                  export_format="GLB", export_yup=True)
    print("  модели записаны в", OUTDIR)

    if "--no-preview" not in sys.argv:
        render_preview([m[0] for m in made], PREVIEW)
        print("  превью:", PREVIEW)


if __name__ == "__main__":
    main()
