# -*- coding: utf-8 -*-
"""ЛИСТ ПЕРСОНАЖА (設定画) — ФИГУРА ЦЕЛИКОМ, ШТРИХАМИ GREASE PENCIL.

ПЕРСОНАЖ. Гатчина, 1894. Дочь паркового садовника, двенадцать лет. Возраст
выбран не наугад: он даёт причину быть у озера одной и без объяснений, а
двенадцать лет это ещё и рост в шесть с третью головы — заметно короче взрослых
семи с половиной, и разница читается в кадре сразу, без подписи.
Костюм: тёмное платье до середины икры, светлый передник, коса, босиком.
Три больших пятна и одна линия косы — силуэт узнаётся с любого расстояния, а
это единственное требование к дизайну персонажа, которое нельзя обойти.

ПАЛИТРА ОГРАНИЧЕНА НАМЕРЕННО. У Ghibli на весь фильм 262-600 цветов (Ясуда), то
есть цвет назначается один раз и переиспользуется. Здесь девять.

КАК УСТРОЕН РИСУНОК. Три слоя, как на целлулоиде:
    fill   — плоские заливки;
    shade  — тени, слой в режиме MULTIPLY (тень не «цвет потемнее», а
             умножение: так она сохраняет оттенок того, что под ней);
    ink    — линия поверх всего, с переменным нажимом.

ВЕС ЛИНИИ НЕ ПОСТОЯННЫЙ. Свет сверху-справа, поэтому линия тяжелеет слева и
снизу — там, где форма уходит в тень. Ровная линия одного веса выдаёт машину
мгновенно.
"""
import bpy, math, sys, numpy as np

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "/tmp/settei.png"

HEADS = 6.3        # рост в головах: подросток, не взрослый
LIGHT = +1.0       # свет справа: линия и тень тяжелее слева

PALETTE = {
    "ink":     (0.105, 0.075, 0.115),
    "ink2":    (0.34, 0.24, 0.26),      # мягкая линия: складки, черты лица
    "skin":    (0.980, 0.860, 0.780),
    "dress":   (0.235, 0.255, 0.330),
    "apron":   (0.900, 0.885, 0.845),
    "hair":    (0.300, 0.190, 0.130),
    "iris":    (0.300, 0.400, 0.360),
    "shade":   (0.760, 0.755, 0.830),   # умножается на то, что под ним
    "mouth":   (0.640, 0.400, 0.390),
}


def smooth(pts, n=None, closed=True):
    """Катмулл-Ром: ломаный силуэт читается многоугольником, а не телом."""
    m = len(pts)
    n = n or m * 8
    out = []
    for i in range(n):
        u = i / n * m if closed else i / (n - 1) * (m - 1)
        k = int(u) % m if closed else min(int(u), m - 2)
        t = u - int(u)
        g = (lambda j: pts[j % m]) if closed else (lambda j: pts[max(0, min(j, m - 1))])
        p0, p1, p2, p3 = g(k - 1), g(k), g(k + 1), g(k + 2)
        out.append(tuple(
            0.5 * ((2 * p1[d]) + (-p0[d] + p2[d]) * t
                   + (2 * p0[d] - 5 * p1[d] + 4 * p2[d] - p3[d]) * t * t
                   + (-p0[d] + 3 * p1[d] - 3 * p2[d] + p3[d]) * t ** 3)
            for d in range(2)))
    return out


def mirror(half, top, bot):
    """Замкнутый силуэт из ПОЛОВИНЫ профиля: тело симметрично, и описывать надо
    только правую сторону — левая обязана совпасть точно."""
    return [top] + [(x, z) for (x, z) in half] + [bot] + \
           [(-x, z) for (x, z) in reversed(half)]


