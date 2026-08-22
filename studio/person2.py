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
    """Приложить болванку — И ВСЁ, ЧТО К НЕЙ ПРИЛАГАЕТСЯ.

    ГЛАВНАЯ ОШИБКА ЭТОГО ЗАХОДА БЫЛА ЗДЕСЬ. Я брал из набора один объект —
    тело — и всё остальное строил руками поверх. А в наборе рядом лежат
    ГЛАЗНЫЕ ЯБЛОКИ этого самого тела: GEO-body_male_realistic.eye.L и .eye.R,
    по 546 вершин, с готовой развёрткой. Я их не загрузил, глазницы остались
    пустыми, и потом я разглядывал рендер и писал «глаза мёртвые». Глаз там
    не было вовсе.
    Там же лежат отдельная голова с анимационной топологией (3242 вершины),
    склера и радужка отдельными объектами, полный скелет. Инвентаризацию
    набора надо было сделать первым делом, а не после трёх заходов.

    Все части приходят в одной системе координат, поэтому масштабируются и
    ставятся на пол ОДНИМ преобразованием — иначе глаза уедут из глазниц.
    """
    if not os.path.exists(BUNDLE):
        raise SystemExit("нет набора болванок: %s" % BUNDLE)
    want = [BODY, BODY + ".eye.L", BODY + ".eye.R"]
    with bpy.data.libraries.load(BUNDLE, link=False) as (src, dst):
        have = [n for n in want if n in src.objects]
        missing = [n for n in want if n not in src.objects]
        if BODY not in have:
            raise SystemExit("в наборе нет «%s»" % BODY)
        dst.objects = have
    if missing:
        print("[человек] в наборе не нашлось:", ", ".join(missing))

    parts = [o for o in dst.objects if o is not None and o.type == 'MESH']
    for o in parts:
        bpy.context.scene.collection.objects.link(o)
    body = [o for o in parts if o.name.startswith(BODY) and "eye" not in o.name][0]
    eyes = [o for o in parts if "eye" in o.name]
    body.name = "Тело"

    # ОДНО преобразование на все части. Считаем его по ТЕЛУ и применяем ко
    # всем: если пересчитывать для каждой части отдельно, глаз встанет по
    # своему габариту и вылезет из глазницы.
    zs = [(body.matrix_world @ v.co).z for v in body.data.vertices]
    was = max(zs) - min(zs)
    k = TARGET_H / was
    lo = min(zs) * k
    M = (Matrix.Translation(Vector((0, 0, -lo)))
         @ Matrix.Diagonal(Vector((k, k, k)).to_4d()))
    for o in parts:
        me = o.data
        me.transform(M @ o.matrix_world)
        o.matrix_world = Matrix.Identity(4)
        me.update()
    bpy.context.view_layer.objects.active = body
    bpy.context.view_layer.update()
    print("[человек] болванка: вершин %d, рост %.3f -> %.3f м"
          % (len(body.data.vertices), was, body.dimensions.z))
    for e in eyes:
        print("[человек] глаз «%s»: вершин %d, поперечник %.1f мм"
              % (e.name.split(".", 1)[1], len(e.data.vertices),
                 e.dimensions.x * 1000))
    return body, eyes


def mat_eye():
    """ГЛАЗ. Три вещи, без которых он мёртвый, и все три — не про цвет.

    ВЛАЖНОСТЬ. Роговица покрыта слёзной плёнкой, это зеркало. Шероховатость
    0.05 против 0.5 у кожи — именно поэтому в глазу видно отражение окна, а в
    щеке нет. Один этот блик и оживляет взгляд.
    РАДУЖКА ТЁМНАЯ ПО КРАЮ. У неё есть лимб — тёмное кольцо по границе с
    белком. Без него радужка выглядит наклейкой.
    БЕЛОК НЕ БЕЛЫЙ. Склера сероватая и краснеет к углам: там сосуды. Чисто
    белый белок — первое, что выдаёт куклу.
    """
    m = bpy.data.materials.new("глаз")
    m.use_nodes = True
    tree = m.node_tree
    b = tree.nodes["Principled BSDF"]
    n = tree.nodes

    tex = n.new("ShaderNodeTexCoord")
    # расстояние от оси взгляда: по нему разделяются радужка, лимб и белок
    sep = n.new("ShaderNodeSeparateXYZ")
    tree.links.new(tex.outputs["Object"], sep.inputs["Vector"])
    dist = n.new("ShaderNodeVectorMath")
    dist.operation = 'LENGTH'
    tree.links.new(tex.outputs["Object"], dist.inputs[0])

    ramp = n.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = 'CONSTANT'
    e = ramp.color_ramp.elements
    e[0].position = 0.0
    e[0].color = (0.045, 0.030, 0.020, 1)      # зрачок
    e[1].position = 0.30
    e[1].color = (0.28, 0.20, 0.10, 1)          # радужка, карий
    e2 = ramp.color_ramp.elements.new(0.52)
    e2.color = (0.10, 0.07, 0.04, 1)            # лимб — тёмное кольцо
    e3 = ramp.color_ramp.elements.new(0.58)
    e3.color = (0.72, 0.68, 0.66, 1)            # склера: сероватая, не белая
    tree.links.new(dist.outputs["Value"], ramp.inputs["Fac"])
    tree.links.new(ramp.outputs["Color"], b.inputs["Base Color"])

    b.inputs["Roughness"].default_value = 0.05  # слёзная плёнка — зеркало
    if "Specular IOR Level" in b.inputs:
        b.inputs["Specular IOR Level"].default_value = 0.8
    if "Coat Weight" in b.inputs:
        b.inputs["Coat Weight"].default_value = 0.5
        b.inputs["Coat Roughness"].default_value = 0.02
    return m


