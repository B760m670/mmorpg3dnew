# -*- coding: utf-8 -*-
"""2D-РИСУНОК ШТРИХАМИ В BLENDER, НАПИСАННЫЙ КОДОМ.

Grease Pencil — это не «ещё один способ обвести 3D», а полноценный 2D-тракт, и
из Python он управляется полностью. Главное, чего нет ни у Freestyle, ни у
рисования растром: у КАЖДОЙ ТОЧКИ штриха своя толщина (point.radius). Именно
переменный нажим отличает проведённую линию от вычисленного контура — линия
тяжелеет там, где форма уходит от света, и утончается на выходе.

Плюс модификаторы линии, которые к растру не приделать:
    GREASE_PENCIL_NOISE     — дрожание, то самое «кипение» рисованной линии;
    GREASE_PENCIL_THICKNESS — вес линии целиком;
    GREASE_PENCIL_BUILD     — прорисовка по кадрам (линия появляется);
    GREASE_PENCIL_DASH      — пунктир;
    GREASE_PENCIL_SMOOTH    — сглаживание.

Рисуется тот же персонаж, что и в studio/character.py: силуэт берётся из ТОЙ ЖЕ
таблицы сечений, поэтому лист и модель не разойдутся.
"""
import bpy, math, sys, numpy as np

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "/tmp/ink.png"

# та же таблица, что в character.py: (высота, полуширина)
SIL = [(0.000, 0.034), (0.055, 0.092), (0.130, 0.152), (0.235, 0.208),
       (0.350, 0.252), (0.460, 0.278), (0.575, 0.292), (0.690, 0.292),
       (0.795, 0.275), (0.875, 0.245), (0.935, 0.194), (0.978, 0.118),
       (1.000, 0.030)]
S = 2.0            # высота головы в единицах сцены


def catmull(pts, n):
    """Гладкая кривая через точки — ломаный силуэт читается как многоугольник."""
    out = []
    m = len(pts)
    for i in range(n + 1):
        u = i / n * (m - 1)
        k = min(int(u), m - 2)
        t = u - k
        p0 = pts[max(k - 1, 0)]; p1 = pts[k]; p2 = pts[k + 1]; p3 = pts[min(k + 2, m - 1)]
        out.append(tuple(
            0.5 * ((2 * p1[d]) + (-p0[d] + p2[d]) * t
                   + (2 * p0[d] - 5 * p1[d] + 4 * p2[d] - p3[d]) * t * t
                   + (-p0[d] + 3 * p1[d] - 3 * p2[d] + p3[d]) * t ** 3)
            for d in range(2)))
    return out


def stroke(dr, pts, radii, mat_idx=0, cyclic=False):
    dr.add_strokes([len(pts)])
    st = dr.strokes[-1]
    st.material_index = mat_idx
    st.cyclic = cyclic
    for i, (x, z) in enumerate(pts):
        st.points[i].position = (x, 0.0, z)
        st.points[i].radius = radii[i]
        st.points[i].opacity = 1.0
    return st


def lid(w, h, n, up=True, tilt=0.10):
    """Линия века. ЗНАК ВЕРТИКАЛИ ПРОТИВОПОЛОЖЕН РАСТРОВОМУ РИСУНКУ: там ось Y
    смотрит вниз, здесь Z смотрит вверх. Перенеся формулы как есть, я получил
    глаза и рот вверх ногами — ровно та же ошибка, что уложила голову на бок."""
    K = math.log(0.5) / math.log(0.40 if up else 0.56)
    o = []
    for i in range(n + 1):
        t = i / n
        u = t ** K
        y = h * (math.sin(math.pi * u) ** 0.80) if up else -h * 0.44 * (math.sin(math.pi * u) ** 0.95)
        o.append((-w + 2 * w * t, y + tilt * h * t))
    return o


