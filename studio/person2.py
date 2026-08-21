#!/usr/bin/env python3
"""ЧЕЛОВЕК ЭПОХИ: болванка художника + одежда, скроенная по телу.

ЧТО БЫЛО НЕ ТАК ДО ЭТОГО. Фигуру я строил с нуля, выписывая координаты вершин —
сперва кольцами в GDScript, потом тем же способом в Блендере. Оба раза вышла
карикатура, и дело не в подборе чисел: я перебирал их весь заход. Тело и лицо
не задаются координатами, их лепят.

ТЕЛО — ГОТОВАЯ БОЛВАНКА. Официальный набор Blender Studio «Human Base Meshes»
v1.4.1, лицензия CC0 (без ограничений, в том числе коммерческих). Тело мужчины:
10582 вершины, рёберные петли вокруг глаз, рта, локтей и коленей. Против моих
328 вершин.
ЛОВУШКА НАБОРА: объект «realistic_body_male» — это КАМЕРА для миниатюры
каталога. Приложение проходит, печатает 10582 вершины, а в кадре пустой фон.
Сетка называется GEO-body_male_realistic.

ОДЕЖДА КРОИТСЯ ПО ТЕЛУ, А НЕ СТРОИТСЯ РЯДОМ С НИМ. Это главное отличие от всего,
что я делал раньше. Раньше рукав был отдельной трубой, поставленной около
корпуса, и её приходилось подгонять на глаз. Здесь одежда — КОПИЯ УЧАСТКА САМОГО
ТЕЛА, отодвинутая наружу по нормали на толщину ткани. Такой рукав не может не
совпасть с рукой: он и есть рука, отодвинутая на 8 мм. Так шьют и в настоящем
производстве, и по той же причине.

ЧТО НОСИЛ ГОРОДСКОЙ ОБЫВАТЕЛЬ ГАТЧИНЫ В 1894 ГОДУ:
  ПАЛЬТО (или поддёвка) ниже колена, двубортное, глухое, тёмного сукна.
  КАРТУЗ — мягкая фуражка с козырьком; носили повсеместно, шляпа означала бы
    другое сословие.
  САПОГИ — высокие, до середины голени, чёрные, ваксёные.
  КОСОВОРОТКА под пальто; из-под воротника виден только её край.
Это не украшение фигуры, а первое, по чему она читается: разбор чужих кадров
дал, что на расстоянии работает только силуэт.

МАТЕРИАЛ — НАСТОЯЩИЙ, а не крашеный пластик. У каждой ткани здесь свой
процедурный рельеф и своя шероховатость:
  СУКНО — валяная шерсть. Поверхность не гладкая: видна саржа (диагональное
    переплетение) и ворс. Ворс даёт «sheen» — светлый ободок по краю силуэта,
    по которому шерсть и узнаётся. Шероховатость 0.88.
  КОЖА — ваксёная, с мелкой мереёй (зерном). Шероховатость 0.36: сапоги чистят,
    и они бликуют, в отличие от сукна.
  КОЖА ЧЕЛОВЕКА — подповерхностное рассеяние: свет уходит внутрь и выходит
    рядом. Без него лицо в тёплом свете лампы выглядит крашеным деревом.

Запуск:
  LIBGL_ALWAYS_SOFTWARE=1 xvfb-run -a /opt/blender/blender -b -noaudio \
      -P studio/person2.py -- --render /tmp/turn.png
  ... -- --out game2/assets/models/person.glb
"""
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

BUNDLE = "/tmp/claude-live/hbm/human-base-meshes-bundle-v1.4.1/human_base_meshes_bundle.blend"
BODY = "GEO-body_male_realistic"
TARGET_H = 1.75

# опорные высоты фигуры (канон 7.5 голов), в метрах от пола
HEAD = TARGET_H / 7.5
Y_ANKLE = 0.35 * HEAD
Y_KNEE = 2.00 * HEAD
Y_CROTCH = 3.75 * HEAD
Y_WAIST = 4.70 * HEAD
Y_SHOULDER = 6.10 * HEAD
Y_CHIN = 6.50 * HEAD
Y_TOP = 7.50 * HEAD


def clear():
    bpy.ops.wm.read_factory_settings(use_empty=True)


# ---------------------------------------------------------------------------
# ТЕЛО
# ---------------------------------------------------------------------------

