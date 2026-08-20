# -*- coding: utf-8 -*-
"""КАДР: ЧЕЛОВЕК У ВОДЫ ПРОТИВ НИЗКОГО СОЛНЦА. Гатчина, вечер.

Это проверка одного решения: держится ли фильм, в котором главное — МЕСТО, а
человек в нём невелик. Если держится, у нас есть путь; если нет, узнаем это за
день, а не за месяц.

ПОЧЕМУ ИМЕННО КОНТРОВОЙ СВЕТ. Против света лицо не видно вовсе — видны силуэт,
пропорция и движение. Ровно то, что считается числами. Это не обход слабого
места: это самый выигрышный свет в анимации вообще, и им сделаны лучшие кадры
у Миядзаки. Слабость постановкой обращается в силу — так работает режиссура.

ПОЧЕМУ ПАЛЬТО И ФУРАЖКА. Силуэт должен читаться одним пятном. Пальто даёт
крупную форму и закрывает торс и бёдра — там анатомия сложнее всего. Фуражка
ставит на голову ясный признак эпохи и снимает вопрос о причёске. Костюм здесь
работает на постановку, а не на достоверность гардероба.

ЗЕМЛЯ НАСТОЯЩАЯ: web/data/slice.bin, тот же срез Гатчины, по которому ходит
игра. Не декорация «похожего места».

Запуск:
  LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe xvfb-run -a \
    /opt/blender/blender -b -noaudio -P studio/shot_lake.py -- ВЫХОД.png
"""
import bpy, bmesh, math, os, struct, sys, time
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "/tmp/shot.png"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SLICE = os.path.join(ROOT, "web/data/slice.bin")

# --- место в мировых координатах игры (0 — уровень дворца)
SHORE = (-16.0, -478.5)     # урез, найден по данным в браузерной версии
CROP = 420.0                # столько метров, чтобы дальний берег (320 м) попал в кадр
NO_WATER = -32768
# Множитель контрового ободка. Отдельной ручкой — чтобы можно было погасить его
# в ноль и увидеть, что даёт диффуз, а что эмиссия. Спорить о причине свечения
# бессмысленно, пока слагаемые не разделены.
RIM_SCALE = float(os.environ.get('RIM', '1.0'))


def load_slice(path):
    with open(path, "rb") as f:
        raw = f.read()
    assert raw[:4] == b"GSL1", "не тот формат среза"
    n, cell, ox, oz, hmin, hmax = struct.unpack_from("<Ifffff", raw, 4)
    p = 28
    hq = np.frombuffer(raw, dtype="<u2", count=n * n, offset=p).reshape(n, n)
    p += n * n * 2
    lq = np.frombuffer(raw, dtype="<i2", count=n * n, offset=p).reshape(n, n)
    bed = hmin + hq.astype(np.float64) * ((hmax - hmin) / 65535.0)
    lvl = np.where(lq == NO_WATER, np.nan, hmin + lq.astype(np.float64) * 0.01)
    return dict(n=n, cell=cell, ox=ox, oz=oz, bed=bed, lvl=lvl)


def build_terrain(sl):
    n, cell, ox, oz, bed = sl["n"], sl["cell"], sl["ox"], sl["oz"], sl["bed"]
    i0 = max(0, int((SHORE[0] - CROP * 0.5 - ox) / cell))
    i1 = min(n - 1, int((SHORE[0] + CROP * 0.5 - ox) / cell))
    j0 = max(0, int((SHORE[1] - CROP * 0.92 - oz) / cell))
    j1 = min(n - 1, int((SHORE[1] + CROP * 0.08 - oz) / cell))
    W, D = i1 - i0 + 1, j1 - j0 + 1
    bm = bmesh.new()
    vs = []
    for j in range(D):
        row = []
        for i in range(W):
            x = ox + (i0 + i) * cell
            z = oz + (j0 + j) * cell
            row.append(bm.verts.new((x, z, bed[j0 + j, i0 + i])))
        vs.append(row)
    bm.verts.ensure_lookup_table()
    for j in range(D - 1):
        for i in range(W - 1):
            try:
                bm.faces.new((vs[j][i], vs[j][i + 1], vs[j + 1][i + 1], vs[j + 1][i]))
            except ValueError:
                pass
    me = bpy.data.meshes.new("ground")
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new("ground", me)
    bpy.context.collection.objects.link(ob)
    print("рельеф: %d x %d узлов, %d треугольников" % (W, D, (W - 1) * (D - 1) * 2))
    return ob


