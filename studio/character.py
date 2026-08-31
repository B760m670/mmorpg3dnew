# -*- coding: utf-8 -*-
"""ГОЛОВА ПЕРСОНАЖА — ЛОФТ ПО СЕЧЕНИЯМ, А НЕ СКУЛЬПТУРА.

Проверка утверждения: можно ли вылепить аниме-персонажа, набирая числа, без
руки художника. Ответ держится на трёх вещах, и все три — свойства именно
аниме-стиля, а не 3D вообще:

1. ГОЛОВА ЗАДАЁТСЯ СИЛУЭТОМ. У рисованного персонажа череп, скулы и подбородок
   — это набор горизонтальных сечений, и каждое описывается тремя числами:
   полуширина, вынос вперёд, вынос назад. Ниже таблица из тринадцати сечений;
   она и есть «дизайн головы». Изменить лицо значит изменить числа в таблице.

2. ЛИЦО ЖИВЁТ В ТЕКСТУРЕ (studio/face_texture.py), спроецированной СПЕРЕДИ.
   Так делают Guilty Gear Xrd, Genshin, VRoid. Геометрия лица при этом почти
   гладкая — там нечего лепить.

3. ПЕРЕД ПЛОЩЕ ЗАДА. Лицевая плоскость почти плоская (показатель суперэллипса
   2.6), затылок круглый (2.0). Одно это отличает аниме-голову от шара.

ЧЕГО ЗДЕСЬ ЧЕСТНО НЕТ: ушей, ноздрей, губ как формы, топологии под мимику.
Ухо — отдельная форма, которую сечениями не описать. Мимика в таком тракте
делается сменой текстуры, а не костями лица.

Запуск:
  LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe xvfb-run -a \
    /opt/blender/blender -b -noaudio -P studio/character.py -- ВЫХОД.png ЛИЦО.png
"""
import bpy, bmesh, math, sys, time
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "/tmp/head.png"
FACE = argv[1] if len(argv) > 1 else "/tmp/face.png"

H = 0.243          # высота головы, м. Рост 1.70 при 7 головах.

# ТАБЛИЦА СЕЧЕНИЙ. Доли высоты головы: y снизу (подбородок 0) вверх (темя 1).
#   w — полуширина, f — вынос лица вперёд, b — вынос затылка назад.
# Челюсть узкая (0.030 у самого подбородка против 0.292 на скуле) — это и есть
# «аниме», а не большие глаза: у реалистичной головы отношение куда мягче.
RINGS = [
    (0.000, 0.034, 0.060, 0.075),
    (0.055, 0.092, 0.108, 0.150),
    (0.130, 0.152, 0.148, 0.232),
    (0.235, 0.208, 0.172, 0.302),
    (0.350, 0.252, 0.188, 0.352),
    (0.460, 0.278, 0.195, 0.381),   # линия глаз
    (0.575, 0.292, 0.193, 0.396),
    (0.690, 0.292, 0.186, 0.393),
    (0.795, 0.275, 0.172, 0.373),
    (0.875, 0.245, 0.151, 0.336),
    (0.935, 0.194, 0.120, 0.271),
    (0.978, 0.118, 0.074, 0.166),
    (1.000, 0.030, 0.020, 0.046),
]
N_U = 48           # точек по кольцу
N_F, N_B = 2.6, 2.0   # показатели суперэллипса: лицо площе затылка


def ring_points(w, f, b):
    """Кольцо: передняя дуга суперэллипсом N_F, задняя — N_B."""
    pts = []
    half = N_U // 2
    for i in range(half):                      # перед, слева направо
        u = -1.0 + 2.0 * i / (half - 1) if half > 1 else 0.0
        t = max(0.0, 1.0 - abs(u) ** N_F) ** (1.0 / N_F)
        pts.append((w * u, -f * t))
    for i in range(1, half):                   # зад, обратно
        u = 1.0 - 2.0 * i / (half - 1) if half > 1 else 0.0
        t = max(0.0, 1.0 - abs(u) ** N_B) ** (1.0 / N_B)
        pts.append((w * u, b * t))
    return pts


