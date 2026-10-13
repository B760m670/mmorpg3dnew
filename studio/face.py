#!/usr/bin/env python3
"""ЛИЦО: речь, мимика, взгляд, моргание.

ВСЁ ЭТО УЖЕ БЫЛО РЯДОМ, и я опять чуть не полез лепить руками. У MPFB есть
служба FaceService и три набора целей, которые ставятся ключами формы:
  faceunits01 — 52 единицы ARKit. Это отраслевой стандарт лицевой анимации:
    jawOpen, eyeBlinkLeft/Right, mouthSmileLeft/Right, browInnerUp, взгляд
    eyeLook* и так далее. Под него сняты тысячи готовых записей мимики.
  visemes01 — 22 визимы речи по стандарту Microsoft/SSML.
  visemes02 — 15 визим Meta/ARKit, под них сделан аддон синхронизации губ.
Наборы НЕ входят в MPFB и качаются отдельно с makehumancommunity.org; без них
FaceService.load_targets молча ничего не грузит.

ЧЕГО ОДНИМИ КЛЮЧАМИ НЕ СДЕЛАТЬ — ВЗГЛЯД. Ключи ARKit eyeLook* двигают ВЕКИ, а
не глазное яблоко: яблоко это отдельная сетка, и вращать его надо костью.
Поэтому здесь ставятся две кости в центрах яблок.

ЧИСЛА, К КОТОРЫМ ВЕДЁМ (измерено на живых, не выдумано):
  открытие рта предельное      50.3–54.2 мм между резцами (несколько работ)
  открытие рта при речи        15–20 мм
  моргание: длительность       100–400 мс, смыкание 50–100 мс
  моргание: частота            15–20 раз в минуту
  межзрачковое расстояние      64 мм у мужчин
"""
import importlib
import math

import bpy
from mathutils import Vector

ADDON = "bl_ext.user_default.mpfb"

# ИЗМЕРЕНО у живых — сюда сверяться, а не к ощущению «похоже»
MOUTH_MAX_MM = (50.3, 54.2)     # предельное открытие между резцами
MOUTH_SPEECH_MM = (15.0, 20.0)  # при обычной речи
BLINK_MS = (100.0, 400.0)       # вся длительность моргания
BLINK_CLOSE_MS = (50.0, 100.0)  # только смыкание
BLINK_PER_MIN = (15.0, 20.0)
IPD_MM = 64.0                   # межзрачковое у мужчин

EYE_BONES = ("глаз.L", "глаз.R")


def svc(name):
    return importlib.import_module("%s.services.%s" % (ADDON, name))


def _fsmod():
    return svc("faceservice")


def unit_names(body):
    """Имена лицевых ключей, которые ЕСТЬ на этом теле."""
    f = _fsmod()
    kb = body.data.shape_keys.key_blocks if body.data.shape_keys else {}
    return [n for n in (f.ARKIT_FACEUNITS + f.MICROSOFT_VISEMES + f.META_VISEMES)
            if n in kb]


def load(body, verbose=True):
    """Поставить лицевые ключи и ПЕРЕНЕСТИ их на зубы, язык и глаза.

    Перенос обязателен: ключи живут на теле, а зубы и язык — отдельные сетки.
    Без переноса при открытом рте нижние зубы остаются висеть на месте.
    """
    FaceService = _fsmod().FaceService
    before = len(body.data.shape_keys.key_blocks) if body.data.shape_keys else 0
    FaceService.load_targets(body, load_microsoft_visemes=True,
                             load_meta_visemes=True, load_arkit_faceunits=True)
    FaceService.interpolate_targets(body)
    bpy.context.view_layer.update()
    got = unit_names(body)
    if verbose:
        after = len(body.data.shape_keys.key_blocks)
        print("[лицо] ключей %d -> %d, лицевых из них %d" % (before, after, len(got)))
        if not got:
            print("[лицо] НАБОРЫ НЕ УСТАНОВЛЕНЫ: нужны faceunits01, visemes01,"
                  " visemes02 с makehumancommunity.org")
    return got


def children(body):
    """Сетки, которые обязаны двигаться вместе с лицом."""
    out = []
    for o in bpy.data.objects:
        if o.type != 'MESH' or o is body:
            continue
        if o.parent is body or (o.name.startswith(body.name + ".")):
            out.append(o)
    return out


def set_units(body, values, kids=None):
    """Поставить значения единиц на теле И на всех его сетках разом."""
    kb = body.data.shape_keys.key_blocks
    kids = children(body) if kids is None else kids
    for name, v in values.items():
        if name in kb:
            kb[name].value = v
        for o in kids:
            sk = o.data.shape_keys
            if sk and name in sk.key_blocks:
                sk.key_blocks[name].value = v


def clear_units(body, kids=None):
    set_units(body, {n: 0.0 for n in unit_names(body)}, kids)