def build_water(sl, lvl):
    """ГЛАДЬ СТРОИТСЯ ПО СРЕЗУ, А НЕ КЛАДЁТСЯ ПЛОСКОСТЬЮ.

    Первый заход накрыл всё озеро прямоугольником на 420 м — и он закрыл собой
    дальний берег, до которого 320 м. Кадр остался без горизонта суши, то есть
    без того единственного, ради чего затевался вид на озеро.

    Здесь клетка попадает в гладь, только если все четыре её узла мокрые. Берег
    получается изогнутым сам, по настоящей батиметрии, — а изогнутая кромка и
    есть половина того, что делает воду водой.
    """
    n, cell, ox, oz = sl["n"], sl["cell"], sl["ox"], sl["oz"]
    wet = (~np.isnan(sl["lvl"])) & ((sl["lvl"] - sl["bed"]) > 0.03)
    i0 = max(0, int((SHORE[0] - CROP * 0.5 - ox) / cell))
    i1 = min(n - 1, int((SHORE[0] + CROP * 0.5 - ox) / cell))
    j0 = max(0, int((SHORE[1] - CROP * 0.92 - oz) / cell))
    j1 = min(n - 1, int((SHORE[1] + CROP * 0.08 - oz) / cell))
    bm = bmesh.new()
    idx = {}
    cnt = 0
    for j in range(j0, j1):
        for i in range(i0, i1):
            if not (wet[j, i] or wet[j, i + 1] or wet[j + 1, i] or wet[j + 1, i + 1]):
                continue
            q = []
            for (jj, ii) in ((j, i), (j, i + 1), (j + 1, i + 1), (j + 1, i)):
                k = (jj, ii)
                if k not in idx:
                    idx[k] = bm.verts.new((ox + ii * cell, oz + jj * cell, lvl - 0.01))
                q.append(idx[k])
            try:
                bm.faces.new(q)
                cnt += 1
            except ValueError:
                pass
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new('water')
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new('water', me)
    bpy.context.collection.objects.link(ob)
    print("вода: %d клеток (%.0f м2)" % (cnt, cnt * cell * cell))
    return ob


def rest_level(sl):
    v = sl["lvl"][~np.isnan(sl["lvl"])]
    return float(np.median(v))


def ground_at(sl, x, z):
    i = int(round((x - sl["ox"]) / sl["cell"]))
    j = int(round((z - sl["oz"]) / sl["cell"]))
    i = min(max(i, 0), sl["n"] - 1)
    j = min(max(j, 0), sl["n"] - 1)
    return float(sl["bed"][j, i])


# ---------------------------------------------------------------- персонаж
def loft(rings, close_top=True, close_bot=True, nu=28):
    """Тело из горизонтальных сечений: (высота, полуширина, полуглубина).

    ЭТО И ЕСТЬ ОБЪЁМ, которого не было у плоского рисунка. Силуэт под любым
    углом теперь берётся из тела, а не назначается координатами.
    """
    bm = bmesh.new()
    grid = []
    for (y, w, d) in rings:
        row = []
        for i in range(nu):
            a = 2 * math.pi * i / nu
            row.append(bm.verts.new((w * math.sin(a), d * math.cos(a), y)))
        grid.append(row)
    bm.verts.ensure_lookup_table()
    for k in range(len(grid) - 1):
        for i in range(nu):
            m = (i + 1) % nu
            try:
                bm.faces.new((grid[k][i], grid[k][m], grid[k + 1][m], grid[k + 1][i]))
            except ValueError:
                pass
    if close_top:
        p = bm.verts.new((0, 0, rings[-1][0] + 0.01))
        for i in range(nu):
            m = (i + 1) % nu
            try:
                bm.faces.new((grid[-1][i], grid[-1][m], p))
            except ValueError:
                pass
    if close_bot:
        p = bm.verts.new((0, 0, rings[0][0] - 0.01))
        for i in range(nu):
            m = (i + 1) % nu
            try:
                bm.faces.new((grid[0][m], grid[0][i], p))
            except ValueError:
                pass
    me = bpy.data.meshes.new("part")
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new("part", me)
    bpy.context.collection.objects.link(ob)
    return ob


