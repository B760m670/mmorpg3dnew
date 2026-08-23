#!/usr/bin/env python3
"""КАК ЧЕЛОВЕК ПРОСТО СТОИТ. Разбор записей спокойного стояния.

ЗАЧЕМ ЭТОТ ФАЙЛ ПОЯВИЛСЯ. Я взялся за ходьбу, когда у персонажа не было
обычного человеческого состояния — стояния. Единственной его позой была
Т-поза от MPFB: руки в стороны, ноги врозь, ладони раскрыты. Это поза для
МОДЕЛИРОВАНИЯ, её придумали, чтобы удобно было разворачивать текстуру и
ставить веса, а не потому, что человек так стоит. Начинать надо было с того,
что человек делает по умолчанию.

СТОЯНИЕ — ЭТО НЕ ПОЗА, А ПРОЦЕСС, и вот что об этом известно из литературы
(числа взяты не с потолка, источники в docs/roadmap.md):
  дыхание 15–20 вдохов в минуту в покое, грудь ходит на 1–2 см;
  перенос веса с ноги на ногу каждые 4–8 секунд;
  качание тела при спокойном стоянии идёт непрерывно, вперёд-назад
    заметно сильнее, чем вбок (на 44–52%);
  для игры петля стояния — 2–4 с, если это только дыхание, и 8–12 с, если
    в неё входит перенос веса; на стыке петли обязаны совпадать не только
    поза, но и СКОРОСТЬ, иначе будет рывок.

ЭТОТ ФАЙЛ НИЧЕГО НЕ ВЫДУМЫВАЕТ. Он берёт запись живого человека и меряет по
ней всё перечисленное: сходятся ли числа с литературой и годится ли запись
нам. Разбор идёт прямо по ASF/AMC на чистом Питоне — без Блендера, поэтому
быстро и поэтому же честно: тут ещё нет ни нашего рига, ни нашего переноса,
которые могли бы что-то испортить.

Запуск:
  python3 studio/stance.py /tmp/claude-live/mocap/140.asf .../140_06.amc
"""
import math
import re
import sys

I3 = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]


def mul(A, B):
    return [[sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3)]
            for i in range(3)]


def mv(A, v):
    return [sum(A[i][k] * v[k] for k in range(3)) for i in range(3)]


def tr(A):
    return [[A[j][i] for j in range(3)] for i in range(3)]