# ---------------------------------------------------------------------------
# КРОЙ
#
# Выкройка — это КОПИЯ УЧАСТКА ТЕЛА. Берём сетку тела, оставляем нужную область,
# отодвигаем каждую вершину наружу по её нормали на толщину ткани. Дальше
# полученная оболочка живёт своей жизнью: подол можно вытянуть вниз, край
# подвернуть, ткань уплотнить.
# ---------------------------------------------------------------------------

def cut(body, name, keep, offset=0.008, relax=0):
    """Скроить деталь: оставить вершины, где keep(co) истинно, и отодвинуть.

    RELAX — ЧИСЛО ПРОХОДОВ РАЗГЛАЖИВАНИЯ, и без него выкройка не одежда.
    Первый заход дал пальто, облегающее как гидрокостюм: сквозь сукно
    просвечивали грудные мышцы и кубики пресса. Это прямое следствие способа —
    выкройка есть копия тела, и она наследует ВСЮ его анатомию. Настоящая
    ткань висит: она перекрывает впадины и ложится по крупной форме. Здесь это
    и делает разглаживание — оно стирает мелкий рельеф, оставляя объём.
    """
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
    for _ in range(relax):
        bmesh.ops.smooth_vert(bm, verts=list(bm.verts), factor=0.6,
                              use_axis_x=True, use_axis_y=True, use_axis_z=True)
    if relax:
        # разглаживание стягивает оболочку внутрь тела — возвращаем наружу
        bm.normal_update()
        for v in bm.verts:
            v.co += v.normal * offset * 0.7
    bm.to_mesh(me)
    bm.free()
    me.update()
    print("[крой] %-12s вершин %d" % (name, len(me.vertices)))
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
    # ВЫБОР КРОМКИ. Первый заход вытянул вместе с подолом и РУКАВА: срез рукава
    # у пальто оказался ровно на той же высоте, что и низ полы, и фильтр «самая
    # нижняя кромка» захватил обе. Рукава уехали вниз до колен и фигура стала
    # монахом. Различает их не высота, а УДАЛЁННОСТЬ ОТ ОСИ ТЕЛА: срез рукава
    # висит в стороне (|x| велик), пола идёт вокруг оси.
    zs = [v.co.z for e in edges for v in e.verts]
    z_lo = min(zs)
    edges = [e for e in edges
             if all(v.co.z < z_lo + 0.06 for v in e.verts)
             and all(abs(v.co.x) < 0.16 for v in e.verts)]
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


def shaft_up(ob, levels):
    """Вытянуть ВЕРХНЮЮ кромку вверх: голенище сапога.

    У сапога голенище растёт от щиколотки ВВЕРХ по голени. hem_down тянул
    нижнюю кромку и делал из сапога ласту: подошва уезжала вниз, а голенища
    не появлялось вовсе.
    """
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.edges.ensure_lookup_table()
    edges = [e for e in bm.edges if len(e.link_faces) == 1]
    if not edges:
        bm.free(); return
    zs = [v.co.z for e in edges for v in e.verts]
    z_hi = max(zs)
    edges = [e for e in edges if all(v.co.z > z_hi - 0.05 for v in e.verts)]
    if not edges:
        bm.free(); return
    for z_to, widen in levels:
        cx = sum(v.co.x for e in edges for v in e.verts) / (2 * len(edges))
        cy = sum(v.co.y for e in edges for v in e.verts) / (2 * len(edges))
        r = bmesh.ops.extrude_edge_only(bm, edges=edges)
        for v in [g for g in r["geom"] if isinstance(g, bmesh.types.BMVert)]:
            v.co.x = cx + (v.co.x - cx) * widen
            v.co.y = cy + (v.co.y - cy) * widen
            v.co.z = z_to
        edges = [g for g in r["geom"] if isinstance(g, bmesh.types.BMEdge)
                 and len(g.link_faces) == 1]
    bm.to_mesh(me); bm.free(); me.update()


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

MAT_DIR = os.environ.get("MAT_DIR", "/tmp/claude-live/mat")
RES = "1K-PNG"


