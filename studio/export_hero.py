#!/usr/bin/env python3
"""ГЕРОЙ В ИГРУ: сборка, ходьба, постановка на землю, вывод в glTF.

ЗАЧЕМ ОТДЕЛЬНЫЙ ФАЙЛ. До сих пор человек существовал только в Блендере: в
`game2/` персонажа нет вовсе. Пока он не в игре, всё сделанное — картинки.
Здесь собирается ровно то, что игра может открыть: один .glb со скелетом,
одеждой и одним циклом ходьбы.

ЦИКЛ, А НЕ ОТРЕЗОК. Из записи вырезается кусок от постановки левой стопы до
следующей постановки левой — тогда клип крутится петлёй.
ИЗМЕРЕНО на записи CMU 07_01: цикл 1.12 с, шаг 1.515 м, скорость 1.35 м/с,
шов петли в среднем 3.4°, худшая кость 12°. Это ходьба взрослого человека
(норма 1.0–1.2 с и 1.2–1.4 м/с) — и это единственная независимая проверка
того, что перенос движения не врёт: числа походки не подгонялись ни под что.

НА МЕСТЕ, А НЕ С ПЕРЕМЕЩЕНИЕМ. Горизонтальный ход из клипа вычитается: пусть
персонажа двигает игра, а анимация только шагает. Так походка сцепляется со
скоростью (шаг ускоряется — значит и ноги), и так проще с физикой и склонами.
Боковое покачивание таза при этом остаётся: оно настоящее.

Запуск:
  LIBGL_ALWAYS_SOFTWARE=1 xvfb-run -a /opt/blender/blender -b -noaudio \
      -P studio/export_hero.py -- --out game2/assets/hero/hero.glb [--nude]
"""
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ground   # noqa: E402
import hero     # noqa: E402
import mocap    # noqa: E402

ASF = os.environ.get("CMU_ASF", "/tmp/claude-live/mocap/07.asf")
AMC = os.environ.get("CMU_AMC", "/tmp/claude-live/mocap/07_01.amc")
STEP = 3          # 120 к/с записи -> 40 к/с клипа
CLIP = "ходьба"


def inplace(arm, f0, f1, root="Hips"):
    """Вычесть из корня равномерный горизонтальный ход за цикл.

    Вычитается именно ПРЯМАЯ между началом и концом цикла, а не всё движение:
    покачивание таза вбок и вверх-вниз — часть настоящей походки, его трогать
    нельзя. Уходит только равномерный проезд вперёд.
    """
    pb = arm.pose.bones[root]
    rest = arm.data.bones[root].matrix_local.to_3x3()
    Wi = arm.matrix_world.to_3x3().inverted()
    pts = {}
    for f in (f0, f1):
        bpy.context.scene.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        pts[f] = arm.evaluated_get(dg).pose.bones[root].head.copy()
    d = pts[f1] - pts[f0]
    d.z = 0.0
    for f in range(f0, f1 + 1):
        bpy.context.scene.frame_set(f)
        w = (f - f0) / max(1, f1 - f0)
        pb.location = pb.location - rest.transposed() @ (Wi @ (d * w))
        pb.keyframe_insert("location", frame=f)
    bpy.context.view_layer.update()
    print("[клип] ход вперёд вычтен: %.3f м за %d кадров" % (d.length, f1 - f0))
    return d.length


def trim(arm, f0, f1):
    """Оставить в действии только кадры цикла и подвинуть их к единице."""
    act = arm.animation_data.action
    for fc in list(act.fcurves):
        keep = [kp for kp in fc.keyframe_points if f0 <= kp.co.x <= f1]
        if not keep:
            act.fcurves.remove(fc)
            continue
        vals = [(kp.co.x - f0 + 1, kp.co.y) for kp in keep]
        for _ in range(len(fc.keyframe_points)):
            fc.keyframe_points.remove(fc.keyframe_points[0], fast=True)
        fc.keyframe_points.add(len(vals))
        for kp, (x, y) in zip(fc.keyframe_points, vals):
            kp.co = (x, y)
            kp.interpolation = 'LINEAR'
        fc.update()
    act.name = CLIP
    if hasattr(act, "use_frame_range"):
        act.use_frame_range = True
        act.frame_start = 1
        act.frame_end = f1 - f0 + 1
    sc = bpy.context.scene
    sc.frame_start = 1
    sc.frame_end = f1 - f0 + 1
    print("[клип] обрезан до %d кадров, назван «%s»" % (sc.frame_end, CLIP))


