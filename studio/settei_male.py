# -*- coding: utf-8 -*-
"""ЛИСТ ПЕРСОНАЖА: МУЖЧИНА. ПОСТРОЕНО ПО МЕТОДУ, А НЕ НА ГЛАЗ.

Предыдущий заход был плоской векторной фигурой, собранной по моим догадкам о
пропорциях. Здесь всё построение идёт из правил, которые в манге считаются
азбукой, и каждое из них — проверяемое число, а не вкус.

ГОЛОВА (аниме/манга, фронт):
  череп — КРУГ, челюсть — клин под ним; это основа, «атари»;
  горизонтальная середина ВЫСОТЫ ГОЛОВЫ — уровень, где стоит ВЕРХ глаза
    (не центр глаза: это самая частая ошибка, из-за неё лицо «уезжает»);
  между глазами помещается ровно ещё один глаз;
  низ носа — посередине между ВЕРХОМ ГЛАЗ и подбородком;
  рот — посередине между низом носа и подбородком.

МУЖЧИНА ОТЛИЧАЕТСЯ ОТ ЖЕНЩИНЫ НЕ «БРУТАЛЬНОСТЬЮ», А ЧЕТЫРЬМЯ ВЕЩАМИ:
  глаз ниже и уже (у женщины прорезь высокая, у мужчины вытянутая вбок);
  бровь толще и ЛЕЖИТ БЛИЖЕ к глазу;
  челюсть идёт углом, а не дугой, подбородок крупнее, лицо длиннее;
  рот шире.

ФИГУРА (7.5 головы — молодой взрослый):
  ПАХ РОВНО НА ПОЛОВИНЕ РОСТА;
  КОЛЕНО — на половине высоты паха;
  плечи около 1.5–1.6 головы в размахе;
  ЛОКОТЬ У МУЖЧИНЫ НА УРОВНЕ ПУПКА, запястье — на уровне паха.
Эти четыре засечки держат фигуру. Всё остальное между ними — уже рисунок.

ПЕРСОНАЖ. Гатчина, 1894. Сын садовника Дворцового парка, девятнадцать лет.
Косоворотка (рубаха с косым воротом — застёжка сдвинута влево от середины, и
это главная опознавательная черта силуэта эпохи), узкий пояс, порты, сапоги.
Три больших пятна: тёмные сапоги внизу, светлая рубаха посередине, тёмные
волосы сверху — фигура читается с любого расстояния.
"""
import bpy, math, sys, numpy as np

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "/tmp/male.png"

HEADS = 7.5
LIGHT = +1.0                      # свет сверху-справа

# ЗАСЕЧКИ ФИГУРЫ — из правил, не подобраны
CROWN = HEADS                     # 7.50
CHIN = HEADS - 1.0                # 6.50
EYE_TOP = CHIN + 0.50             # 7.00  середина высоты головы
NOSE = (EYE_TOP + CHIN) / 2       # 6.75
MOUTH = (NOSE + CHIN) / 2         # 6.625
CROTCH = HEADS / 2                # 3.75  ровно половина роста
KNEE = CROTCH / 2                 # 1.875 половина высоты паха
NAVEL = 5.00                      # там же локоть
WRIST = CROTCH                    # запястье на уровне паха

PAL = {
    "ink":    (0.085, 0.062, 0.095),
    "ink2":   (0.30, 0.215, 0.235),
    "skin":   (0.955, 0.800, 0.700),
    "shirt":  (0.880, 0.860, 0.800),
    "belt":   (0.400, 0.245, 0.170),
    "pants":  (0.310, 0.300, 0.330),
    "boot":   (0.185, 0.150, 0.155),
    "hair":   (0.155, 0.115, 0.115),
    "iris":   (0.245, 0.310, 0.330),
    "shade":  (0.740, 0.735, 0.815),
    "mouth":  (0.520, 0.330, 0.310),
}


def smooth(pts, n=None, closed=True):
    m = len(pts)
    n = n or m * 10
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
    return [top] + list(half) + [bot] + [(-x, z) for (x, z) in reversed(half)]


def limb(axis, w0, w1):
    n = len(axis)
    a, b = [], []
    for i, (x, z) in enumerate(axis):
        t = i / (n - 1)
        w = w0 + (w1 - w0) * t
        if i < n - 1:
            dx, dz = axis[i + 1][0] - x, axis[i + 1][1] - z
        else:
            dx, dz = x - axis[i - 1][0], z - axis[i - 1][1]
        L = math.hypot(dx, dz) or 1
        nx, nz = -dz / L, dx / L
        a.append((x + nx * w, z + nz * w))
        b.append((x - nx * w, z - nz * w))
    return a + list(reversed(b))