def append_body():
    if not os.path.exists(BUNDLE):
        raise SystemExit("нет набора болванок: %s" % BUNDLE)
    with bpy.data.libraries.load(BUNDLE, link=False) as (src, dst):
        names = [n for n in src.objects if BODY in n]
        if not names:
            raise SystemExit("в наборе нет «%s»" % BODY)
        dst.objects = names[:1]
    ob = dst.objects[0]
    if ob is None or ob.type != 'MESH':
        raise SystemExit("приложился не тот объект: %s" % ob)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ob.name = "Тело"

    # Преобразование по САМИМ ВЕРШИНАМ, а не операторами: bpy.ops требуют, чтобы
    # объект уже лежал в активном слое вида, и падают на только что приложенном.
    me = ob.data
    me.transform(ob.matrix_world)
    ob.matrix_world = Matrix.Identity(4)
    zs = [v.co.z for v in me.vertices]
    was = max(zs) - min(zs)
    k = TARGET_H / was
    me.transform(Matrix.Diagonal(Vector((k, k, k)).to_4d()))
    me.transform(Matrix.Translation(Vector((0, 0, -min(v.co.z for v in me.vertices)))))
    me.update()
    bpy.context.view_layer.update()
    print("[человек] болванка: вершин %d, рост %.3f -> %.3f м"
          % (len(me.vertices), was, ob.dimensions.z))
    return ob


# ---------------------------------------------------------------------------
# КРОЙ
#
# Выкройка — это КОПИЯ УЧАСТКА ТЕЛА. Берём сетку тела, оставляем нужную область,
# отодвигаем каждую вершину наружу по её нормали на толщину ткани. Дальше
# полученная оболочка живёт своей жизнью: подол можно вытянуть вниз, край
# подвернуть, ткань уплотнить.
# ---------------------------------------------------------------------------

def cut(body, name, keep, offset=0.008):
    """Скроить деталь: оставить вершины, где keep(co) истинно, и отодвинуть."""
    me = body.data.copy()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)

    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    bm.normal_update()
    # отодвигаем ДО удаления: нормали целой поверхности честнее, чем нормали
    # обрезанного лоскута, у которого края уже смотрят куда попало
    for v in bm.verts:
        v.co += v.normal * offset
    doomed = [v for v in bm.verts if not keep(v.co)]
    bmesh.ops.delete(bm, geom=doomed, context='VERTS')
    bm.to_mesh(me)
    bm.free()
    me.update()
    print("[крой] %-10s вершин %d" % (name, len(me.vertices)))
    return ob


def hem_down(ob, levels, name="подол"):
    """Вытянуть нижнюю кромку вниз: подол пальто, голенище сапога.

    Кромка — это граничные рёбра (у которых одна грань). Выдавливаем её
    ступенями, задавая на каждой высоту и во сколько раз расширить: пальто
    книзу расходится, голенище сапога — нет.
    """
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.edges.ensure_lookup_table()
    edges = [e for e in bm.edges if len(e.link_faces) == 1]
    if not edges:
        bm.free()
        return
    # берём только НИЖНЮЮ кромку: у пальто есть ещё горловина и проймы
    zs = [v.co.z for e in edges for v in e.verts]
    z_lo = min(zs)
    edges = [e for e in edges
             if all(v.co.z < z_lo + 0.06 for v in e.verts)]
    if not edges:
        bm.free()
        return
    cx = sum(v.co.x for e in edges for v in e.verts) / (2 * len(edges))
    cy = sum(v.co.y for e in edges for v in e.verts) / (2 * len(edges))
    for z_to, widen in levels:
        r = bmesh.ops.extrude_edge_only(bm, edges=edges)
        new_v = [g for g in r["geom"] if isinstance(g, bmesh.types.BMVert)]
        for v in new_v:
            v.co.x = cx + (v.co.x - cx) * widen
            v.co.y = cy + (v.co.y - cy) * widen
            v.co.z = z_to
        edges = [g for g in r["geom"] if isinstance(g, bmesh.types.BMEdge)
                 and len(g.link_faces) == 1]
    bm.to_mesh(me)
    bm.free()
    me.update()


def solidify(ob, thickness=0.006):
    """Толщина ткани. Без неё край подола — бумажный, и это видно в силуэте."""
    m = ob.modifiers.new("ткань", 'SOLIDIFY')
    m.thickness = thickness
    m.offset = 1.0
    m.use_rim = True
    return m


def smooth(ob, levels=1):
    m = ob.modifiers.new("сглаживание", 'SUBSURF')
    m.levels = levels
    m.render_levels = levels
    for p in ob.data.polygons:
        p.use_smooth = True
    return m


