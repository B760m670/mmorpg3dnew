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


# --- грудные мышцы: нижний край, а не общая полнота ---------------------------

PEC_KEY = "анатомия: грудные"

# ПРЕДЫДУЩИЙ РЕЛЬЕФ БЫЛ ВЫДУМАН, И ВОТ ЧЕМ ОН ОТЛИЧАЛСЯ ОТ ЧЕЛОВЕКА.
# Я лепил два гауссовых бугра: центр на 82 мм от средней линии, высота 30 мм,
# нижний край горизонтальный. Разбор по источникам (см. studio/anatomy_data.py)
# показал три ошибки, и ни одну из них нельзя было увидеть подбором величины:
#   — высота втрое больше человеческой: мышца в покое 11.8–14.3 мм (ультразвук),
#     а не 30. Оттого «прибавить ещё» никогда и не помогало: росла не мышца,
#     а общая полнота, и грудь только больше походила на женскую;
#   — форма: у человека это ВЕЕР от грудины к плечевой кости, а не купол.
#     Изнутри у грудины мышца тонкая — там ложбина, а не выпуклость;
#   — нижний край идёт КОСО, поднимаясь к подмышке. Горизонтального нижнего
#     края у человека нет вовсе, а тень читается именно по этому краю.
#
# ТЕПЕРЬ ОЧЕРТАНИЕ БЕРЁТСЯ ИЗ АТЛАСА, а привязка к нашему телу — из обмера
# живых мужчин. Своего в этой форме остаётся ровно одно число: PEC_A, высота
# рельефа. Оно ПРЕДПОЛОЖЕНИЕ и помечено как предположение, потому что мышца
# лежит не голая: над ней кожа и подкожный слой, и насколько мышца выходит на
# поверхность — не то же самое, что её толщина.
PEC_GAIN = 1.0       # доля измеренной недостачи, которую выбираем
PEC_UNDER = 0.0090   # подрез под нижним краем: от него и берётся тень.
                     # ПРЕДПОЛОЖЕНИЕ: величину задаёт не замер, а то, читается
                     # ли край в кадре. При 2 мм граница выходила размытым
                     # полутоном вместо складки. Поперечный разрез на высоте
                     # соска подрез не трогает — он ниже.
PEC_FOLD_V = -0.85   # где в таблице атласа проходит подгрудная складка
PEC_BELLY_U = 0.575  # где в таблице брюшко мышцы
PEC_T_REF = 0.86     # толщина по таблице на высоте соска в брюшке — там мерена
                     # недостача, поэтому по ней и нормируется
REF_STATURE = 1.760  # рост тех 100 мужчин, у кого мерены соски и ширина груди
NIPPLE_X_MM = 114.0  # половина межсоскового расстояния (228.9 мм) у них же
NIPPLE_Z = 0.7352    # высота соска в долях роста, ANSUR II (4082 мужчины)


def _sample(u, v):
    """Толщина мышцы в точке (u, v) таблицы атласа, с наклонной вставкой."""
    import anatomy_data as ad
    rows = ad.PEC
    if v > rows[0][0] or v < rows[-1][0]:
        return 0.0
    j = 0
    while j + 1 < len(rows) and rows[j + 1][0] > v:
        j += 1
    if j + 1 >= len(rows):
        return 0.0
    v0, r0 = rows[j]
    v1, r1 = rows[j + 1]
    tv = 0.0 if abs(v1 - v0) < 1e-9 else (v - v0) / (v1 - v0)
    n = len(r0)
    fu = (u - ad.U0) / (ad.U1 - ad.U0) * (n - 1)
    if fu < 0 or fu > n - 1:
        return 0.0
    i = min(n - 2, int(fu))
    tu = fu - i
    a = r0[i] * (1 - tu) + r0[i + 1] * tu
    b = r1[i] * (1 - tu) + r1[i + 1] * tu
    return a * (1 - tv) + b * tv