def _map(asset, kind):
    return os.path.join(MAT_DIR, asset, "%s_%s_%s.png" % (asset, RES, kind))


def _img(path, non_color=False):
    if not os.path.exists(path):
        raise SystemExit("нет карты %s — запусти studio/fetch_materials.py" % path)
    im = bpy.data.images.load(path, check_existing=True)
    if non_color:
        # НЕ ЦВЕТ, А ЧИСЛО. Карты нормалей и шероховатости хранят величины, а не
        # цвета; если движок прогонит их через гамму sRGB, рельеф станет вдвое
        # мягче, а шероховатость поедет вся. Это самая частая тихая ошибка при
        # подключении сканов, и она не видна иначе как по сравнению с эталоном.
        im.colorspace_settings.name = 'Non-Color'
    return im


def _nodes(m):
    m.use_nodes = True
    return m.node_tree, m.node_tree.nodes["Principled BSDF"]


def _uv_scale(tree, scale):
    """Сколько раз скан укладывается на метр поверхности.

    Величина не декоративная: скан снят с куска ткани известного размера, и
    если положить его не в том масштабе, нитка окажется толщиной с палец. У
    сукна шаг переплетения около миллиметра, поэтому квадрат скана — это
    примерно 20 см ткани, то есть 5 укладок на метр.
    """
    n = tree.nodes
    tex = n.new("ShaderNodeTexCoord")
    mp = n.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (scale, scale, scale)
    tree.links.new(tex.outputs["UV"], mp.inputs["Vector"])
    return mp


def mat_scan(name, asset, scale=5.0, tint=None, rough_shift=0.0, sheen=0.0):
    """МАТЕРИАЛ ИЗ НАСТОЯЩЕГО СКАНА, а не из формулы.

    До этого ткань я писал процедурно: волна для саржи, шум для ворса. Это
    похоже на ткань ровно настолько, насколько формула похожа на нитку.
    Здесь — фотограмметрический скан с ambientCG (лицензия CC0): карта цвета с
    неровностями крашения, карта нормалей с каждой ниткой переплетения, карта
    шероховатости, где ворс блестит иначе, чем впадины между нитями, и карта
    затенения складок.

    TINT перекрашивает скан, не трогая рельеф: сукно 1890-х глухого тёмного
    тона, а снятый образец светлее. Умножение на цвет сохраняет всю мелкую
    неровность крашения и только смещает общий тон — так и красят ткань.
    """
    m = bpy.data.materials.new(name)
    tree, b = _nodes(m)
    n = tree.nodes
    mp = _uv_scale(tree, scale)

    col = n.new("ShaderNodeTexImage")
    col.image = _img(_map(asset, "Color"))
    tree.links.new(mp.outputs["Vector"], col.inputs["Vector"])
    src = col.outputs["Color"]
    if tint is not None:
        mul = n.new("ShaderNodeMix")
        mul.data_type = 'RGBA'
        mul.blend_type = 'MULTIPLY'
        mul.inputs["Factor"].default_value = 1.0
        tree.links.new(col.outputs["Color"], mul.inputs[6])
        mul.inputs[7].default_value = (*tint, 1.0)
        src = mul.outputs[2]
    # ЗАТЕНЕНИЕ СКЛАДОК идёт в цвет, а не отдельным входом: у Principled нет
    # входа AO, а без него ткань выглядит выглаженной утюгом.
    ao_p = _map(asset, "AmbientOcclusion")
    if os.path.exists(ao_p):
        ao = n.new("ShaderNodeTexImage")
        ao.image = _img(ao_p, non_color=True)
        tree.links.new(mp.outputs["Vector"], ao.inputs["Vector"])
        mix = n.new("ShaderNodeMix")
        mix.data_type = 'RGBA'
        mix.blend_type = 'MULTIPLY'
        mix.inputs["Factor"].default_value = 0.75
        tree.links.new(src, mix.inputs[6])
        tree.links.new(ao.outputs["Color"], mix.inputs[7])
        src = mix.outputs[2]
    tree.links.new(src, b.inputs["Base Color"])

    ro = n.new("ShaderNodeTexImage")
    ro.image = _img(_map(asset, "Roughness"), non_color=True)
    tree.links.new(mp.outputs["Vector"], ro.inputs["Vector"])
    if rough_shift:
        add = n.new("ShaderNodeMath")
        add.operation = 'ADD'
        add.inputs[1].default_value = rough_shift
        add.use_clamp = True
        tree.links.new(ro.outputs["Color"], add.inputs[0])
        tree.links.new(add.outputs["Value"], b.inputs["Roughness"])
    else:
        tree.links.new(ro.outputs["Color"], b.inputs["Roughness"])

    nr = n.new("ShaderNodeTexImage")
    nr.image = _img(_map(asset, "NormalGL"), non_color=True)
    tree.links.new(mp.outputs["Vector"], nr.inputs["Vector"])
    nm = n.new("ShaderNodeNormalMap")
    nm.inputs["Strength"].default_value = 1.0
    tree.links.new(nr.outputs["Color"], nm.inputs["Color"])
    tree.links.new(nm.outputs["Normal"], b.inputs["Normal"])

    if sheen and "Sheen Weight" in b.inputs:
        # ВОРС шерсти: светлый ободок по краю силуэта, там где смотришь на
        # ткань вскользь. Скан его не содержит — это свойство объёма волокна,
        # а не поверхности, и задаётся отдельно.
        b.inputs["Sheen Weight"].default_value = sheen
        b.inputs["Sheen Roughness"].default_value = 0.4
    return m


