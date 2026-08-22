#!/usr/bin/env python3
"""ГЕРОЙ ИГРЫ. Мужчина 30–40 лет, простого сословия. Гатчина, 1894.

СОБИРАЕТСЯ ИЗ ГОТОВОГО, И ЭТО ГЛАВНОЕ. Три захода подряд я строил руками то,
что уже существует: тело выписывал кольцами вершин, глаза лепил шарами (а они
шли в комплекте с болванкой и я их просто не загрузил), кожу красил числами по
правилу трёх зон. Каждый раз выходила карикатура, и каждый раз готовое лежало
рядом. Вывод записан, чтобы не повторить: инвентаризацию делать ПЕРВЫМ ДЕЛОМ.

ЧТО ИСПОЛЬЗУЕТСЯ, ВСЁ ПОД ОТКРЫТОЙ ЛИЦЕНЗИЕЙ:
  MPFB 2.0.17 — MakeHuman внутри Блендера, официальное расширение из реестра
    extensions.blender.org. Даёт параметрическое тело (19158 вершин),
    скелеты, шейдеры кожи и глаза.
  Паки ассетов makehumancommunity.org, CC0: глаза, брови (26 вариантов),
    ресницы (9), зубы, язык, причёски (35), кожи (36), одежда, прокси-меши.
  Кожа jartur69_middleage_slavic_male_with_genitals_and_beard — фотоскан
    2048×2048 кожи славянина средних лет. Щетина, губы, поры, неровности тона
    сняты с живого человека; числами такого не нарисовать.

ЧТО ОСТАЁТСЯ НАШЕЙ РАБОТОЙ И РАДИ ЧЕГО ВСЁ ЭТО: костюм эпохи, свет, походка,
сцены. То есть игра. Анатомию и топологию мы не изобретаем.

ПРО ГЛАЗА, РЕСНИЦЫ И БРОВИ — их спрашивали отдельно, и правильно. Это не
детали отделки. Взгляд читается по трём вещам, и ни одна не про форму глазного
яблока: влажный блик на роговице, тень от ресниц на белке́ и линия брови,
задающая выражение. Без них лицо мёртвое, сколько ни возись с кожей. Здесь
все три — настоящие меши из набора, а не нарисованные пятна.

Запуск:
  LIBGL_ALWAYS_SOFTWARE=1 xvfb-run -a /opt/blender/blender -b -noaudio \
      -P studio/hero.py -- --face /tmp/face.png
      -P studio/hero.py -- --full /tmp/full.png
      -P studio/hero.py -- --out game2/assets/models/hero.glb
"""
import importlib
import math
import os
import sys

import bpy
from mathutils import Vector

ADDON = "bl_ext.user_default.mpfb"
DATA = "/root/.config/blender/4.5/extensions/.user/user_default/mpfb/data"
TARGET_H = 1.75

# Кто он: параметры тела. Возрастов у MakeHuman четыре ступени; «young» это
# примерно 25 лет, «old» — сильно за шестьдесят. Наши 30–40 ближе к young, а
# возраст добавим через сложение фигуры: средний вес, средняя мускулатура,
# без юношеской худобы.
# РАСА ЗАДАЁТСЯ ВЛОЖЕННЫМ СЛОВАРЁМ, а не тремя ключами вровень с остальными:
# create_human разбирает "race" отдельно. С плоскими ключами падает на
# «This entity has no property matching africanval».
PHENOTYPE = {
    "gender": 0.9,        # 0 женщина, 1 мужчина
    "age": 0.62,          # 0.5 — 25 лет, 1.0 — старик; 0.62 даёт около 35
    "muscle": 0.55,
    "weight": 0.55,
    "height": 0.52,
    "proportions": 0.5,
    "cupsize": 0.0,
    "firmness": 0.5,
    "race": {"african": 0.05, "asian": 0.10, "caucasian": 0.85},
}

# Что на нём и в нём. Тип важен: MPFB по нему знает, куда сажать ассет и как
# подгонять его при изменении фигуры.
PARTS = [
    ("Eyes",      "eyes/high-poly/high-poly.mhclo"),
    ("Eyebrows",  "eyebrows/eyebrow010/eyebrow010.mhclo"),
    ("Eyelashes", "eyelashes/eyelashes01/eyelashes01.mhclo"),
    ("Teeth",     "teeth/teeth_base/teeth_base.mhclo"),
    ("Tongue",    "tongue/tongue01/tongue01.mhclo"),
    ("Hair",      "hair/short02/short02.mhclo"),
]
SKIN = ("skins/jartur69_middleage_slavic_male_with_genitals_and_beard/"
        "jartur69_middleage_slavic_male_with_genitals_and_beard.mhmat")


