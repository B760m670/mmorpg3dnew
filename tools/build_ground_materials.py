#!/usr/bin/env python3
"""НАБОР почвенных материалов для СИСТЕМЫ земли (height-blend), из РЕАЛЬНЫХ
сканов — не синтез. Правильный AAA-путь: реальный альбедо (истина) + честная
геометрия, запечённая в Blender.

Вход — реальный CC0-скан голой земли ambientCG Ground054 (assets/materials/real/
ground054: Color/Normal/Roughness). Из его СКАНИРОВАННОЙ нормали восстанавливаем
НАСТОЯЩУЮ высоту (интегрирование градиента, Пуассон/FFT — не «яркость=высота»),
поднимаем ею реальную геометрию комьев и запекаем в Blender:
  Height  — из скан-нормали (для height-blend слоёв и параллакса)
  AO      — трассированный по перекрытиям комьев (Cycles)
  Normal  — перезапечён с поднятой геометрии (согласован с Height)
Альбедо/шероховатость берём как есть — они РЕАЛЬНЫЕ (скан).

Два слоя из одного скана (одна микроструктура, разное состояние — честно):
  soil_loam  — сухой суглинок: реальный альбедо скана как есть
  soil_humus — влажный гумус/грязь (низины, дно водоёмов): тот же скан,
               альбедо сведён по ЧИСЛАМ к тёмной влажной земле (замер линейный).

Выход: game2/assets/materials/created/{soil_loam,soil_humus}/
       Color/Normal/Roughness/AmbientOcclusion/Height (2048²) + превью Cycles.
Запуск: python3 tools/build_ground_materials.py
"""
import os
import time

import numpy as np
from PIL import Image

HERE = os.path.dirname(__file__)
ROOT = os.path.join(HERE, "..")
REAL = os.path.join(ROOT, "game2", "assets", "materials", "real", "ground054")
OUTDIR = os.path.join(ROOT, "game2", "assets", "materials", "created")
RES = 2048
TILE_M = 2.0
RELIEF_M = 0.05          # амплитуда реального микрорельефа комьев, м

# Скан Ground054 РЕАЛЬНЫЙ, но это СВЕТЛАЯ ПЕСЧАНАЯ земля (linear ~0.333/0.259/
# 0.157) — не почва Гатчины. Микроструктуру и вариацию скана храним, а СРЕДНИЙ
# ЦВЕТ сводим по числам к измеренной дерново-подзолистой почве района:
#   soil_loam  — сухой серо-бурый суглинок (A-горизонт, сухая поверхность)
#   soil_humus — влажный тёмный гумус (низины, дно водоёмов) — темнее и холоднее
# Сырой песок Ground054 ещё пригодится как «плац/песок» — отдельным слоем позже.
LOAM_LIN_TARGET = np.array([0.135, 0.100, 0.062])    # сухая дерново-подзолистая
HUMUS_LIN_TARGET = np.array([0.070, 0.052, 0.034])   # мокрый гумус (в ~2× темнее)


def srgb_to_lin(c):
    c = c / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(c):
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def height_from_normal(nrm_rgb):
    """НАСТОЯЩАЯ высота из скан-нормали: интегрируем поле наклонов (Пуассон, FFT).
    n=2*rgb-1; наклоны p=-nx/nz, q=-ny/nz; ∇²h=∂p/∂x+∂q/∂y → h в частотах."""
    n = nrm_rgb.astype(np.float32) / 255.0 * 2.0 - 1.0
    nx, ny, nz = n[..., 0], n[..., 1], n[..., 2]
    nz = np.where(np.abs(nz) < 1e-3, 1e-3, nz)
    p = -nx / nz
    q = -ny / nz
    H, W = p.shape
    dpdx = (np.roll(p, -1, 1) - np.roll(p, 1, 1)) * 0.5
    dqdy = (np.roll(q, -1, 0) - np.roll(q, 1, 0)) * 0.5
    f = dpdx + dqdy
    wx = 2 * np.pi * np.fft.fftfreq(W)
    wy = 2 * np.pi * np.fft.fftfreq(H)
    WX, WY = np.meshgrid(wx, wy)
    denom = (WX ** 2 + WY ** 2)
    denom[0, 0] = 1.0
    h = np.real(np.fft.ifft2(np.fft.fft2(f) / (-denom)))
    h[0, 0] = 0.0
    h -= h.min()
    h /= max(h.max(), 1e-6)
    return h.astype(np.float32)


def load_resized(path, res, gray=False):
    im = Image.open(path)
    im = im.convert("L" if gray else "RGB").resize((res, res), Image.LANCZOS)
    return np.asarray(im).astype(np.float32)