def paint_skin(body, eyes):
    """РАСКРАСИТЬ КОЖУ ПО АНАТОМИИ. Тон пишется в вершины, а не берётся из
    тайловой картинки, и вот почему это правильнее.

    Свободных фотосканов ЛИЦА под открытой лицензией нет — есть тайловые
    заплатки кожи. Заплатка не знает, где губы и где нос: она повторяется. А
    кожа человека не однотонная, и неоднотонна она НЕ СЛУЧАЙНО.

    ПРАВИЛО ТРЁХ ЗОН — то, чему учат портретистов, и оно про анатомию:
      ЛОБ И ВИСКИ — желтее: кость близко к поверхности, крови мало.
      СЕРЕДИНА ЛИЦА (нос, скулы, уши) — краснее всего: капилляры густые и
        поверхностные. Кончик носа и уши на просвет красные.
      ПОДБОРОДОК И ЧЕЛЮСТЬ — холоднее, в синеву: кожа толще, а у мужчины ещё
        и тень от щетины даже сразу после бритья.
    Плюс губы, где кожа переходит в слизистую, и веки, где она тоньше всего.
    Ровно окрашенная кожа выглядит парафином — именно это и было в кадре.

    ЖИРНОСТЬ ТОЖЕ ПО ЗОНАМ. Лоб и нос блестят (сальные железы гуще), щёки
    матовые. Разница в блеске между Т-зоной и щекой заметнее, чем разница в
    цвете, и без неё лицо выглядит вылепленным из одного вещества.
    """
    me = body.data
    if "тон" not in me.color_attributes:
        me.color_attributes.new(name="тон", type='FLOAT_COLOR', domain='POINT')
    if "жир" not in me.attributes:
        me.attributes.new(name="жир", type='FLOAT', domain='POINT')
    col = me.color_attributes["тон"]
    oil = me.attributes["жир"]

    BASE = Vector((0.60, 0.435, 0.355))
    WARM = Vector((0.115, -0.030, -0.055))   # добавка «краснее»
    YELL = Vector((0.035, 0.020, -0.045))    # добавка «желтее»
    COOL = Vector((-0.075, -0.055, 0.010))   # добавка «холоднее»

    for i, v in enumerate(me.vertices):
        c = v.co
        t = BASE.copy()
        o = 0.0
        # --- лицо ---
        if c.z > Y_CHIN - 0.06:
            h = (c.z - Y_CHIN) / 0.233          # доля высоты головы от подбородка
            face = max(0.0, -c.y) / 0.10        # насколько это перёд лица
            if h > 0.62:                        # лоб и виски
                t += YELL * min(1.0, (h - 0.62) / 0.25) * face
                o += 0.55 * face
            if 0.28 < h < 0.68:                 # середина: нос, скулы
                t += WARM * (1.0 - abs(h - 0.46) / 0.22) * face
            if h < 0.30:                        # подбородок и челюсть
                t += COOL * (1.0 - h / 0.30)
            # кончик носа — самая красная точка лица
            d = (c - Vector((0.0, -0.088, Y_CHIN + 0.100))).length
            if d < 0.030:
                t += WARM * 1.4 * (1.0 - d / 0.030)
                o += 0.7 * (1.0 - d / 0.030)
            # уши — на просвет красные
            if abs(c.x) > 0.062 and Y_CHIN + 0.06 < c.z < Y_CHIN + 0.17:
                t += WARM * 1.2
            # губы: кожа переходит в слизистую
            dl = (c - Vector((0.0, -0.075, Y_CHIN + 0.045))).length
            if dl < 0.026:
                k = 1.0 - dl / 0.026
                t = t.lerp(Vector((0.46, 0.235, 0.215)), k)
                o += 0.9 * k
            # веки — тончайшая кожа, синеет
            for sx in (1.0, -1.0):
                de = (c - Vector((sx * 0.032, -0.070, Y_CHIN + 0.148))).length
                if de < 0.024:
                    t += COOL * 0.9 * (1.0 - de / 0.024)
        # --- кисти: костяшки краснеют ---
        if c.z < Y_CROTCH + 0.10 and abs(c.x) > 0.20:
            t += WARM * 0.55
        col.data[i].color = (t.x, t.y, t.z, 1.0)
        oil.data[i].value = min(1.0, o)
    print("[кожа] тон и жирность расписаны по %d вершинам" % len(me.vertices))


