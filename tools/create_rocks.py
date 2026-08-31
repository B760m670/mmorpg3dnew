#!/usr/bin/env python3
"""СОЗДАНИЕ камней как ОТДЕЛЬНЫХ объектов (не часть почвы/поверхности).

Камни района Гатчины — ледниковые валуны и обломки: гранит (серый/розоватый),
известняк (палевый), тёмный диабаз. Каждый — своя геометрия (икосфера →
воронойные грани + бугры displace), свой размер/форма/цвет, фотореалистичный
материал Cycles. Экспорт glTF — потом накидываются на рельеф с физикой
(коллизия), по каменистым зонам/land-cover. Создавать по отдельности и
накидывать — не валить в кучу с почвой.

Запуск: python3 tools/create_rocks.py
"""
import math
import os
import random

import bpy

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUTDIR = os.path.join(ROOT, "game2", "assets", "models")

REF = os.path.join(ROOT, "game2", "assets", "materials", "real", "rock030")

# породы: реальная поверхность камня (скан rock030) × тон породы × множ.шерох.
# Тон лишь подкрашивает НАСТОЯЩЕЕ зерно/прожилки — не заменяет их.
ROCK_TYPES = [
    ("granite_grey", (0.88, 0.90, 0.92), 1.00),
    ("granite_pink", (1.08, 0.88, 0.80), 0.95),
    ("limestone", (1.18, 1.10, 0.94), 1.10),
    ("diabase_dark", (0.55, 0.56, 0.64), 0.88),
    ("granite_grey", (0.94, 0.93, 0.90), 1.02),
]


def _teximg(nt, fn, noncolor):
    img = bpy.data.images.load(os.path.join(REF, fn))
    if noncolor:
        img.colorspace_settings.name = 'Non-Color'
    n = nt.nodes.new("ShaderNodeTexImage")
    n.image = img
    return n


