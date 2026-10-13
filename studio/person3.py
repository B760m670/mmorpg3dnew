#!/usr/bin/env python3
"""ЧЕЛОВЕК НА MPFB. Третий заход, и он отменяет два предыдущих.

ЧТО Я ДЕЛАЛ НЕ ТАК ТРИ РАЗА ПОДРЯД. Я строил руками то, что уже существует
готовым, и каждый раз обнаруживал это после того, как потратил часы:

  1. Тело выписывал кольцами вершин — сперва в GDScript, потом в Блендере.
     Получалась карикатура. Готовая болванка художника лежала в свободном
     доступе (Blender Studio, CC0).
  2. Глаза лепил шарами и жаловался в отчётах, что «глаза мёртвые». Глазные
     яблоки ШЛИ В КОМПЛЕКТЕ С БОЛВАНКОЙ — GEO-body_male_realistic.eye.L и .R,
     по 546 вершин с развёрткой. Я их просто не загрузил: глазниц не заполнил
     и потом разглядывал пустые дыры.
  3. Кожу красил вершинными цветами по правилу трёх зон портретиста. Выходили
     пятна. А рядом лежал фотоскан кожи славянского мужчины средних лет со
     вписанной щетиной, губами и порами, Public Domain.

Общий вывод один: ИНВЕНТАРИЗАЦИЮ НАДО ДЕЛАТЬ ПЕРВЫМ ДЕЛОМ. Не «что я умею
построить», а «что уже построено и лежит рядом».

ЧТО ЗДЕСЬ ИСПОЛЬЗУЕТСЯ:
  MPFB 2.0.17 — MakeHuman внутри Блендера, официальное расширение из реестра
    Blender (extensions.blender.org). 45 МБ, 143 оператора: параметрический
    человек, скелеты (в том числе Rigify), применение кож, волосы и — важное
    для нас — bake_hair_operator, запекание волос в карты-полоски для игры.
    Работает в headless, проверено.
  Пак кож skins02 с makehumancommunity.org, лицензия CC0. В нём
    jartur69_middleage_slavic_male_with_genitals_and_beard: фотоскан 2048×2048
    кожи славянина средних лет. Щетина, губы, брови, поры и неровности тона
    уже вписаны в текстуру — это то, чего числами не нарисовать.

ГЕРОЙ: мужчина 30–40 лет, простого сословия, Гатчина 1894 года. Пол и возраст
заданы заказчиком; до этого я молча взял мужскую болванку, не спросив.

ЧТО ОСТАЁТСЯ НАШЕЙ РАБОТОЙ: костюм эпохи (крой из person2.py переносится —
он работает от любого тела), укладка волос, привязка к игре, походка.

Установка (один раз):
  curl -sSL -o mpfb.zip <ссылка из extensions.blender.org>
  unzip mpfb.zip -d ~/.config/blender/4.5/extensions/user_default/mpfb
  python3 studio/fetch_materials.py        # ткани
  # пак кож: files2.makehumancommunity.org/asset_packs/skins02/skins02_cc0.zip

Запуск:
  LIBGL_ALWAYS_SOFTWARE=1 xvfb-run -a /opt/blender/blender -b -noaudio \
      -P studio/person3.py -- --face /tmp/face.png
"""
import math
import os
import sys

import bpy
from mathutils import Vector

ADDON = "bl_ext.user_default.mpfb"
SKINS = os.environ.get("MH_SKINS", "/tmp/claude-live/sk2/skins")
SKIN = "jartur69_middleage_slavic_male_with_genitals_and_beard"
TARGET_H = 1.75


def enable_mpfb():
    bpy.ops.preferences.addon_enable(module=ADDON)


def wipe():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)


def make_human():
    """Создать человека. Одна команда там, где у меня было шестьсот строк."""
    bpy.ops.mpfb.create_human()
    h = bpy.data.objects["Human"]
    # рост под нашего героя: MakeHuman отдаёт около 1.66 м
    was = h.dimensions.z
    k = TARGET_H / was
    h.scale = (k, k, k)
    bpy.context.view_layer.update()
    print("[человек] MPFB: вершин %d, рост %.3f -> %.3f м"
          % (len(h.data.vertices), was, h.dimensions.z))
    return h