# ---------------------------------------------------------------------------
# МАТЕРИАЛЫ
# ---------------------------------------------------------------------------

def _nodes(m):
    m.use_nodes = True
    return m.node_tree, m.node_tree.nodes["Principled BSDF"]


def mat_wool(name, rgb):
    """СУКНО: валяная шерсть. Саржа плюс ворс.

    Ткань узнаётся не цветом, а двумя вещами: диагональным переплетением
    (саржа) и ворсом. Ворс в Principled — это Sheen: светлый ободок по краю
    силуэта, там где смотришь на ткань вскользь. Без него сукно неотличимо
    от крашеного пластика, каким бы тёмным его ни сделать.
    """
    m = bpy.data.materials.new(name)
    tree, b = _nodes(m)
    n = tree.nodes
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = 0.88
    b.inputs["Metallic"].default_value = 0.0
    if "Sheen Weight" in b.inputs:
        b.inputs["Sheen Weight"].default_value = 0.35
        b.inputs["Sheen Roughness"].default_value = 0.45
    if "Specular IOR Level" in b.inputs:
        b.inputs["Specular IOR Level"].default_value = 0.25

    # САРЖА: две волны под углом дают диагональный рубчик. Шаг 0.9 мм —
    # настоящий шаг переплетения у грубого сукна.
    tex = n.new("ShaderNodeTexCoord")
    wav = n.new("ShaderNodeTexWave")
    wav.wave_type = 'BANDS'
    wav.bands_direction = 'DIAGONAL'
    wav.inputs["Scale"].default_value = 380.0
    wav.inputs["Distortion"].default_value = 2.0
    wav.inputs["Detail"].default_value = 2.0
    tree.links.new(tex.outputs["Object"], wav.inputs["Vector"])
    # ВОРС: мелкий шум поверх переплетения — шерсть не гладкая нигде
    noi = n.new("ShaderNodeTexNoise")
    noi.inputs["Scale"].default_value = 220.0
    noi.inputs["Detail"].default_value = 6.0
    tree.links.new(tex.outputs["Object"], noi.inputs["Vector"])
    mix = n.new("ShaderNodeMix")
    mix.data_type = 'RGBA'
    mix.inputs["Factor"].default_value = 0.45
    tree.links.new(wav.outputs["Color"], mix.inputs[6])
    tree.links.new(noi.outputs["Color"], mix.inputs[7])
    bump = n.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.22
    bump.inputs["Distance"].default_value = 0.0008     # рубчик высотой 0.8 мм
    tree.links.new(mix.outputs[2], bump.inputs["Height"])
    tree.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def mat_leather(name, rgb):
    """КОЖА ВАКСЁНАЯ: мелкая мерея (зерно) и блеск.

    Сапоги чистят, поэтому они бликуют — шероховатость 0.36 против 0.88 у
    сукна. Разница в блеске между сапогом и пальто важнее разницы в цвете:
    в кадре именно она разделяет эти две чёрные поверхности.
    """
    m = bpy.data.materials.new(name)
    tree, b = _nodes(m)
    n = tree.nodes
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = 0.36
    if "Specular IOR Level" in b.inputs:
        b.inputs["Specular IOR Level"].default_value = 0.6
    tex = n.new("ShaderNodeTexCoord")
    vor = n.new("ShaderNodeTexVoronoi")     # мерея: ячейки кожи
    vor.feature = 'DISTANCE_TO_EDGE'
    vor.inputs["Scale"].default_value = 900.0
    tree.links.new(tex.outputs["Object"], vor.inputs["Vector"])
    bump = n.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.30
    bump.inputs["Distance"].default_value = 0.0004
    tree.links.new(vor.outputs["Distance"], bump.inputs["Height"])
    tree.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    # неровный износ блеска: голенище тускнее носка
    ro = n.new("ShaderNodeTexNoise")
    ro.inputs["Scale"].default_value = 14.0
    tree.links.new(tex.outputs["Object"], ro.inputs["Vector"])
    rmap = n.new("ShaderNodeMapRange")
    rmap.inputs["To Min"].default_value = 0.28
    rmap.inputs["To Max"].default_value = 0.52
    tree.links.new(ro.outputs["Fac"], rmap.inputs["Value"])
    tree.links.new(rmap.outputs["Result"], b.inputs["Roughness"])
    return m


