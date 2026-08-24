#!/usr/bin/env python3
"""ТО, ЧЕГО НЕТ В БАЗОВОЙ СЕТКЕ: мужской пах.

ПОЧЕМУ ПРИШЛОСЬ ДЕЛАТЬ САМОМУ, хотя правило проекта — брать готовое.
Проверено тремя замерами подряд:
  1. Цели MakeHuman penis-length, penis-circ, penis-testicles СТОЯТ как ключи
     формы с нужными значениями — и не меняют ни одной вершины: выступ 122 мм
     и при значении 0, и при 1.
  2. В таблице групп вершин самого MPFB у базовой сетки группа genitals —
     ПУСТОЙ СПИСОК. Эти цели рассчитаны на отдельную накладку-ассет, которая
     подсаживается поверх тела; групп с вершинами там несколько, и все они
     привязаны к UUID конкретных ассетов.
  3. При поле 0.0 и 1.0 выступ одинаков — 120 и 119 мм. То есть базовая сетка
     в этом месте гладкая у обоих полов, «кукольная».
Готовой накладки в открытых паках нет: просмотрены все шесть bodyparts
(там ногти, уши, языки), поиск по сайту сообщества ничего не отдаёт.

ЧТО ЗДЕСЬ СДЕЛАНО. Не «нарисован орган», а поднята форма: две сглаженные
выпуклости — ствол и мошонка, — заданные размерами живого человека и
вдавленные в сетку изнутри. Вершины отодвигаются наружу до нужного радиуса с
мягким затуханием по краям, поэтому шва не возникает и складки не рвутся.

РАЗМЕРЫ ВЗЯТЫ ИЗ ИЗМЕРЕНИЙ, А НЕ ИЗ ГОЛОВЫ. Сводный обзор Veale и др. (2015),
15 521 мужчина: длина в покое 9.16 см, обхват в покое 9.31 см (то есть
диаметр около 3 см). Мошонка в покое около 5 см поперёк. В кадре герой одет,
и от этой части нужен ровно силуэт под тканью — поэтому форма мягкая, без
подробностей, какие всё равно не увидеть.

ЗАПИСЫВАЕТСЯ ОТДЕЛЬНЫМ КЛЮЧОМ ФОРМЫ, а не правкой сетки: у тела уже полсотни
ключей от MakeHuman, и они складываются. Свой ключ становится ещё одним
слагаемым и не мешает ни подгонке, ни привязке одежды.
"""
import math

import bpy
from mathutils import Matrix, Vector

KEY = "анатомия: пах"

# всё в метрах, от лобковой точки
SHAFT_LEN = 0.075        # длина ствола, чуть меньше измеренной: часть уходит внутрь
SHAFT_R = 0.017          # радиус ствола (обхват 9.3 см -> диаметр 3 см)
SHAFT_DROP = 0.80        # насколько ствол свисает вниз (0 — вперёд, 1 — вниз)
SCROT_R = 0.026          # радиус мошонки
SCROT_DOWN = 0.030       # насколько её центр ниже лобковой точки
SCROT_FWD = 0.012        # и насколько впереди
FALLOFF = 0.055          # радиус затухания, за ним сетка не трогается


def _base_positions(body):
    """Положения ИСХОДНЫХ вершин со всеми целями, но без модификаторов.

    Первая версия читала вычисленную сетку — а в ней 13380 вершин вместо
    19158: маска выбрасывает служебную оболочку MakeHuman. Номера вершин
    после этого не совпадают с ключом формы, и правка уходила в никуда:
    сдвинуто 0 вершин. Поэтому модификаторы временно выключаются, и сетка
    читается в исходном порядке; служебные вершины отсеиваются по той же
    группе, по которой их прячет маска.
    """
    states = [(m, m.show_viewport) for m in body.modifiers]
    for m, _ in states:
        m.show_viewport = False
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = body.evaluated_get(dg)
    tmp = ev.to_mesh()
    cur = [v.co.copy() for v in tmp.vertices]
    ev.to_mesh_clear()
    for m, st in states:
        m.show_viewport = st
    bpy.context.view_layer.update()

    real = [True] * len(cur)
    msk = next((m for m in body.modifiers if m.type == 'MASK'), None)
    if msk and msk.vertex_group and msk.vertex_group in body.vertex_groups:
        gi = body.vertex_groups[msk.vertex_group].index
        inv = getattr(msk, "invert_vertex_group", False)
        for i, v in enumerate(body.data.vertices):
            if i >= len(real):
                break
            w = any(g.group == gi and g.weight > 0.0 for g in v.groups)
            real[i] = (not w) if inv else w
    return cur, real


