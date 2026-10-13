#!/usr/bin/env python3
"""КАЛЬСОНЫ 1894 ГОДА: сшиты по телу, а не натянуты поверх.

ПРО ЭПОХУ. «Трусов» в 1894 году не существовало — короткое мужское бельё
появилось в 1920-х. Мужчина этого времени носил КАЛЬСОНЫ (подштанники):
длинные, из небелёного полотна или бязи, со шнурком в поясе, у щиколотки
завязки. Наши — до колена, как носили под сапоги: так они не сбиваются в
голенище.

ПОЧЕМУ СВОИ, А НЕ ГОТОВЫЕ. В открытых наборах мужского белья нет: в
underwear01/02/04 женское бельё, чулки и современные спортивные плавки, в
системном наборе MakeHuman белья нет вовсе. Проверено списком.

КАК СШИТО, и это тот же способ, каким делают настоящие ассеты одежды:
  1. Берётся КОПИЯ ТЕЛА — значит крой заведомо сидит по фигуре и наследует
     развесовку по костям, то есть двигается вместе с человеком.
  2. Отрезается всё, кроме полосы от пояса до колена.
  3. Полоса делится вдвое-втрое чаще: у тела в паху сетка редкая, а ткани
     нужны складки и выпуклость.
  4. НАТЯГИВАЕТСЯ ПО БОЛВАНКЕ. Болванка — это тело ВМЕСТЕ с анатомией паха;
     ткань садится на неё с зазором в несколько миллиметров. Выпуклость под
     тканью получается сама, из формы болванки, а не рисуется отдельно — так
     же, как это происходит с настоящей тканью.
  5. Придаётся толщина, иначе край читается бумагой.

ЗАЗОРЫ РАЗНЫЕ ПО МЕСТАМ: в поясе и по бедру ткань лежит почти по телу (4 мм),
ниже свободнее (до 12 мм) — кальсоны не облегающие.
"""
import math

import bpy
import bmesh
from mathutils import Vector

NAME = "кальсоны"
Z_TOP = 0.605        # пояс, доля роста (чуть выше пупка — так носили)
Z_BOTTOM = 0.275     # низ, чуть ниже колена
GAP_TIGHT = 0.009    # зазор у пояса и в паху
GAP_LOOSE = 0.013    # зазор внизу штанины
THICK = 0.0018       # толщина полотна
# выпуклость под тканью: те же размеры, что у анатомии (studio/anatomy.py)
BULGE_A = 0.030      # насколько ткань отходит в самом высоком месте
BULGE_S = 0.028      # как широко расходится


def _dup(ob, name):
    me = ob.data.copy()
    new = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(new)
    new.matrix_world = ob.matrix_world.copy()
    return new


def _evaluated_copy(objs, name):
    """Слепок из нескольких объектов со всеми их формами — болванка для ткани."""
    dg = bpy.context.evaluated_depsgraph_get()
    bm = bmesh.new()
    for ob in objs:
        if ob is None:
            continue
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        tmp = bmesh.new()
        tmp.from_mesh(me)
        tmp.transform(ob.matrix_world)
        tmp.to_mesh(me)
        bm.from_mesh(me)
        ev.to_mesh_clear()
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    return ob