def rot(ax, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    if ax == 'X':
        return [[1, 0, 0], [0, c, -s], [0, s, c]]
    if ax == 'Y':
        return [[c, 0, s], [0, 1, 0], [-s, 0, c]]
    return [[c, -s, 0], [s, c, 0], [0, 0, 1]]


def euler(a, order):
    """Свёртка углов по правилу ASF: R = Rz·Ry·Rx.

    Углы перечислены как rx, ry, rz, но применяются к НЕПОДВИЖНЫМ осям —
    сначала вокруг X, потом вокруг Y, потом вокруг Z. Значит в произведении
    они идут в обратном порядке. Проверено на записи стоящего человека:
    при обратной свёртке его стопы улетают на 1.75 м вверх, при этой —
    остаются на полу.
    """
    m = I3
    for ax, d in zip(reversed(order), reversed(list(a))):
        m = mul(m, rot(ax, d))
    return m


def parse_asf(path):
    txt = open(path).read()
    scale = 0.0254 / 0.45
    m = re.search(r":units(.*?):", txt, re.S)
    if m:
        u = re.search(r"length\s+([-\d.eE+]+)", m.group(1))
        if u:
            scale = 0.0254 / float(u.group(1))
    bones = {}
    for blk in re.findall(r"begin(.*?)end", txt, re.S):
        nm = re.search(r"name\s+(\S+)", blk)
        if not nm:
            continue
        d = re.search(r"direction\s+([-\d.eE+\s]+)", blk)
        ln = re.search(r"length\s+([-\d.eE+]+)", blk)
        ax = re.search(r"axis\s+([-\d.eE+\s]+?)\s+([XYZ]{3})", blk)
        bones[nm.group(1)] = {
            "dir": [float(x) for x in d.group(1).split()[:3]] if d else [0, 0, 0],
            "len": float(ln.group(1)) if ln else 0.0,
            "axis": [float(x) for x in ax.group(1).split()[:3]] if ax else [0, 0, 0],
            "order": ax.group(2) if ax else "XYZ",
            "dof": re.findall(r"\b(r[xyz])\b", blk.split("limits")[0]),
        }
    bones["root"] = {"dir": [0, 0, 0], "len": 0.0, "axis": [0, 0, 0],
                     "order": "XYZ", "dof": ["rx", "ry", "rz"]}
    par = {}
    h = re.search(r":hierarchy(.*?)(?::|$)", txt, re.S)
    if h:
        for line in h.group(1).splitlines():
            w = line.split()
            if len(w) >= 2 and w[0] not in ("begin", "end"):
                for c in w[1:]:
                    par[c] = w[0]
    return bones, par, scale


def parse_amc(path):
    frames, cur = [], None
    for line in open(path):
        line = line.strip()
        if not line or line[0] in "#:":
            continue
        if re.fullmatch(r"\d+", line):
            cur = {}
            frames.append(cur)
            continue
        if cur is None:
            continue
        w = line.split()
        cur[w[0]] = [float(x) for x in w[1:]]
    return frames


def solve(bones, par, scale, fr):
    """Положения суставов в кадре. Ось Y — вверх (так у CMU)."""
    order, seen = [], set()

    def walk(b):
        if b in seen:
            return
        seen.add(b)
        order.append(b)
        for c, p in par.items():
            if p == b:
                walk(c)
    walk("root")
    A, P = {}, {}
    for b in order:
        bd = bones.get(b)
        if bd is None:
            continue
        vals = fr.get(b, [])
        if b == "root":
            A[b] = euler(vals[3:6] if len(vals) >= 6 else [0, 0, 0], "XYZ")
            P[b] = [v * scale for v in (vals[:3] if len(vals) >= 3 else [0, 0, 0])]
        else:
            C = euler(bd["axis"], bd["order"])
            R = I3
            for nm, v in zip(bd["dof"] or ["rx", "ry", "rz"], vals):
                R = mul(R, rot({"rx": 'X', "ry": 'Y', "rz": 'Z'}[nm], v))
            A[b] = mul(A[par[b]], mul(C, mul(R, tr(C))))
            off = mv(A[b], [c * bd["len"] * scale for c in bd["dir"]])
            P[b] = [P[par[b]][k] + off[k] for k in range(3)]
    return P


def _rms(x):
    m = sum(x) / len(x)
    return math.sqrt(sum((v - m) ** 2 for v in x) / len(x))


def _smooth(x, w):
    """Скользящее среднее. Без него любой счётчик колебаний считает шум."""
    if w < 2:
        return list(x)
    out = []
    for i in range(len(x)):
        a, b = max(0, i - w), min(len(x), i + w + 1)
        out.append(sum(x[a:b]) / (b - a))
    return out


def _periods(x, fps, smooth=0):
    """Средний период колебания: по пересечениям среднего снизу вверх.

    СГЛАЖИВАНИЕ ЗДЕСЬ НЕ УКРАШЕНИЕ. Первая версия считала пересечения по
    сырому ряду и выдала «дыхание 1007 раз в минуту» — это она считала
    дрожание захвата. Дыхание в покое это 0.25–0.33 Гц, перенос веса ещё
    медленнее; всё, что быстрее, к делу не относится и должно быть срезано
    до счёта, а не после.
    """
    y = _smooth(x, smooth)
    m = sum(y) / len(y)
    cr = [i for i in range(1, len(y)) if y[i - 1] < m <= y[i]]
    if len(cr) < 2:
        return 0.0, 0
    d = [(b - a) / fps for a, b in zip(cr, cr[1:])]
    return sum(d) / len(d), len(d)


def analyse(asf, amc, fps=120, name=""):
    bones, par, scale = parse_asf(asf)
    frames = parse_amc(amc)
    P = [solve(bones, par, scale, f) for f in frames]
    n = len(P)
    dur = n / fps
    print("=" * 70)
    print("СТОЯНИЕ: %s — %d кадров, %.1f с при %d к/с" % (name or amc, n, dur, fps))

    # ТАЗ: качание вбок и вперёд-назад. У CMU x — вбок, z — вперёд, y — вверх.
    x = [p["root"][0] for p in P]
    z = [p["root"][2] for p in P]
    y = [p["root"][1] for p in P]
    ml, ap = _rms(x) * 1000, _rms(z) * 1000
    print("  таз: качание вбок %.0f мм скз (размах %.0f), "
          "вперёд-назад %.0f мм скз (размах %.0f)"
          % (ml, (max(x) - min(x)) * 1000, ap, (max(z) - min(z)) * 1000))
    print("       вперёд-назад больше вбок в %.2f× (в литературе 1.44–1.52×)"
          % (ap / ml if ml else 0))
    print("  таз по высоте: размах %.0f мм" % ((max(y) - min(y)) * 1000))

    # ПЕРЕНОС ВЕСА меряется ОТНОСИТЕЛЬНО СТОП, а не в мировых координатах.
    # Первая версия считала пересечения средней линии по абсолютному x таза и
    # для записи «Idle» нашла ноль переносов — просто потому, что человек за
    # эти полминуты потихоньку сместился по площадке, и среднее оказалось не
    # там, где он стоял. Правильная величина безразмерна: где таз между
    # стопами. −1 — вес полностью на левой ноге, +1 — на правой.
    if "lfoot" in P[0] and "rfoot" in P[0]:
        bal = []
        for p in P:
            mid = [(p["lfoot"][k] + p["rfoot"][k]) / 2 for k in (0, 2)]
            hw = math.hypot(p["rfoot"][0] - p["lfoot"][0],
                            p["rfoot"][2] - p["lfoot"][2]) / 2
            ax = [(p["rfoot"][0] - p["lfoot"][0]), (p["rfoot"][2] - p["lfoot"][2])]
            L = math.hypot(*ax) or 1.0
            ax = [c / L for c in ax]
            d = [p["root"][0] - mid[0], p["root"][2] - mid[1]]
            bal.append((d[0] * ax[0] + d[1] * ax[1]) / hw if hw > 1e-6 else 0.0)
        per, cnt = _periods(bal, fps, smooth=fps // 4)
        print("  вес между стопами: %+.2f..%+.2f (−1 левая нога, +1 правая)"
              % (min(bal), max(bal)))
        print("  перенос веса: период %.1f с (%d раз за запись); "
              "в литературе 4–8 с — %s"
              % (per, cnt, "СХОДИТСЯ" if 3.0 <= per <= 10.0 else "НЕ СХОДИТСЯ"))

    # ДЫХАНИЕ: грудь ходит вверх-вниз. Берём разницу высот груди и таза, чтобы
    # убрать общее качание тела.
    if "thorax" in P[0]:
        ch = _smooth([p["thorax"][1] - p["root"][1] for p in P], fps // 6)
        amp = (max(ch) - min(ch)) * 1000
        per, cnt = _periods(ch, fps, smooth=fps // 6)
        bpm = 60.0 / per if per else 0.0
        print("  грудь относительно таза: размах %.0f мм, %.0f колебаний в минуту"
              % (amp, bpm))
        print("       дыхание в покое 15–20 в минуту, грудь 10–20 мм — %s"
              % ("похоже" if 8 <= amp <= 45 and 8 <= bpm <= 30 else "НЕ ПОХОЖЕ"))

    # СТОПЫ: стоят ли обе на месте всю запись
    for f in ("lfoot", "rfoot", "ltoes", "rtoes"):
        if f not in P[0]:
            continue
        xs = [p[f][0] for p in P]
        zs = [p[f][2] for p in P]
        ys = [p[f][1] for p in P]
        move = math.hypot(max(xs) - min(xs), max(zs) - min(zs)) * 1000
        print("  %-6s сдвиг по полу %.0f мм, по высоте %.0f мм"
              % (f, move, (max(ys) - min(ys)) * 1000))
    # РАССТОЯНИЕ МЕЖДУ СТОПАМИ
    if "lfoot" in P[0] and "rfoot" in P[0]:
        d = [math.hypot(p["lfoot"][0] - p["rfoot"][0],
                        p["lfoot"][2] - p["rfoot"][2]) for p in P]
        print("  стопы врозь: %.0f..%.0f мм (у стоящего человека 100–250)"
              % (min(d) * 1000, max(d) * 1000))
    return P


def best_loop(P, fps=120, want=(8.0, 12.0), root="root"):
    """Найти окно, которое лучше всего замкнётся в петлю.

    Петля хороша, когда совпадают И ПОЗА, И СКОРОСТЬ на стыке — иначе рывок.
    Поэтому цена стыка складывается из разницы положений всех суставов и
    разницы их скоростей.
    """
    n = len(P)
    keys = [k for k in P[0] if k != "root"]

    def vel(i, k):
        j = max(1, min(n - 1, i))
        return [(P[j][k][c] - P[j - 1][k][c]) * fps for c in range(3)]

    best = None
    lo, hi = int(want[0] * fps), int(want[1] * fps)
    for a in range(0, n - lo, max(1, fps // 4)):
        for L in range(lo, min(hi, n - a), max(1, fps // 2)):
            b = a + L
            dp = sum(math.dist(P[a][k], P[b][k]) for k in keys) / len(keys)
            dv = sum(math.dist(vel(a, k), vel(b, k)) for k in keys) / len(keys)
            cost = dp * 1000 + dv * 100
            if best is None or cost < best[0]:
                best = (cost, a, b, dp * 1000, dv * 1000)
    if best:
        print("  лучшая петля: кадры %d..%d (%.1f с), стык: поза %.1f мм, "
              "скорость %.0f мм/с" % (best[1], best[2], (best[2] - best[1]) / fps,
                                      best[3], best[4]))
    print("=" * 70)
    return best


if __name__ == "__main__":
    a, m = sys.argv[1], sys.argv[2]
    fps = int(sys.argv[3]) if len(sys.argv) > 3 else 120
    P = analyse(a, m, fps)
    best_loop(P, fps)