def svc(name):
    return importlib.import_module("%s.services.%s" % (ADDON, name))


def build():
    bpy.ops.preferences.addon_enable(module=ADDON)
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    HumanService = svc("humanservice").HumanService

    # МАСШТАБ. MPFB меряет в дециметрах (scale=0.1 — «метры»), поэтому рост
    # приходит около 1.66 м; наш герой 1.75, доводим множителем и печатаем оба
    # числа, чтобы подгонка была видна, а не подразумевалась.
    body = HumanService.create_human(macro_detail_dict=dict(PHENOTYPE))
    was = body.dimensions.z
    k = TARGET_H / was
    body.scale = (k, k, k)
    bpy.context.view_layer.update()
    print("[герой] тело: вершин %d, рост %.3f -> %.3f м"
          % (len(body.data.vertices), was, body.dimensions.z))

    for kind, rel in PARTS:
        p = os.path.join(DATA, rel)
        if not os.path.exists(p):
            print("[герой] НЕТ %-10s %s" % (kind, rel))
            continue
        HumanService.add_mhclo_asset(p, body, asset_type=kind,
                                     material_type='MAKESKIN')
        print("[герой] надето: %-10s %s" % (kind, os.path.basename(rel)))

    sp = os.path.join(DATA, SKIN)
    if os.path.exists(sp):
        # ENHANCED_SSS — шейдер кожи самого MPFB поверх фотоскана. Рассеяние
        # текстура содержать не может: это свойство объёма, а не поверхности.
        HumanService.set_character_skin(sp, body, skin_type='ENHANCED_SSS')
        print("[герой] кожа: %s" % os.path.basename(SKIN))
    else:
        print("[герой] НЕТ кожи:", SKIN)

    n = sum(len(o.data.vertices) for o in bpy.data.objects if o.type == 'MESH')
    print("[герой] всего вершин: %d, объектов: %d"
          % (n, len([o for o in bpy.data.objects if o.type == 'MESH'])))
    return body


# --- проверка глазами -------------------------------------------------------

def look(frm, to):
    return (Vector(to) - Vector(frm)).to_track_quat('-Z', 'Y').to_euler()


def stage(res):
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE_NEXT'
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.view_settings.view_transform = 'Standard'
    w = bpy.data.worlds.new("w")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.30, 0.32, 0.35, 1)
    sc.world = w
    # Рисующий свет сбоку-сверху даёт форму; заполняющий не даёт провалиться в
    # чёрное; контровой отделяет от фона. Блик на роговице — от рисующего.
    for nm, pos, en in (("рисующий", (1.2, -1.4, 1.9), 60.0),
                        ("заполняющий", (-1.6, -0.9, 1.4), 22.0),
                        ("контровой", (0.3, 1.8, 1.9), 40.0)):
        lt = bpy.data.lights.new(nm, 'AREA')
        lt.energy = en
        lt.size = 1.2
        lo = bpy.data.objects.new(nm, lt)
        lo.location = pos
        lo.rotation_euler = look(pos, (0, 0, 1.55))
        bpy.context.collection.objects.link(lo)


def shoot(body, out, face):
    sc = bpy.context.scene
    cd = bpy.data.cameras.new("c")
    cd.lens = 85.0 if face else 55.0
    cam = bpy.data.objects.new("c", cd)
    bpy.context.collection.objects.link(cam)
    sc.camera = cam
    top = max((body.matrix_world @ v.co).z for v in body.data.vertices)
    if face:
        aim = (0, 0, top - 0.10)
        cam.location = (0.20, -0.70, top - 0.09)
    else:
        aim = (0, 0, top * 0.52)
        cam.location = (0.8, -3.2, top * 0.58)
    cam.rotation_euler = look(cam.location, aim)
    sc.render.filepath = out
    bpy.ops.render.render(write_still=True)
    print("[кадр] %s" % out)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    body = build()
    if "--face" in argv:
        stage((760, 760))
        shoot(body, argv[argv.index("--face") + 1], True)
    elif "--full" in argv:
        stage((540, 960))
        shoot(body, argv[argv.index("--full") + 1], False)
    elif "--out" in argv:
        out = argv[argv.index("--out") + 1]
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.export_scene.gltf(filepath=out, export_format='GLB',
                                  export_apply=True)
        print("[герой] вывезено:", out, os.path.getsize(out), "байт")


if __name__ == "__main__":
    main()