def _deficit(x, H):
    """Сколько не хватает вперёд на расстоянии x от средней линии, в метрах.

    Таблица снята на теле ростом 1.731 против препарата атласа; переносится с
    поправкой на рост, потому что грудь растёт вместе с человеком.
    """
    import anatomy_data as ad
    k = H / 1.731
    xs = ad.DEFICIT_MM
    xm = x * 1000.0 / k
    if xm <= xs[0][0] or xm >= xs[-1][0]:
        return 0.0
    for (a, va), (b, vb) in zip(xs, xs[1:]):
        if a <= xm <= b:
            f = 0.0 if b == a else (xm - a) / (b - a)
            return (va + (vb - va) * f) / 1000.0 * k
    return 0.0


def _normals(body):
    """Наружные нормали исходных вершин: со всеми целями, но без модификаторов."""
    states = [(m, m.show_viewport) for m in body.modifiers]
    for m, _ in states:
        m.show_viewport = False
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = body.evaluated_get(dg)
    tmp = ev.to_mesh()
    nrm = [Vector(v.normal) for v in tmp.vertices]
    ev.to_mesh_clear()
    for m, st in states:
        m.show_viewport = st
    bpy.context.view_layer.update()
    return nrm


def pectorals(body, verbose=True):
    """Поднять грудные мышцы по НАСТОЯЩЕМУ очертанию, а не по догадке.

    КАК ФОРМА САДИТСЯ НА НАШЕ ТЕЛО. У таблицы атласа две безразмерные оси:
    поперёк (u) и вниз от яремной вырезки (v), обе в долях длины грудины.
    Чтобы их разложить на нашем теле, нужны две точки, и обе взяты у живых:
      — поперёк: брюшко мышцы (u = 0.575) приходится на 105 мм от средней
        линии у препарата, а сосок у ста живых мужчин — на 114 мм. Два
        независимых источника, разница 9 мм; это и задаёт масштаб;
      — вниз: подгрудная складка на 33 ± 9 мм ниже соска (те же сто мужчин),
        а высота соска — 0.7352 роста (ANSUR, 4082 мужчины).
    СВЕРКА, КОТОРАЯ ЭТО ПОДТВЕРЖДАЕТ: при такой раскладке верх мышцы попадает
    на 0.807 роста, а яремная вырезка у ANSUR стоит на 0.813. Расхождение
    0.6% — то есть три источника, снятые независимо, сходятся на нашем теле.

    ВАЖНО, ЧТО СОСОК НЕ СОВПАДАЕТ С САМЫМ ТОЛСТЫМ МЕСТОМ МЫШЦЫ. Я сначала
    свёл их в одну точку и получил складку на 86 мм ниже соска вместо
    измеренных 33. У человека мышца толще всего ВЫШЕ соска примерно на треть
    ладони: сосок лежит в нижней половине мышцы, у четвёртого межреберья, а
    мышца доходит до шестого ребра. Поэтому привязка идёт по СКЛАДКЕ, а не по
    брюшку: складка — резкая граница, её видно и её мерили.
    """
    cur, real = _base_positions(body)
    nrm = _normals(body)
    M = body.matrix_world
    Mi = M.inverted()
    zs = [(M @ c).z for c, r in zip(cur, real) if r]
    lo, hi = min(zs), max(zs)
    H = hi - lo

    # масштаб: одна единица таблицы (длина грудины) в метрах нашего тела
    nip_x = NIPPLE_X_MM / 1000.0 * (H / REF_STATURE)
    nip_z = lo + NIPPLE_Z * H
    L = nip_x * (105.0 / 114.0) / PEC_BELLY_U
    z_fold = nip_z - 0.033 * (H / REF_STATURE)

    def uv(p):
        return abs(p.x) / L, (p.z - z_fold) / L + PEC_FOLD_V

    me = body.data
    if me.shape_keys is None:
        body.shape_key_add(name="Basis", from_mix=False)
    key = me.shape_keys.key_blocks.get(PEC_KEY)
    if key is None:
        key = body.shape_key_add(name=PEC_KEY, from_mix=False)
    key.value = 1.0
    basis = me.shape_keys.key_blocks[0]

    # НАРУЖНЫЙ ПРЕДЕЛ: боковой край мышцы уходит под дельту, и там его не
    # видно. Ширина тела на своей высоте — честная граница: у самого бока
    # рельеф гасится, иначе выпуклость лезет в подмышку.
    def half_width(z):
        c = [abs((M @ q).x) for q, r in zip(cur, real) if r
             and abs((M @ q).z - z) < 0.010]
        return max(c) if c else 0.20

    moved, mx, mn = 0, 0.0, 0.0
    for i, co in enumerate(cur):
        if i >= len(key.data) or not real[i]:
            continue
        p = M @ co
        if p.y > 0 or not (z_fold - 0.10 < p.z < z_fold + 0.30):
            continue
        u, v = uv(p)
        t = _sample(u, v)
        # подрез идёт ПОД складкой, ниже нижнего края мышцы
        vu = v + 0.10
        under = _sample(u, vu) if v < PEC_FOLD_V else 0.0
        if t <= 0.0 and under <= 0.0:
            continue
        hw = half_width(p.z)
        fade = 1.0
        if hw > 0 and abs(p.x) > hw * 0.72:
            fade = max(0.0, 1.0 - (abs(p.x) - hw * 0.72) / (hw * 0.28))
        d = _deficit(abs(p.x), H) * PEC_GAIN
        amp = d * (t / PEC_T_REF) * fade - PEC_UNDER * under * fade
        if abs(amp) < 1e-5:
            continue
        n = nrm[i] if i < len(nrm) else Vector((0.0, -1.0, 0.0))
        if n.length < 1e-6:
            n = Vector((0.0, -1.0, 0.0))
        push = n.normalized() * amp
        key.data[i].co = basis.data[i].co + (Mi.to_3x3() @ push)
        moved += 1
        mx = max(mx, amp)
        mn = min(mn, amp)
    bpy.context.view_layer.update()
    if verbose:
        print("[грудные] очертание из атласа: единица (грудина) %.0f мм, "
              "сосок %.0f мм от середины на высоте %.3f, складка %.3f"
              % (L * 1000, nip_x * 1000, nip_z, z_fold))
        print("[грудные] сдвинуто %d вершин, наружу до %.1f мм, подрез до %.1f мм; "
              "верх мышцы на %.3f роста (яремная вырезка у ANSUR 0.813)"
              % (moved, mx * 1000, -mn * 1000,
                 ((z_fold + (0.02 - PEC_FOLD_V) * L) - lo) / H))
    return moved