class Sheet:
    def __init__(self):
        for o in list(bpy.data.objects):
            bpy.data.objects.remove(o, do_unlink=True)
        self.mats = {}
        bpy.ops.object.grease_pencil_add(type='EMPTY')
        self.gp = bpy.context.object
        # слоты чистятся: объект создаётся уже с материалом, и свои съезжают
        self.gp.data.materials.clear()
        self.layers = {}
        for name, blend in (("fill", 'REGULAR'), ("shade", 'MULTIPLY'), ("ink", 'REGULAR')):
            L = self.gp.data.layers.new(name)
            L.use_lights = False
            L.blend_mode = blend
            L.frames.new(1)
            self.layers[name] = L

    def mat(self, name, stroke=None, fill=None):
        key = (name, stroke, fill)
        if key in self.mats:
            return self.mats[key]
        m = bpy.data.materials.new(name)
        bpy.data.materials.create_gpencil_data(m)
        g = m.grease_pencil
        g.show_stroke = stroke is not None
        g.show_fill = fill is not None
        if stroke:
            g.color = tuple(stroke) + (1,)
        if fill:
            g.fill_color = tuple(fill) + (1,)
        self.gp.data.materials.append(m)
        self.mats[key] = len(self.gp.data.materials) - 1
        return self.mats[key]

    def draw(self, layer, pts, radii, mi, cyclic=False):
        dr = self.layers[layer].frames[0].drawing
        dr.add_strokes([len(pts)])
        st = dr.strokes[-1]
        st.material_index = mi
        st.cyclic = cyclic
        for i, (x, z) in enumerate(pts):
            st.points[i].position = (x, 0.0, z)
            st.points[i].radius = radii[i]
            st.points[i].opacity = 1.0

    def flat(self, layer, pts, color):
        self.draw(layer, pts, [0.0008] * len(pts), self.mat('f_' + str(color), fill=color), True)

    def line(self, pts, base=0.009, color=None, cyclic=False):
        """Линия с нажимом: тяжелее там, где форма уходит от света."""
        col = color or PALETTE["ink"]
        r = []
        for (x, z) in pts:
            away = 0.5 - 0.5 * (x * LIGHT) / max(1e-6, max(abs(p[0]) for p in pts) or 1)
            r.append(base * (0.55 + 0.95 * away))
        self.draw("ink", pts, r, self.mat('s_' + str(col), stroke=col), cyclic)


