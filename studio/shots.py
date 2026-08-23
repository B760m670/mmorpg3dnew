#!/usr/bin/env python3
"""СЪЁМКА ПЕРСОНАЖА: свет, пол и три ракурса, которые не надо выставлять руками.

ЗАЧЕМ. Я трижды подряд фотографировал затылок, будучи уверенным, что снимаю
лицо, и один раз положил фигуру набок неверной осью «вверх». Ракурс нельзя
задавать наугад: направление взгляда надо ВЫЧИСЛЯТЬ. Здесь оно берётся по
стопам — стопа смотрит туда же, куда человек: от пятки к носку.

Три ракурса — это минимум, по которому видно фигуру: анфас (пропорции и
симметрия), три четверти (объём) и профиль (осанка, вынос головы, прогиб).
"""
import math

import bpy
from mathutils import Vector


def facing(arm):
    """Куда смотрит человек. По стопам: от пятки (кость) к носку."""
    d = Vector((0.0, 0.0, 0.0))
    for a, b in (("LeftFoot", "LeftToeBase"), ("RightFoot", "RightToeBase")):
        if a in arm.pose.bones and b in arm.pose.bones:
            v = arm.pose.bones[b].head - arm.pose.bones[a].head
            v.z = 0.0
            if v.length > 1e-6:
                d += v.normalized()
    if d.length < 1e-6:
        return Vector((0.0, -1.0, 0.0))
    return d.normalized()


def stage(res=(560, 900), ground=True, back=(0.33, 0.36, 0.40)):
    """Свет для РАЗГЛЯДЫВАНИЯ фигуры, а не для красоты.

    Прежняя раскладка была пересвечена: три источника по 400/130/220 Вт при
    передаче 'Standard' выбивали кожу в белое, и тело читалось гладким мешком
    — я по таким кадрам судил об анатомии и ошибался. Форму показывает не
    яркость, а ПЕРЕПАД: главный источник сбоку и сверху, заполняющий втрое
    слабее, контровой по краю. Передача AgX с мягким сведением светов не даёт
    коже выбиваться в белое.
    """
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE_NEXT'
    sc.render.resolution_x, sc.render.resolution_y = res
    try:
        sc.view_settings.view_transform = 'AgX'
        sc.view_settings.look = 'AgX - Medium Contrast'
    except Exception:
        sc.view_settings.view_transform = 'Filmic'
    w = bpy.data.worlds.new("w")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (*back, 1)
    sc.world = w
    if ground:
        bpy.ops.mesh.primitive_plane_add(size=24, location=(0, 0, 0))
        m = bpy.data.materials.new("пол")
        m.use_nodes = True
        b = m.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (0.21, 0.20, 0.18, 1)
        b.inputs["Roughness"].default_value = 0.92
        bpy.context.object.data.materials.append(m)
    # трёхточечный свет: рисующий сбоку-сверху, заполняющий слабее с другой
    # стороны, контровой сзади — он отделяет фигуру от фона
    for pos, en, sz in (((2.2, -2.4, 2.6), 260.0, 1.2),
                        ((-2.6, -1.8, 1.8), 60.0, 2.5),
                        ((0.4, 2.6, 2.4), 180.0, 1.0)):
        lt = bpy.data.lights.new("свет", 'AREA')
        lt.energy = en
        lt.size = sz
        lo = bpy.data.objects.new("свет", lt)
        lo.location = pos
        lo.rotation_euler = (Vector((0, 0, 1.0)) - Vector(pos)) \
            .to_track_quat('-Z', 'Y').to_euler()
        bpy.context.collection.objects.link(lo)
    cd = bpy.data.cameras.new("камера")
    cd.lens = 60.0
    cam = bpy.data.objects.new("камера", cd)
    bpy.context.collection.objects.link(cam)
    sc.camera = cam
    return cam