def make(body, arm, former_extra=None, verbose=True):
    """Сшить кальсоны на теле. former_extra — что ещё входит в болванку."""
    old = bpy.data.objects.get(NAME)
    if old:
        bpy.data.objects.remove(old, do_unlink=True)

    M = body.matrix_world
    dg = bpy.context.evaluated_depsgraph_get()
    ev = body.evaluated_get(dg)
    tmp = ev.to_mesh()
    zs = [(M @ v.co).z for v in tmp.vertices]
    lo, hi = min(zs), max(zs)
    ev.to_mesh_clear()
    H = hi - lo
    z_top = lo + Z_TOP * H
    z_bot = lo + Z_BOTTOM * H

    # 1-2. копия тела, обрезанная по поясу и колену
    g = _dup(body, NAME)
    g.modifiers.clear()
    # КРОЙ СНИМАЕТСЯ С ПОДОГНАННОГО ТЕЛА, А НЕ С ИСХОДНОГО.
    #
    # Сперва я просто сбрасывал ключи формы у копии — и бельё получалось сшито
    # по БАЗОВОЙ фигуре MakeHuman, без наших промеров. Настоящее тело шире:
    # плечи, бёдра, икры подогнаны по антропометрии. В кадре это выглядело
    # пятнами кожи сквозь полотно, будто в ткани дыры, — а дыр не было
    # (проверено: у кроя ноль граничных рёбер, он замкнут). Сквозь ткань лезло
    # тело.
    import anatomy
    fitted, _real = anatomy._base_positions(body)
    if g.data.shape_keys:
        g.shape_key_clear()
    for i, co in enumerate(fitted):
        if i < len(g.data.vertices):
            g.data.vertices[i].co = co
    bm = bmesh.new()
    bm.from_mesh(g.data)
    bm.verts.ensure_lookup_table()
    # ПОРЯДОК: СНАЧАЛА ВЫБРОСИТЬ СЛУЖЕБНУЮ ОБОЛОЧКУ, ПОТОМ РЕЗАТЬ.
    # Наоборот не работает: у MakeHuman вокруг тела есть редкая клетка-помощник
    # для подгонки одежды, и если резать вместе с ней, её обрывки повисают
    # бахромой по краю — в кадре это выглядело сосульками по бедру.
    dl = bm.verts.layers.deform.verify()
    msk = next((m for m in body.modifiers if m.type == 'MASK'), None)
    if msk and msk.vertex_group in body.vertex_groups:
        gi = body.vertex_groups[msk.vertex_group].index
        bad = [v for v in bm.verts if v[dl].get(gi, 0.0) <= 0.0]
        bmesh.ops.delete(bm, geom=bad, context='VERTS')
        bm.verts.ensure_lookup_table()
    # РУКИ ВЫБРАСЫВАЮТСЯ ОТДЕЛЬНО. Полоса «от пояса до колена» захватывает и
    # кисти: у стоящего человека они висят ровно на этой высоте. На первом
    # кадре кальсоны надеЛИСЬ на ладони — ткань облепила пальцы.
    hands = {g2.index for g2 in body.vertex_groups
             if any(k in g2.name for k in ("Hand", "Finger", "Thumb",
                                           "ForeArm", "Arm"))}
    if hands:
        bad = [v for v in bm.verts
               if sum(w for k, w in v[dl].items() if k in hands) > 0.25]
        if bad:
            bmesh.ops.delete(bm, geom=bad, context='VERTS')
            bm.verts.ensure_lookup_table()

    # РЕЖЕМ ПЛОСКОСТЬЮ, А НЕ УДАЛЯЕМ ВЕРШИНЫ. Удаление целых вершин давало
    # рваный край зубцами по рёбрам сетки; рез плоскостью даёт ровную кромку.
    Mi = M.inverted()
    for z, upward in ((z_top, True), (z_bot, False)):
        bmesh.ops.bisect_plane(
            bm, geom=list(bm.verts) + list(bm.edges) + list(bm.faces),
            plane_co=Mi @ Vector((0.0, 0.0, z)),
            plane_no=Vector((0.0, 0.0, 1.0)),
            clear_outer=upward, clear_inner=not upward)
        bm.verts.ensure_lookup_table()
    # убрать всё, что осталось без граней, и вырожденные рёбра
    loose = [v for v in bm.verts if not v.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context='VERTS')
    bmesh.ops.dissolve_degenerate(bm, dist=1e-5,
                                  edges=list(bm.edges))
    bm.verts.ensure_lookup_table()
    bnd = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    print("[кальсоны] кромка: %d граничных рёбер" % bnd)

    # 3. чаще сетка — ткани нужны складки и место под выпуклость
    bmesh.ops.subdivide_edges(bm, edges=list(bm.edges), cuts=1,
                              use_grid_fill=True)
    # НОРМАЛИ ПЕРЕСЧИТЫВАЮТСЯ ПОСЛЕ РЕЗА. Иначе часть граней смотрит внутрь,
    # и «отодвинуть наружу» для них означает внутрь: в кадре по бедру шли
    # пятна кожи сквозь полотно, будто камуфляж.
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.normal_update()

    # 4. ПОСАДКА СЧИТАЕТСЯ САМА, БЕЗ МОДИФИКАТОРОВ ПОДГОНКИ.
    #
    # Два способа из Блендера не подошли, и оба провалились на кадре:
    #   «по ближайшей точке» — вершины кроя ЛЕЖАТ на болванке, направление
    #     смещения не определено, часть ткани ушла внутрь и кожа светила
    #     полосами;
    #   «проекция вдоль нормали» — крой разлетелся клочьями по всей сцене.
    # Поэтому смещение считается прямо: каждая вершина отходит по своей
    # нормали на зазор, а в паху добавляется выпуклость — та же гауссиана и
    # те же размеры, какими задана анатомия. Крой уже частый, ей есть на чём
    # лечь. Это ровно то, что заказчик и просил: под тканью читается форма,
    # а самой анатомии в кадре нет.
    zt, zb = z_top, z_bot
    # ЛОБКОВАЯ ТОЧКА ИЩЕТСЯ ПО ТЕЛУ, А НЕ В ДОЛЯХ ОТ ПОЯСА ДО КОЛЕНА.
    # Первый вариант брал полосу «0.34–0.46 от низа кроя» и попал на середину
    # бедра: центр выпуклости встал на высоте 0.725 при лобке 0.843, да ещё в
    # 28 мм от середины. Правильный ориентир — промежность тела, она уже
    # посчитана в studio/anatomy.py тем же способом, что и для анатомии.
    ctr = None
    import anatomy as _an
    P0, _hh = _an._anchor(body)
    if P0 is not None:
        band = [v for v in bm.verts
                if abs((M @ v.co).x) < 0.035
                and abs((M @ v.co).z - P0.z) < 0.020
                and (M @ v.co).y < 0]
        if band:
            f = min(band, key=lambda v: (M @ v.co).y)
            ctr = Vector((0.0, (M @ f.co).y, P0.z))
    mx = 0.0
    nb = [0]
    for v in bm.verts:
        p = M @ v.co
        t = (p.z - zb) / max(1e-6, (zt - zb))
        gap = GAP_LOOSE + (GAP_TIGHT - GAP_LOOSE) * max(0.0, min(1.0, t))
        push = v.normal * gap
        if ctr is not None and p.y < ctr.y + 0.06:
            # ВЫПУКЛОСТЬ НАПРАВЛЕННАЯ И УЗКАЯ. Первый вариант отодвигал ткань
            # вдоль нормали и широко (σ 45 мм) — вышла общая полнота, а не
            # форма: 26 мм прибавки, и в кадре ничего не читается. Под тканью
            # видно форму, когда она собрана в одном месте и смотрит в одну
            # сторону. Два центра: ствол чуть выше и вперёд-вниз, мошонка
            # ниже и вниз.
            for c, amp, sig, dr in (
                    (ctr + Vector((0.0, 0.0, -0.012)), BULGE_A, BULGE_S,
                     Vector((0.0, -0.80, -0.60)).normalized()),
                    (ctr + Vector((0.0, 0.0, -0.042)), BULGE_A * 0.7,
                     BULGE_S * 1.15, Vector((0.0, -0.45, -0.89)).normalized())):
                r = (p - c).length
                if r < sig * 2.8:
                    push = push + dr * (amp * math.exp(-(r * r) /
                                                       (2.0 * sig * sig)))
        b = (push - v.normal * gap).length
        if b > 0.005:
            nb[0] += 1
        mx = max(mx, b)
        v.co = v.co + (Mi.to_3x3() @ push)
    bmesh.ops.smooth_vert(bm, verts=list(bm.verts), factor=0.15,
                          mirror_clip_x=False, mirror_clip_y=False,
                          mirror_clip_z=False)
    bm.to_mesh(g.data)
    bm.free()

    so = g.modifiers.new("толщина", 'SOLIDIFY')
    so.thickness = THICK
    so.offset = 1.0

    # 5. привязка: группы костей достались от тела вместе с копией
    am = g.modifiers.new("Armature", 'ARMATURE')
    am.object = arm
    g.parent = arm
    for p in g.data.polygons:
        p.use_smooth = True

    n = len(g.data.vertices)
    if verbose:
        print("[кальсоны] сшиты: %d вершин, пояс %.3f, низ %.3f, "
              "зазор %.0f–%.0f мм, выпуклость %.0f мм%s"
              % (n, z_top, z_bot, GAP_TIGHT * 1000, GAP_LOOSE * 1000,
                 mx * 1000, "" if ctr else "  — ЦЕНТР НЕ НАЙДЕН"))
        print("[кальсоны] центр выпуклости %s, вершин с выпуклостью >5 мм: %d"
              % (None if ctr is None else tuple(round(x, 3) for x in ctr), nb[0]))
    return g, None