def mat_skin(name):
    m = bpy.data.materials.new(name)
    tree, b = _nodes(m)
    b.inputs["Base Color"].default_value = (0.60, 0.44, 0.36, 1.0)
    b.inputs["Roughness"].default_value = 0.58
    if "Subsurface Weight" in b.inputs:
        b.inputs["Subsurface Weight"].default_value = 0.22
        b.inputs["Subsurface Radius"].default_value = (0.036, 0.014, 0.008)
    return m


def mat_plain(name, rgb, rough):
    m = bpy.data.materials.new(name)
    _t, b = _nodes(m)
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = rough
    return m


def put(ob, m):
    ob.data.materials.clear()
    ob.data.materials.append(m)


# ---------------------------------------------------------------------------
# ОДЕТЬ
# ---------------------------------------------------------------------------

def dress(body):
    made = []

    # ПАЛЬТО: от основания шеи до бёдер по телу, дальше подол свободно вниз.
    # Верхнюю границу ведём НЕ по высоте, а по высоте минус расстояние от оси:
    # горловина у шеи выше, чем срез у плеча, иначе пальто «съедает» шею.
    def keep_coat(c):
        if c.z > Y_CHIN - 0.045:
            return False
        if c.z > Y_SHOULDER + 0.02 and math.hypot(c.x, c.y) > 0.075:
            return False
        return c.z > Y_CROTCH - 0.02
    coat = cut(body, "Пальто", keep_coat, offset=0.011)
    # подол: до середины голени, слегка расходясь
    hem_down(coat, [(Y_CROTCH - 0.10, 1.06),
                    (Y_KNEE + 0.06, 1.10),
                    (Y_KNEE - 0.10, 1.12),
                    (Y_KNEE - 0.115, 1.12)])   # ступень вплотную: острый обрез
    solidify(coat, 0.007)
    smooth(coat, 1)
    put(coat, mat_wool("сукно пальто", (0.052, 0.050, 0.048)))
    made.append(coat)

    # САПОГИ: от подъёма до середины голени, голенище не расширяется.
    def keep_boot(c):
        return c.z < Y_ANKLE + 0.02
    boots = cut(body, "Сапоги", keep_boot, offset=0.006)
    hem_down(boots, [(Y_ANKLE + 0.16, 1.02), (Y_KNEE - 0.30, 1.00)])
    solidify(boots, 0.005)
    smooth(boots, 1)
    put(boots, mat_leather("кожа сапог", (0.020, 0.017, 0.015)))
    made.append(boots)

    # КОСОВОРОТКА: виден только край у горла, но без него в вырезе пальто
    # чернота, и шея висит в пустоте.
    def keep_shirt(c):
        return Y_SHOULDER - 0.10 < c.z < Y_CHIN - 0.030
    shirt = cut(body, "Косоворотка", keep_shirt, offset=0.005)
    solidify(shirt, 0.003)
    smooth(shirt, 1)
    put(shirt, mat_wool("холст рубахи", (0.42, 0.40, 0.36)))
    made.append(shirt)

    # КАРТУЗ: тулья по черепу, козырёк — дуга вперёд.
    def keep_cap(c):
        return c.z > Y_TOP - 0.075
    cap = cut(body, "Картуз", keep_cap, offset=0.012)
    solidify(cap, 0.005)
    smooth(cap, 1)
    put(cap, mat_wool("сукно картуза", (0.045, 0.044, 0.046)))
    made.append(cap)
    made.append(_visor())

    return made


def _visor():
    """Козырёк: плоская дуга ВПЕРЁД (−Y). Отдельной деталью, потому что по телу
    он не кроится — его в теле нет."""
    me = bpy.data.meshes.new("Козырёк")
    bm = bmesh.new()
    a0, a1 = 0.62 * math.pi, 1.38 * math.pi
    n = 10
    rows = []
    for (rx, ry, cy, z) in ((0.084, 0.098, 0.012, Y_TOP - 0.072),
                            (0.091, 0.132, -0.028, Y_TOP - 0.086)):
        row = []
        for i in range(n + 1):
            a = a0 + (a1 - a0) * i / n
            row.append(bm.verts.new((rx * math.sin(a), cy + ry * math.cos(a), z)))
        rows.append(row)
    for i in range(n):
        bm.faces.new((rows[0][i], rows[0][i + 1], rows[1][i + 1], rows[1][i]))
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("Козырёк", me)
    bpy.context.scene.collection.objects.link(ob)
    solidify(ob, 0.004)
    put(ob, mat_wool("сукно козырька", (0.040, 0.039, 0.041)))
    return ob


