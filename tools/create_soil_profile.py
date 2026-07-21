#!/usr/bin/env python3
"""СОЗДАНИЕ НУТРА почвы — профиль (горизонты), то, что видно при вскапывании.

Дерново-подзолистая почва района Гатчины (реальная педология):
  A  (0..18 см)  гумусовый — тёмный серо-бурый (= наш поверхностный материал)
  E  (18..32 см) подзолистый — белёсый, вымытый (ash-grey)
  B  (32..75 см) иллювиальный — рыже-бурый (вмыты железо/глина)
  C  (75+  см)   материнская порода — серо-палевый суглинок/супесь, с камнями

Пока это только СРЕЗ + карта «глубина→цвет горизонта» (data/soil_profile.json),
которую шейдер выемки будет читать, показывая профиль на стенках ямы. Цвета —
не на глаз: гумус/материнская сверены с реальными сканами (Ground054 lin≈0.30/
0.23/0.14; наш soil_sod), подзол/иллювий — по педологии. Строит срез в Blender,
рендерит Cycles. Запуск: python3 tools/create_soil_profile.py
"""
import json
import math
import os

import bpy

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUTJSON = os.path.join(ROOT, "game2", "data", "soil_profile.json")

# горизонты: (имя, глубина_низа_м, цвет sRGB, шероховатость)
HORIZONS = [
    ("A_гумус",   0.18, (0.34, 0.28, 0.20), 0.96),   # тёмный серо-бурый (по эталону)
    ("E_подзол",  0.32, (0.62, 0.60, 0.55), 0.95),   # белёсый вымытый
    ("B_иллювий", 0.75, (0.46, 0.31, 0.19), 0.92),   # рыже-бурый (железо/глина)
    ("C_порода",  1.60, (0.55, 0.49, 0.40), 0.94),   # серо-палевый суглинок
]


def srgb_to_lin(c):
    return tuple((v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4) for v in c)


def main():
    # --- data: карта глубина→цвет (для шейдера выемки) ---
    os.makedirs(os.path.dirname(OUTJSON), exist_ok=True)
    prof = {"horizons": [{"name": n, "bottom_m": d, "color_srgb": list(c), "rough": r}
                         for n, d, c, r in HORIZONS]}
    json.dump(prof, open(OUTJSON, "w"), ensure_ascii=False, indent=1)
    print("профиль → data/soil_profile.json:", " / ".join(h[0] for h in HORIZONS))

    # --- срез в Blender: блок земли, стенка окрашена по горизонтам ---
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'; sc.cycles.samples = 48

    W, D = 1.4, 1.0
    # четыре слоя-объекта, сложенных вниз от z=0 — реальные цвета горизонтов
    tops = [0.0] + [h[1] for h in HORIZONS[:-1]]
    for i, (name, bottom, col, rough) in enumerate(HORIZONS):
        z_top = -tops[i]
        z_bot = -bottom
        th = z_top - z_bot
        cz = (z_top + z_bot) / 2
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, cz))
        o = bpy.context.object; o.name = name
        o.scale = (W, D, abs(th))       # size=1 куб (высота 1) → полная толщина слоя
        print("  %-10s z=[%.2f..%.2f]" % (name, z_bot, z_top))
        m = bpy.data.materials.new(name); m.use_nodes = True
        nt = m.node_tree; bsdf = nt.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = (*col, 1)
        bsdf.inputs["Roughness"].default_value = rough
        # зернистость земли (бамп) — не плоская стенка
        n = nt.nodes.new("ShaderNodeTexNoise"); n.inputs["Scale"].default_value = 90.0
        n.inputs["Detail"].default_value = 8.0
        bump = nt.nodes.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.4
        nt.links.new(n.outputs["Fac"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
        # лёгкая вариация цвета по крупному шуму (границы горизонтов не идеальны)
        nc = nt.nodes.new("ShaderNodeTexNoise"); nc.inputs["Scale"].default_value = 6.0
        mixc = nt.nodes.new("ShaderNodeMix"); mixc.data_type = 'RGBA'
        mixc.inputs["Factor"].default_value = 0.12
        mixc.inputs[6].default_value = (*col, 1)
        mixc.inputs[7].default_value = (col[0] * 0.7, col[1] * 0.7, col[2] * 0.7, 1)
        nt.links.new(nc.outputs["Fac"], mixc.inputs[0])
        nt.links.new(mixc.outputs[2], bsdf.inputs["Base Color"])
        o.data.materials.append(m)

    # трава-бровка сверху (тонкая кромка дёрна на верхней грани — контекст)
    sod = bpy.data.materials.new("sod"); sod.use_nodes = True
    sod.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.13, 0.20, 0.07, 1)

    sun = bpy.data.lights.new("s", 'SUN'); so = bpy.data.objects.new("s", sun)
    sc.collection.objects.link(so); sun.energy = 3.5; sun.angle = 0.02
    so.rotation_euler = (math.radians(48), 0, math.radians(35))
    w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.5, 0.6, 0.78, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 0.5
    cam = bpy.data.cameras.new("c"); co = bpy.data.objects.new("c", cam)
    sc.collection.objects.link(co); sc.camera = co
    cam.lens = 45
    co.location = (2.0, -3.4, -0.5); co.rotation_euler = (math.radians(84), 0, math.radians(30))
    sc.render.resolution_x = 760; sc.render.resolution_y = 820
    sc.view_settings.view_transform = 'AgX'
    sc.render.filepath = "/tmp/soil_profile_preview.png"
    import time; t = time.time()
    bpy.ops.render.render(write_still=True)
    print("срез профиля Cycles за %.0f с → /tmp/soil_profile_preview.png" % (time.time() - t))


if __name__ == "__main__":
    main()