IDLE = "покой"
# ДЫХАНИЕ. ИЗМЕРЕНО у взрослых в покое: 12–20 вдохов в минуту; берём 15, то
# есть 4 секунды на вдох-выдох. Ход грудной клетки при спокойном дыхании
# 1–2 см; в кадре через плечо видно верх спины, и полсантиметра подъёма плеч
# читается, а сантиметр уже похож на вздох.
IDLE_BREATH_S = 4.0
IDLE_RISE = 0.005          # на сколько поднимается грудь, м
IDLE_SWAY = 0.004          # боковое качание таза, м — человек не статуя


def idle_clip(arm, fps=40):
    """Отдельный клип СТОЯНИЯ. Без него человек в покое замирает в шаге.

    ЗАЧЕМ ОТДЕЛЬНЫЙ КЛИП, А НЕ «нулевой кадр ходьбы». Нулевой кадр записи —
    это момент постановки стопы: ноги врозь, вес на одной. Остановившийся на
    нём человек выглядит выключенным в полушаге, и это первое, что видно в
    игре. Стойка — отдельное состояние, а не точка внутри шага.

    Поза берётся из studio/idle.py: она построена наведением костей на
    направления (не поворотом на углы, потому что покой у нашей сетки —
    А-поза), решена на левой стороне и отзеркалена на правую, отчего
    расхождение сторон ровно 0.0 мм.
    """
    import idle
    import math as _m
    sc = bpy.context.scene
    n = max(2, int(round(IDLE_BREATH_S * fps)))
    if arm.animation_data is None:
        arm.animation_data_create()
    act = bpy.data.actions.new(IDLE)
    prev = arm.animation_data.action
    arm.animation_data.action = act

    idle.apply_base(arm)
    base_loc = {pb.name: pb.location.copy() for pb in arm.pose.bones}
    base_rot = {pb.name: pb.rotation_quaternion.copy() for pb in arm.pose.bones}

    root = arm.pose.bones.get("Hips")
    chest = arm.pose.bones.get("Spine1") or arm.pose.bones.get("Spine")
    for i in range(n + 1):
        f = 1 + i
        t = (i % n) / float(n)
        # дыхание — один полный цикл на клип; качание вдвое медленнее, чтобы
        # два движения не совпадали по фазе и не читались как один толчок
        br = (1.0 - _m.cos(2.0 * _m.pi * t)) * 0.5
        sw = _m.sin(2.0 * _m.pi * t * 0.5)
        for pb in arm.pose.bones:
            pb.location = base_loc[pb.name].copy()
            pb.rotation_quaternion = base_rot[pb.name].copy()
        if chest is not None:
            chest.location = base_loc[chest.name] + Vector((0.0, IDLE_RISE * br, 0.0))
        if root is not None:
            root.location = base_loc[root.name] + Vector((IDLE_SWAY * sw, 0.0, 0.0))
        for pb in arm.pose.bones:
            pb.keyframe_insert("location", frame=f)
            pb.keyframe_insert("rotation_quaternion", frame=f)
    for fc in act.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = 'LINEAR'
        fc.update()
    if hasattr(act, "use_frame_range"):
        act.use_frame_range = True
        act.frame_start = 1
        act.frame_end = n + 1
    arm.animation_data.action = prev
    # ДЕЙСТВИЕ НАДО УДЕРЖАТЬ ОТ СБОРЩИКА: у действия без пользователей счётчик
    # нулевой, и до экспорта оно не доживёт.
    act.use_fake_user = True
    print("[клип] «%s»: %d кадров, дыхание %.1f с, подъём груди %.0f мм, "
          "качание таза %.0f мм" % (IDLE, n + 1, IDLE_BREATH_S,
                                     IDLE_RISE * 1000, IDLE_SWAY * 1000))
    return act


# ПРЕДЕЛ РАЗМЕРА ТЕКСТУРЫ, в пикселях. Первый вывод весил 80 МБ, из них 46 —
# две карты пальто по 4096². На телефоне такая карта занимает столько же
# видеопамяти, сколько весь остальной герой, а на экране 6.9 дюйма её никто
# не различит. Лицо — исключение: камера через плечо смотрит на затылок и
# щёку вплотную, поэтому коже оставляем 2048.
CAP = [("Jartur", 2048), ("eye", 512), ("eyelash", 256), ("eyebrow", 256),
       ("teeth", 256), ("tongue", 256), ("short02", 1024)]
