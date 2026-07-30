#!/usr/bin/env python3
"""РАСТЕНИЯ В ГЕОМЕТРИЮ — печётся здесь, без Blender.

ПОЧЕМУ БЕЗ BLENDER. tools/build_plants.py написан на bpy и поэтому не
запускается там, где идёт работа: Blender в окружении нет. Из-за одной этой
причины трава стояла месяц. Здесь то же самое делается numpy и пишется в наш
бинарь — тем же способом, каким уже испечены город (gatchina_city.bin),
дворец и поверхность воды (water_surface.bin). Загрузчик в игре тонкий.

ЧТО ПЕЧЁТСЯ. Не «трава вообще», а ДЕРНИНА каждого вида по его собственным
числам из ботаники (tools/vegetation.py → data/real/vegetation.json): высота
побега в июне, ширина листа, сколько побегов в дернине, тип роста.
  ЗЛАК — узкие изогнутые листья от корня веером плюс соцветие сверху;
  РАЗНОТРАВЬЕ — стебель, широкие листья попарно, цветок;
  КУСТАРНИЧЕК — одревесневшая веточка с мелкими листьями;
  ПАПОРОТНИК — вайя с перьями по обе стороны;
  ОСОКА — как злак, но лист жёсткий и стоит прямее: у осок трёхгранный стебель
    и килеватый лист, поэтому дернина читается пучком прямых лезвий.
Лист — не плоский треугольник, а изогнутая сужающаяся лента из сегментов: у
настоящего листа есть перегиб, и вблизи читается именно он.

ЧЕСТНО ПРО ПЛОТНОСТЬ. Луг держит 11 000 побегов/м² (проверено в vegetation.py).
Круг радиусом 8 м — это 2.2 млн побегов и около 6.6 млн треугольников только у
ног. Столько не тянет ни один телефон, и никто так не делает: вблизи стоит
геометрия, дальше карточки, ещё дальше покров уходит в материал земли. Поэтому
здесь печётся ДЕРНИНА как единица посева, а сколько дернин станет геометрией —
решает бюджет кадра, и это число надо замерить на устройстве.

ФОРМАТ (game2/assets/plants/plants.bin), всё little-endian:
  uint32 версия = 1
  uint32 число видов
  на вид:
    uint8  длина имени, затем имя (utf-8, латинское)
    uint8  тип роста: 0 злак, 1 разнотравье, 2 кустарничек, 3 папоротник, 4 осока
    float  высота дернины, м (для отбора по расстоянию)
    float  проективное покрытие дернины, м² (сколько земли закрывает сверху)
    uint32 вершин, uint32 индексов
    вершины: float x,y,z, float nx,ny,nz, uint8 r,g,b,a   (28 байт)
    индексы: uint32
Цвет лежит в вершине: у травы цвет — свойство вида и части растения (лист или
соцветие), и отдельной текстуры для этого не нужно.

Запуск: python3 tools/bake_plants.py
"""
import json
import math
import os
import struct

import numpy as np

ROOT = os.path.join(os.path.dirname(__file__), "..")
G2 = os.path.join(ROOT, "game2")
OUT_DIR = os.path.join(G2, "assets", "plants")
OUT = os.path.join(OUT_DIR, "plants.bin")

HABIT_CODE = {"злак": 0, "разнотравье": 1, "кустарничек": 2, "папоротник": 3,
              "осока": 4}
# Сегментов на лист. Пять — из наблюдения: меньше, и перегиб листа исчезает,
# больше, и растёт цена, а на кадре ничего не добавляется.
LEAF_SEGS = 5