def find_skin():
    d = os.path.join(SKINS, SKIN)
    if not os.path.isdir(d):
        raise SystemExit("нет пака кож: %s\n"
                         "скачай skins02_cc0.zip с files2.makehumancommunity.org" % d)
    png = [f for f in os.listdir(d) if f.lower().endswith(".png")
           and not f.endswith(".thumb")]
    if not png:
        raise SystemExit("в %s нет текстуры" % d)
    return os.path.join(d, png[0])


def mat_skin(path):
    """КОЖА ИЗ ФОТОСКАНА.

    Всё, что я пытался вычислить — щетина, губы, поры, краснота на скулах,
    синева под глазами — уже снято с живого человека и лежит в этой картинке.
    Моя работа тут только в том, как она освещена.

    ПОДПОВЕРХНОСТНОЕ РАССЕЯНИЕ остаётся за нами: текстура его не содержит и
    содержать не может — это свойство объёма, а не поверхности. Радиусы
    36/14/8 мм по каналам — измеренные длины свободного пробега света в
    человеческой ткани. Файл материала MakeHuman задаёт то же самое в своих
    единицах (sssRScale 5.0, sssGScale 2.5, sssBScale 1.0) — те же 5:2.5:1.
    """
    m = bpy.data.materials.new("кожа славянина")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = bpy.data.images.load(path, check_existing=True)
    nt.links.new(t.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.52
    if "Subsurface Weight" in b.inputs:
        b.inputs["Subsurface Weight"].default_value = 0.25
        b.inputs["Subsurface Radius"].default_value = (0.036, 0.014, 0.008)
        if "Subsurface Scale" in b.inputs:
            b.inputs["Subsurface Scale"].default_value = 0.010
    if "Specular IOR Level" in b.inputs:
        b.inputs["Specular IOR Level"].default_value = 0.5
    print("[кожа] %s" % os.path.basename(path))
    return m


def look(frm, to):
    return (Vector(to) - Vector(frm)).to_track_quat('-Z', 'Y').to_euler()


def stage(res=(700, 700)):
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE_NEXT'
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.view_settings.view_transform = 'Standard'
    w = bpy.data.worlds.new("w")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.30, 0.32, 0.35, 1)
    sc.world = w
    for nm, pos, en in (("рисующий", (1.2, -1.4, 1.9), 60.0),
                        ("заполняющий", (-1.6, -0.9, 1.4), 22.0),
                        ("контровой", (0.3, 1.8, 1.9), 40.0)):
        lt = bpy.data.lights.new(nm, 'AREA')
        lt.energy = en
        lt.size = 1.2
        lo = bpy.data.objects.new(nm, lt)
        lo.location = pos
        lo.rotation_euler = look(pos, (0, 0, 1.6))
        bpy.context.collection.objects.link(lo)


def shoot(h, out, face=True):
    sc = bpy.context.scene
    cd = bpy.data.cameras.new("c")
    cd.lens = 85.0 if face else 60.0
    cam = bpy.data.objects.new("c", cd)
    bpy.context.collection.objects.link(cam)
    sc.camera = cam
    top = max((h.matrix_world @ v.co).z for v in h.data.vertices)
    if face:
        aim = (0, 0, top - 0.11)
        cam.location = (0.22, -0.75, top - 0.11)
    else:
        aim = (0, 0, top * 0.52)
        cam.location = (0.9, -3.0, top * 0.55)
    cam.rotation_euler = look(cam.location, aim)
    sc.render.filepath = out
    bpy.ops.render.render(write_still=True)
    print("[кадр] %s" % out)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    enable_mpfb()
    wipe()
    h = make_human()
    m = mat_skin(find_skin())
    h.data.materials.clear()
    h.data.materials.append(m)
    stage()
    if "--face" in argv:
        shoot(h, argv[argv.index("--face") + 1], face=True)
    elif "--full" in argv:
        stage(res=(520, 940))
        shoot(h, argv[argv.index("--full") + 1], face=False)


if __name__ == "__main__":
    main()