class Sheet:
    def __init__(self):
        for o in list(bpy.data.objects):
            bpy.data.objects.remove(o, do_unlink=True)
        self.mats = {}
        bpy.ops.object.grease_pencil_add(type='EMPTY')
        self.gp = bpy.context.object
        self.gp.data.materials.clear()
        self.L = {}
        for name, blend in (("fill", 'REGULAR'), ("shade", 'MULTIPLY'), ("ink", 'REGULAR')):
            l = self.gp.data.layers.new(name)
            l.use_lights = False
            l.blend_mode = blend
            l.frames.new(1)
            self.L[name] = l

    def mat(self, stroke=None, fill=None):
        key = (stroke, fill)
        if key in self.mats:
            return self.mats[key]
        m = bpy.data.materials.new('m%d' % len(self.mats))
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

    def raw(self, layer, pts, radii, mi, cyclic=False):
        dr = self.L[layer].frames[0].drawing
        dr.add_strokes([len(pts)])
        st = dr.strokes[-1]
        st.material_index = mi
        st.cyclic = cyclic
        for i, (x, z) in enumerate(pts):
            st.points[i].position = (x, 0.0, z)
            st.points[i].radius = radii[i]
            st.points[i].opacity = 1.0

    def fill(self, pts, color, layer="fill"):
        self.raw(layer, pts, [0.0006] * len(pts), self.mat(fill=color), True)

    def ink(self, pts, w=0.010, color=None, taper=True):
        """ЛИНИЯ С НАЖИМОМ И СБЕГОМ НА КОНЦАХ.

        Проведённая линия начинается и кончается в ноль — перо касается бумаги и
        отрывается. Линия постоянной толщины с прямыми торцами выдаёт машину
        мгновенно; это было главным, что делало прошлый лист «обычным рисунком».
        Вес растёт слева и снизу: там форма уходит от света.
        """
        col = color or PAL["ink"]
        mx = max(abs(p[0]) for p in pts) or 1.0
        n = len(pts)
        r = []
        for i, (x, z) in enumerate(pts):
            away = 0.5 - 0.5 * (x * LIGHT) / mx
            k = 0.50 + 1.00 * away
            if taper:
                t = i / (n - 1)
                k *= min(1.0, (min(t, 1 - t) / 0.16) ** 0.55)
            r.append(max(0.0002, w * k))
        self.raw("ink", pts, r, self.mat(stroke=col))

    def outline(self, closed_pts, w=0.011, gaps=((0.10, 0.16), (0.60, 0.66))):
        """СИЛУЭТ РИСУЕТСЯ ДУГАМИ С РАЗРЫВАМИ, А НЕ ОДНОЙ ЗАМКНУТОЙ ЛИНИЕЙ.

        Сплошной замкнутый контур читается наклейкой. В рисованной анимации линия
        рвётся там, где форма выходит на свет, — и именно эти разрывы дают
        ощущение объёма, потому что глаз достраивает их сам.
        """
        n = len(closed_pts)
        cuts = []
        for (a, b) in gaps:
            cuts.append((int(a * n) % n, int(b * n) % n))
        keep = [True] * n
        for (a, b) in cuts:
            i = a
            while i != b:
                keep[i] = False
                i = (i + 1) % n
        run, runs = [], []
        for i in range(n + 1):
            j = i % n
            if keep[j] and (i < n):
                run.append(closed_pts[j])
            else:
                if len(run) > 6:
                    runs.append(run)
                run = []
        if len(run) > 6:
            runs.append(run)
        for r in runs:
            self.ink(r, w)