def pupil_pos(eyes):
    """Самая передняя точка каждого яблока — роговица, то есть зрачок.

    ПРОВЕРЯТЬ ВЗГЛЯД НАДО ПО НЕЙ, А НЕ ПО ЦЕНТРУ ЯБЛОКА. Я сначала мерил
    смещение центра и получил 0.00 мм, что и записал в успех: мол, яблоко
    вращается вокруг себя. Но у НЕПОДВИЖНОГО яблока центр смещается ровно так
    же — на ноль. Замер не различал поворот и бездействие. Поворот на 18° при
    радиусе 12 мм двигает зрачок примерно на 3.7 мм — вот это и надо видеть.
    """
    dg = bpy.context.evaluated_depsgraph_get()
    ev = eyes.evaluated_get(dg)
    me = ev.to_mesh()
    M = eyes.matrix_world
    pts = [M @ v.co for v in me.vertices]
    ev.to_mesh_clear()
    L = [p for p in pts if p.x > 0]
    R = [p for p in pts if p.x < 0]
    front = lambda s: min(s, key=lambda p: p.y) if s else None
    return front(L), front(R)


def eye_centres(eyes):
    """Центры двух глазных яблок. Сетка одна на оба глаза, делим по x."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = eyes.evaluated_get(dg)
    me = ev.to_mesh()
    M = eyes.matrix_world
    pts = [M @ v.co for v in me.vertices]
    ev.to_mesh_clear()
    L = [p for p in pts if p.x > 0]
    R = [p for p in pts if p.x < 0]
    mean = lambda s: (sum(s, Vector()) / len(s)) if s else None
    return mean(L), mean(R)


def add_eye_bones(body, arm, eyes, verbose=True):
    """Две кости в центрах глазных яблок, чтобы взгляд мог двигаться.

    ПОЧЕМУ КОСТИ, А НЕ КЛЮЧИ. Единицы ARKit eyeLook* двигают веки — это верно
    и нужно, но само яблоко они не поворачивают: оно отдельная сетка со своим
    центром. Поворачивать объект целиком тоже нельзя: оба глаза в одной сетке
    и оба пойдут вокруг общего центра, то есть разъедутся.
    """
    if arm is None or eyes is None:
        return 0
    cl, cr = eye_centres(eyes)
    if cl is None or cr is None:
        return 0
    head = None
    for n in ("Head", "head", "neck02", "Neck"):
        if n in arm.data.bones:
            head = n
            break
    prev = bpy.context.view_layer.objects.active
    bpy.ops.object.select_all(action='DESELECT')
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    for name, c in zip(EYE_BONES, (cl, cr)):
        if name in arm.data.edit_bones:
            arm.data.edit_bones.remove(arm.data.edit_bones[name])
        eb = arm.data.edit_bones.new(name)
        loc = arm.matrix_world.inverted() @ c
        eb.head = loc
        eb.tail = loc + Vector((0.0, -0.025, 0.0))   # вперёд: куда смотрит
        if head:
            eb.parent = arm.data.edit_bones[head]
        eb.use_deform = True
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.objects.active = prev

    # ВЕСА: яблоко должно слушаться ТОЛЬКО своей кости.
    # Первый заход этого не сделал, и взгляд не двигался вовсе: MPFB уже
    # привязал глаза к голове с весом 1, я добавил свою группу тоже с весом 1,
    # Блендер веса нормализует — и яблоко поехало на полпути между головой и
    # своей костью, то есть почти никуда. Поэтому старые группы у этих вершин
    # обнуляются.
    for name in EYE_BONES:
        if name in eyes.vertex_groups:
            eyes.vertex_groups.remove(eyes.vertex_groups[name])
    M = eyes.matrix_world
    li, ri = [], []
    for i, v in enumerate(eyes.data.vertices):
        (li if (M @ v.co).x > 0 else ri).append(i)
    for g in list(eyes.vertex_groups):
        g.remove(li + ri)
    gl = eyes.vertex_groups.new(name=EYE_BONES[0])
    gr = eyes.vertex_groups.new(name=EYE_BONES[1])
    gl.add(li, 1.0, 'REPLACE')
    gr.add(ri, 1.0, 'REPLACE')
    if not any(m.type == 'ARMATURE' for m in eyes.modifiers):
        m = eyes.modifiers.new("Armature", 'ARMATURE')
        m.object = arm
        eyes.parent = arm
    if verbose:
        print("[взгляд] кости глаз поставлены, вершин слева %d, справа %d, "
              "межзрачковое %.0f мм (у мужчин 64)"
              % (len(li), len(ri), (cl - cr).length * 1000))
    return 2


def look(arm, yaw_deg, pitch_deg):
    """Повернуть взгляд. Вбок — yaw, вверх-вниз — pitch, в градусах.

    Предел вращения глаза около ±45°, но в разговоре взгляд ходит в пределах
    ±15–20°: дальше человек поворачивает голову, а не глаза.
    """
    n = 0
    for name in EYE_BONES:
        pb = arm.pose.bones.get(name)
        if pb is None:
            continue
        pb.rotation_mode = 'XYZ'
        pb.rotation_euler = (math.radians(pitch_deg), 0.0,
                             math.radians(yaw_deg))
        n += 1
    return n