def tube(axis, r0, r1, nu=16):
    """Конечность: осевая ломаная и радиус по ней."""
    bm = bmesh.new()
    grid = []
    n = len(axis)
    for k, (x, y, z) in enumerate(axis):
        t = k / (n - 1)
        r = r0 + (r1 - r0) * t
        nx, ny, nz = (axis[min(k + 1, n - 1)][d] - axis[max(k - 1, 0)][d] for d in range(3))
        L = math.sqrt(nx * nx + ny * ny + nz * nz) or 1
        ax = Vector((nx / L, ny / L, nz / L))
        up = Vector((0, 1, 0)) if abs(ax.z) > 0.9 else Vector((0, 0, 1))
        u = ax.cross(up).normalized()
        v = ax.cross(u).normalized()
        row = []
        for i in range(nu):
            a = 2 * math.pi * i / nu
            p = Vector((x, y, z)) + u * (r * math.cos(a)) + v * (r * math.sin(a))
            row.append(bm.verts.new(p))
        grid.append(row)
    bm.verts.ensure_lookup_table()
    for k in range(len(grid) - 1):
        for i in range(nu):
            m = (i + 1) % nu
            try:
                bm.faces.new((grid[k][i], grid[k][m], grid[k + 1][m], grid[k + 1][i]))
            except ValueError:
                pass
    for row, sgn in ((grid[0], -1), (grid[-1], 1)):
        c = bm.verts.new(tuple(sum(vv.co[d] for vv in row) / nu for d in range(3)))
        for i in range(nu):
            m = (i + 1) % nu
            try:
                bm.faces.new((row[i], row[m], c) if sgn > 0 else (row[m], row[i], c))
            except ValueError:
                pass
    me = bpy.data.meshes.new("limb")
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new("limb", me)
    bpy.context.collection.objects.link(ob)
    return ob


def build_man(HGT=1.78):
    """Мужчина, 1894. Рост 1.78 — семь с половиной голов.

    ЧИСЛА ОТ РОСТА, А НЕ ОТ ГЛАЗА: плечи 0.115 роста в полуширину (20.5 см —
    норма взрослого мужчины), талия 0.092, подол пальто ниже колена (0.33).
    Пропорции взрослого отличаются от подростковых не «на глаз», а вот этими
    отношениями, и именно они делают фигуру взрослой в силуэте.
    """
    H = HGT
    parts = []

    coat = loft([
        (0.845 * H, 0.058, 0.052),      # горловина
        (0.818 * H, 0.132, 0.082),      # плечо
        (0.760 * H, 0.120, 0.082),
        (0.680 * H, 0.101, 0.076),
        (0.600 * H, 0.094, 0.072),      # талия, пальто в талию
        (0.530 * H, 0.104, 0.078),
        (0.430 * H, 0.122, 0.094),
        (0.330 * H, 0.134, 0.104),      # подол ниже колена
    ], close_top=False, close_bot=True)
    parts.append(("coat", coat))

    neck = loft([(0.840 * H, 0.042, 0.040), (0.878 * H, 0.040, 0.038)],
                close_top=False, close_bot=False)
    parts.append(("skin", neck))

    hh = 0.133 * H                      # высота головы
    chin = 0.867 * H
    head = loft([
        (chin + 0.00 * hh, 0.030, 0.038),
        (chin + 0.10 * hh, 0.052, 0.060),
        (chin + 0.26 * hh, 0.066, 0.074),
        (chin + 0.46 * hh, 0.073, 0.082),
        (chin + 0.66 * hh, 0.074, 0.084),
        (chin + 0.84 * hh, 0.066, 0.076),
        (chin + 0.96 * hh, 0.044, 0.050),
    ])
    parts.append(("skin", head))

    # ФУРАЖКА: тулья и козырёк. Два простых тела, но силуэт эпохи задаёт именно
    # она — с ней фигуру не спутать с современной.
    capz = chin + 0.90 * hh
    cap = loft([(capz, 0.080, 0.088), (capz + 0.030, 0.086, 0.094),
                (capz + 0.062, 0.082, 0.090)], close_top=True, close_bot=True)
    parts.append(("dark", cap))
    peak = loft([(capz + 0.004, 0.078, 0.086), (capz + 0.014, 0.080, 0.132)],
                close_top=True, close_bot=True)
    peak.scale = (1.0, 1.0, 0.35)
    parts.append(("dark", peak))

    sh = 0.104 * H
    for s in (-1, 1):
        arm = tube([(s * (sh - 0.020), 0.008, 0.806 * H), (s * (sh - 0.012), 0.014, 0.700 * H),
                    (s * (sh - 0.004), 0.006, 0.598 * H), (s * (sh + 0.004), -0.014, 0.500 * H),
                    (s * (sh + 0.006), -0.026, 0.424 * H)], 0.050, 0.030)
        parts.append(("coat", arm))
        hand = tube([(s * (sh + 0.006), -0.028, 0.418 * H),
                     (s * (sh + 0.006), -0.036, 0.386 * H)], 0.029, 0.022)
        parts.append(("skin", hand))
        leg = tube([(s * 0.048, 0.0, 0.360 * H), (s * 0.046, 0.0, 0.285 * H),
                    (s * 0.044, 0.0, 0.150 * H), (s * 0.042, 0.0, 0.045 * H)], 0.060, 0.044)
        parts.append(("boot", leg))
        foot = tube([(s * 0.042, 0.0, 0.030 * H), (s * 0.042, -0.075, 0.024 * H)], 0.042, 0.030)
        parts.append(("boot", foot))
    return parts