CAP_DEFAULT = 1024


def shrink():
    """Ужать текстуры до разумного и заставить экспортёр их пережать."""
    было = после = 0
    for im in bpy.data.images:
        # В фоновом Блендере картинка не загружена, пока её не тронешь:
        # has_data лжёт False, size показывает нули. Поэтому сначала reload.
        if im.size[0] == 0:
            try:
                im.reload()
            except Exception:
                pass
        w, h = im.size
        if w == 0:
            continue
        было += w * h
        cap = CAP_DEFAULT
        for key, c in CAP:
            if key.lower() in im.name.lower():
                cap = c
                break
        k = max(w, h) / float(cap)
        if k > 1.0:
            im.scale(max(1, int(w / k)), max(1, int(h / k)))
            print("[текстуры] %-46s %dx%d -> %dx%d"
                  % (im.name[:46], w, h, im.size[0], im.size[1]))
        после += im.size[0] * im.size[1]
    print("[текстуры] пикселей всего: %.1f -> %.1f млн"
          % (было / 1e6, после / 1e6))


def bake_helpers(ob, verbose=True):
    """Выбросить служебную оболочку НАСОВСЕМ, а не прятать её модификатором.

    У тела MakeHuman поверх сетки лежит служебная оболочка, и её скрывает
    модификатор «маска». Модификатор нельзя ни применить к сетке с ключами
    формы, ни оставить: экспорт с применением модификаторов ключи вырезает.
    Выход — удалить эти вершины по-настоящему. Удаление вершин ключи формы
    переживают: Блендер вычёркивает вершину из каждого ключа разом.
    """
    import bmesh
    m = next((x for x in ob.modifiers if x.type == 'MASK'), None)
    if m is None or not m.vertex_group or m.vertex_group not in ob.vertex_groups:
        return 0
    gi = ob.vertex_groups[m.vertex_group].index
    inv = getattr(m, "invert_vertex_group", False)
    kill = []
    for v in ob.data.vertices:
        w = any(g.group == gi and g.weight > 0.0 for g in v.groups)
        keep = (not w) if inv else w
        if not keep:
            kill.append(v.index)
    if kill:
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bm.verts.ensure_lookup_table()
        bmesh.ops.delete(bm, geom=[bm.verts[i] for i in kill], context='VERTS')
        bm.to_mesh(ob.data)
        bm.free()
    ob.modifiers.remove(m)
    if verbose:
        print("[экспорт] %s: служебных вершин удалено %d, осталось %d"
              % (ob.name, len(kill), len(ob.data.vertices)))
    return len(kill)


def bake_shape_basis(ob, keep, verbose=True):
    """Впечь формообразующие ключи в базис, оставить только нужные игре.

    ЗАЧЕМ. Тело MakeHuman собрано ключами формы: пол, возраст, мышцы, все
    measure-*, наши правки подбородка и ушей. В .glb они уезжают как цели
    морфа с постоянными весами — то есть игра обязана каждый кадр держать
    полсотни морфов только для того, чтобы человек оставался собой. Это и
    лишний вес файла, и лишняя работа на телефоне, и ловушка: движок, который
    веса по умолчанию не применит, покажет неподогнанную болванку.

    ПОЧЕМУ НЕЛЬЗЯ ПРОСТО ПОДМЕНИТЬ БАЗИС. Ключ хранит АБСОЛЮТНЫЕ положения, а
    работает разностью «ключ минус базис». Сдвинешь базис — все лицевые ключи
    поедут на ту же величину в обратную сторону. Поэтому дельта прибавляется
    и к базису, И К КАЖДОМУ оставляемому ключу: разность тогда сохраняется.
    """
    sk = ob.data.shape_keys
    if sk is None:
        return 0
    kb = sk.key_blocks
    basis = kb[0]
    n = len(basis.data)
    drop = [k for k in kb[1:] if k.name not in keep]
    if not drop:
        return 0
    delta = [Vector((0.0, 0.0, 0.0)) for _ in range(n)]
    for k in drop:
        v = k.value
        if abs(v) < 1e-6:
            continue
        for i in range(n):
            d = k.data[i].co - basis.data[i].co
            if d.length_squared > 1e-14:
                delta[i] += d * v
    for i in range(n):
        basis.data[i].co = basis.data[i].co + delta[i]
    for k in kb[1:]:
        if k.name in keep:
            for i in range(n):
                k.data[i].co = k.data[i].co + delta[i]
    for k in drop:
        ob.shape_key_remove(k)
    for i, v in enumerate(ob.data.vertices):
        v.co = basis.data[i].co
    if verbose:
        print("[экспорт] %s: впечено в базис %d ключей, осталось %d"
              % (ob.name, len(drop), len(ob.data.shape_keys.key_blocks) - 1))
    return len(drop)