def build():
    S = Sheet()
    Z = lambda h: h                      # высоты прямо в головах

    # --- ПРОПОРЦИИ.半身 подростка: плечи узкие, талия высокая, ноги короче
    # взрослых по отношению к росту. Числа — доли головы от пяток.
    chin, crown = HEADS - 1.0, HEADS
    head_half = [(0.034, 0.00), (0.152, 0.13), (0.252, 0.35), (0.292, 0.575),
                 (0.292, 0.69), (0.245, 0.875), (0.118, 0.978)]
    head = mirror([(w, chin + z) for (w, z) in head_half], (0.0, crown), (0.0, chin))

    # ПЛЕЧИ У ДВЕНАДЦАТИЛЕТНЕЙ УЖЕ, ЧЕМ У ВЗРОСЛОЙ. Первый заход дал 1.12 головы
    # в размахе плеч — это взрослая фигура, и на её фоне голова читалась мелкой.
    # У подростка плечи около 0.95 головы; голова тогда встаёт на своё место
    # сама, без её увеличения.
    body_half = [
        (0.100, 5.30), (0.110, 5.14),    # шея
        (0.478, 5.02),                   # плечо
        (0.402, 4.62),                   # подмышка
        (0.336, 4.16),                   # талия
        (0.438, 3.74),                   # бедро
        (0.632, 2.90),                   # юбка расходится
        (0.775, 2.22),                   # подол
    ]
    body = mirror(body_half, (0.0, 5.34), (0.0, 2.12))

    def limb(pts, w0, w1):
        """Рука или нога: осевая линия и толщина по ней."""
        n = len(pts)
        left, right = [], []
        for i, (x, z) in enumerate(pts):
            t = i / (n - 1)
            w = w0 + (w1 - w0) * t
            if i < n - 1:
                dx, dz = pts[i + 1][0] - x, pts[i + 1][1] - z
            else:
                dx, dz = x - pts[i - 1][0], z - pts[i - 1][1]
            L = math.hypot(dx, dz) or 1
            nx, nz = -dz / L, dx / L
            left.append((x + nx * w, z + nz * w))
            right.append((x - nx * w, z - nz * w))
        return left + list(reversed(right))

    # РУКИ ВЫНЕСЕНЫ НАРУЖУ силуэта платья: внутри они тонули, и от них оставались
    # только линии поперёк юбки — читалось как швы, а не как руки.
    arm_r = limb([(0.455, 4.96), (0.560, 4.42), (0.615, 3.90), (0.610, 3.40), (0.600, 3.04)], 0.098, 0.066)
    arm_l = [(-x, z) for (x, z) in arm_r]
    leg_r = limb([(0.205, 2.34), (0.200, 1.70), (0.185, 1.00), (0.170, 0.36), (0.180, 0.10)], 0.150, 0.082)
    leg_l = [(-x, z) for (x, z) in leg_r]

    apron = mirror([(0.150, 4.72), (0.175, 4.40), (0.282, 4.16),
                    (0.432, 3.40), (0.545, 2.46)], (0.0, 4.78), (0.0, 2.40))

    hair_half = [(0.318, chin + 0.60), (0.318, chin + 0.70), (0.268, chin + 0.885),
                 (0.130, chin + 0.995)]
    hair = mirror(hair_half, (0.0, crown + 0.030), (0.0, chin + 0.60))
    # ЧЁЛКА рваным краем — пряди делает пила, а не отдельные волосы
    fr = []
    for i in range(33):
        t = i / 32
        x = (-0.312 + 0.624 * t)
        saw = (0.5 + 0.5 * math.cos(2 * math.pi * t * 4.0)) * (0.55 + 0.45 * math.sin(t * 9.7 + 1.1))
        fr.append((x, chin + 0.885 - 0.135 * saw))
    fringe = fr + [(0.312, chin + 1.02), (-0.312, chin + 1.02)]
    # КОСА через левое плечо: одна кривая, три перехвата
    # КОСА ИДЁТ ВДОЛЬ ПЛЕЧА, А НЕ ЧЕРЕЗ ВСЁ ТЕЛО. Первый заход вёл её от виска
    # до бедра, и она читалась лямкой поперёк фигуры — силуэт разваливался.
    braid = smooth([(-0.30, chin + 0.42), (-0.375, chin + 0.10), (-0.405, chin - 0.28),
                    (-0.375, chin - 0.62), (-0.325, chin - 0.82)], 52, closed=False)

    # ---------- ЗАЛИВКИ ----------
    # ПОРЯДОК ЗАЛИВОК И ЛИНИЙ ОДИН И ТОТ ЖЕ. Разошлись — и рука оказывалась под
    # платьем по цвету, но поверх него по линии.
    S.flat("fill", smooth(leg_l), PALETTE["skin"])
    S.flat("fill", smooth(leg_r), PALETTE["skin"])
    S.flat("fill", smooth(body), PALETTE["dress"])
    S.flat("fill", smooth(apron), PALETTE["apron"])
    S.flat("fill", smooth(arm_l), PALETTE["skin"])
    S.flat("fill", smooth(arm_r), PALETTE["skin"])
    S.flat("fill", smooth(head), PALETTE["skin"])
    S.flat("fill", smooth(hair), PALETTE["hair"])
    S.flat("fill", smooth(fringe), PALETTE["hair"])

    # ---------- ТЕНИ (слой MULTIPLY) ----------
    # ТЕНЬ — ФИГУРА, А НЕ РАСЧЁТ. Свет сверху-справа; тень кладётся крупными
    # пятнами по левой стороне и под выступающими частями. Мелких теней нет:
    # в рисунке их не бывает, они превращают фигуру в грязь.
    sh = PALETTE["shade"]
    S.flat("shade", smooth(mirror([(0.09, 5.30), (0.115, 5.14), (0.30, 5.02),
                                   (0.22, 4.86)], (0.0, 5.32), (0.0, 4.88))), sh)   # под подбородком
    S.flat("shade", smooth([(-0.10, 5.02), (-0.478, 5.02), (-0.402, 4.62),
                            (-0.336, 4.16), (-0.438, 3.74), (-0.632, 2.90),
                            (-0.775, 2.22), (-0.37, 2.22), (-0.25, 3.20),
                            (-0.19, 4.20), (-0.15, 5.00)]), sh)                     # левая сторона платья
    S.flat("shade", smooth(arm_l), sh)
    S.flat("shade", smooth(leg_l), sh)
    S.flat("shade", smooth([(-0.545, 2.46), (-0.432, 3.40), (-0.282, 4.16),
                            (-0.175, 4.40), (-0.09, 4.28), (-0.22, 3.50),
                            (-0.34, 2.48)]), sh)                                    # левый край передника
    S.flat("shade", smooth([(-0.318, chin + 0.62), (0.10, chin + 0.62),
                            (0.05, chin + 0.30), (-0.20, chin + 0.20),
                            (-0.30, chin + 0.40)]), sh)                             # тень от чёлки на лбу

    # ---------- ЛИНИЯ ----------
    for shape in (leg_l, leg_r, body, apron, arm_l, arm_r, head):
        S.line(smooth(shape), base=0.0105, cyclic=True)
    S.line(smooth(hair), base=0.0115, cyclic=True)
    S.line(smooth(fringe), base=0.0115, cyclic=True)
    S.line(braid, base=0.0125)
    for t in (0.22, 0.48, 0.74):
        i = int(t * (len(braid) - 1))
        x, z = braid[i]
        S.line(smooth([(x - 0.075, z + 0.02), (x, z - 0.03), (x + 0.075, z + 0.02)], 14, closed=False),
               base=0.007, color=PALETTE["ink2"])
    # складки юбки — три, не десять
    for x0, x1 in ((-0.26, -0.44), (0.04, 0.08), (0.30, 0.52)):
        S.line(smooth([(x0, 3.70), ((x0 + x1) / 2, 2.95), (x1, 2.28)], 26, closed=False),
               base=0.006, color=PALETTE["ink2"])

    # ---------- ЛИЦО ----------
    ey = chin + 0.495
    dx, ew, eh = 0.108, 0.080, 0.062

    def lidc(w, h, n, up):
        K = math.log(0.5) / math.log(0.40 if up else 0.56)
        return [(-w + 2 * w * (i / n),
                 (h if up else -h * 0.44) * (math.sin(math.pi * (i / n) ** K) ** (0.80 if up else 0.95))
                 + 0.10 * h * (i / n)) for i in range(n + 1)]

    for s in (-1, 1):
        up = [(s * (x + dx), ey + y) for (x, y) in lidc(ew, eh, 34, True)]
        if s < 0:
            up.reverse()
        rr = [0.0045 + 0.0125 * (i / len(up)) ** 0.75 for i in range(len(up))]
        if s < 0:
            rr.reverse()
        S.draw("ink", up, rr, S.mat('s_ink', stroke=PALETTE["ink"]))
        dn = [(s * (x + dx), ey + y) for (x, y) in lidc(ew * 0.8, eh, 18, False)]
        S.draw("ink", dn, [0.0032] * len(dn), S.mat('s_ink2', stroke=PALETTE["ink2"]))
        iris = [(s * dx + ew * 0.42 * math.cos(a * math.pi / 10),
                 ey - eh * 0.06 + eh * 0.52 * math.sin(a * math.pi / 10)) for a in range(20)]
        S.flat("fill", iris, PALETTE["iris"])
        S.draw("ink", iris, [0.0030] * 20, S.mat('s_ink', stroke=PALETTE["ink"]), True)
        bw = 0.050
        br = [(s * (0.100 + (-bw + 2 * bw * (i / 16))),
               ey + 0.100 + 0.016 * math.sin(math.pi * i / 16)) for i in range(17)]
        S.draw("ink", br, [0.0085 - 0.0055 * (i / 16) for i in range(17)],
               S.mat('s_ink', stroke=PALETTE["ink"]))
    mw = 0.028
    mo = [(-mw + 2 * mw * (i / 12), ey - 0.140 - mw * 0.40 * (1 - (2 * (i / 12) - 1) ** 2))
          for i in range(13)]
    S.draw("ink", mo, [0.0030 + 0.0025 * math.sin(math.pi * i / 12) for i in range(13)],
           S.mat('s_mouth', stroke=PALETTE["mouth"]))

    return S