def build_head():
    bm = bmesh.new()
    grid = []
    for (yy, w, f, b) in RINGS:
        row = [bm.verts.new((x * H, z * H, yy * H)) for (x, z) in ring_points(w, f, b)]
        grid.append(row)
    bm.verts.ensure_lookup_table()
    n = len(grid[0])
    for j in range(len(grid) - 1):
        a, c = grid[j], grid[j + 1]
        for i in range(n):
            k = (i + 1) % n
            try:
                bm.faces.new((a[i], a[k], c[k], c[i]))
            except ValueError:
                pass
    # шапки: темя и подбородок закрываются веером к полюсу
    for row, y in ((grid[-1], (RINGS[-1][0] + 0.012) * H), (grid[0], (RINGS[0][0] - 0.010) * H)):
        pole = bm.verts.new((0.0, 0.0, y))
        for i in range(n):
            k = (i + 1) % n
            try:
                bm.faces.new((row[i], row[k], pole) if row is grid[-1] else (row[k], row[i], pole))
            except ValueError:
                pass
    me = bpy.data.meshes.new("head")
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("head", me)
    bpy.context.collection.objects.link(ob)

    # UV — ПРОЕКЦИЯ СПЕРЕДИ. Именно поэтому лицо и может быть текстурой: спереди
    # голова почти плоская, и растяжения на лице нет. Бока и затылок текстура
    # размазывает, но там ровный тон кожи, а сверху ляжет причёска.
    wmax = max(r[1] for r in RINGS) * H
    me.uv_layers.new(name="UVMap")
    uv = me.uv_layers.active.data
    for poly in me.polygons:
        for li in poly.loop_indices:
            v = me.vertices[me.loops[li].vertex_index].co
            uv[li].uv = (0.5 + v.x / (2.0 * wmax), v.z / H)

    ob.modifiers.new("sub", 'SUBSURF').levels = 2
    ob.modifiers["sub"].render_levels = 2
    for p in me.polygons:
        p.use_smooth = True
    return ob


def build_hair(head):
    """ПРИЧЁСКА — ВТОРАЯ ОБОЛОЧКА С РВАНЫМ КРАЕМ.

    В аниме волосы это не волосы, а объём с силуэтом: шапка поверх черепа плюс
    чёлка, у которой край пилой. Пила и читается как «пряди» — отдельные волосы
    не нужны и вредны.
    """
    bm = bmesh.new()
    grid = []
    # Линия глаз на 0.495 высоты головы, верх прорези около 0.56. Шапка обязана
    # начинаться ВЫШЕ: было 0.30, и волосы закрывали лицо целиком.
    lo = 0.62
    for (yy, w, f, b) in RINGS:
        if yy < lo:
            continue
        k = 1.055 + 0.045 * max(0.0, (yy - 0.55)) / 0.45      # объём растёт кверху
        row = [bm.verts.new((x * H * k, z * H * k, yy * H)) for (x, z) in ring_points(w, f, b)]
        grid.append(row)
    # нижний край шапки: пила по кольцу, глубже спереди (чёлка)
    n = len(grid[0])
    for i, v in enumerate(grid[0]):
        u = i / n
        front = max(0.0, math.cos(2 * math.pi * u))
        saw = 0.5 + 0.5 * math.cos(2 * math.pi * u * 9.0)
        v.co.z -= H * (0.012 + 0.075 * front * saw)
    bm.verts.ensure_lookup_table()
    for j in range(len(grid) - 1):
        a, c = grid[j], grid[j + 1]
        for i in range(n):
            k2 = (i + 1) % n
            try:
                bm.faces.new((a[i], a[k2], c[k2], c[i]))
            except ValueError:
                pass
    pole = bm.verts.new((0.0, 0.0, (RINGS[-1][0] + 0.020) * H))
    for i in range(n):
        k2 = (i + 1) % n
        try:
            bm.faces.new((grid[-1][i], grid[-1][k2], pole))
        except ValueError:
            pass
    me = bpy.data.meshes.new("hair")
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("hair", me)
    bpy.context.collection.objects.link(ob)
    ob.modifiers.new("sol", 'SOLIDIFY').thickness = 0.004
    ob.modifiers.new("sub", 'SUBSURF').levels = 1
    ob.modifiers["sub"].render_levels = 1
    for p in me.polygons:
        p.use_smooth = True
    return ob


def build_neck():
    bm = bmesh.new()
    prof = [(-0.30, 0.075, 0.085), (-0.14, 0.070, 0.082), (-0.02, 0.066, 0.080)]
    grid = []
    for (yy, w, d) in prof:
        row = []
        for i in range(N_U):
            a = 2 * math.pi * i / N_U
            row.append(bm.verts.new((w * H * math.sin(a), d * H * math.cos(a) * 0.9 + 0.02 * H, yy * H)))
        grid.append(row)
    bm.verts.ensure_lookup_table()
    for j in range(len(grid) - 1):
        for i in range(N_U):
            k = (i + 1) % N_U
            try:
                bm.faces.new((grid[j][i], grid[j][k], grid[j + 1][k], grid[j + 1][i]))
            except ValueError:
                pass
    me = bpy.data.meshes.new("neck")
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new("neck", me)
    bpy.context.collection.objects.link(ob)
    for p in me.polygons:
        p.use_smooth = True
    return ob


