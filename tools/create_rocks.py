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

# породы: (имя, базовый цвет, вторичный цвет, шероховатость)
ROCK_TYPES = [
    ("granite_grey", (0.42, 0.41, 0.40), (0.24, 0.23, 0.24), 0.62),
    ("granite_pink", (0.52, 0.40, 0.37), (0.34, 0.27, 0.26), 0.60),
    ("limestone", (0.50, 0.46, 0.38), (0.36, 0.33, 0.27), 0.70),
    ("diabase_dark", (0.20, 0.20, 0.22), (0.11, 0.11, 0.13), 0.55),
    ("granite_grey", (0.46, 0.45, 0.43), (0.26, 0.25, 0.25), 0.64),
]


def rock_material(name, c0, c1, rough):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    # цвет варьирует по шуму: две породы-тона смешиваются пятнами
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 4.5
    noise.inputs["Detail"].default_value = 8.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*c1, 1)
    ramp.color_ramp.elements[1].color = (*c0, 1)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    # кромочный износ + мох во впадинах через pointiness (стандарт фотореал-камня):
    # крутые кромки — светлее (обтёрты), впадины — темнее и мшисто-зеленее
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    wear = nt.nodes.new("ShaderNodeValToRGB")
    wear.color_ramp.elements[0].position = 0.44
    wear.color_ramp.elements[0].color = (0.42, 0.50, 0.36, 1)   # впадины — мшисто
    wear.color_ramp.elements[1].position = 0.60
    wear.color_ramp.elements[1].color = (1.25, 1.22, 1.15, 1)   # кромки — износ
    nt.links.new(geo.outputs["Pointiness"], wear.inputs["Fac"])
    mixw = nt.nodes.new("ShaderNodeMix")
    mixw.data_type = 'RGBA'
    mixw.blend_type = 'MULTIPLY'
    mixw.inputs["Factor"].default_value = 0.9
    nt.links.new(ramp.outputs["Color"], mixw.inputs[6])         # A
    nt.links.new(wear.outputs["Color"], mixw.inputs[7])         # B
    nt.links.new(mixw.outputs[2], bsdf.inputs["Base Color"])    # Result
    # шероховатость чуть варьирует (влажные впадины глаже)
    rr = nt.nodes.new("ShaderNodeTexNoise"); rr.inputs["Scale"].default_value = 9.0
    rmap = nt.nodes.new("ShaderNodeMapRange")
    rmap.inputs["To Min"].default_value = rough - 0.1
    rmap.inputs["To Max"].default_value = rough + 0.12
    nt.links.new(rr.outputs["Fac"], rmap.inputs["Value"])
    nt.links.new(rmap.outputs["Result"], bsdf.inputs["Roughness"])
    # мелкий рельеф камня — бампом (микротрещины), не плоско
    bump_n = nt.nodes.new("ShaderNodeTexNoise"); bump_n.inputs["Scale"].default_value = 45.0
    bump_n.inputs["Detail"].default_value = 10.0
    bump = nt.nodes.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.25
    nt.links.new(bump_n.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
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
    m_auto = o.modifiers.new("auto", 'WEIGHTED_NORMAL') if False else None
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
    for i, (name, c0, c1, rough) in enumerate(ROCK_TYPES):
        mat = rock_material(name, c0, c1, rough)
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