def bake_all_shapes(verbose=True):
    """Оставить в файле только лицевые ключи: мимику и речь."""
    try:
        import face as face_mod
        import importlib
        fs = importlib.import_module("bl_ext.user_default.mpfb.services.faceservice")
        keep = set(fs.ARKIT_FACEUNITS + fs.MICROSOFT_VISEMES + fs.META_VISEMES)
    except Exception as e:
        print("[экспорт] список лицевых не собрался (%s) — ключи не трогаем"
              % str(e)[:50])
        return 0
    total = 0
    for ob in bpy.data.objects:
        if ob.type == 'MESH' and ob.data.shape_keys:
            total += bake_shape_basis(ob, keep, verbose=verbose)
    if verbose:
        print("[экспорт] формообразующих ключей впечено всего: %d" % total)
    return total


def bake_modifiers(verbose=True):
    """Запечь модификаторы ДО экспорта, по-разному для двух видов сеток.

    ПОЧЕМУ НЕ ПОЛАГАТЬСЯ НА ГАЛОЧКУ ЭКСПОРТЁРА. `export_apply` в Блендере
    описан прямым текстом: «WARNING: prevents exporting shape keys», и в коде
    экспортёра стоит «shape keys are not preserved if we apply modifiers».
    То есть с ней все 89 лицевых ключей в .glb не попадут и лицо в игре
    останется неподвижным. А без неё одежда потеряет смещение слоёв и толщину.
    Поэтому: у кого ключей нет (одежда) — модификаторы применяются
    разрушительно; у кого есть (тело, зубы, язык, глаза, брови, ресницы,
    волосы) — маска выпекается удалением вершин, остальное снимается.
    Арматуру не трогаем ни у кого: её экспортёр везёт сам.
    """
    applied = stripped = 0
    for ob in list(bpy.data.objects):
        if ob.type != 'MESH':
            continue
        has_keys = ob.data.shape_keys is not None
        if has_keys:
            bake_helpers(ob, verbose=verbose)
            for m in list(ob.modifiers):
                if m.type == 'ARMATURE':
                    continue
                # остальное к сетке с ключами не применить — снимаем
                if verbose:
                    print("[экспорт] %s: снят модификатор %s (сетка с ключами)"
                          % (ob.name, m.type))
                ob.modifiers.remove(m)
                stripped += 1
            continue
        bpy.context.view_layer.objects.active = ob
        for m in list(ob.modifiers):
            if m.type == 'ARMATURE':
                continue
            # МОДИФИКАТОР, ВЫКЛЮЧЕННЫЙ ВО ВЬЮПОРТЕ, НЕ ПРИМЕНЯЕТСЯ ВОВСЕ:
            # «Modifier is disabled, skipping apply». MPFB вешает на одежду
            # подразделение только для рендера, и в игру одежда уезжала гранёной
            # — пять предметов из пяти. Включаем показ перед применением.
            m.show_viewport = True
            try:
                bpy.ops.object.modifier_apply(modifier=m.name)
                applied += 1
            except Exception as e:
                print("[экспорт] %s: %s не применился (%s)"
                      % (ob.name, m.type, str(e)[:40]))
    if verbose:
        print("[экспорт] модификаторов применено %d, снято %d" % (applied, stripped))
    return applied, stripped


def check_glb(path):
    """Доехали ли ключи формы. Смотрим в сам файл, а не верим экспортёру."""
    import json
    import struct
    with open(path, "rb") as f:
        magic, ver, total = struct.unpack("<III", f.read(12))
        if magic != 0x46546C67:
            print("[проверка] это не glb")
            return None
        ln, kind = struct.unpack("<II", f.read(8))
        js = json.loads(f.read(ln).decode("utf-8"))
    tgt = 0
    named = []
    for me in js.get("meshes", []):
        for p in me.get("primitives", []):
            tgt += len(p.get("targets", []))
        if me.get("extras", {}).get("targetNames"):
            named = me["extras"]["targetNames"]
    print("[проверка] в файле сеток %d, целей морфа %d"
          % (len(js.get("meshes", [])), tgt))
    if named:
        face = [n for n in named if n in ("jawOpen", "eyeBlinkLeft",
                                          "mouthSmileLeft", "viseme_aa")]
        print("[проверка] лицевые на месте: %s"
              % (", ".join(face) if face else "НЕТ НИ ОДНОЙ"))
    return tgt