def main():
    S = build()
    w = bpy.data.worlds.get('World') or bpy.data.worlds.new('World')
    bpy.context.scene.world = w
    w.use_nodes = True
    w.node_tree.nodes['Background'].inputs[0].default_value = (0.955, 0.950, 0.935, 1)

    cam_d = bpy.data.cameras.new('c')
    cam_d.type = 'ORTHO'
    cam_d.ortho_scale = HEADS + 0.9
    cam = bpy.data.objects.new('c', cam_d)
    bpy.context.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    cam.location = (0, -10, HEADS / 2.0)
    cam.rotation_euler = (math.pi / 2, 0, 0)

    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = 8
    sc.render.resolution_x, sc.render.resolution_y = 560, 1000

    def shot(path, note):
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)
        im = bpy.data.images.load(path)
        px = np.array(im.pixels[:]).reshape(-1, 4)[:, :3]
        print('%-22s мин %.3f макс %.3f средн %.3f' % (note, px.min(), px.max(), px.mean()))
        bpy.data.images.remove(im)

    base = OUT.rsplit('.', 1)[0]
    shot(base + '_clean.png', 'лист как есть')
    nz = S.gp.modifiers.new('Noise', 'GREASE_PENCIL_NOISE')
    nz.factor = 0.020
    nz.factor_thickness = 0.28
    nz.noise_scale = 0.22
    nz.seed = 5
    shot(base + '_wobble.png', '+ дрожание линии')
    n = sum(len(f.drawing.strokes) for L in S.layers.values() for f in L.frames)
    print('ШТРИХОВ', n)


main()