def build():
    S = Sheet()

    # ---------- ГОЛОВА: КРУГ ЧЕРЕПА + КЛИН ЧЕЛЮСТИ ----------
    R = 0.355                                   # радиус черепа
    CZ = CROWN - R                              # центр круга
    # ширина черепа на уровне глаз — из круга, а не назначена
    w_eye = math.sqrt(max(R * R - (CZ - EYE_TOP) ** 2, 1e-6))
    head_half = []
    for i in range(13):                          # верхняя дуга круга
        a = math.pi * 0.5 * i / 12
        head_half.append((R * math.cos(a) * 0.0 + R * math.sin(a), CZ + R * math.cos(a)))
    head_half += [
        (w_eye, EYE_TOP),
        (0.315, EYE_TOP - 0.16),                 # скула
        (0.268, CHIN + 0.22),                    # УГОЛ ЧЕЛЮСТИ — у мужчины он есть
        (0.150, CHIN + 0.055),
        (0.052, CHIN + 0.002),
    ]
    head = mirror(head_half, (0.0, CROWN), (0.0, CHIN))

    # ---------- ТЕЛО ----------
    SHO = 6.12
    body_half = [
        (0.145, CHIN - 0.02), (0.150, SHO + 0.20),   # шея (у мужчины толстая)
        (0.815, SHO),                                 # плечо: размах 1.63 головы
        (0.640, 5.72),                                # подмышка
        (0.505, NAVEL),                               # талия
        (0.560, 4.45),                                # бедро
        (0.545, CROTCH + 0.10),
    ]
    torso = mirror(body_half, (0.0, CHIN - 0.05), (0.0, CROTCH - 0.02))

    # рубаха: ниже пояса, чуть шире тела
    shirt_half = [
        (0.165, CHIN - 0.02), (0.185, SHO + 0.22),
        (0.845, SHO - 0.02),
        (0.665, 5.70),
        (0.520, NAVEL),
        (0.590, 4.72),
        (0.560, 4.46),
    ]
    shirt = mirror(shirt_half, (0.0, CHIN - 0.05), (0.0, 4.40))

    arm_r = limb([(0.752, 6.02), (0.800, NAVEL + 0.55), (0.845, NAVEL),
                  (0.860, 4.35), (0.855, WRIST), (0.840, WRIST - 0.33)], 0.150, 0.095)
    arm_l = [(-x, z) for (x, z) in arm_r]
    # рукав кончается манжетой у запястья
    sleeve_r = limb([(0.752, 6.02), (0.805, NAVEL + 0.55), (0.852, NAVEL),
                     (0.868, 4.35), (0.862, WRIST + 0.06)], 0.178, 0.118)
    sleeve_l = [(-x, z) for (x, z) in sleeve_r]
    hand_r = limb([(0.856, WRIST - 0.03), (0.852, WRIST - 0.20), (0.836, WRIST - 0.34)],
                  0.098, 0.052)
    hand_l = [(-x, z) for (x, z) in hand_r]

    # ТАЗ ОТДЕЛЬНОЙ ФОРМОЙ. Ноги начинались от паха, а рубаха кончалась выше —
    # между ними оставалась голая полоса. Ног от паха не бывает: между поясом и
    # разделением ног есть таз, и он одет.
    pelvis = mirror([(0.565, 4.62), (0.552, 4.14), (0.520, 3.72)], (0.0, 4.64), (0.0, 3.64))
    leg_r = limb([(0.245, CROTCH + 0.05), (0.250, 2.80), (0.235, KNEE),
                  (0.245, 1.10), (0.230, 0.36)], 0.255, 0.135)
    leg_l = [(-x, z) for (x, z) in leg_r]
    # САПОГ СТРОИТСЯ ВОКРУГ ОСИ НОГИ, а не зеркалится относительно нуля: в первом
    # заходе оба сапога оказались по центру фигуры и наложились друг на друга.
    boot_r = limb([(0.238, 1.63), (0.242, 1.05), (0.233, 0.42), (0.228, 0.04)], 0.208, 0.192)
    boot_l = [(-x, z) for (x, z) in boot_r]
    belt = mirror([(0.520, NAVEL + 0.10), (0.528, NAVEL - 0.06)],
                  (0.0, NAVEL + 0.12), (0.0, NAVEL - 0.08))

    # ---------- ВОЛОСЫ: МАССА ПО ЧЕРЕПУ + КОРОТКИЕ ПРЯДИ ОТ ЛИНИИ РОСТА ----------
    # Первый заход пускал пряди ЛУЧАМИ ОТ МАКУШКИ через всё лицо, и голову
    # затянуло сетью. В манге устройство другое и оно жёсткое:
    #   одна МАССА лежит по черепу, чуть выступая за силуэт (0.04-0.06 головы),
    #     и её нижний край РВАНЫЙ — именно край читается как пряди;
    #   от линии роста вниз идут КОРОТКИЕ клинья, каждый сходится в остриё;
    #   пряди НЕ пересекают лицо: они кончаются у брови и выше.
    HAIRLINE = EYE_TOP + 0.29                  # 7.29 — линия роста волос
    K = 0.052                                  # насколько масса выступает за череп
    # ОБХОД ЧЕРЕПА ОДНОЙ ДУГОЙ. Первый заход шёл двумя циклами с ветвлением, и
    # на стыке рождалась точка с x=0 посреди головы — от неё через темя тянулась
    # диагональ.
    mass = []
    A = math.pi / 2 + 0.62                    # докуда масса опускается по бокам
    for i in range(41):
        a = -A + 2 * A * i / 40
        mass.append((math.sin(a) * (R + K), CZ + math.cos(a) * (R + K)))
    # НИЖНИЙ КРАЙ МАССЫ — ПРОСТАЯ ДУГА, БЕЗ ЗУБЦОВ. Рваный силуэт дают ПРЯДИ,
    # и если зубцы есть ещё и у массы, полоса чёлки обводится дважды и слипается
    # в клубок — ровно это и было на кадре.
    edge = []
    for i in range(21):
        t = i / 20
        x = -0.375 + 0.750 * t
        edge.append((x, HAIRLINE - 0.02 - 0.045 * math.sin(math.pi * t)))
    hair_mass = mass + list(reversed(edge))

    # ПРЯДИ ЧЁЛКИ — короткие клинья от линии роста вниз, с пробором слева.
    # Каждая сходится в остриё; кончики на уровне брови и выше, лицо открыто.
    PART = -0.14                               # пробор смещён влево от середины
    clumps = []
    for (x0, x1, wd, top) in (
        (-0.325, -0.395, 0.062, 0.01), (-0.212, -0.292, 0.070, 0.04),
        (-0.098, -0.162, 0.066, 0.05), (0.022, 0.014, 0.058, 0.05),
        (0.142, 0.196, 0.068, 0.04), (0.258, 0.332, 0.064, 0.02),
    ):
        tip_z = EYE_TOP + 0.055 + 0.075 * abs(x0 - PART)
        axis = [(x0, HAIRLINE + top), ((x0 + x1) / 2, (HAIRLINE + tip_z) / 2), (x1, tip_z)]
        clumps.append(limb(smooth(axis, 12, closed=False), wd, 0.003))
    # висок: короткая прядь перед ухом
    for s_ in (-1, 1):
        axis = [(s_ * 0.345, EYE_TOP + 0.22), (s_ * 0.372, EYE_TOP - 0.02), (s_ * 0.355, EYE_TOP - 0.19)]
        clumps.append(limb(smooth(axis, 12, closed=False), 0.060, 0.004))
    cap = hair_mass

    # ---------- ЗАЛИВКИ ----------
    for p in (leg_l, leg_r):
        S.fill(smooth(p), PAL["skin"])
    S.fill(smooth(leg_l), PAL["pants"]); S.fill(smooth(leg_r), PAL["pants"])
    S.fill(smooth(boot_l), PAL["boot"]); S.fill(smooth(boot_r), PAL["boot"])
    S.fill(smooth(torso), PAL["skin"])
    S.fill(smooth(pelvis), PAL["pants"])
    S.fill(smooth(shirt), PAL["shirt"])
    S.fill(smooth(belt), PAL["belt"])
    S.fill(smooth(arm_l), PAL["skin"]); S.fill(smooth(arm_r), PAL["skin"])
    S.fill(smooth(hand_l), PAL["skin"]); S.fill(smooth(hand_r), PAL["skin"])
    S.fill(smooth(sleeve_l), PAL["shirt"]); S.fill(smooth(sleeve_r), PAL["shirt"])
    S.fill(smooth(head), PAL["skin"])
    S.fill(smooth(cap), PAL["hair"])
    for c in clumps:
        S.fill(smooth(c), PAL["hair"])

    # ---------- ТЕНИ ----------
    sh = PAL["shade"]
    S.fill(smooth([(-0.16, CHIN + 0.02), (0.16, CHIN + 0.02), (0.14, CHIN - 0.30),
                   (-0.15, CHIN - 0.32)]), sh, "shade")                    # шея под подбородком
    S.fill(smooth([(-0.355, EYE_TOP + 0.30), (0.355, EYE_TOP + 0.30),
                   (0.330, EYE_TOP + 0.02), (0.10, EYE_TOP + 0.10),
                   (-0.12, EYE_TOP + 0.02), (-0.330, EYE_TOP + 0.10)]), sh, "shade")
    # тень от чёлки на лбу: без неё волосы висят отдельно от головы
    S.fill(smooth([(-0.185, SHO + 0.20), (-0.845, SHO - 0.02), (-0.665, 5.70),
                   (-0.520, NAVEL), (-0.590, 4.72), (-0.560, 4.46), (-0.30, 4.46),
                   (-0.26, 5.00), (-0.30, 5.70), (-0.22, SHO)]), sh, "shade")
    S.fill(smooth(sleeve_l), sh, "shade")
    S.fill(smooth(arm_l), sh, "shade")
    S.fill(smooth(hand_l), sh, "shade")
    S.fill(smooth(leg_l), sh, "shade")
    S.fill(smooth(boot_l), sh, "shade")

    # ---------- ЛИНИЯ ----------
    for p in (boot_l, boot_r, leg_l, leg_r):
        S.outline(smooth(p), 0.0115)
    S.outline(smooth(pelvis), 0.0105, gaps=((0.20, 0.26), (0.70, 0.76)))
    S.outline(smooth(shirt), 0.0125, gaps=((0.06, 0.11), (0.55, 0.60)))
    S.outline(smooth(belt), 0.0090, gaps=((0.20, 0.24),))
    for p in (sleeve_l, sleeve_r):
        S.outline(smooth(p), 0.0110)
    S.outline(smooth(arm_l), 0.0100, gaps=((0.30, 0.36),))
    S.outline(smooth(arm_r), 0.0100, gaps=((0.30, 0.36),))
    S.outline(smooth(hand_l), 0.0095, gaps=((0.46, 0.50),))
    S.outline(smooth(hand_r), 0.0095, gaps=((0.46, 0.50),))
    S.outline(smooth(head), 0.0120, gaps=((0.05, 0.09),))
    # нижний край массы не обводится: его силуэт дают пряди
    S.outline(smooth(cap), 0.0130, gaps=((0.52, 0.99),))
    # У ПРЯДИ РИСУЮТ ОДНУ ЛИНИЮ ПО КРАЮ, А НЕ КОНТУР ВОКРУГ. Обведённая по
    # кругу прядь слипается с соседними в клубок — это и было на кадре. Инкер
    # ведёт по пряди один штрих, сбегающий в остриё; вторую сторону держит
    # соседняя прядь или силуэт массы.
    for c in clumps:
        half = smooth(c)[:len(smooth(c)) // 2]
        S.ink(half, 0.0100)

    # КОСОЙ ВОРОТ — опознавательная черта эпохи: планка сдвинута ВЛЕВО от середины
    S.ink(smooth([(0.055, CHIN - 0.06), (0.050, SHO + 0.06), (-0.135, 5.86),
                  (-0.150, 5.50)], 40, closed=False), 0.0085, PAL["ink"])
    S.ink(smooth([(-0.150, SHO + 0.10), (0.055, CHIN - 0.06)], 18, closed=False),
          0.0085, PAL["ink"])
    # СКЛАДКИ ТАМ, ГДЕ ТКАНЬ РАБОТАЕТ: у пояса, в локтевом сгибе, над сапогом
    for a, b, c in ((-0.34, -0.42, -0.30), (0.10, 0.16, 0.08), (0.36, 0.44, 0.30)):
        S.ink(smooth([(a, NAVEL - 0.10), (b, 4.72), (c, 4.36)], 22, closed=False),
              0.0058, PAL["ink2"])
    for s in (-1, 1):
        S.ink(smooth([(s * 0.80, NAVEL + 0.14), (s * 0.905, NAVEL), (s * 0.80, NAVEL - 0.14)],
                     16, closed=False), 0.0055, PAL["ink2"])
        S.ink(smooth([(s * 0.20, 1.90), (s * 0.28, 1.74), (s * 0.20, 1.62)], 14, closed=False),
              0.0055, PAL["ink2"])

    # ---------- ЛИЦО ПО ПРАВИЛАМ ----------
    EW, EH = 0.150, 0.098                    # мужской глаз: шире, чем высок
    dx = EW                                  # между глазами ровно один глаз
    for s in (-1, 1):
        cx = s * dx
        # верхнее веко: вершина смещена к внутреннему углу, гладкой дугой
        K = math.log(0.5) / math.log(0.42)
        up = []
        for i in range(31):
            t = i / 30
            x = -EW / 2 + EW * t
            up.append((cx + s * x, EYE_TOP - EH * (1 - math.sin(math.pi * (t ** K)) ** 0.85)
                       - 0.02 * t * s * s))
        if s < 0:
            up.reverse()
        # У МУЖЧИНЫ РЕСНИЧНАЯ ЛИНИЯ ТОНЬШЕ И ПРЯМЕЕ, чем у женщины
        rr = [0.0060 + 0.0090 * (i / 30) ** 0.7 for i in range(31)]
        if s < 0:
            rr.reverse()
        S.raw("ink", up, rr, S.mat(stroke=PAL["ink"]))
        low = [(cx + s * (-EW / 2 + EW * (i / 16)),
                EYE_TOP - EH - 0.012 * math.sin(math.pi * i / 16)) for i in range(17)]
        S.raw("ink", low, [0.0030] * 17, S.mat(stroke=PAL["ink2"]))
        iris = [(cx + EW * 0.235 * math.cos(a * math.pi / 9),
                 EYE_TOP - EH * 0.44 + EH * 0.46 * math.sin(a * math.pi / 9)) for a in range(18)]
        S.fill(iris, PAL["iris"])
        S.raw("ink", iris, [0.0034] * 18, S.mat(stroke=PAL["ink"]), True)
        # БРОВЬ ТОЛСТАЯ И БЛИЗКО К ГЛАЗУ — главный мужской признак лица
        bz = EYE_TOP + 0.075
        bw = EW * 0.62
        br = []
        for i in range(15):
            t = i / 14
            br.append((cx + s * (-bw + 2 * bw * t), bz + 0.030 * t - 0.014 * math.sin(math.pi * t)))
        S.raw("ink", br, [0.0125 - 0.0075 * (i / 14) for i in range(15)],
              S.mat(stroke=PAL["ink"]))
    # нос — короткий клин у линии носа, смещён от середины
    S.ink(smooth([(0.030, NOSE + 0.075), (0.058, NOSE), (0.012, NOSE - 0.012)],
                 14, closed=False), 0.0050, PAL["ink2"])
    # рот шире женского и почти прямой
    mw = 0.075
    mo = [(-mw + 2 * mw * (i / 12), MOUTH - 0.012 * math.sin(math.pi * i / 12)) for i in range(13)]
    S.raw("ink", mo, [0.0028 + 0.0026 * math.sin(math.pi * i / 12) for i in range(13)],
          S.mat(stroke=PAL["mouth"]))
    return S


def main():
    S = build()
    w = bpy.data.worlds.get('World') or bpy.data.worlds.new('World')
    bpy.context.scene.world = w
    w.use_nodes = True
    w.node_tree.nodes['Background'].inputs[0].default_value = (0.965, 0.960, 0.948, 1)
    cam_d = bpy.data.cameras.new('c')
    cam_d.type = 'ORTHO'
    cam_d.ortho_scale = HEADS + 0.7
    cam = bpy.data.objects.new('c', cam_d)
    bpy.context.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    cam.location = (0, -10, HEADS / 2.0)
    cam.rotation_euler = (math.pi / 2, 0, 0)
    sc = bpy.context.scene
    # ВИД STANDARD, А НЕ AgX. По умолчанию Blender 4.5 показывает кадр через AgX —
    # фотографическую кривую для широкого динамического диапазона. Она сильно
    # гасит насыщенность, и назначенные цвета приходят на экран другими: кожа
    # (0.955, 0.800, 0.700) выходила серо-лиловой. Для плоского рисунка, где цвет
    # НАЗНАЧЕН, любое преобразование вида — искажение замысла.
    sc.view_settings.view_transform = 'Standard'
    sc.view_settings.look = 'None'
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = 8
    sc.render.resolution_x, sc.render.resolution_y = 620, 1080

    base = OUT.rsplit('.', 1)[0]

    def shot(path, note):
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)
        im = bpy.data.images.load(path)
        px = np.array(im.pixels[:]).reshape(-1, 4)[:, :3]
        print('%-20s мин %.3f макс %.3f средн %.3f' % (note, px.min(), px.max(), px.mean()))
        bpy.data.images.remove(im)

    shot(base + '_full.png', 'фигура')
    # крупно голова: лицо надо смотреть отдельно, на фигуре оно 90 пикселей
    cam_d.ortho_scale = 1.52
    cam.location = (0, -10, CHIN + 0.56)
    sc.render.resolution_x, sc.render.resolution_y = 700, 760
    shot(base + '_head.png', 'голова крупно')
    print('ШТРИХОВ', sum(len(f.drawing.strokes) for L in S.L.values() for f in L.frames))


main()