def mat_skin():
    """КОЖА. Тон берётся из вершин (см. paint_skin), а не задан одним цветом.

    ПОДПОВЕРХНОСТНОЕ РАССЕЯНИЕ. Свет уходит под кожу и выходит рядом, на
    разную глубину по цветам: красный около 36 мм, зелёный 14, синий 8. Это
    измеренные длины свободного пробега в человеческой ткани, а не подбор.

    ПОРА шагом около 0.3 мм — рельеф из скана мелкозернистой кожи, берётся
    только карта нормалей: цвет чужой, а размер зерна тот.
    """
    m = bpy.data.materials.new("кожа")
    tree, b = _nodes(m)
    n = tree.nodes

    tone = n.new("ShaderNodeVertexColor")
    tone.layer_name = "тон"
    # мелкая пятнистость поверх зон: кожа неровна и внутри зоны
    noi = n.new("ShaderNodeTexNoise")
    noi.inputs["Scale"].default_value = 28.0
    noi.inputs["Detail"].default_value = 5.0
    hue = n.new("ShaderNodeMix")
    hue.data_type = 'RGBA'
    hue.blend_type = 'OVERLAY'
    hue.inputs["Factor"].default_value = 0.10
    tree.links.new(tone.outputs["Color"], hue.inputs[6])
    tree.links.new(noi.outputs["Color"], hue.inputs[7])
    tree.links.new(hue.outputs[2], b.inputs["Base Color"])

    # ЖИРНОСТЬ: лоб и нос блестят, щёки матовые
    oil = n.new("ShaderNodeAttribute")
    oil.attribute_name = "жир"
    rng = n.new("ShaderNodeMapRange")
    rng.inputs["To Min"].default_value = 0.62      # матовая щека
    rng.inputs["To Max"].default_value = 0.26      # блестящий нос
    tree.links.new(oil.outputs["Fac"], rng.inputs["Value"])
    tree.links.new(rng.outputs["Result"], b.inputs["Roughness"])

    if "Subsurface Weight" in b.inputs:
        b.inputs["Subsurface Weight"].default_value = 0.30
        b.inputs["Subsurface Radius"].default_value = (0.036, 0.014, 0.008)
        if "Subsurface Scale" in b.inputs:
            b.inputs["Subsurface Scale"].default_value = 0.010
    if "Specular IOR Level" in b.inputs:
        b.inputs["Specular IOR Level"].default_value = 0.5

    mp = _uv_scale(tree, 26.0)
    nr = n.new("ShaderNodeTexImage")
    nr.image = _img(_map("Leather029", "NormalGL"), non_color=True)
    tree.links.new(mp.outputs["Vector"], nr.inputs["Vector"])
    nm = n.new("ShaderNodeNormalMap")
    nm.inputs["Strength"].default_value = 0.35
    tree.links.new(nr.outputs["Color"], nm.inputs["Color"])
    tree.links.new(nm.outputs["Normal"], b.inputs["Normal"])
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

    # ШТАНЫ. Между подолом пальто и голенищем сапога был голый участок ноги —
    # человек в пальто на босу ногу. Штаны кроятся от пояса до щиколотки и
    # почти целиком скрыты, но именно этот просвет в 15 см их и требует.
    def keep_trousers(c):
        return c.z < Y_WAIST + 0.02
    trousers = cut(body, "Штаны", keep_trousers, offset=0.010, relax=6)
    solidify(trousers, 0.005)
    smooth(trousers, 1)
    put(trousers, mat_scan("шерсть штанов", "Fabric030", scale=6.0,
                           tint=(0.30, 0.29, 0.27), sheen=0.25))
    made.append(trousers)

    # САПОГИ: стопа по телу, дальше голенище ВВЕРХ по голени до середины.
    def keep_boot(c):
        return c.z < Y_ANKLE + 0.03
    boots = cut(body, "Сапоги", keep_boot, offset=0.008, relax=3)
    shaft_up(boots, [(Y_ANKLE + 0.14, 1.03),
                     (Y_KNEE - 0.16, 1.02),
                     (Y_KNEE - 0.14, 1.02)])   # ступень вплотную: жёсткий край
    solidify(boots, 0.005)
    smooth(boots, 1)
    put(boots, mat_scan("кожа сапог", "Leather027", scale=9.0,
                        tint=(0.55, 0.52, 0.50), rough_shift=-0.12))
    made.append(boots)

    # КОСОВОРОТКА: виден только край у горла, но без него в вырезе пальто
    # чернота, и шея висит в пустоте.
    def keep_shirt(c):
        return Y_SHOULDER - 0.14 < c.z < Y_CHIN - 0.020
    shirt = cut(body, "Косоворотка", keep_shirt, offset=0.006, relax=4)
    solidify(shirt, 0.003)
    smooth(shirt, 1)
    put(shirt, mat_scan("холст рубахи", "Fabric066", scale=10.0,
                        tint=(0.85, 0.83, 0.76), sheen=0.15))
    made.append(shirt)

    # ПАЛЬТО. РУКАВ КОНЧАЕТСЯ У ЗАПЯСТЬЯ, а не у колена: в первом заходе я
    # обрезал всю выкройку по одной высоте, и рукав уехал вниз вместе с полой.
    # Запястье находится примерно на высоте паха — но отличить его от полы
    # можно только по удалённости от оси, потому и условие двойное.
    def keep_coat(c):
        if c.z > Y_CHIN - 0.055:
            return False
        if c.z > Y_SHOULDER + 0.015 and math.hypot(c.x, c.y) > 0.085:
            return False
        far = abs(c.x) > 0.15                      # рука, а не корпус
        if far:
            return c.z > Y_CROTCH + 0.055          # обрез рукава у запястья
        return c.z > Y_CROTCH - 0.02
    coat = cut(body, "Пальто", keep_coat, offset=0.016, relax=10)
    hem_down(coat, [(Y_CROTCH - 0.12, 1.05),
                    (Y_KNEE + 0.04, 1.10),
                    (Y_KNEE - 0.12, 1.13),
                    (Y_KNEE - 0.135, 1.13)])   # ступень вплотную: острый обрез
    solidify(coat, 0.008)
    smooth(coat, 1)
    put(coat, mat_scan("сукно пальто", "Fabric039", scale=5.0,
                       tint=(0.26, 0.25, 0.25), sheen=0.35))
    made.append(coat)

    # КАРТУЗ: тулья по черепу до линии бровей, козырёк отдельной деталью.
    def keep_cap(c):
        return c.z > Y_TOP - 0.098
    cap = cut(body, "Картуз", keep_cap, offset=0.016, relax=4)
    solidify(cap, 0.006)
    smooth(cap, 1)
    put(cap, mat_scan("сукно картуза", "Fabric039", scale=9.0,
                      tint=(0.22, 0.22, 0.23), sheen=0.35))
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
    put(ob, mat_scan("сукно козырька", "Fabric039", scale=12.0,
                     tint=(0.20, 0.20, 0.21), sheen=0.30))
    return ob