# ПРОЗРАЧНОСТЬ РАЗДАЁТСЯ ПОИМЕННО, А НЕ ВСЕМ ПОДРЯД.
#
# В игре пальто пропало. В файле оно было — меш на месте, цвет 0.17 записан, —
# а в кадре его не было. Причина нашлась в JSON выведенного файла: У ВСЕХ
# ВОСЕМНАДЦАТИ материалов стоял alphaMode = BLEND, включая кожу, сапоги и
# штаны. Прозрачное смешение не пишет глубину: слои перестают закрывать друг
# друга, порядок отрисовки решается сортировкой по расстоянию и пляшет от угла
# камеры. Одежда тонула в теле, тело в одежде.
#
# ОТКУДА ВЗЯЛОСЬ: у mhmat-файлов почти всегда стоит transparent True и
# alphaToCoverage True — это верно для волос и ресниц, где вырез делается
# альфой, и бессмысленно для сукна. MakeSkin переносит флаг как есть, а
# экспортёр — дальше в файл.
#
# ПРОЗРАЧНОСТЬ НУЖНА РОВНО ТАМ, ГДЕ ФОРМА ЗАДАНА ВЫРЕЗОМ В КАРТИНКЕ: волосы,
# брови, ресницы. Им ставим MASK (порог, глубина пишется), остальным OPAQUE.
ALPHA_MASK = ("short01", "eyebrow", "eyelash", "hair")
# А ВОТ ГЛАЗУ ПРОЗРАЧНОСТЬ НУЖНА НАСТОЯЩАЯ, И ЭТО МОЯ ЖЕ ОШИБКА, ПОЙМАННАЯ
# КРУПНЫМ ПЛАНОМ. У высокополигонального глаза MPFB две оболочки на одном
# материале: само яблоко с радужкой и поверх него роговица. На развёртке
# роговице отведён белый круг в углу картинки, и держится она только альфой.
# Переведя ВСЕ материалы в непрозрачные, я накрыл радужку белым куполом:
# в кадре у человека вместо глаз были плоские голубые миндалины без зрачка.
# Порога тут мало — роговица полупрозрачна по всей площади, а не вырезана.
ALPHA_BLEND = ("high-poly", "cornea")


def fix_alpha(path):
    """Переписать alphaMode в готовом glb. Правится файл, а не Блендер.

    Так честнее: между материалом Блендера и записью в файле стоит экспортёр
    со своими правилами, и проверять надо то, что уехало, а не то, что задано.
    """
    import json
    import struct
    with open(path, "rb") as f:
        data = f.read()
    magic, ver, total = struct.unpack("<III", data[:12])
    if magic != 0x46546C67:
        print("[прозрачность] это не glb")
        return
    ln, kind = struct.unpack("<II", data[12:20])
    js = json.loads(data[20:20 + ln].decode("utf-8"))
    rest = data[20 + ln:]
    было = {}
    for m in js.get("materials", []):
        было[m.get("alphaMode", "OPAQUE")] = было.get(
            m.get("alphaMode", "OPAQUE"), 0) + 1
        name = (m.get("name") or "").lower()
        if any(k in name for k in ALPHA_MASK):
            m["alphaMode"] = "MASK"
            m["alphaCutoff"] = 0.35
        elif any(k in name for k in ALPHA_BLEND):
            m["alphaMode"] = "BLEND"
            m.pop("alphaCutoff", None)
        else:
            m["alphaMode"] = "OPAQUE"
            m.pop("alphaCutoff", None)
    стало = {}
    for m in js.get("materials", []):
        стало[m["alphaMode"]] = стало.get(m["alphaMode"], 0) + 1
    blob = json.dumps(js, ensure_ascii=False).encode("utf-8")
    blob += b" " * ((4 - len(blob) % 4) % 4)
    out = (struct.pack("<III", magic, ver, 12 + 8 + len(blob) + len(rest))
           + struct.pack("<II", len(blob), kind) + blob + rest)
    with open(path, "wb") as f:
        f.write(out)
    print("[прозрачность] было %s -> стало %s"
          % (", ".join("%s %d" % kv for kv in sorted(было.items())),
             ", ".join("%s %d" % kv for kv in sorted(стало.items()))))