def toon_mat(name, color, tex=None, size=0.62, smooth=0.02):
    """ПЛОСКИЙ СВЕТ. Toon BSDF в Cycles — это ступенька «свет/тень» с
    управляемой шириной перехода; Shader to RGB тут не нужен (он только в EEVEE,
    а EEVEE без видеокарты не поднять)."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for nd in list(nt.nodes):
        if nd.type != 'OUTPUT_MATERIAL':
            nt.nodes.remove(nd)
    t = nt.nodes.new('ShaderNodeBsdfToon')
    t.component = 'DIFFUSE'
    t.inputs['Size'].default_value = size
    t.inputs['Smooth'].default_value = smooth
    if tex:
        im = nt.nodes.new('ShaderNodeTexImage')
        im.image = bpy.data.images.load(tex)
        im.interpolation = 'Cubic'
        nt.links.new(im.outputs['Color'], t.inputs['Color'])
    else:
        t.inputs['Color'].default_value = color
    nt.links.new(t.outputs[0], nt.nodes['Material Output'].inputs['Surface'])
    return m


def main():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)

    w = bpy.data.worlds.get('World') or bpy.data.worlds.new('World')
    bpy.context.scene.world = w
    w.use_nodes = True
    w.node_tree.nodes['Background'].inputs[0].default_value = (0.62, 0.70, 0.78, 1)
    w.node_tree.nodes['Background'].inputs[1].default_value = 0.9

    head = build_head()
    head.data.materials.append(toon_mat('skin', (0.95, 0.86, 0.80, 1), tex=FACE))
    neck = build_neck()
    neck.data.materials.append(toon_mat('skin2', (0.93, 0.83, 0.77, 1)))
    hair = build_hair(head)
    hair.data.materials.append(toon_mat('hair', (0.115, 0.085, 0.105, 1), size=0.70, smooth=0.03))

    li = bpy.data.lights.new('key', 'SUN'); li.energy = 3.2; li.angle = 0.0
    lo = bpy.data.objects.new('key', li); bpy.context.collection.objects.link(lo)
    lo.rotation_euler = (math.radians(62), 0, math.radians(-34))
    li2 = bpy.data.lights.new('fill', 'SUN'); li2.energy = 0.7
    lo2 = bpy.data.objects.new('fill', li2); bpy.context.collection.objects.link(lo2)
    lo2.rotation_euler = (math.radians(78), 0, math.radians(150))

    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = 24
    sc.render.resolution_x, sc.render.resolution_y = 520, 660
    sc.render.use_freestyle = True
    vl = sc.view_layers[0]
    fs = vl.freestyle_settings
    # КРЕЙСЫ ПОЧТИ ВЫКЛЮЧЕНЫ. На гладкой голове линия нужна только по силуэту;
    # если пустить её по перегибам, лицо покроется паутиной.
    fs.crease_angle = math.radians(152)
    ls = (fs.linesets[0] if fs.linesets else fs.linesets.new('outline'))
    ls.select_silhouette = True
    ls.select_border = True
    ls.select_crease = True
    ls.linestyle.color = (0.10, 0.07, 0.10)
    sc.render.line_thickness_mode = 'ABSOLUTE'
    sc.render.line_thickness = 1.5

    cam_d = bpy.data.cameras.new('cam'); cam_d.lens = 85
    cam = bpy.data.objects.new('cam', cam_d)
    bpy.context.collection.objects.link(cam)
    sc.camera = cam
    target = Vector((0, 0, H * 0.52))

    def shoot(az, path):
        r = H * 4.2
        a = math.radians(az)
        cam.location = (math.sin(a) * r, -math.cos(a) * r, target.z + H * 0.10)
        d = target - Vector(cam.location)
        cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = path
        t0 = time.time()
        bpy.ops.render.render(write_still=True)
        print('  %s за %.1f с' % (path, time.time() - t0))

    base = OUT.rsplit('.', 1)[0]
    shoot(0, base + '_front.png')
    shoot(32, base + '_34.png')
    shoot(78, base + '_side.png')
    print('ГОТОВО')


main()