class Mesh:
    def __init__(self):
        self.v = []      # x,y,z
        self.n = []      # nx,ny,nz
        self.c = []      # r,g,b
        self.i = []      # индексы

    def add_ribbon(self, pts, widths, color, normal_hint):
        """Лента по осевой линии: pts — точки оси, widths — полуширина в них."""
        base = len(self.v)
        for k, (p, w) in enumerate(zip(pts, widths)):
            # направление оси в этой точке
            if k == 0:
                d = pts[1] - pts[0]
            elif k == len(pts) - 1:
                d = pts[-1] - pts[-2]
            else:
                d = pts[k + 1] - pts[k - 1]
            d = d / (np.linalg.norm(d) + 1e-9)
            side = np.cross(d, normal_hint)
            ln = np.linalg.norm(side)
            if ln < 1e-6:
                side = np.array([1.0, 0.0, 0.0])
            else:
                side = side / ln
            nrm = np.cross(side, d)
            nrm = nrm / (np.linalg.norm(nrm) + 1e-9)
            for s in (-1.0, 1.0):
                self.v.append(p + side * (w * s))
                self.n.append(nrm)
                self.c.append(color)
        for k in range(len(pts) - 1):
            a = base + k * 2
            self.i += [a, a + 1, a + 2, a + 1, a + 3, a + 2]

    def tri_count(self):
        return len(self.i) // 3

    def ground_cover(self, cell=0.01):
        """ПРОЕКТИВНОЕ ПОКРЫТИЕ дернины, м² — сколько земли она закрывает,
        если смотреть сверху. Это и есть та величина, которую в играх совмещают
        с ботаникой, а НЕ число побегов: глазу важно, видно ли землю, а не
        сколько в квадратном метре стеблей. Считается растеризацией
        треугольников на сетку 1 см в плане — без домыслов о форме."""
        if not self.i:
            return 0.0
        v = np.array(self.v, dtype=float)
        tri = np.array(self.i, dtype=int).reshape(-1, 3)
        p = v[:, [0, 2]]                      # вид сверху
        filled = set()
        for a, b, c in tri:
            pa, pb, pc = p[a], p[b], p[c]
            lo = np.floor(np.minimum(np.minimum(pa, pb), pc) / cell).astype(int)
            hi = np.ceil(np.maximum(np.maximum(pa, pb), pc) / cell).astype(int)
            if (hi - lo).max() > 400:
                continue
            d = (pb[1] - pc[1]) * (pa[0] - pc[0]) + (pc[0] - pb[0]) * (pa[1] - pc[1])
            if abs(d) < 1e-12:
                continue
            for gi in range(lo[0], hi[0] + 1):
                for gj in range(lo[1], hi[1] + 1):
                    q = np.array([(gi + 0.5) * cell, (gj + 0.5) * cell])
                    l1 = ((pb[1] - pc[1]) * (q[0] - pc[0]) + (pc[0] - pb[0]) * (q[1] - pc[1])) / d
                    l2 = ((pc[1] - pa[1]) * (q[0] - pc[0]) + (pa[0] - pc[0]) * (q[1] - pc[1])) / d
                    l3 = 1.0 - l1 - l2
                    if l1 >= -1e-6 and l2 >= -1e-6 and l3 >= -1e-6:
                        filled.add((gi, gj))
        return len(filled) * cell * cell

    def pack(self):
        v = np.array(self.v, dtype="<f4")
        n = np.array(self.n, dtype="<f4")
        c = np.clip(np.array(self.c, dtype=float) * 255.0, 0, 255).astype(np.uint8)
        out = bytearray()
        for k in range(len(v)):
            out += struct.pack("<6f4B", v[k][0], v[k][1], v[k][2],
                               n[k][0], n[k][1], n[k][2],
                               c[k][0], c[k][1], c[k][2], 255)
        idx = np.array(self.i, dtype="<u4").tobytes()
        return bytes(out), idx, len(v), len(self.i)


def arc(h, lean, bend, segs=LEAF_SEGS, az=0.0):
    """Дуга листа: от корня вверх с наклоном lean и перегибом bend."""
    pts = []
    for k in range(segs + 1):
        t = k / segs
        # высота растёт с замедлением, отклонение — по кубике: перегиб к концу
        y = h * math.sin(t * math.pi * 0.5)
        r = h * (lean * t + bend * t ** 3)
        pts.append(np.array([r * math.cos(az), y, r * math.sin(az)]))
    return pts