def hair_and_face():
    """Волосы, бакенбарды и усы. Усы у взрослого мужчины 1890-х — норма, а не
    характер: гладко выбритое лицо в эту эпоху скорее исключение."""
    me = bpy.data.meshes.new("Волосы")
    bm = bmesh.new()
    for s in (1.0, -1.0):        # бакенбарды
        bmesh.ops.create_uvsphere(
            bm, u_segments=8, v_segments=6, radius=1.0,
            matrix=Matrix.Translation(Vector((s * 0.070, -0.010, Y_CHIN + 0.075)))
            @ Matrix.Diagonal(Vector((0.012, 0.022, 0.032)).to_4d()))
    bmesh.ops.create_uvsphere(   # усы
        bm, u_segments=10, v_segments=6, radius=1.0,
        matrix=Matrix.Translation(Vector((0.0, -0.082, Y_CHIN + 0.070)))
        @ Matrix.Diagonal(Vector((0.028, 0.014, 0.008)).to_4d()))
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("Волосы", me)
    bpy.context.scene.collection.objects.link(ob)
    smooth(ob, 1)
    put(ob, mat_plain("волос", (0.055, 0.038, 0.026), 0.72))
    return ob


# ---------------------------------------------------------------------------
# ПРОВЕРКА ГЛАЗАМИ
# ---------------------------------------------------------------------------

def _look_at(frm, to):
    d = to - frm
    up = 'Y' if abs(d.normalized().y) < 0.98 else 'Z'
    return d.to_track_quat('-Z', up).to_euler()


def stage():
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE_NEXT'
    sc.render.resolution_x = 460
    sc.render.resolution_y = 940
    sc.view_settings.view_transform = 'Standard'
    w = bpy.data.worlds.new("w")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.34, 0.36, 0.39, 1)
    sc.world = w
    for name, pos, energy in (("рисующий", (2.2, -2.6, 2.6), 110.0),
                              ("заполняющий", (-2.8, -1.6, 1.4), 38.0),
                              ("контровой", (0.4, 3.2, 2.4), 90.0)):
        lt = bpy.data.lights.new(name, 'AREA')
        lt.energy = energy
        lt.size = 2.0
        lo = bpy.data.objects.new(name, lt)
        lo.location = pos
        lo.rotation_euler = _look_at(Vector(pos), Vector((0, 0, 1.0)))
        bpy.context.collection.objects.link(lo)


def turnaround():
    sc = bpy.context.scene
    stage()
    cd = bpy.data.cameras.new("cam")
    cd.lens = 70.0
    cam = bpy.data.objects.new("cam", cd)
    bpy.context.collection.objects.link(cam)
    sc.camera = cam
    for i, ang in enumerate((0.0, 40.0, 90.0, 180.0)):
        a = math.radians(ang)
        d = 3.4
        cam.location = (d * math.sin(a), -d * math.cos(a), 0.95)
        cam.rotation_euler = _look_at(Vector(cam.location), Vector((0, 0, 0.88)))
        sc.render.filepath = "/tmp/claude-live/_p2_%d.png" % i
        bpy.ops.render.render(write_still=True)
        print("[человек] вид %3.0f°" % ang)
    # КРУПНО ЛИЦО: на общем плане ткань и черты не видны, а судят по ним.
    cam.location = (0.30, -0.85, 1.60)
    cam.rotation_euler = _look_at(Vector(cam.location), Vector((0, 0, 1.60)))
    sc.render.resolution_x = 700
    sc.render.resolution_y = 700
    sc.render.filepath = "/tmp/claude-live/_p2_face.png"
    bpy.ops.render.render(write_still=True)
    print("[человек] лицо крупно")


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    clear()
    body = append_body()
    put(body, mat_skin("кожа"))
    dress(body)
    hair_and_face()

    n = sum(len(o.data.vertices) for o in bpy.data.objects if o.type == 'MESH')
    print("[человек] всего вершин в фигуре: %d" % n)

    if "--render" in argv:
        turnaround()
        return
    out = argv[argv.index("--out") + 1] if "--out" in argv \
        else "game2/assets/models/person.glb"
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.export_scene.gltf(filepath=out, export_format='GLB', export_apply=True)
    print("[человек] вывезено:", out, os.path.getsize(out), "байт")


if __name__ == "__main__":
    main()