def main():
    t0 = time.time()
    color = load_resized(os.path.join(REAL, "Color.jpg"), RES)
    normal = load_resized(os.path.join(REAL, "Normal.jpg"), RES)
    rough = load_resized(os.path.join(REAL, "Roughness.jpg"), RES, gray=True)

    # реальная высота из скан-нормали
    h = height_from_normal(normal)
    print("высота из скан-нормали: σ=%.3f (реконструкция градиента, не яркость)" % h.std())

    scan_lin = srgb_to_lin(color)
    scan_mean = scan_lin.reshape(-1, 3).mean(0)

    def retint(target):
        """свести СРЕДНЕЕ линейного альбедо к target, ВАРИАЦИЮ скана сохранить."""
        ratio = target / np.maximum(scan_mean, 1e-4)
        lin = np.clip(scan_lin * ratio[None, None, :], 0.0, 1.0)
        return lin_to_srgb(lin) * 255.0, lin.reshape(-1, 3).mean(0)

    # --- soil_loam: сухой серо-бурый суглинок (цвет сведён к почве района) ---
    loam_srgb, loam_m = retint(LOAM_LIN_TARGET)
    print("soil_loam  линейный альбедо = %.3f/%.3f/%.3f (сведён к сухой дерновой)" % tuple(loam_m))

    # --- soil_humus: влажный тёмный гумус (низины/дно) ---
    humus_srgb, humus_m = retint(HUMUS_LIN_TARGET)
    print("soil_humus линейный альбедо = %.3f/%.3f/%.3f (сведён к мокрому гумусу)" % tuple(humus_m))
    humus_rough = np.clip(rough * 0.72, 0, 255)   # мокрая земля глаже сухой

    layers = {
        "soil_loam": (loam_srgb, rough),
        "soil_humus": (humus_srgb, humus_rough),
    }
    for name, (col, rgh) in layers.items():
        d = os.path.join(OUTDIR, name)
        os.makedirs(d, exist_ok=True)
        Image.fromarray(np.clip(col, 0, 255).astype(np.uint8)).save(os.path.join(d, "Color.png"))
        Image.fromarray(np.clip(rgh, 0, 255).astype(np.uint8)).save(os.path.join(d, "Roughness.png"))
        Image.fromarray((h * 255).astype(np.uint8)).save(os.path.join(d, "Height.png"))

    # ---------- Blender: поднять геометрию реальной высотой, запечь Normal+AO ----------
    import bpy
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'

    himg_path = os.path.abspath(os.path.join(OUTDIR, "soil_loam", "Height.png"))
    himg = bpy.data.images.load(himg_path)

    bpy.ops.mesh.primitive_grid_add(x_subdivisions=639, y_subdivisions=639, size=TILE_M)
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
    print("hi-геометрия: %d полигонов" % len(hi.data.polygons))

    bpy.ops.mesh.primitive_plane_add(size=TILE_M)
    lo = bpy.context.object
    mat = bpy.data.materials.new("bake"); mat.use_nodes = True
    lo.data.materials.append(mat)
    nt = mat.node_tree
    bake_img = bpy.data.images.new("bake_target", RES, RES, alpha=False, float_buffer=False)
    node = nt.nodes.new("ShaderNodeTexImage"); node.image = bake_img
    nt.nodes.active = node; node.select = True

    hi.select_set(True); lo.select_set(True)
    bpy.context.view_layer.objects.active = lo

    t = time.time()
    bake_img.colorspace_settings.name = 'Non-Color'
    bpy.ops.object.bake(type='NORMAL', use_selected_to_active=True,
                        cage_extrusion=0.1, max_ray_distance=0.35, margin=8)
    # общая для обоих слоёв (одна геометрия)
    for name in layers:
        bake_img.filepath_raw = os.path.abspath(os.path.join(OUTDIR, name, "Normal.png"))
        bake_img.file_format = 'PNG'; bake_img.save()
    print("Normal запечён с поднятой геометрии за %.0f с" % (time.time() - t))

    t = time.time()
    sc.cycles.samples = 16
    bpy.ops.object.bake(type='AO', use_selected_to_active=True,
                        cage_extrusion=0.1, max_ray_distance=0.35, margin=8)
    for name in layers:
        bake_img.filepath_raw = os.path.abspath(os.path.join(OUTDIR, name, "AmbientOcclusion.png"))
        bake_img.save()
    print("AO трассирован за %.0f с" % (time.time() - t))

    # ---------- превью soil_loam: реальный рельеф под низким солнцем ----------
    lo.hide_render = True
    aimg = bpy.data.images.load(os.path.abspath(os.path.join(OUTDIR, "soil_loam", "Color.png")))
    rimg = bpy.data.images.load(os.path.abspath(os.path.join(OUTDIR, "soil_loam", "Roughness.png")))
    rimg.colorspace_settings.name = 'Non-Color'
    pmat = bpy.data.materials.new("soil"); pmat.use_nodes = True
    pnt = pmat.node_tree; bsdf = pnt.nodes.get("Principled BSDF")
    ta = pnt.nodes.new("ShaderNodeTexImage"); ta.image = aimg
    tr = pnt.nodes.new("ShaderNodeTexImage"); tr.image = rimg
    pnt.links.new(ta.outputs["Color"], bsdf.inputs["Base Color"])
    pnt.links.new(tr.outputs["Color"], bsdf.inputs["Roughness"])
    hi.data.materials.append(pmat)

    sun = bpy.data.lights.new("sun", 'SUN'); so = bpy.data.objects.new("sun", sun)
    sc.collection.objects.link(so); sun.energy = 8.0; sun.angle = 0.02
    so.rotation_euler = (1.25, 0.0, 2.4)
    w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.45, 0.55, 0.75, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 0.9
    cam = bpy.data.cameras.new("c"); co = bpy.data.objects.new("c", cam)
    sc.collection.objects.link(co); sc.camera = co; cam.lens = 35
    co.location = (0.55, -0.85, 0.34); co.rotation_euler = (1.18, 0.0, 0.55)
    sc.cycles.samples = 32
    sc.render.resolution_x = 960; sc.render.resolution_y = 560
    sc.view_settings.view_transform = 'AgX'
    sc.render.filepath = "/tmp/soil_loam_preview.png"
    t = time.time()
    bpy.ops.render.render(write_still=True)
    print("превью Cycles за %.0f с → /tmp/soil_loam_preview.png" % (time.time() - t))
    print("ГОТОВ набор почв за %.0f с: soil_loam + soil_humus (Color/Normal/Rough/AO/Height 2048²)"
          % (time.time() - t0))


if __name__ == "__main__":
    main()
