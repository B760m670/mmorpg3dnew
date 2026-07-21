#!/usr/bin/env python3
"""СОЗДАНИЕ почвы (не скан, не рисунок): конвейер TLOU2-класса в Blender.

  1. numpy строит ПЕРИОДИЧЕСКИЙ микрорельеф почвы (комья, крупинки-агрегаты,
     редкие камешки) — бесшовный тайл по построению (функции make_materials).
  2. Blender поднимает РЕАЛЬНУЮ геометрию: сетка 512² смещается этим рельефом
     (262k полигонов настоящих комьев на тайл 2 м).
  3. Cycles ЗАПЕКАЕТ с настоящей геометрии: тангенс-нормали и трассированный
     AO (не аналитические из градиента — честные, с перекрытиями комьев).
  4. В игру идут карты Color/Normal/Roughness/AO/Height — телефону легко,
     деталь несут карты. Это стандартный AAA-пайплайн (hi-poly → bake).

Первый материал: ДЕРНОВАЯ почва (гумусная, под лугами Гатчины — по нашему
почвенному полю). Запуск: python3 tools/create_soil_material.py
"""
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(__file__)
sys.path.append(HERE)
from make_materials import fbm, voronoi, N  # периодические шумы (тайл!)

ROOT = os.path.join(HERE, "..")
OUT = os.path.join(ROOT, "game2", "assets", "materials", "created", "soil_sod")
TILE_M = 2.0          # мировой размер тайла
RELIEF_M = 0.045      # амплитуда микрорельефа почвы, м


def build_fields():
    """Высота + альбедо + шероховатость дерновой почвы, всё периодическое."""
    from scipy.ndimage import gaussian_filter

    # комья пашни/дернины: крупные мягкие + средние
    lumps = 0.55 * fbm(6, 4) + 0.30 * fbm(14, 3)
    # агрегаты-крупинки ДВУХ фракций, и не везде — кучками (маска пятен)
    d1, _, _, _, _ = voronoi(80)
    d1b, _, _, _, _ = voronoi(45)
    crumb = 0.6 * np.clip(1.0 - d1 * 1.8, 0, 1) ** 1.4 \
        + 0.4 * np.clip(1.0 - d1b * 1.5, 0, 1) ** 1.4
    crumb_mask = np.clip((fbm(7, 3) - 0.38) * 2.8, 0, 1)
    # ТОЛЬКО почва: комья + крупинки гумуса. Камней здесь НЕТ — камни отдельные
    # объекты (создаются мешами и накидываются), не запекаются в поверхность.
    soft = gaussian_filter(lumps * 0.72 + crumb * crumb_mask * 0.18,
                           sigma=1.5, mode='wrap')
    h = (soft - soft.min()) / (soft.max() - soft.min())

    # альбедо СЛЕДУЕТ из геометрии (не крашеные пятна): гребни комьев (высокое h)
    # суше и светлее, западины держат влагу/органику — темнее. Плюс тонкая
    # зернистость гумуса (±%, не пятна). Камешки серые — их цвет оправдан их
    # реальными куполами. Никакой нарисованной «соломы» — солома будет геометрией.
    fine = fbm(48, 2)
    base_dark = np.array([0.115, 0.088, 0.062])          # влажный гумус в западинах
    base_dry = np.array([0.320, 0.255, 0.185])           # сухой гребень комка
    dryness = np.clip(h * 1.2 - 0.08, 0.0, 1.0)          # сухость ∝ высоте рельефа
    alb = base_dark[None, None, :] * (1 - dryness[..., None]) \
        + base_dry[None, None, :] * dryness[..., None]
    alb *= (0.92 + 0.16 * (fine - 0.5))[..., None]        # зернистость гумуса ±8%
    alb = np.clip(alb, 0, 1)

    rough = 0.95 + 0.05 * (fine - 0.5)          # почва матовая, чуть варьирует
    return h, np.clip(alb, 0, 1), np.clip(rough, 0, 1)


def save8(path, a):
    Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8)).save(path)