# ---------------------------------------------------------------- материалы
def toon(name, color, size=0.55, smooth=0.03, rim=None, sun=None):
    """Плоский свет + КОНТРОВОЙ ОБОДОК.

    Ободок — не украшение. Против света фигура почти чёрная, и без светящейся
    каймы по краю она сливается с землёй в одно пятно. Кайма ставится там, где
    поверхность смотрит ВСКОЛЬЗЬ (край силуэта) И одновременно в сторону солнца:
    произведение этих двух условий и даёт настоящий контровой ободок, а не
    свечение по всему контуру.
    """
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for nd in list(nt.nodes):
        if nd.type != 'OUTPUT_MATERIAL':
            nt.nodes.remove(nd)
    out = nt.nodes['Material Output']
    t = nt.nodes.new('ShaderNodeBsdfToon')
    t.component = 'DIFFUSE'
    t.inputs['Color'].default_value = tuple(color) + (1,)
    t.inputs['Size'].default_value = size
    t.inputs['Smooth'].default_value = smooth
    if rim is None:
        nt.links.new(t.outputs[0], out.inputs['Surface'])
        return m
    geo = nt.nodes.new('ShaderNodeNewGeometry')
    # СКОЛЬЗЯЩИЙ ВЗГЛЯД СЧИТАЕТСЯ ЯВНО, А НЕ НОДОЙ Layer Weight: у неё
    # неочевидная семантика, и первый заход дал свечение по ВСЕЙ фигуре вместо
    # каймы по краю. |N·I| = 1 в лоб, 0 вскользь; значит край это 1 - |N·I|.
    fac = nt.nodes.new('ShaderNodeVectorMath'); fac.operation = 'DOT_PRODUCT'
    nt.links.new(geo.outputs['Normal'], fac.inputs[0])
    nt.links.new(geo.outputs['Incoming'], fac.inputs[1])
    ab = nt.nodes.new('ShaderNodeMath'); ab.operation = 'ABSOLUTE'
    nt.links.new(fac.outputs['Value'], ab.inputs[0])
    inv = nt.nodes.new('ShaderNodeMath'); inv.operation = 'SUBTRACT'
    inv.inputs[0].default_value = 1.0
    nt.links.new(ab.outputs[0], inv.inputs[1])
    pw = nt.nodes.new('ShaderNodeMath'); pw.operation = 'POWER'
    pw.inputs[1].default_value = 6.0
    nt.links.new(inv.outputs[0], pw.inputs[0])
    dot = nt.nodes.new('ShaderNodeVectorMath'); dot.operation = 'DOT_PRODUCT'
    dot.inputs[1].default_value = tuple(sun)
    nt.links.new(geo.outputs['Normal'], dot.inputs[0])
    # МЯГКАЯ ОБЁРТКА ВМЕСТО СТРОГОГО max(0, N·S).
    # Когда солнце ТОЧНО за фигурой, требование «смотреть вскользь к камере И
    # прямо на солнце» самопротиворечиво: на кромке силуэта нормаль
    # перпендикулярна обоим, и произведение всегда ноль — ободка не было вовсе.
    # Здесь N·S переводится из [-0.4..0.4] в [0..1]: кайма идёт по всему краю,
    # но со стороны света вдвое ярче. Так это и выглядит в рисунке.
    mx = nt.nodes.new('ShaderNodeMapRange')
    mx.inputs['From Min'].default_value = -0.40
    mx.inputs['From Max'].default_value = 0.40
    mx.inputs['To Min'].default_value = 0.18
    mx.inputs['To Max'].default_value = 1.0
    mx.clamp = True
    nt.links.new(dot.outputs['Value'], mx.inputs['Value'])
    mul = nt.nodes.new('ShaderNodeMath'); mul.operation = 'MULTIPLY'
    nt.links.new(pw.outputs[0], mul.inputs[0])
    nt.links.new(mx.outputs['Result'], mul.inputs[1])
    gain = nt.nodes.new('ShaderNodeMath'); gain.operation = 'MULTIPLY'
    gain.inputs[1].default_value = rim[3] * RIM_SCALE
    nt.links.new(mul.outputs[0], gain.inputs[0])
    em = nt.nodes.new('ShaderNodeEmission')
    em.inputs['Color'].default_value = tuple(rim[:3]) + (1,)
    nt.links.new(gain.outputs[0], em.inputs['Strength'])
    add = nt.nodes.new('ShaderNodeAddShader')
    nt.links.new(t.outputs[0], add.inputs[0])
    nt.links.new(em.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs['Surface'])
    return m