def _anchor(body):
    """Лобковая точка: центральная точка тела сразу над промежностью.

    Ищется по сетке, а не по кости: кость таза стоит выше и глубже, и от неё
    до поверхности сантиметра три — как раз столько, чтобы промахнуться.
    """
    cur, real = _base_positions(body)
    M = body.matrix_world
    pts = [M @ c for c, r in zip(cur, real) if r]
    zs = [p.z for p in pts]
    lo, hi = min(zs), max(zs)
    H = hi - lo
    # промежность: самая нижняя высота, где сечение ещё цельное
    crotch = lo + 0.48 * H
    for i in range(int(H * 1000 * 0.38), int(H * 1000 * 0.60)):
        z = lo + i / 1000.0
        xs = sorted(p.x for p in pts if abs(p.z - z) < 0.004)
        if len(xs) < 8:
            continue
        if max((b - a) for a, b in zip(xs, xs[1:])) < 0.02:
            crotch = z
            break
    band = [p for p in pts if abs(p.x) < 0.03 and crotch < p.z < crotch + 0.05]
    if not band:
        return None, H
    front = min(band, key=lambda p: p.y)      # вперёд у нас −y
    return Vector((0.0, front.y, crotch + 0.012)), H


# ПЕРВЫЙ ПОДХОД — СДВИГ ВЕРШИН ТЕЛА — ВЫБРОШЕН, и вот почему, чтобы не
# возвращаться: форма живёт в ПУСТОМ месте. Ниже лобка средняя линия тела это
# промежность, она уходит назад на шесть сантиметров (замерено: передняя точка
# на уровне лобка y=−0.122, тремя сантиметрами ниже y=−0.059). Сдвигать там
# нечего, и пять попыток подряд давали то мягкий бугор, то ничего:
#   — «вытолкнуть до радиуса» не сдвинуло ни одной вершины (сетка редкая);
#   — ось перед поверхностью двигала вершины НАЗАД (выступ упал со 106 до 88);
#   — радиальное направление у верхнего конца оси задирало лобок ВВЕРХ на 29 мм;
#   — центры на уровне лобка висели в воздухе, до сетки доставали только хвосты.
# Ровно поэтому у самого MakeHuman это отдельная накладка, а не цель формы.


# --- отдельная сетка, потому что двигать нечего --------------------------------

MESH_NAME = "пах"
SHAFT_L = 0.072      # длина в покое за вычетом скрытой части
SHAFT_D = 0.030      # диаметр (обхват 9.3 см)
SCROT_D = 0.052      # мошонка поперёк
TILT = 68.0          # градусов от горизонтали, вниз