def rock_material(name, tint, rough_mul):
    """РЕАЛЬНАЯ поверхность камня (скан rock030) на геометрии, подкрашенная тоном
    породы, + кромочный износ/мох (pointiness). Настоящее зерно/прожилки — из
    скана, не выдуманы."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    col = _teximg(nt, "Color.jpg", False)
    nrm = _teximg(nt, "Normal.jpg", True)
    rgh = _teximg(nt, "Roughness.jpg", True)

    # тон породы множит РЕАЛЬНЫЙ цвет (зерно сохраняется)
    tn = nt.nodes.new("ShaderNodeMix"); tn.data_type = 'RGBA'; tn.blend_type = 'MULTIPLY'
    tn.inputs["Factor"].default_value = 1.0
    tn.inputs[7].default_value = (*tint, 1.0)
    nt.links.new(col.outputs["Color"], tn.inputs[6])
    # кромочный износ + мох во впадинах (pointiness)
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    wear = nt.nodes.new("ShaderNodeValToRGB")
    wear.color_ramp.elements[0].position = 0.44
    wear.color_ramp.elements[0].color = (0.50, 0.55, 0.42, 1)   # впадины — мшисто
    wear.color_ramp.elements[1].position = 0.60
    wear.color_ramp.elements[1].color = (1.30, 1.28, 1.20, 1)   # кромки — износ
    nt.links.new(geo.outputs["Pointiness"], wear.inputs["Fac"])
    mixw = nt.nodes.new("ShaderNodeMix"); mixw.data_type = 'RGBA'; mixw.blend_type = 'MULTIPLY'
    mixw.inputs["Factor"].default_value = 0.85
    nt.links.new(tn.outputs[2], mixw.inputs[6])
    nt.links.new(wear.outputs["Color"], mixw.inputs[7])
    nt.links.new(mixw.outputs[2], bsdf.inputs["Base Color"])
    # реальная нормаль (микрорельеф зерна)
    nmap = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(nrm.outputs["Color"], nmap.inputs["Color"])
    nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    # реальная шероховатость × множитель породы
    rm = nt.nodes.new("ShaderNodeMath"); rm.operation = 'MULTIPLY'
    rm.inputs[1].default_value = rough_mul
    nt.links.new(rgh.outputs["Color"], rm.inputs[0])
    nt.links.new(rm.outputs["Value"], bsdf.inputs["Roughness"])
    return m


def make_rock(seed, size, mat):
    random.seed(seed)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=4, radius=size)
    o = bpy.context.object
    o.name = "rock_%d" % seed
    # форма: неравномерный масштаб (валун не шар), лёгкая приплюснутость
    o.scale = (random.uniform(0.75, 1.25), random.uniform(0.75, 1.25),
               random.uniform(0.55, 0.9))
    bpy.ops.object.transform_apply(scale=True)
    # крупные бугры: облачный displace (общая неровная форма)
    tc = bpy.data.textures.new("c%d" % seed, 'CLOUDS')
    tc.noise_scale = random.uniform(0.35, 0.55)
    d0 = o.modifiers.new("lump", 'DISPLACE')
    d0.texture = tc; d0.texture_coords = 'LOCAL'
    d0.strength = size * random.uniform(0.22, 0.34); d0.mid_level = 0.5
    # грани-сколы: воронойный displace, МЕЛКИЕ ячейки (рублёный камень)
    tv = bpy.data.textures.new("v%d" % seed, 'VORONOI')
    tv.noise_scale = random.uniform(0.22, 0.34)
    tv.noise_intensity = 1.0
    d1 = o.modifiers.new("facet", 'DISPLACE')
    d1.texture = tv; d1.texture_coords = 'LOCAL'
    d1.strength = size * random.uniform(0.24, 0.34); d1.mid_level = 0.45
    # микросколы: ещё мельче воронoй
    tv2 = bpy.data.textures.new("v2_%d" % seed, 'VORONOI')
    tv2.noise_scale = random.uniform(0.10, 0.16)
    d2 = o.modifiers.new("chip", 'DISPLACE')
    d2.texture = tv2; d2.texture_coords = 'LOCAL'
    d2.strength = size * random.uniform(0.07, 0.12); d2.mid_level = 0.5
    for md in ("lump", "facet", "chip"):
        bpy.ops.object.modifier_apply(modifier=md)
    # плоские фаски камня читаются — авто-сглаживание по углу
    o.data.polygons.foreach_set("use_smooth", [True] * len(o.data.polygons))
    o.data.update()
    # UV-развёртка — чтобы реальная поверхность камня легла на геометрию
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.02)
    bpy.ops.object.mode_set(mode='OBJECT')
    # сесть на землю: низ в 0
    zs = [(o.matrix_world @ v.co).z for v in o.data.vertices]
    o.location.z -= min(zs)
    o.data.materials.append(mat)
    return o, len(o.data.polygons)


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'; sc.cycles.samples = 64

    rocks = []
    x = 0.0
    sizes = [0.9, 0.55, 1.05, 0.35, 0.7]
    for i, (name, tint, rough_mul) in enumerate(ROCK_TYPES):
        mat = rock_material(name, tint, rough_mul)
        o, tris = make_rock(1894 + i * 7, sizes[i], mat)
        o.location.x = x
        x += sizes[i] * 1.4 + 0.9
        rocks.append((o, name, tris))
    total_x = x
    for o, name, tris in rocks:
        o.location.x -= total_x / 2
        print("камень %-13s size~%.2f  △=%d" % (name, o.dimensions.z, tris))

    # земля-подложка для кадра
    gm = bpy.data.materials.new("g"); gm.use_nodes = True
    gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.20, 0.17, 0.12, 1)
    bpy.ops.mesh.primitive_plane_add(size=30)
    bpy.context.object.data.materials.append(gm)

    sun = bpy.data.lights.new("s", 'SUN'); so = bpy.data.objects.new("s", sun)
    sc.collection.objects.link(so); sun.energy = 3.0; sun.angle = 0.02
    so.rotation_euler = (math.radians(52), 0, math.radians(40))
    w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.5, 0.6, 0.78, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 0.4
    cam = bpy.data.cameras.new("c"); co = bpy.data.objects.new("c", cam)
    sc.collection.objects.link(co); sc.camera = co
    cam.lens = 50
    co.location = (0, -10.5, 3.4); co.rotation_euler = (math.radians(74), 0, 0)
    sc.render.resolution_x = 1400; sc.render.resolution_y = 430
    sc.view_settings.view_transform = 'AgX'
    sc.render.filepath = "/tmp/rocks_preview.png"
    import time; t = time.time()
    bpy.ops.render.render(write_still=True)
    print("рендер камней Cycles за %.0f с → /tmp/rocks_preview.png" % (time.time() - t))

    # экспорт glTF (для накидывания с физикой в игре)
    bpy.data.objects.remove([o for o in bpy.data.objects if o.name.startswith("Plane")][0], do_unlink=True)
    for o, name, tris in rocks:
        o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=os.path.abspath(os.path.join(OUTDIR, "rocks")),
                              export_format='GLB', use_selection=True)
    print("glTF → game2/assets/models/rocks.glb (%d вариантов)" % len(rocks))


if __name__ == "__main__":
    main()