def chest_profile(body, tag="", verbose=True):
    """Поперечный разрез груди на высоте соска — тот самый замер, по которому
    ставится рельеф. Отдельной работой, чтобы проверять, а не верить."""
    from mathutils.bvhtree import BVHTree
    import anatomy_data as ad
    dg = bpy.context.evaluated_depsgraph_get()
    ev = body.evaluated_get(dg)
    me = ev.to_mesh()
    M = body.matrix_world
    vs = [M @ v.co for v in me.vertices]
    fs = [[i for i in p.vertices] for p in me.polygons]
    ev.to_mesh_clear()
    bvh = BVHTree.FromPolygons(vs, fs, all_triangles=False, epsilon=0.0)
    zs = [p.z for p in vs]
    lo, hi = min(zs), max(zs)
    z = lo + NIPPLE_Z * (hi - lo)
    k = (hi - lo) / 1.731

    def at(x):
        h = bvh.ray_cast(Vector((x, -2.0, z)), Vector((0, 1, 0)), 4.0)
        return None if h[0] is None else h[0].y

    base = at(0.0)
    out = []
    for xm in (0, 20, 40, 60, 80, 100, 120):
        y = at(xm / 1000.0 * k)
        out.append((xm, None if y is None or base is None else (base - y) * 1000 / k))
    if verbose:
        atlas = {0: 0.0, 20: 9.1, 40: 10.8, 60: 10.0, 80: 9.3, 100: 6.0, 120: -3.8}
        print("[грудь] %sвынос вперёд от грудины, мм (рост %.3f):" % (tag, hi - lo))
        print("        x=  " + "".join("%6d" % x for x, _ in out))
        print("  атлас   " + "".join("%6.1f" % atlas[x] for x, _ in out))
        print("  наше    " + "".join("  ----" if v is None else "%6.1f" % v
                                     for _, v in out))
        print("  промах  " + "".join("  ----" if v is None else "%+6.1f" % (v - atlas[x])
                                     for x, v in out))
    return out