def main():
    os.makedirs(OUT, exist_ok=True)
    h, alb, rough = build_fields()
    save8(os.path.join(OUT, "Height.png"), h)
    save8(os.path.join(OUT, "Color.png"), alb)
    save8(os.path.join(OUT, "Roughness.png"), rough)
    print("поля: h σ=%.3f  alb=%.2f/%.2f/%.2f  rough=%.2f" % (
        h.std(), *alb.reshape(-1, 3).mean(0), rough.mean()))

    # ---------- Blender: реальная геометрия → запекание нормалей и AO ----------
    import bpy
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'

    himg = bpy.data.images.load(os.path.abspath(os.path.join(OUT, "Height.png")))

    # высокодетальная сетка, смещённая НАСТОЯЩИМ рельефом
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=511, y_subdivisions=511,
                                    size=TILE_M)
    hi = bpy.context.object
    tex = bpy.data.textures.new("h", 'IMAGE')
    tex.image = himg
    tex.extension = 'REPEAT'
    mod = hi.modifiers.new("disp", 'DISPLACE')
    mod.texture = tex
    mod.texture_coords = 'UV'
    mod.strength = RELIEF_M
    mod.mid_level = 0.5
    bpy.ops.object.modifier_apply(modifier="disp")
    hi.data.polygons.foreach_set("use_smooth", [True] * len(hi.data.polygons))
    hi.data.update()
    print("hi-геометрия: %d полигонов (настоящие комья)" % len(hi.data.polygons))

    # низкополигональная цель с теми же UV
    bpy.ops.mesh.primitive_plane_add(size=TILE_M)
    lo = bpy.context.object
    mat = bpy.data.materials.new("bake")
    mat.use_nodes = True
    lo.data.materials.append(mat)
    nt = mat.node_tree
    bake_img = bpy.data.images.new("bake_target", 1024, 1024,
                                   alpha=False, float_buffer=False)
    node = nt.nodes.new("ShaderNodeTexImage")
    node.image = bake_img
    nt.nodes.active = node
    node.select = True

    hi.select_set(True)
    lo.select_set(True)
    bpy.context.view_layer.objects.active = lo

    import time

    # нормали с настоящей геометрии
    t = time.time()
    bake_img.colorspace_settings.name = 'Non-Color'
    bpy.ops.object.bake(type='NORMAL', use_selected_to_active=True,
                        cage_extrusion=0.09, max_ray_distance=0.3, margin=8)
    bake_img.filepath_raw = os.path.abspath(os.path.join(OUT, "Normal.png"))
    bake_img.file_format = 'PNG'
    bake_img.save()
    print("Normal запечён с геометрии за %.0f с" % (time.time() - t))

    # трассированный AO (честные перекрытия комьев)
    t = time.time()
    sc.cycles.samples = 12
    bpy.ops.object.bake(type='AO', use_selected_to_active=True,
                        cage_extrusion=0.09, max_ray_distance=0.3, margin=8)
    bake_img.filepath_raw = os.path.abspath(os.path.join(OUT, "AmbientOcclusion.png"))
    bake_img.save()
    print("AO трассирован за %.0f с" % (time.time() - t))

    # ---------- превью: настоящий рельеф под низким солнцем ----------
    lo.hide_render = True          # цель запекания в кадре не нужна
    aimg = bpy.data.images.load(os.path.abspath(os.path.join(OUT, "Color.png")))
    rimg = bpy.data.images.load(os.path.abspath(os.path.join(OUT, "Roughness.png")))
    rimg.colorspace_settings.name = 'Non-Color'
    pmat = bpy.data.materials.new("soil")
    pmat.use_nodes = True
    pnt = pmat.node_tree
    bsdf = pnt.nodes.get("Principled BSDF")
    ta = pnt.nodes.new("ShaderNodeTexImage"); ta.image = aimg
    tr = pnt.nodes.new("ShaderNodeTexImage"); tr.image = rimg
    pnt.links.new(ta.outputs["Color"], bsdf.inputs["Base Color"])
    pnt.links.new(tr.outputs["Color"], bsdf.inputs["Roughness"])
    hi.data.materials.append(pmat)

    sun = bpy.data.lights.new("sun", 'SUN')
    so = bpy.data.objects.new("sun", sun)
    sc.collection.objects.link(so)
    sun.energy = 9.0
    sun.angle = 0.02
    so.rotation_euler = (1.25, 0.0, 2.4)         # низкое тёплое солнце
    w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.45, 0.55, 0.75, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 0.9
    cam = bpy.data.cameras.new("c"); co = bpy.data.objects.new("c", cam)
    sc.collection.objects.link(co); sc.camera = co
    cam.lens = 35
    co.location = (0.55, -0.85, 0.34)
    co.rotation_euler = (1.18, 0.0, 0.55)
    sc.cycles.samples = 32
    sc.render.resolution_x = 960; sc.render.resolution_y = 560
    sc.view_settings.view_transform = 'AgX'
    sc.render.filepath = "/tmp/soil_sod_preview.png"
    t = time.time()
    bpy.ops.render.render(write_still=True)
    print("превью Cycles за %.0f с → /tmp/soil_sod_preview.png" % (time.time() - t))


if __name__ == "__main__":
    main()
