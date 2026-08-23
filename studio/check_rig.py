#!/usr/bin/env python3
"""ПРОВЕРКА ДВИЖЕНИЯ ЧИСЛАМИ. Смотрит на СЕТКУ, а не на кости.

ЗАЧЕМ ИМЕННО ТАК. Сегодня я дважды ошибся в одну сторону: мерил кости, а
рвалась сетка. Скелет показывал безупречные числа — длины костей сохранялись
до миллиметра — и я на этом основании написал «походка легла верно». А в кадре
торс уезжал отдельно от ног. Кости были правы, привязка нет.

ПОЭТОМУ ЗДЕСЬ МЕРЯЕТСЯ ТО, ЧТО ВИДИТ ГЛАЗ: вычисленная сетка после всех
модификаторов. Пять проверок, каждая ловит свой класс поломки:

  РАСТЯЖЕНИЕ РЁБЕР — главная. Для каждого ребра сетки сравнивается длина в
    кадре с длиной в позе покоя. Ткань и кожа почти не тянутся; ребро,
    растянутое вдвое, means привязка сломана. Именно это поймало бы разрыв
    из-за масштаба сразу, а не после рендера.
  ХОД КИСТЕЙ — ловит «руки не машут». За шаг кисть проходит заметный путь;
    если она стоит, значит углы плеча не доехали. Я это пропустил ГЛАЗАМИ,
    разглядывая шесть кадров.
  ВЫСОТА СТОПЫ — ловит и провал под землю, и полёт над ней.
  ПРОСКАЛЬЗЫВАНИЕ ОПОРНОЙ СТОПЫ — ловит «конькобежца»: стопа стоит на земле,
    а тело едет мимо. Самый заметный на глаз порок игровой ходьбы.
  ПРОНИКНОВЕНИЕ ОДЕЖДЫ — доля вершин одежды, оказавшихся ВНУТРИ тела.

ПОРЯДОК ПРОВЕРКИ: СНАЧАЛА ГОЛОЕ ТЕЛО. Одежда добавляет свои поломки поверх
чужих, и разбирать их вместе — тратить время впустую. Это ровно та ошибка,
которую я и совершил: оделся и стал разглядывать, вместо того чтобы сперва
убедиться, что едет само тело.

Запуск (внутри Блендера):
  from check_rig import report; report(body, arm, frames=(1,5,10,15,20))
"""
import math

import bpy
from mathutils import Vector


def _evaluated(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    return ev.to_mesh(), ev


def _edge_lengths(ob):
    me, ev = _evaluated(ob)
    M = ob.matrix_world
    out = []
    for e in me.edges:
        a = M @ me.vertices[e.vertices[0]].co
        b = M @ me.vertices[e.vertices[1]].co
        out.append((a - b).length)
    ev.to_mesh_clear()
    return out


def _verts(ob):
    me, ev = _evaluated(ob)
    M = ob.matrix_world
    out = [M @ v.co for v in me.vertices]
    ev.to_mesh_clear()
    return out


def stretch(ob, rest, frames):
    """Насколько рвётся сетка. Возвращает худшее растяжение по всем кадрам."""
    worst = 1.0
    worst_f = 0
    over = 0
    for f in frames:
        bpy.context.scene.frame_set(f)
        cur = _edge_lengths(ob)
        for r, c in zip(rest, cur):
            if r < 1e-6:
                continue
            k = c / r
            if k > worst:
                worst, worst_f = k, f
            if k > 1.6:
                over += 1
    return worst, worst_f, over


def bone_travel(arm, name, frames):
    """Сколько прошла кость за все кадры. Ноль — значит не двигалась."""
    pts = []
    for f in frames:
        bpy.context.scene.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        pts.append(arm.evaluated_get(dg).pose.bones[name].head.copy())
    path = sum((b - a).length for a, b in zip(pts, pts[1:]))
    # ход ОТНОСИТЕЛЬНО таза: иначе кисть «идёт» просто потому, что идёт человек
    hips = []
    for f in frames:
        bpy.context.scene.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        hips.append(arm.evaluated_get(dg).pose.bones["Hips"].head.copy())
    rel = [p - h for p, h in zip(pts, hips)]
    rel_path = sum((b - a).length for a, b in zip(rel, rel[1:]))
    return path, rel_path


def foot_check(arm, frames, ground=0.0):
    """Высота стоп и проскальзывание опорной.

    Опорной считается та стопа, что в этом кадре ниже. Если она стоит на
    земле, её горизонтальный сдвиг между кадрами обязан быть около нуля;
    всё, что больше — это конькобежец.
    """
    lo = {"LeftFoot": [], "RightFoot": []}
    slip = 0.0
    prev = {}
    for f in frames:
        bpy.context.scene.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        a = arm.evaluated_get(dg)
        h = {n: a.pose.bones[n].head.copy() for n in lo}
        for n in lo:
            lo[n].append(h[n].z)
        stance = min(lo, key=lambda n: h[n].z)
        if stance in prev and h[stance].z < min(lo[stance]) + 0.03:
            d = h[stance] - prev[stance]
            slip += math.hypot(d.x, d.y)
        prev = h
    return lo, slip


def report(body, arm, frames, clothes=()):
    """Полный отчёт. Печатает числа и явно говорит, что не в порядке."""
    sc = bpy.context.scene
    sc.frame_set(frames[0])
    print("=" * 66)
    print("ПРОВЕРКА ДВИЖЕНИЯ: %d кадров, тело %s" % (len(frames), body.name))

    # растяжение считаем от ПОЗЫ ПОКОЯ, для чего временно снимаем анимацию
    act = arm.animation_data.action if arm.animation_data else None
    if act:
        arm.animation_data.action = None
    bpy.context.view_layer.update()
    rest = _edge_lengths(body)
    if act:
        arm.animation_data.action = act
    bpy.context.view_layer.update()

    w, wf, over = stretch(body, rest, frames)
    verdict = "ЦЕЛА" if w < 1.6 else "РВЁТСЯ"
    print("  сетка тела:      худшее растяжение ребра %.2f× (кадр %d), "
          "рёбер сверх 1.6×: %d — %s" % (w, wf, over, verdict))

    for hand in ("LeftHand", "RightHand"):
        if hand in arm.pose.bones:
            _, rel = bone_travel(arm, hand, frames)
            v = "МАШЕТ" if rel > 0.15 else "НЕ ДВИГАЕТСЯ"
            print("  %-10s ход относительно таза %.3f м — %s" % (hand, rel, v))

    lo, slip = foot_check(arm, frames)
    for n, zs in lo.items():
        print("  %-10s высота %.3f..%.3f м" % (n, min(zs), max(zs)))
    v = "НЕТ" if slip < 0.10 else "ЕСТЬ, %.2f м" % slip
    print("  проскальзывание опорной стопы: %s" % v)

    for c in clothes:
        vb = set()
        sc.frame_set(frames[len(frames) // 2])
        bv = _verts(body)
        cv = _verts(c)
        # грубо: доля вершин одежды ближе к оси, чем ближайшая вершина тела
        inside = 0
        for p in cv[::7]:
            near = min(bv[::11], key=lambda q: (q - p).length_squared)
            if (p - near).length < 0.001:
                inside += 1
        print("  %-12s вершин внутри тела: %d из %d"
              % (c.name, inside, len(cv[::7])))
    print("=" * 66)