def add_mesh(body, arm, verbose=True):
    """Построить пах ОТДЕЛЬНОЙ сеткой и привязать к тазу.

    ПОЧЕМУ НЕ СДВИГОМ ВЕРШИН, КАК Я ПЫТАЛСЯ ПЯТЬ РАЗ. Форма живёт в ПУСТОМ
    МЕСТЕ: ниже лобка средняя линия тела — это промежность, и она уходит
    назад на шесть сантиметров (замерено: передняя точка на уровне лобка
    y=−0.122, на три сантиметра ниже уже y=−0.059). Двигать там нечего.
    Ровно поэтому у MakeHuman это отдельный ассет-накладка, а не цель формы;
    цели penis-* рассчитаны на неё и на голом теле не делают ничего.

    Форма простая и намеренно простая: капсула и шар нужных размеров. В игре
    герой одет, и от этой части нужен силуэт под тканью, а не подробности.
    Размеры — из сводного обзора Veale и др. (2015), 15 521 мужчина: длина в
    покое 9.2 см, обхват 9.3 см (диаметр 3 см); мошонка около 5 см поперёк.
    """
    import bmesh
    P, _H = _anchor(body)
    if P is None:
        print("[пах] не нашёл лобковую точку")
        return None
    old = bpy.data.objects.get(MESH_NAME)
    if old:
        bpy.data.objects.remove(old, do_unlink=True)

    me = bpy.data.meshes.new(MESH_NAME)
    bm = bmesh.new()
    # ствол: капсула вдоль оси Y, потом повернём
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=16,
                          radius1=SHAFT_D / 2, radius2=SHAFT_D / 2 * 0.92,
                          depth=SHAFT_L, matrix=Matrix.Translation((0, 0, -SHAFT_L / 2)))
    bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=10,
                              radius=SHAFT_D / 2 * 0.96,
                              matrix=Matrix.Translation((0, 0, -SHAFT_L)))
    bmesh.ops.create_uvsphere(bm, u_segments=18, v_segments=12,
                              radius=SCROT_D / 2,
                              matrix=Matrix.Translation((0, 0.012, -0.026)))
    for f in bm.faces:
        f.smooth = True
    bm.to_mesh(me)
    bm.free()

    ob = bpy.data.objects.new(MESH_NAME, me)
    bpy.context.collection.objects.link(ob)
    # наклон вниз-вперёд и посадка на лобковую точку
    # ЗНАК НАКЛОНА: поворот на +22° уводил ствол вниз-НАЗАД, в тело. Вперёд у
    # нас −y, поэтому наклон отрицательный. Поймано глазом на первом же кадре.
    ob.rotation_euler = (-math.radians(90.0 - TILT), 0.0, 0.0)
    # основание прячется в лобковый бугор, иначе форма выглядит приклеенной
    ob.location = (0.0, P.y + 0.030, P.z + 0.002)

    # материал: тон кожи со своим рассеянием, потому что развёртки у этой
    # сетки нет и фотоскан на неё не ляжет
    mat = bpy.data.materials.new("кожа паха")
    mat.use_nodes = True
    b = mat.node_tree.nodes["Principled BSDF"]
    # ТОН ПОДБИРАЕТСЯ ПОД ТЕЛО, а не «телесный вообще»: на первом кадре
    # накладка вышла светлее кожи и читаласьбелым пластиком. Светлее её делали
    # два слагаемых сразу — сильное подповерхностное рассеяние и блик.
    b.inputs["Base Color"].default_value = (0.60, 0.42, 0.38, 1.0)
    b.inputs["Roughness"].default_value = 0.62
    if "Specular IOR Level" in b.inputs:
        b.inputs["Specular IOR Level"].default_value = 0.35
    if "Subsurface Weight" in b.inputs:
        b.inputs["Subsurface Weight"].default_value = 0.10
        b.inputs["Subsurface Radius"].default_value = (0.036, 0.014, 0.008)
    me.materials.append(mat)

    # привязка к тазу: одна кость, никаких весов
    g = ob.vertex_groups.new(name="Hips")
    g.add(range(len(me.vertices)), 1.0, 'REPLACE')
    m = ob.modifiers.new("Armature", 'ARMATURE')
    m.object = arm
    ob.parent = arm
    if verbose:
        print("[пах] отдельная сетка: %d вершин, длина %.0f мм, наклон %.0f°, "
              "посажена на %.3f/%.3f" % (len(me.vertices), SHAFT_L * 1000, TILT,
                                         ob.location[1], ob.location[2]))
    return ob