def shoot(arm, cam, out, frame=None, angle=0.0, dist=3.6, height=0.92,
          up=0.25, lens=None):
    """Снять с поворотом angle градусов от лица (0 — анфас, 180 — спина)."""
    sc = bpy.context.scene
    if frame is not None:
        sc.frame_set(frame)
    if lens:
        cam.data.lens = lens
    dg = bpy.context.evaluated_depsgraph_get()
    a = arm.evaluated_get(dg)
    f = facing(a)
    h = a.pose.bones["Hips"].head
    r = math.radians(angle)
    d = Vector((f.x * math.cos(r) - f.y * math.sin(r),
                f.x * math.sin(r) + f.y * math.cos(r), 0.0))
    aim = Vector((h.x, h.y, height))
    cam.location = aim + d * dist + Vector((0, 0, up))
    cam.rotation_euler = (aim - cam.location).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = out
    bpy.ops.render.render(write_still=True)
    print("[кадр] %s (кадр %s, %.0f°)" % (out, frame, angle))


def turnaround(arm, cam, prefix, frame=None, angles=(0, 40, 90, 180)):
    for a in angles:
        shoot(arm, cam, "%s_%03d.png" % (prefix, a), frame=frame, angle=a)


def face(arm, cam, out, frame=None):
    """Лицо крупно: 85 мм от глаз, как в портрете."""
    sc = bpy.context.scene
    if frame is not None:
        sc.frame_set(frame)
    dg = bpy.context.evaluated_depsgraph_get()
    a = arm.evaluated_get(dg)
    f = facing(a)
    head = a.pose.bones["Head"].head if "Head" in a.pose.bones else None
    z = (head.z + 0.10) if head else 1.60
    aim = Vector((head.x, head.y, z)) if head else Vector((0, 0, z))
    cam.data.lens = 85.0
    cam.location = aim + f * 0.75 + Vector((0.10, 0, 0.02))
    cam.rotation_euler = (aim - cam.location).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = out
    bpy.ops.render.render(write_still=True)
    cam.data.lens = 60.0
    print("[кадр] %s (лицо)" % out)


def silhouette_stage(res=(667, 1000)):
    """Сцена для ОБМЕРА, а не для красоты: чёрная фигура на белом.

    Первый заход мерил обычный кадр на белом фоне, и прибор не нашёл тела
    вовсе: белый фон светил на кожу, она стала почти белой, и порог по яркости
    отсекал вместе с фоном половину человека. Для силуэта нужен не свет, а
    контраст — поэтому всем мешам ставится чёрное свечение, а миру белое.
    Тогда граница тела определяется однозначно, с точностью до пикселя.

    ДЛИННЫЙ ОБЪЕКТИВ (135 мм с девяти метров) — чтобы перспектива не искажала
    пропорции: с близкого широкого объектива ближняя нога всегда шире дальней,
    и любое сравнение с фотографией теряет смысл.
    """
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE_NEXT'
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.film_transparent = False
    sc.view_settings.view_transform = 'Standard'
    w = bpy.data.worlds.new("белый")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (1, 1, 1, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 1.0
    sc.world = w
    m = bpy.data.materials.new("силуэт")
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.type != 'OUTPUT_MATERIAL':
            nt.nodes.remove(n)
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs[0].default_value = (0, 0, 0, 1)
    e.inputs[1].default_value = 1.0
    nt.links.new(e.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
    for o in bpy.data.objects:
        if o.type == 'MESH':
            o.data.materials.clear()
            o.data.materials.append(m)
    cd = bpy.data.cameras.new("обмерная")
    cd.lens = 135.0
    cam = bpy.data.objects.new("обмерная", cd)
    bpy.context.collection.objects.link(cam)
    sc.camera = cam
    return cam


def silhouette_shot(arm, cam, out, frame=None, dist=9.0, height=0.86):
    sc = bpy.context.scene
    if frame is not None:
        sc.frame_set(frame)
    dg = bpy.context.evaluated_depsgraph_get()
    a = arm.evaluated_get(dg)
    f = facing(a)
    h = a.pose.bones["Hips"].head
    aim = Vector((h.x, h.y, height))
    cam.location = aim + f * dist
    cam.rotation_euler = (aim - cam.location).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = out
    bpy.ops.render.render(write_still=True)
    print("[силуэт] %s" % out)