def export(path):
    shrink()
    bake_modifiers()
    bake_all_shapes()
    # ПРОВЕРКА, ЧТО ЗАПЕЧЁННОЕ ТЕЛО ОСТАЛОСЬ СОБОЙ. Размер файла этого не
    # доказывает: при ошибке в пересчёте базиса в игру уехала бы неподогнанная
    # болванка MakeHuman, и заметили бы это нескоро. Меряем голову после
    # запекания и сверяем с тем же ANSUR, что и в Блендере.
    try:
        import measure_face as mf
        body = next((o for o in bpy.data.objects
                     if o.type == 'MESH' and o.name.startswith("Human")
                     and len(o.data.vertices) > 5000), None)
        eyes = next((o for o in bpy.data.objects
                     if o.type == 'MESH' and "high-poly" in o.name), None)
        if body is not None:
            # МЕРИТЬ НАДО В ПОКОЕ. Первый заход мерил тело прямо в шаге: рост
            # выходил 1.780 вместо 1.736 (в стойке фигура ниже, чем в
            # середине шага), голова наклонена, подбородок не находился вовсе,
            # уши «выросли» на 15%. Числа были не про запекание, а про позу.
            arms = [o for o in bpy.data.objects if o.type == 'ARMATURE']
            was = [(a, a.data.pose_position) for a in arms]
            for a, _ in was:
                a.data.pose_position = 'REST'
            bpy.context.view_layer.update()
            mf.report(body, eyes, "после запекания, в покое")
            for a, p in was:
                a.data.pose_position = p
            bpy.context.view_layer.update()
    except Exception as e:
        print("[экспорт] обмер после запекания не снялся: %s" % str(e)[:60])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.export_scene.gltf(
        filepath=path, export_format='GLB', use_selection=True,
        export_animations=True, export_frame_range=True,
        export_animation_mode='ACTIONS', export_skins=True,
        # export_apply ВЫКЛЮЧЕН НАМЕРЕННО: он вырезает все ключи формы, то есть
        # всю мимику и речь. Модификаторы уже запечены выше, каждый по-своему.
        export_apply=False, export_yup=True,
        export_morph=True, export_morph_normal=False,
        export_image_format='AUTO', export_jpeg_quality=88,
    )
    fix_alpha(path)
    mb = os.path.getsize(path) / 1048576.0
    print("[вывод] %s — %.1f МБ" % (path, mb))
    check_glb(path)
    return mb


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = argv[argv.index("--out") + 1] if "--out" in argv \
        else "game2/assets/hero/hero.glb"
    body = hero.build(skip_clothes=("--nude" in argv))
    arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')

    n = mocap.load_cmu(arm, ASF, AMC, start=1, count=0, step=STEP)
    F = list(range(1, n + 1))
    ground.lock(body, arm, F)
    ground.lock(body, arm, F)     # второй проход: опора уточняется по первому
    ground.report(body, arm, F, "ПЕРЕД ВЫВОДОМ")
    c = ground.cycle(body, arm, F)
    if not c:
        raise SystemExit("цикл шага не найден")
    f0, f1, dist, dur, seam = c
    inplace(arm, f0, f1)
    trim(arm, f0, f1)
    # КЛИП ПОКОЯ СТРОИТСЯ ПОСЛЕ ходьбы и НЕ становится текущим действием:
    # иначе он затрёт обрезанный цикл, и в файл уедет одна стойка.
    idle_clip(arm)

    tri = sum(len(o.data.loop_triangles) if o.data.loop_triangles else 0
              for o in bpy.data.objects if o.type == 'MESH')
    if not tri:
        for o in bpy.data.objects:
            if o.type == 'MESH':
                o.data.calc_loop_triangles()
        tri = sum(len(o.data.loop_triangles) for o in bpy.data.objects
                  if o.type == 'MESH')
    print("[герой] треугольников %d, объектов %d, костей %d"
          % (tri, len([o for o in bpy.data.objects if o.type == 'MESH']),
             len(arm.data.bones)))
    mb = export(out)
    print("[итог] клип «%s»: %.2f с, шаг %.3f м, скорость %.2f м/с, "
          "шов %.1f°, файл %.1f МБ" % (CLIP, dur, dist, dist / dur, seam, mb))


if __name__ == "__main__":
    main()