def grass_tuft(sp, rng):
    """ЗЛАК: веер изогнутых листьев от корня + соцветие."""
    m = Mesh()
    h_lo, h_hi = sp["h_cm"]
    shoots = int(sp["shoots"])
    lw = sp["leaf_mm"] / 1000.0 * 0.5      # полуширина листа, м
    col = sp["color"]
    fcol = sp["flower"]
    for s in range(shoots):
        h = rng.uniform(h_lo, h_hi) / 100.0
        az = rng.uniform(0.0, math.tau)
        lean = rng.uniform(0.05, 0.18)
        bend = rng.uniform(0.10, 0.35)
        pts = arc(h, lean, bend, az=az)
        # лента сужается к кончику
        widths = [lw * (1.0 - 0.85 * (k / LEAF_SEGS) ** 1.5) for k in range(LEAF_SEGS + 1)]
        shade = rng.uniform(0.85, 1.15)
        m.add_ribbon(pts, widths, [min(1.0, c * shade) for c in col],
                     np.array([0.0, 1.0, 0.0]))
        # СОЦВЕТИЕ у части побегов: в июне колосится не каждый
        if s % 3 == 0:
            top = pts[-1]
            d = top - pts[-2]
            d = d / (np.linalg.norm(d) + 1e-9)
            sp_pts = [top + d * (h * 0.02 * k) for k in range(4)]
            sp_w = [lw * 1.8, lw * 2.2, lw * 1.6, lw * 0.4]
            m.add_ribbon(sp_pts, sp_w, fcol, np.array([1.0, 0.0, 0.0]))
    return m