def build_clouds(lvl, alt=1400.0, scale=26.0, dens0=0.470, dens1=0.505, em=2.6):
    """ОБЛАКА. Измерено: структура нашего неба 0.014 против 0.14-0.18 у
    референса — в десять раз меньше. Голый градиент вместо неба, и это была
    главная разница, которую я сам не видел.

    Слой облаков — плоскость на 900 м, видимая снизу почти вскользь: перспектива
    сама сжимает шум к горизонту в полосы, и отдельно вытягивать его не нужно.
    ПОДСВЕЧЕНЫ СЗАДИ: тонкий край светится, плотная середина тёмно-лиловая. Это
    обратно обычному облаку и верно именно для заката — солнце за ними.
    """
    bm = bmesh.new()
    # Половина поля зрения по вертикали 9.9°, значит слой на высоте A виден
    # только дальше A/tg(9.9°) = 5.7·A. При 900 м это 5.2 км, а плоскость
    # кончалась на 4.2 — облака лежали ЦЕЛИКОМ ПОД КАДРОМ.
    R = 60000.0
    vs = [bm.verts.new((SHORE[0] + dx * R, SHORE[1] + dz * R, lvl + alt))
          for dx, dz in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    bm.faces.new(vs)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new('clouds')
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new('clouds', me)
    bpy.context.collection.objects.link(ob)

    m = bpy.data.materials.new('clouds')
    m.use_nodes = True
    nt = m.node_tree
    for nd in list(nt.nodes):
        if nd.type != 'OUTPUT_MATERIAL':
            nt.nodes.remove(nd)
    out = nt.nodes['Material Output']
    tc = nt.nodes.new('ShaderNodeTexCoord')
    mp = nt.nodes.new('ShaderNodeMapping')
    mp.inputs['Scale'].default_value = (5.5, 1.0, 1.0)   # полосы вдоль горизонта
    nt.links.new(tc.outputs['Generated'], mp.inputs['Vector'])
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = scale
    nz.inputs['Detail'].default_value = 8.0
    nz.inputs['Roughness'].default_value = 0.62
    nt.links.new(mp.outputs['Vector'], nz.inputs['Vector'])
    # плотность: порог с мягким краем — у облака есть кромка, а не туман
    # КРАЙ У ОБЛАКА РЕЗКИЙ. Мягкий порог (0.36..0.52) давал размытые пятна, и
    # кадр читался дымом: измеренная структура неба не сдвинулась (0.033 -> 0.037).
    # Облако — это форма с кромкой, а не градиент плотности.
    dens = nt.nodes.new('ShaderNodeValToRGB')
    dens.color_ramp.elements[0].position = dens0
    dens.color_ramp.elements[1].position = dens1
    nt.links.new(nz.outputs['Fac'], dens.inputs['Fac'])
    # цвет: тонкое светится тёплым, плотное уходит в лиловую тень
    col = nt.nodes.new('ShaderNodeValToRGB')
    col.color_ramp.elements[0].position = 0.42
    col.color_ramp.elements[0].color = (1.00, 0.72, 0.42, 1)
    col.color_ramp.elements[1].position = 0.86
    col.color_ramp.elements[1].color = (0.16, 0.11, 0.17, 1)
    nt.links.new(nz.outputs['Fac'], col.inputs['Fac'])
    emn = nt.nodes.new('ShaderNodeEmission')
    emn.inputs['Strength'].default_value = em
    nt.links.new(col.outputs['Color'], emn.inputs['Color'])
    tr = nt.nodes.new('ShaderNodeBsdfTransparent')
    mix = nt.nodes.new('ShaderNodeMixShader')
    nt.links.new(dens.outputs['Color'], mix.inputs['Fac'])
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(emn.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs['Surface'])
    # облака не должны бросать тень на озеро и попадать в обводку
    ob.visible_shadow = False
    ob.data.materials.append(m)
    return ob


def water_mat(rough=0.16):
    """Вода. ЗДЕСЬ ФИЗИКА ВЫИГРЫВАЕТ У СТИЛИЗАЦИИ: солнечная дорожка против
    низкого солнца сама выходит правильной формы, если поверхность настоящая.
    Стилизовать её здесь значило бы выдумывать то, что и так верно."""
    m = bpy.data.materials.new('water')
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (0.035, 0.055, 0.070, 1)
    b.inputs['Roughness'].default_value = rough
    b.inputs['IOR'].default_value = 1.333
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = 5.5
    nz.inputs['Detail'].default_value = 6.0
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.10
    nt.links.new(nz.outputs['Fac'], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], b.inputs['Normal'])
    return m