def main():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    w = bpy.data.worlds.get('World') or bpy.data.worlds.new('World')
    bpy.context.scene.world = w
    w.use_nodes = True
    w.node_tree.nodes['Background'].inputs[0].default_value = (0.955, 0.945, 0.925, 1)

    def gpmat(name, col, fill=None):
        m = bpy.data.materials.new(name)
        bpy.data.materials.create_gpencil_data(m)
        m.grease_pencil.color = col + (1,)
        m.grease_pencil.show_stroke = True
        if fill:
            m.grease_pencil.fill_color = fill + (1,)
            m.grease_pencil.show_fill = True
        return m

    ink = gpmat('ink', (0.10, 0.07, 0.11))
    soft = gpmat('soft', (0.42, 0.30, 0.30))
    hairm = gpmat('hair', (0.12, 0.09, 0.12), fill=(0.155, 0.120, 0.165))
    hairm.grease_pencil.show_stroke = False   # контур чёлки рисуется отдельно
    skinm = gpmat('skin', (0.10, 0.07, 0.11), fill=(0.980, 0.855, 0.775))

    bpy.ops.object.grease_pencil_add(type='EMPTY')
    gp = bpy.context.object
    # ОБЪЕКТ СОЗДАЁТСЯ УЖЕ С МАТЕРИАЛОМ В НУЛЕВОМ СЛОТЕ. Первый заход добавлял
    # свои четыре поверх и обращался по индексам 0..3 — всё съехало на один:
    # заливка лица взяла материал волос, чёлка взяла бледно-розовый. Поэтому
    # слоты чистятся, а индекс берётся ПО ИМЕНИ, а не считается на пальцах.
    gp.data.materials.clear()
    MI = {}
    for m in (ink, soft, hairm, skinm):
        gp.data.materials.append(m)
        MI[m.name] = len(gp.data.materials) - 1
    lay = gp.data.layers.new('ink')
    lay.use_lights = False
    fr = lay.frames.new(1)
    dr = fr.drawing

    # --- ЗАЛИВКА ЛИЦА: тот же силуэт, что у модели, замкнутым штрихом
    left = [(-w * S, z * S) for (z, w) in SIL]
    right = [(w * S, z * S) for (z, w) in reversed(SIL)]
    sil = catmull(left, 90) + catmull(right, 90)
    stroke(dr, sil, [0.001] * len(sil), mat_idx=MI['skin'], cyclic=True)

    # --- КОНТУР ЛИЦА. Вес линии НЕ постоянный: тяжелее по челюсти (там форма
    # уходит в тень), легче на темени. Это и есть разница между проведённой
    # линией и вычисленным контуром.
    n = len(sil)
    rad = []
    for i in range(n):
        zz = sil[i][1] / S
        rad.append(0.010 + 0.026 * max(0.0, 1.0 - zz / 0.55) ** 1.3)
    stroke(dr, sil, rad, mat_idx=MI['ink'], cyclic=True)

    eye_z = 0.495 * S
    dx = 0.112 * S
    ew, eh = 0.082 * S, 0.062 * S
    for s in (-1, 1):
        up = lid(ew, eh, 40, True)
        pts = [(s * x + s * dx, eye_z + y) for (x, y) in up]
        if s < 0:
            pts.reverse()
        r = [0.006 + 0.024 * (i / len(pts)) ** 0.8 for i in range(len(pts))]
        if s < 0:
            r.reverse()
        stroke(dr, pts, r, mat_idx=MI['ink'])
        dn = lid(ew * 0.78, eh, 22, False)
        p2 = [(s * x + s * dx, eye_z + y) for (x, y) in dn]
        stroke(dr, p2, [0.005] * len(p2), mat_idx=MI['soft'])
        # зрачок заливкой
        cir = [(s * dx + ew * 0.30 * math.cos(a * math.pi / 12),
                eye_z + ew * 0.34 * math.sin(a * math.pi / 12)) for a in range(24)]
        stroke(dr, cir, [0.004] * 24, mat_idx=MI['ink'], cyclic=True)
        # бровь
        bw = 0.052 * S
        br = [(s * (0.097 * S) + s * (-bw + 2 * bw * (i / 18)),
               eye_z + 0.118 * S + 0.018 * S * math.sin(math.pi * i / 18))
              for i in range(19)]
        stroke(dr, br, [0.016 - 0.010 * (i / 18) for i in range(19)], mat_idx=MI['ink'])

    mz = eye_z - 0.135 * S
    mw = 0.030 * S
    mo = [(-mw + 2 * mw * (i / 14), mz - mw * 0.42 * (1 - (2 * (i / 14) - 1) ** 2)) for i in range(15)]
    stroke(dr, mo, [0.005 + 0.007 * math.sin(math.pi * i / 14) for i in range(15)], mat_idx=MI['soft'])

    # --- ЧЁЛКА заливкой с рваным краем
    fr_pts = []
    for i in range(41):
        t = i / 40
        x = (-0.300 + 0.600 * t) * S
        saw = (0.5 + 0.5 * math.cos(2 * math.pi * t * 5.0)) * (0.55 + 0.45 * math.sin(t * 11.3 + 1.7))
        fr_pts.append((x, (0.72 - 0.16 * saw * (1 - abs(2 * t - 1) ** 2)) * S))
    fr_pts += [(0.300 * S, 1.04 * S), (-0.300 * S, 1.04 * S)]
    stroke(dr, fr_pts, [0.009] * len(fr_pts), mat_idx=MI['hair'], cyclic=True)
    # край чёлки обводится отдельно, только по зубцам — замкнутый контур
    # заливки давал в кадре прямоугольник поверх головы
    edge = fr_pts[:41]
    stroke(dr, edge, [0.008 + 0.006 * math.sin(math.pi * i / 40) for i in range(41)], mat_idx=MI['ink'])

    print('ШТРИХОВ НАРИСОВАНО:', len(dr.strokes),
          'точек:', sum(len(s.points) for s in dr.strokes))

    cam_d = bpy.data.cameras.new('c'); cam_d.type = 'ORTHO'; cam_d.ortho_scale = 1.75
    cam = bpy.data.objects.new('c', cam_d)
    bpy.context.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    cam.location = (0, -8, 0.55 * S)
    cam.rotation_euler = (math.pi / 2, 0, 0)
    li = bpy.data.lights.new('s', 'SUN'); li.energy = 2.2
    lo = bpy.data.objects.new('s', li); bpy.context.collection.objects.link(lo)
    lo.rotation_euler = (math.radians(55), 0, math.radians(-30))

    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'; sc.cycles.samples = 8
    sc.render.resolution_x, sc.render.resolution_y = 620, 720

    def shot(path, note):
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)
        im = bpy.data.images.load(path)
        px = np.array(im.pixels[:]).reshape(-1, 4)[:, :3]
        print('%-26s мин %.3f макс %.3f средн %.3f' % (note, px.min(), px.max(), px.mean()))
        bpy.data.images.remove(im)

    base = OUT.rsplit('.', 1)[0]
    shot(base + '_clean.png', 'штрихи как есть')
    nz = gp.modifiers.new('Noise', 'GREASE_PENCIL_NOISE')
    nz.factor = 0.045; nz.factor_thickness = 0.22; nz.noise_scale = 0.30; nz.seed = 11
    shot(base + '_wobble.png', '+ дрожание линии')


main()