# ---------------------------------------------------------------------------
# ВОЛОСЫ — КРИВЫМИ, А НЕ ШАРАМИ
#
# До этого я лепил бакенбарды и усы из эллипсоидов. Это не волосы, и никакая
# доводка чисел этого не исправит: волос — это НИТЬ, и всё, по чему глаз узнаёт
# причёску, живёт в нитях. Направление роста, изгиб под своим весом, разная
# длина, торчащие пряди, просвет у корней.
#
# В играх волосы почти всегда делают КАРТАМИ-ПОЛОСКАМИ: низкополигональные
# плоскости с текстурой прядей и прозрачностью, уложенные слоями. Здесь взяты
# КРИВЫЕ — настоящая грумерская система Блендера, где каждый волос это кривая.
# Для кадра она честнее; для телефона её потом придётся запечь в те же карты, и
# это отдельная работа, которую надо будет сделать.
#
# ПРИЧЁСКА МУЖЧИНЫ 30–40 ЛЕТ ПРОСТОГО СОСЛОВИЯ, 1894 ГОД: коротко стриженые
# волосы под картуз, борода. Бритое лицо в это время у простого сословия
# скорее исключение, чем правило.
# ---------------------------------------------------------------------------

POINTS = 6            # точек на волос: меньше — ломаная, больше — впустую


def _scalp(co):
    """Волосистая часть головы: от линии роста волос назад и вниз до затылка."""
    if co.z < Y_CHIN + 0.108:
        return False
    front = -0.070 + 0.5 * abs(co.x)     # линия роста: спереди ниже, к вискам поднимается
    return co.y > front


def _beard(co):
    """Борода: подбородок, щёки до линии «угол рта — козелок уха», шея под
    челюстью. Верхняя граница наклонная — так борода и растёт."""
    if not (Y_CHIN - 0.050 < co.z < Y_CHIN + 0.085):
        return False
    if co.y > -0.010:
        return False
    return co.z < Y_CHIN + 0.070 - 0.42 * abs(co.x)


def _beard_len(co):
    """Длина бороды от точки: у скул коротко, к подбородку вдвое длиннее.
    Ровная по длине борода читается приклеенным щитом."""
    d = math.hypot(co.x * 1.6, co.z - (Y_CHIN + 0.010))
    return 1.0 + 1.1 * max(0.0, 1.0 - d / 0.075)


def _stache(co):
    """Усы: над верхней губой, до уголков рта. У мужчины 1890-х борода почти
    всегда с усами; голая губа при бороде выглядит нарочно."""
    return (Y_CHIN + 0.058 < co.z < Y_CHIN + 0.082
            and co.y < -0.055 and abs(co.x) < 0.030)