def herb_plant(sp, rng):
    """РАЗНОТРАВЬЕ: стебель, широкие листья попарно, цветок."""
    m = Mesh()
    h_lo, h_hi = sp["h_cm"]
    h = rng.uniform(h_lo, h_hi) / 100.0
    lw = sp["leaf_mm"] / 1000.0 * 0.5
    col = sp["color"]
    fcol = sp["flower"]
    # стебель — узкая почти прямая лента
    st = arc(h, 0.03, 0.05, az=rng.uniform(0, math.tau))
    m.add_ribbon(st, [lw * 0.35] * (LEAF_SEGS + 1), col, np.array([0.0, 1.0, 0.0]))
    pairs = max(2, int(sp["shoots"]) // 3)
    for p in range(pairs):
        t = 0.25 + 0.6 * p / max(1, pairs - 1)
        base_y = h * math.sin(t * math.pi * 0.5)
        az = rng.uniform(0, math.tau)
        for s in (0.0, math.pi):
            a = az + s
            leaf_len = h * rng.uniform(0.18, 0.32)
            pts = [np.array([0.0, base_y, 0.0])]
            for k in range(1, LEAF_SEGS + 1):
                q = k / LEAF_SEGS
                pts.append(np.array([
                    leaf_len * q * math.cos(a),
                    base_y + leaf_len * 0.35 * math.sin(q * math.pi),
                    leaf_len * q * math.sin(a)]))
            widths = [lw * (0.5 + 1.5 * math.sin(k / LEAF_SEGS * math.pi))
                      for k in range(LEAF_SEGS + 1)]
            shade = rng.uniform(0.9, 1.1)
            m.add_ribbon(pts, widths, [min(1.0, c * shade) for c in col],
                         np.array([0.0, 1.0, 0.0]))
    # цветок — короткая широкая лента крест-накрест
    top = st[-1]
    for a in (0.0, math.pi * 0.5):
        pts = [top + np.array([-0.012 * math.cos(a), 0.0, -0.012 * math.sin(a)]),
               top,
               top + np.array([0.012 * math.cos(a), 0.004, 0.012 * math.sin(a)])]
        m.add_ribbon(pts, [0.004, 0.010, 0.004], fcol, np.array([0.0, 1.0, 0.0]))
    return m


def shrub_plant(sp, rng):
    """КУСТАРНИЧЕК: одревесневшая веточка с мелкими листьями."""
    m = Mesh()
    h_lo, h_hi = sp["h_cm"]
    h = rng.uniform(h_lo, h_hi) / 100.0
    lw = sp["leaf_mm"] / 1000.0 * 0.5
    col = sp["color"]
    wood = [c * 0.55 + 0.10 for c in col]
    branches = max(2, int(sp["shoots"]) // 2)
    for b in range(branches):
        az = rng.uniform(0, math.tau)
        bh = h * rng.uniform(0.6, 1.0)
        st = arc(bh, rng.uniform(0.15, 0.4), rng.uniform(0.1, 0.3), az=az)
        m.add_ribbon(st, [lw * 0.5] * (LEAF_SEGS + 1), wood, np.array([0.0, 1.0, 0.0]))
        for k in range(2, LEAF_SEGS + 1):
            p = st[k]
            a = az + rng.uniform(-1.2, 1.2)
            ln = bh * 0.12
            pts = [p, p + np.array([ln * math.cos(a), ln * 0.4, ln * math.sin(a)])]
            m.add_ribbon(pts, [lw * 1.6, lw * 0.3], col, np.array([0.0, 1.0, 0.0]))
    return m


def fern_plant(sp, rng):
    """ПАПОРОТНИК: вайя с перьями по обе стороны рахиса."""
    m = Mesh()
    h_lo, h_hi = sp["h_cm"]
    lw = sp["leaf_mm"] / 1000.0 * 0.5
    col = sp["color"]
    fronds = max(3, int(sp["shoots"]) // 2)
    for f in range(fronds):
        h = rng.uniform(h_lo, h_hi) / 100.0
        az = rng.uniform(0, math.tau)
        rachis = arc(h, 0.12, 0.45, segs=7, az=az)
        m.add_ribbon(rachis, [lw * 0.6] * 8, [c * 0.8 for c in col],
                     np.array([0.0, 1.0, 0.0]))
        for k in range(1, 8):
            p = rachis[k]
            t = k / 7.0
            pl = h * 0.16 * (1.0 - 0.6 * t)
            for s in (-1.0, 1.0):
                a = az + s * math.pi * 0.5
                pts = [p, p + np.array([pl * math.cos(a), -pl * 0.15, pl * math.sin(a)])]
                m.add_ribbon(pts, [lw * 1.4, lw * 0.2], col, np.array([0.0, 1.0, 0.0]))
    return m


def sedge_tuft(sp, rng):
    """ОСОКА: похожа на злак, но лист жёсткий, килеватый и стоит прямее.
    Это не придирка к названию: у осок трёхгранный стебель и лист с килем,
    поэтому дернина осоки на кадре читается как пучок прямых лезвий, а злак —
    как поникший веер. Разница видна, значит должна быть в геометрии."""
    m = Mesh()
    h_lo, h_hi = sp["h_cm"]
    shoots = int(sp["shoots"])
    lw = sp["leaf_mm"] / 1000.0 * 0.5
    col = sp["color"]
    fcol = sp["flower"]
    for s in range(shoots):
        h = rng.uniform(h_lo, h_hi) / 100.0
        az = rng.uniform(0.0, math.tau)
        # наклон и перегиб ВДВОЕ меньше, чем у злака: лист жёсткий
        pts = arc(h, rng.uniform(0.02, 0.08), rng.uniform(0.04, 0.14), az=az)
        widths = [lw * (1.0 - 0.7 * (k / LEAF_SEGS) ** 2) for k in range(LEAF_SEGS + 1)]
        shade = rng.uniform(0.88, 1.12)
        m.add_ribbon(pts, widths, [min(1.0, c * shade) for c in col],
                     np.array([0.0, 1.0, 0.0]))
        if s % 4 == 0:
            top = pts[-1]
            d = top - pts[-2]
            d = d / (np.linalg.norm(d) + 1e-9)
            # колосок осоки — плотный, короткий, тёмный
            sp_pts = [top + d * (h * 0.015 * k) for k in range(3)]
            m.add_ribbon(sp_pts, [lw * 2.4, lw * 2.0, lw * 0.5], fcol,
                         np.array([1.0, 0.0, 0.0]))
    return m


BUILDERS = {"злак": grass_tuft, "разнотравье": herb_plant,
            "кустарничек": shrub_plant, "папоротник": fern_plant,
            "осока": sedge_tuft}


def community_patch(veg, species, cname, com, rng, side_m=0.5, widen=3.0):
    """КУРТИНА сообщества — крупная единица для средней дали.

    ЗАЧЕМ ОНА ВООБЩЕ. Дернина закрывает 0.0018 м², и на луг с покрытием 97%
    их нужно 539 на квадратный метр — 59 536 △/м², то есть геометрия кончается
    на 2.1 м от ног. Кадра из этого не выйдет. Куртина закрывает ту же землю
    много меньшим числом треугольников, потому что её листья ШИРЕ.

    ПОЧЕМУ РАСШИРЯТЬ ЛИСТ — НЕ ОБМАН. ИЗМЕРЕНО: на телефоне (1290 пикселей по
    ширине, поле зрения 66°) один пиксель на расстоянии 8 м закрывает 8 мм, а
    лист травы шириной 5-9 мм — это ровно один пиксель. Лист тоньше пикселя
    нарисовать НЕЛЬЗЯ: он либо исчезает, либо мерцает. Расширение с расстоянием
    — это правильное поведение при нехватке разрешения, тот же довод, по
    которому рябь воды переходит в шероховатость.

    Число листьев не назначается, а ИЩЕТСЯ: добавляем, пока измеренное покрытие
    куртины не дойдёт до покрытия сообщества.
    """
    target = com["cover"] * side_m * side_m
    names = list(com["mix"].keys())
    shares = np.array([com["mix"][n] for n in names], dtype=float)
    shares = shares / shares.sum()
    m = Mesh()
    added = 0
    for _ in range(4000):
        cov = m.ground_cover(cell=0.01)
        if cov >= target:
            break
        sname = names[int(rng.choice(len(names), p=shares))]
        sp = species[sname]
        h_lo, h_hi = sp["h_cm"]
        h = rng.uniform(h_lo, h_hi) / 100.0
        lw = sp["leaf_mm"] / 1000.0 * 0.5 * widen
        col = sp["color"]
        # место листа внутри куртины
        px = rng.uniform(0.0, side_m)
        pz = rng.uniform(0.0, side_m)
        az = rng.uniform(0.0, math.tau)
        pts = [np.array([px, 0.0, pz]) + p for p in
               arc(h, rng.uniform(0.05, 0.20), rng.uniform(0.10, 0.35), az=az)]
        widths = [lw * (1.0 - 0.8 * (k / LEAF_SEGS) ** 1.5) for k in range(LEAF_SEGS + 1)]
        shade = rng.uniform(0.82, 1.18)
        m.add_ribbon(pts, widths, [min(1.0, c * shade) for c in col],
                     np.array([0.0, 1.0, 0.0]))
        added += 1
    return m, added, m.ground_cover(cell=0.01)


def main():
    veg = json.load(open(os.path.join(G2, "data/real/vegetation.json")))
    species = veg["species"]
    os.makedirs(OUT_DIR, exist_ok=True)
    print("== РАСТЕНИЯ В ГЕОМЕТРИЮ (без Blender) ==")
    print("вид                     | тип           | △    | высота, м | вершин | покрытие м²")
    rows = []
    blobs = []
    for name, sp in sorted(species.items()):
        habit = sp["habit"]
        rng = np.random.default_rng(abs(hash(name)) % (2 ** 31))
        m = BUILDERS[habit](sp, rng)
        vb, ib, nv, ni = m.pack()
        top = max(p[1] for p in m.v)
        cover = m.ground_cover()
        rows.append((sp["lat"], habit, m.tri_count(), top, nv, cover))
        blobs.append((sp["lat"], HABIT_CODE[habit], top, cover, vb, ib, nv, ni))
        print("%-23s | %-13s | %4d | %9.2f | %5d | %8.4f"
              % (sp["lat"], habit, m.tri_count(), top, nv, cover))

    with open(OUT, "wb") as f:
        f.write(struct.pack("<II", 1, len(blobs)))
        for lat, code, top, cover, vb, ib, nv, ni in blobs:
            nm = lat.encode("utf-8")
            f.write(struct.pack("<BBff", len(nm), code, top, cover))
            f.write(nm)
            f.write(struct.pack("<II", nv, ni))
            f.write(vb)
            f.write(ib)

    # --- КУРТИНЫ СООБЩЕСТВ (средняя даль) ---
    print("\n== КУРТИНЫ 0.5 x 0.5 м (лист расширен втрое — по пикселю на 8 м) ==")
    print("сообщество | листьев | покрытие | △    | куртин/м² | △/м²  | радиус при 800 тыс.")
    patch_blobs = []
    for cname, com in veg["communities"].items():
        rng = np.random.default_rng(1000 + abs(hash(cname)) % 10000)
        pm, added, cov = community_patch(veg, species, cname, com, rng)
        vb, ib, nv, ni = pm.pack()
        top = max(p[1] for p in pm.v) if pm.v else 0.0
        patch_blobs.append((cname, com["zone"], top, cov, vb, ib, nv, ni))
        n_m2 = 1.0 / 0.25                      # куртина закрывает свои 0.25 м²
        tri_m2 = n_m2 * pm.tri_count()
        radius = math.sqrt(800000.0 / max(tri_m2, 1.0) / math.pi)
        print("%-10s | %7d | %7.0f%% | %4d | %9.1f | %6.0f | %.1f м"
              % (cname, added, 100.0 * cov / 0.25, pm.tri_count(), n_m2, tri_m2, radius))

    with open(os.path.join(OUT_DIR, "patches.bin"), "wb") as f:
        f.write(struct.pack("<II", 1, len(patch_blobs)))
        for cname, zone, top, cov, vb, ib, nv, ni in patch_blobs:
            nm = cname.encode("utf-8")
            f.write(struct.pack("<BBff", len(nm), zone, top, cov))
            f.write(nm)
            f.write(struct.pack("<II", nv, ni))
            f.write(vb)
            f.write(ib)
    print("  записано: %s (%.1f КБ)"
          % (os.path.join(OUT_DIR, "patches.bin"),
             os.path.getsize(os.path.join(OUT_DIR, "patches.bin")) / 1024.0))

    tris = sum(r[2] for r in rows)
    print("\nвсего видов %d, треугольников на все дернины %d" % (len(rows), tris))
    print("средняя дернина %.0f △" % (tris / max(len(rows), 1)))
    print("записано: %s (%.1f КБ)" % (OUT, os.path.getsize(OUT) / 1024.0))

    # --- СВЕРКА С БОТАНИКОЙ: высота геометрии обязана попадать в диапазон вида
    print("\n== СВЕРКА С БОТАНИКОЙ ==")
    bad = 0
    for name, sp in sorted(species.items()):
        lat = sp["lat"]
        top = [r[3] for r in rows if r[0] == lat][0]
        lo, hi = sp["h_cm"][0] / 100.0, sp["h_cm"][1] / 100.0
        ok = lo * 0.9 <= top <= hi * 1.1
        if not ok:
            bad += 1
            print("  %-23s высота %.2f м вне ботаники %.2f..%.2f м" % (lat, top, lo, hi))
    print("  видов с высотой вне диапазона: %d из %d" % (bad, len(rows)))

    # --- СКОЛЬКО ДЕРНИН НУЖНО, ЧТОБЫ ЗАКРЫТЬ ЗЕМЛЮ ---
    # Совмещаем ПОКРЫТИЕ, а не число побегов. Настоящий луг держит 11 000
    # побегов/м², и геометрией это не показать никогда: 1100 дернин/м² при 89 △
    # это 98 тысяч треугольников на КАЖДЫЙ квадратный метр. Но глазу важно
    # другое — видно ли землю. Покрытие луга 97%, и его можно закрыть на два
    # порядка меньшим числом дернин, потому что одна дернина закрывает не
    # 1/11000 квадратного метра, а измеренную здесь площадь.
    print("\n== СКОЛЬКО ДЕРНИН НУЖНО ПО ПОКРЫТИЮ ==")
    print("сообщество | покрытие | дернин/м² | △/м²  | радиус при 800 тыс. △")
    budget = 800000.0        # треугольников на весь покров в кадре
    for cname, com in veg["communities"].items():
        mix = com["mix"]
        # среднее покрытие и цена дернины по составу сообщества
        cov = 0.0
        tri = 0.0
        for sname, share in mix.items():
            lat = species[sname]["lat"]
            r = [x for x in rows if x[0] == lat][0]
            cov += share * r[5]
            tri += share * r[2]
        if cov <= 0.0:
            continue
        # дернины перекрываются, поэтому нужно больше, чем покрытие/площадь:
        # при случайной раскладке доля закрытой земли равна 1-exp(-n·cov)
        target = com["cover"]
        n_m2 = -math.log(max(1.0 - target, 0.01)) / cov
        tri_m2 = n_m2 * tri
        radius = math.sqrt(budget / tri_m2 / math.pi)
        print("%-10s | %7.0f%% | %9.0f | %6.0f | %.1f м"
              % (cname, target * 100, n_m2, tri_m2, radius))
    print("  Радиус — это докуда доходит ГЕОМЕТРИЯ при бюджете %.0f тыс. △." % (budget / 1000))
    print("  Дальше покров обязан уходить в материал земли, иначе кадра не будет.")
    print("  Число надо будет ЗАМЕРИТЬ на устройстве, здесь оно расчётное.")


if __name__ == "__main__":
    main()