def cloth_material(g, tex_dir=None):
    """Полотно: небелёный лён. Цвет и шероховатость — как у настоящей ткани.

    Если рядом лежат скачанные сканы ambientCG (studio/fetch_materials.py),
    берётся их карта; иначе однотонное полотно с мелкой неровностью.
    """
    import os
    m = bpy.data.materials.new("полотно")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.82, 0.78, 0.68, 1.0)
    b.inputs["Roughness"].default_value = 0.88
    if "Specular IOR Level" in b.inputs:
        b.inputs["Specular IOR Level"].default_value = 0.25
    col = None
    if tex_dir and os.path.isdir(tex_dir):
        for f in sorted(os.listdir(tex_dir)):
            if "Color" in f and f.lower().endswith((".jpg", ".png")):
                col = os.path.join(tex_dir, f)
                break
    if col:
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = bpy.data.images.load(col, check_existing=True)
        co = nt.nodes.new("ShaderNodeTexCoord")
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (14.0, 14.0, 14.0)
        nt.links.new(co.outputs["Object"], mp.inputs["Vector"])
        nt.links.new(mp.outputs["Vector"], t.inputs["Vector"])
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = 'RGBA'
        mix.blend_type = 'MULTIPLY'
        # ТКАНЬ БЕРЁТСЯ ЗА ФАКТУРУ, А НЕ ЗА ЦВЕТ. Скан Fabric030 — тёмно-серое
        # сукно; если взять его цвет как есть, кальсоны выходят серыми, а
        # небелёное полотно почти белое с желтизной. Поэтому карта осветляется
        # и подкрашивается: рисунок переплетения остаётся, тон становится
        # льняным.
        mix.blend_type = 'SCREEN'
        mix.inputs["Factor"].default_value = 0.72
        mix.inputs[7].default_value = (0.84, 0.80, 0.69, 1.0)
        nt.links.new(t.outputs["Color"], mix.inputs[6])
        nt.links.new(mix.outputs[2], b.inputs["Base Color"])
        print("[кальсоны] полотно: %s" % os.path.basename(col))
    g.data.materials.clear()
    g.data.materials.append(m)
    return m