def _brow(co):
    return (Y_CHIN + 0.150 < co.z < Y_CHIN + 0.170
            and co.y < -0.060 and 0.010 < abs(co.x) < 0.050)


def grow(body, name, region, length, droop, spread, thick, dens=90000,
         seed=1, curl=0.0, lay=0.0, lay_dir=(0.0, 0.0, -1.0), taper=None):
    """Вырастить волосы на области тела.

    СЕЕМ ПО ГРАНЯМ, А НЕ ПО ВЕРШИНАМ. Первый заход сажал по одному волосу на
    вершину и дал 94 волоса на всю голову — это не стрижка, а редкие торчащие
    прутья. Вершин у болванки на темени просто мало, и никакая настройка этого
    не изменит. Точки надо брать СЛУЧАЙНО ВНУТРИ ГРАНЕЙ: тогда густота
    задаётся числом волос на квадратный метр кожи и не зависит от сетки.
    Настоящая густота на голове около 200 волос на см², то есть два миллиона
    на квадратный метр; столько нам не нужно и не потянуть — здесь порядка
    90 тысяч, что для кадра достаточно, потому что волос толще настоящего.

    Каждый волос идёт по нормали, на каждом шаге заваливаясь вниз: DROOP —
    это вес. Короткая щетина почти не гнётся, длинная прядь падает. Только
    поэтому стрижка и борода выглядят по-разному при одном направлении роста.

    LAY — НАСКОЛЬКО ВОЛОС ЛЕЖИТ, А НЕ ТОРЧИТ, и без этого причёски не будет.
    Первый заход растил строго по нормали к коже: волосы встали перпендикулярно
    черепу и разошлись венцом во все стороны — солома, воткнутая в голову.
    Настоящий волос выходит из кожи под острым углом и сразу ложится по ней.
    Здесь направление роста — смесь нормали и заданного направления (вниз и
    назад для стрижки, вниз для бороды).

    TAPER — функция длины от точки. Борода не одной длины: у скул щетина
    короткая, к подбородку прядь удлиняется вдвое. Без этого борода выходит
    нагрудником — ровным щитом поперёк груди.
    """
    import random
    rnd = random.Random(seed)
    me = body.data
    me.calc_loop_triangles()

    seeds = []
    total_area = 0.0
    for t in me.loop_triangles:
        c = t.center
        if not region(c):
            continue
        a, b2, c3 = (me.vertices[i].co for i in t.vertices)
        area = (b2 - a).cross(c3 - a).length * 0.5
        total_area += area
        n = dens * area
        k = int(n) + (1 if rnd.random() < (n - int(n)) else 0)
        for _ in range(k):
            u, v = rnd.random(), rnd.random()
            if u + v > 1.0:
                u, v = 1.0 - u, 1.0 - v
            p = a + (b2 - a) * u + (c3 - a) * v
            seeds.append((p, t.normal.copy()))

    if not seeds:
        print("[волосы] %-12s область пуста" % name)
        return None

    cu = bpy.data.hair_curves.new(name)
    ob = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(ob)
    cu.add_curves([POINTS] * len(seeds))

    ld = Vector(lay_dir).normalized()
    flat, rad = [], []
    for p0, n in seeds:
        L = length * rnd.uniform(0.6, 1.3)
        if taper is not None:
            L *= taper(p0)
        d = n.lerp(ld, lay)
        d = (d + Vector((rnd.gauss(0, spread), rnd.gauss(0, spread),
                         rnd.gauss(0, spread)))).normalized()
        p = p0.copy()
        vel = d * (L / (POINTS - 1))
        ph = rnd.uniform(0.0, 6.28)
        for k in range(POINTS):
            flat.extend((p.x, p.y, p.z))
            rad.append(thick * (1.0 - 0.75 * k / (POINTS - 1)))
            vel.z -= droop * (L / (POINTS - 1))
            if curl:
                # ВОЛОС НЕ ПРЯМОЙ. Даже у прямых волос прядь вьётся; без этого
                # причёска выглядит соломой, воткнутой в череп.
                vel.x += curl * math.cos(ph + k * 1.7) * (L / (POINTS - 1))
                vel.y += curl * math.sin(ph + k * 1.7) * (L / (POINTS - 1))
            p = p + vel
    cu.attributes['position'].data.foreach_set('vector', flat)
    if 'radius' in cu.attributes:
        cu.attributes['radius'].data.foreach_set('value', rad)
    cu.update_tag()
    print("[волосы] %-12s волос %d на %.1f см² кожи, длина %.0f мм, толщина %.0f мкм"
          % (name, len(seeds), total_area * 10000, length * 1000, thick * 1e6))
    return ob