def main():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    sl = load_slice(SLICE)
    lvl = rest_level(sl)
    print("урез %.2f м" % lvl)

    ground = build_terrain(sl)

    # --- ВЕЧЕР. Солнце низко (6°) и ЗА фигурой, над дальним берегом.
    # ГДЕ ЛЕЖИТ СОЛНЕЧНАЯ ДОРОЖКА — ЭТО ГЕОМЕТРИЯ, А НЕ НАСТРОЙКА ЯРКОСТИ.
    # Зеркальная точка солнца лежит в d = h/tg(e) от глаза: при высоте 1.6 м и
    # солнце в 11° это 8 метров, то есть ещё берег — дорожки в кадре не было в
    # принципе. При 7° и камере в 2.4 м это 19.5 м, уже открытая вода.
    # Азимут уведён влево, в ту треть кадра, где вода, а не берег.
    SUN_EL = math.radians(4.2)
    # Азимут подобран так, чтобы дорожка вышла ЗА ФИГУРОЙ: тёмный силуэт на
    # светящейся полосе — это и есть композиция контрового кадра, а не
    # фигура и дорожка порознь в разных углах.
    SUN_AZ = math.radians(-3.0)
    sun_vec = Vector((math.sin(SUN_AZ) * math.cos(SUN_EL),
                      -math.cos(SUN_AZ) * math.cos(SUN_EL),
                      math.sin(SUN_EL)))

    li = bpy.data.lights.new('sun', 'SUN')
    li.energy = 5.5
    li.angle = math.radians(0.53)       # настоящий угловой размер диска
    li.color = (1.0, 0.72, 0.42)        # низкое солнце: путь через атмосферу длинный
    lo = bpy.data.objects.new('sun', li)
    bpy.context.collection.objects.link(lo)
    lo.rotation_euler = Vector((0, 0, -1)).rotation_difference(-sun_vec).to_euler()

    w = bpy.data.worlds.get('World') or bpy.data.worlds.new('World')
    bpy.context.scene.world = w
    w.use_nodes = True
    bgn = w.node_tree.nodes['Background']
    sky = w.node_tree.nodes.new('ShaderNodeTexSky')
    sky.sky_type = 'NISHITA'
    sky.sun_elevation = SUN_EL
    sky.sun_rotation = SUN_AZ
    # ДИСК В НЕБЕ ОБЯЗАН БЫТЬ. Я выключил его, понадеявшись на лампу, — но лампа
    # Солнца в фоне НЕ ВИДНА, она только светит. Воде стало нечего отражать, и
    # дорожка пропала: она ведь и есть отражение диска, а не отдельный эффект.
    # ДИСК ДОЛЖЕН БЫТЬ МНОГО ЯРЧЕ НЕБА ВОКРУГ. На закате небо у солнца и так
    # почти белое; при интенсивности 1.0 диск в нём растворяется, и отражать
    # в воде становится нечего. У настоящего солнца превышение над
    # околосолнечным небом — порядки, а не проценты.
    # Диск ярче неба вокруг, но не втрое от всего купола: интенсивность 12
    # поднимала ВЕСЬ Nishita-купол, и фигура светилась даже при доле
    # рассеянного 0.13. Пять хватает, чтобы дорожка отделилась.
    sky.sun_intensity = 5.0
    if hasattr(sky, 'sun_disc'):
        sky.sun_disc = True
    print('диск неба:', getattr(sky, 'sun_disc', '?'),
          'размер %.3f°' % math.degrees(getattr(sky, 'sun_size', 0.0)))
    sky.altitude = 60
    sky.air_density = 1.6
    sky.dust_density = 2.4              # вечерняя дымка: она и красит небо
    w.node_tree.links.new(sky.outputs[0], bgn.inputs['Color'])
    # НЕБО ЯРКОЕ ДЛЯ ГЛАЗА, ТУСКЛОЕ КАК ИСТОЧНИК.
    #
    # Замерено: при выключенном ободке голова всё равно выходила (255,242,32)
    # при материале почти чёрном — значит фигуру заливала не эмиссия, а само
    # небо. Закатный купол с ярким диском светит как прожектор со всех сторон, и
    # контровой кадр от этого исчезает: тёмным не остаётся ничего.
    #
    # Разделяем по типу луча: камера и зеркальное отражение (вода) видят небо
    # целиком — иначе пропадут и закат, и солнечная дорожка; рассеянный свет
    # берёт от него восьмую часть. Это не подгонка яркости, а разделение двух
    # РАЗНЫХ ролей неба, которые физический движок держит одной величиной.
    lp = w.node_tree.nodes.new('ShaderNodeLightPath')
    mx2 = w.node_tree.nodes.new('ShaderNodeMath'); mx2.operation = 'MAXIMUM'
    w.node_tree.links.new(lp.outputs['Is Camera Ray'], mx2.inputs[0])
    w.node_tree.links.new(lp.outputs['Is Glossy Ray'], mx2.inputs[1])
    mixs = w.node_tree.nodes.new('ShaderNodeMapRange')
    mixs.inputs['To Min'].default_value = 0.045    # каким небо светит
    mixs.inputs['To Max'].default_value = 1.00     # каким небо видно
    w.node_tree.links.new(mx2.outputs['Value'], mixs.inputs['Value'])
    w.node_tree.links.new(mixs.outputs['Result'], bgn.inputs['Strength'])
    # Небо на закате — источник больше солнца по телесному углу, и на полной
    # силе оно засветило фигуру ровным тоном, съев контровой эффект.

    # У ЗЕМЛИ ОБОДКА НЕТ, И ЭТО НЕ ЭКОНОМИЯ. На большой плоскости, которую камера
    # видит вскользь, условие «скользящий взгляд» истинно ВЕЗДЕ — и эмиссия
    # залила весь берег кремовым. Ободок это свойство фигуры, у которой есть
    # край; у земли края в кадре нет. Тёмный берег против светлой воды — то, что
    # и требуется контровому кадру.
    ground.data.materials.append(toon('ground', (0.040, 0.047, 0.030), size=0.14, smooth=0.02))

    # ДВА ЯРУСА. У настоящего заката облака идут не одним слоем, и именно
    # разница масштабов даёт небу структуру, а не один ровный ряд полос.
    build_clouds(lvl)
    low = build_clouds(lvl, alt=620.0, scale=11.0, dens0=0.545, dens1=0.575, em=1.5)
    wob = build_water(sl, lvl)
    wob.data.materials.append(water_mat())

    # --- ФИГУРА у самой кромки, лицом к воде
    fx, fz = SHORE[0] + 0.4, SHORE[1] + 0.5
    fy = ground_at(sl, fx, fz)
    mats = {
        "coat": toon('coat', (0.016, 0.017, 0.024), size=0.50, smooth=0.02,
                     rim=(1.0, 0.78, 0.48, 2.6), sun=sun_vec),
        # ГОЛОВА НЕ ДОЛЖНА СВЕТИТЬСЯ ЯРЧЕ ВСЕГО В КАДРЕ: при усилении 5.0 лицо
        # стало самым светлым пятном и тянуло взгляд как фонарь.
        "skin": toon('skin', (0.042, 0.034, 0.030), size=0.55, smooth=0.03,
                     rim=(1.0, 0.80, 0.55, 1.4), sun=sun_vec),
        "dark": toon('dark', (0.018, 0.019, 0.026), size=0.50, smooth=0.02,
                     rim=(1.0, 0.76, 0.46, 2.4), sun=sun_vec),
        "boot": toon('boot', (0.022, 0.020, 0.024), size=0.50, smooth=0.02,
                     rim=(1.0, 0.74, 0.44, 1.6), sun=sun_vec),
    }
    figure = []
    for kind, ob in build_man():
        ob.data.materials.append(mats[kind])
        ob.location = (fx, fz, fy)
        ob.rotation_euler = (0, 0, math.radians(186))   # спиной к нам, к воде
        figure.append(ob)

    # --- КАМЕРА: средний план, фигура в левой трети, дорожка уходит к горизонту
    cam_d = bpy.data.cameras.new('cam')
    # ДАЛЬНЯЯ ПЛОСКОСТЬ ОТСЕЧЕНИЯ. По умолчанию она около километра, а слой
    # облаков виден только дальше 10 км (высота 1400 м делённая на тангенс
    # верхнего края кадра). Облака отрезались камерой, а я искал ошибку в
    # материале и в размере плоскости.
    cam_d.clip_start = 0.05
    cam_d.clip_end = 200000.0
    cam_d.lens = 58
    cam_d.sensor_width = 36
    cam = bpy.data.objects.new('cam', cam_d)
    bpy.context.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    # ФИГУРА В ЛЕВОЙ ТРЕТИ — ДОВОРОТОМ НА ВЫЧИСЛЕННЫЙ УГОЛ, а не подбором точки
    # взгляда. Первый заход отвёл камеру на 21° при половине поля зрения 17.2°,
    # и фигура просто вышла за кадр. Треть кадра это atan(0.33 * tan(17.2)) = 5.9°.
    import mathutils
    cam.location = (fx + 2.85, fz + 7.40, fy + 1.95)
    half_fov = math.atan(cam_d.sensor_width * 0.5 / cam_d.lens)
    yaw = math.atan(0.34 * math.tan(half_fov))
    # целимся в грудь, а не в пояс: иначе голова уходит за верхний край
    # ЦЕЛИТЬСЯ ПОЧТИ ВРОВЕНЬ. Наклон на 10.7° при половине поля 9.9° выбросил
    # горизонт за верхний край — линия горизонта должна лежать в кадре, иначе
    # это не вид на озеро, а вид на берег.
    d = Vector((fx, fz, fy + 1.72)) - Vector(cam.location)
    d.rotate(mathutils.Matrix.Rotation(-yaw, 4, 'Z'))
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    print('поле зрения %.1f°, доворот %.1f°' % (math.degrees(half_fov) * 2, math.degrees(yaw)))

    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = 40
    sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = 960, 540
    sc.view_settings.view_transform = 'Standard'
    # ИЗМЕРЕНО: 69% площади кадра лежало в самой светлой ступени тона, у
    # референса 3-4%. Кадр был выжжен, и никакая работа с формой этого не
    # исправит, пока масса тона не сядет в середину.
    sc.view_settings.exposure = -1.9

    # КОНТУР ТОЛЬКО ПО СИЛУЭТАМ. Против света внутренних линий почти нет —
    # рисованный кадр в контровом свете и правда почти без линии, одни пятна.
    sc.render.use_freestyle = True
    vl = sc.view_layers[0]
    fs = vl.freestyle_settings
    fs.crease_angle = math.radians(158)
    ls = fs.linesets[0] if fs.linesets else fs.linesets.new('sil')
    coll = bpy.data.collections.new('inked')
    bpy.context.scene.collection.children.link(coll)
    for ob in [ground] + figure:
        coll.objects.link(ob)
    ls.select_by_collection = True
    ls.collection = coll
    ls.select_silhouette = True
    ls.select_border = True
    ls.select_crease = False
    ls.linestyle.color = (0.045, 0.040, 0.060)
    sc.render.line_thickness_mode = 'ABSOLUTE'
    sc.render.line_thickness = 1.1

    sc.render.filepath = OUT
    t0 = time.time()
    bpy.ops.render.render(write_still=True)
    print('КАДР ЗА %.1f с -> %s' % (time.time() - t0, OUT))


main()