def mat_hair(name, rgb, rough=0.28):
    """ВОЛОС — НЕ ПОВЕРХНОСТЬ, А ЦИЛИНДР. Свет в нём идёт вдоль и выходит
    сбоку, отсюда двойной блик и просвет на кончиках. Обычный Principled этого
    не даёт вовсе — нужен отдельный узел для волоса."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.type != 'OUTPUT_MATERIAL':
            nt.nodes.remove(n)
    out = [n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'][0]
    h = nt.nodes.new("ShaderNodeBsdfHairPrincipled")
    if "Color" in h.inputs:
        h.inputs["Color"].default_value = (*rgb, 1.0)
    if "Roughness" in h.inputs:
        h.inputs["Roughness"].default_value = rough
    if "Radial Roughness" in h.inputs:
        h.inputs["Radial Roughness"].default_value = 0.55
    nt.links.new(h.outputs[0], out.inputs["Surface"])
    return m


def hair_and_face(body):
    """Стрижка, борода, брови. Цвет один на всё: волос на голове и в бороде у
    одного человека одного цвета, разница только в длине и толщине."""
    RUS = (0.055, 0.032, 0.020)        # тёмно-русый
    made = []
    head = grow(body, "Стрижка", _scalp, length=0.032, droop=0.30,
                spread=0.10, thick=0.00006, dens=300000, seed=1, curl=0.06,
                lay=0.78, lay_dir=(0.0, 0.55, -1.0))
    if head:
        put(head, mat_hair("волос головы", RUS))
        made.append(head)
    beard = grow(body, "Борода", _beard, length=0.022, droop=0.30,
                 spread=0.16, thick=0.00008, dens=240000, seed=2, curl=0.10,
                 lay=0.62, lay_dir=(0.0, 0.30, -1.0), taper=_beard_len)
    if beard:
        put(beard, mat_hair("волос бороды", RUS, rough=0.34))
        made.append(beard)
    stache = grow(body, "Усы", _stache, length=0.019, droop=0.35,
                  spread=0.18, thick=0.00009, dens=700000, seed=4, curl=0.08,
                  lay=0.80, lay_dir=(0.0, -0.35, -1.0))
    if stache:
        put(stache, mat_hair("волос усов", RUS, rough=0.32))
        made.append(stache)
    brow = grow(body, "Брови", _brow, length=0.011, droop=0.5,
                spread=0.20, thick=0.00008, dens=900000, seed=3,
                lay=0.75, lay_dir=(0.35, -0.5, -0.2))
    if brow:
        put(brow, mat_hair("волос брови", RUS, rough=0.36))
        made.append(brow)
    return made


# ---------------------------------------------------------------------------
# ПРОВЕРКА ГЛАЗАМИ
# ---------------------------------------------------------------------------

def _look_at(frm, to):
    """Направить камеру. Вектор «вверх» ВСЕГДА Z — это мир, а не взгляд.

    Здесь стояло 'Y', и вид со спины выходил ВВЕРХ НОГАМИ: при направлении
    взгляда вдоль оси Y ось «вверх» совпадала с осью взгляда, кватернион
    вырождался и камера переворачивалась. Подпорка «если смотрим вдоль Y, то
    брать Z» лечила симптом: правильный вертикальный вектор в этой сцене — Z,
    всегда, потому что фигура стоит по Z.
    """
    # Ось взгляда '-Z', ось «вверх» 'Y' — это КАМЕРНОЕ пространство Блендера, а
    # не мировое. Я пытался «починить» переворот, поставив сюда 'Z', и сломал
    # хуже: ось взгляда и ось «вверх» совпали, кватернион выродился, и фигура
    # легла набок. Правильная пара для камеры именно ('-Z', 'Y').
    return (to - frm).to_track_quat('-Z', 'Y').to_euler()


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


def turnaround(face_only=False):
    sc = bpy.context.scene
    stage()
    cd = bpy.data.cameras.new("cam")
    cd.lens = 70.0
    cam = bpy.data.objects.new("cam", cd)
    bpy.context.collection.objects.link(cam)
    sc.camera = cam
    for i, ang in enumerate(() if face_only else (0.0, 40.0, 90.0, 180.0)):
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
    body, eyes = append_body()
    paint_skin(body, eyes)
    put(body, mat_skin())
    em = mat_eye()
    for e in eyes:
        put(e, em)
    dress(body)
    hair_and_face(body)

    n = sum(len(o.data.vertices) for o in bpy.data.objects if o.type == 'MESH')
    print("[человек] всего вершин в фигуре: %d" % n)

    if "--render" in argv or "--face" in argv:
        turnaround("--face" in argv)
        return
    out = argv[argv.index("--out") + 1] if "--out" in argv \
        else "game2/assets/models/person.glb"
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.export_scene.gltf(filepath=out, export_format='GLB', export_apply=True)
    print("[человек] вывезено:", out, os.path.getsize(out), "байт")


if __name__ == "__main__":
    main()
