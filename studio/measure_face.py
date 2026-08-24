#!/usr/bin/env python3
"""ОБМЕР ГОЛОВЫ И ЛИЦА против ANSUR II (4082 мужчины).

ЧИСЛА ПОСЧИТАНЫ ИЗ СЫРЫХ ДАННЫХ, а не переписаны из чужого пересказа: взят
открытый файл ANSUR II MALE Public.csv и по нему посчитаны средние. Доли роста
приведены, чтобы переносить на наше тело любого роста.

ЛОВУШКА ЕДИНИЦ, НА КОТОРОЙ ЛЕГКО СЕСТЬ: столбец interpupillarybreadth в этом
наборе записан В ДЕСЯТЫХ МИЛЛИМЕТРА — среднее 640.2 при разбросе 530–770. Это
64.0 мм, а не 640: 640 мм шире всей головы. Остальные столбцы в миллиметрах.
Проверять надо не среднее, а РАЗБРОС: он сразу показывает масштаб.

ОРИЕНТИРЫ БЕРУТСЯ ПО МАТЕРИАЛАМ СЕТКИ, А НЕ НА ГЛАЗ. У базовой сетки MakeHuman
отдельные слоты материалов на уши, губы, ногти, глаза. Значит «где губы» и
«где уши» — не догадка по высоте, а точный список многоугольников. Ширину
головы без ушей иначе не померить: уши торчат дальше скул.
"""
import bpy
from mathutils import Vector

# ИЗМЕРЕНО: средние по 4082 мужчинам, рост в наборе 1756 мм.
# (промер, доля роста, среднее в мм)
TARGET = {
    "ширина скул":        (0.0812, 142.6),   # bizygomaticbreadth
    "ширина головы":      (0.0879, 154.3),   # headbreadth, без ушей
    "длина головы":       (0.1136, 199.5),   # headlength, лоб-затылок
    "обхват головы":      (0.3271, 574.4),   # headcircumference
    "лицо: нос-подбородок": (0.0698, 122.6),  # mentonsellionlength
    "межзрачковое":       (0.0364, 64.0),    # interpupillarybreadth
    "длина уха":          (0.0366, 64.2),    # earlength
    "ширина уха":         (0.0205, 36.1),    # earbreadth
    "ухо-макушка":        (0.0747, 131.1),   # tragiontopofhead
}
# Промеры, которых в ANSUR нет; взяты из работ по лицевой антропометрии и
# помечены отдельно, чтобы не путать источники.
TARGET_OTHER = {
    "ширина рта":         53.0,   # cheilion-cheilion, взрослый мужчина
}


def _mat_index(body, needle):
    for i, m in enumerate(body.data.materials):
        if m is not None and needle in m.name.lower():
            return i
    return None


def _by_material(body, needle):
    """Вершины многоугольников с этим материалом, в мире, по ВЫЧИСЛЕННОЙ сетке."""
    idx = _mat_index(body, needle)
    if idx is None:
        return []
    dg = bpy.context.evaluated_depsgraph_get()
    ev = body.evaluated_get(dg)
    me = ev.to_mesh()
    M = body.matrix_world
    out = []
    for p in me.polygons:
        if p.material_index == idx:
            out += [M @ me.vertices[i].co for i in p.vertices]
    ev.to_mesh_clear()
    return out


def _all(body):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = body.evaluated_get(dg)
    me = ev.to_mesh()
    M = body.matrix_world
    pts = [M @ v.co for v in me.vertices]
    ev.to_mesh_clear()
    return pts


def _perim(pts):
    """Периметр выпуклой оболочки набора точек в плоскости xy."""
    P = sorted(set((round(p.x, 5), round(p.y, 5)) for p in pts))
    if len(P) < 3:
        return 0.0

    def half(seq):
        h = []
        for p in seq:
            while len(h) >= 2:
                (x1, y1), (x2, y2) = h[-2], h[-1]
                if (x2 - x1) * (p[1] - y1) - (y2 - y1) * (p[0] - x1) > 0:
                    break
                h.pop()
            h.append(p)
        return h
    hull = half(P)[:-1] + half(P[::-1])[:-1]
    return sum(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
               for a, b in zip(hull, hull[1:] + hull[:1]))


def midline_profile(body, step=0.002):
    """Профиль средней линии лица: для каждой высоты — самая передняя точка.

    Нужен, чтобы найти ПОДБОРОДОК. Первый заход брал «самую нижнюю точку
    средней линии головы», а областью головы считалось всё выше макушки минус
    270 мм — то есть шея и верх груди. Подбородок уезжал на 40 мм вниз, в шею,
    и вместе с ним все промеры, отсчитанные от него. Ширина головы вышла
    302 мм при человеческих 154 — невозможное число, по нему и поймал.
    """
    pts = _all(body)
    top = max(p.z for p in pts)
    prof = []
    z = top - 0.06
    while z > top - 0.34:
        band = [p for p in pts if abs(p.x) < 0.008 and abs(p.z - z) < step
                and p.y < 0]
        if band:
            prof.append((z, min(p.y for p in band)))
        z -= step
    return prof


CHIN_BACK = 0.012        # на сколько подбородок отступает назад под собой


def chin_z(body):
    """Высота подбородка (гнатион), устойчиво.

    ВТОРОЙ ЗАХОД. Первый брал «самый большой отступ назад» на всём профиле —
    и оказался ломким: под нижней губой отступ почти такой же, как под
    подбородком, и победитель менялся от мелочи. Одно и то же тело мерилось
    то на 118 мм, то на 106.
    Теперь так: сперва находим САМУЮ ПЕРЕДНЮЮ точку подбородка (погонион) —
    это выступ ниже рта, — а гнатион ищем под ней: там, где поверхность
    отступила назад больше чем на 12 мм. Обе опоры устойчивы, потому что
    выступ подбородка на профиле один и ни с чем не спорит.
    """
    prof = midline_profile(body)
    if len(prof) < 8:
        return None
    # кончик носа — самая передняя точка всего профиля
    i_nose = min(range(len(prof)), key=lambda i: prof[i][1])
    below = prof[i_nose:]
    if len(below) < 6:
        return None
    # рот — самая ЗАДНЯЯ точка под носом; подбородок ищем уже под ртом
    i_mouth = max(range(len(below)), key=lambda i: below[i][1])
    lower = below[i_mouth:]
    if len(lower) < 4:
        lower = below
    # погонион: самая передняя точка ниже рта
    i_pog = min(range(len(lower)), key=lambda i: lower[i][1])
    y_pog = lower[i_pog][1]
    for z, y in lower[i_pog:]:
        if y - y_pog > CHIN_BACK:
            return z
    return lower[-1][0]


def measure(body, eyes=None):
    pts = _all(body)
    zs = [p.z for p in pts]
    top, H = max(zs), max(zs) - min(zs)
    ears = _by_material(body, "ear")
    lips = _by_material(body, "lip")
    ear_ids = set((round(p.x, 6), round(p.y, 6), round(p.z, 6)) for p in ears)
    m = {}

    z_chin = chin_z(body)
    if z_chin is None:
        z_chin = top - 0.23
    # ГОЛОВА — ЭТО ОТ ПОДБОРОДКА ВВЕРХ, и ни миллиметром ниже: там шея.
    head = [p for p in pts if p.z >= z_chin]
    head_noears = [p for p in head
                   if (round(p.x, 6), round(p.y, 6), round(p.z, 6)) not in ear_ids]
    m["_подбородок"] = z_chin
    m["высота головы"] = top - z_chin

    # ПЕРЕНОСИЦА: самая задняя точка средней линии МЕЖДУ кончиком носа и лбом.
    prof = midline_profile(body)
    if prof:
        # кончик носа — самая передняя точка профиля
        zt = min(prof, key=lambda p: p[1])[0]
        above = [(z, y) for z, y in prof if zt < z < zt + 0.055]
        if above:
            zb = max(above, key=lambda p: p[1])[0]
            m["лицо: нос-подбородок"] = zb - z_chin

    # ЧЕРЕПНАЯ КОРОБКА: только выше глаз, иначе в срез лезут челюсть и шея
    crown = [p for p in head_noears if p.z > z_chin + 0.085]
    if crown:
        m["ширина головы"] = max(p.x for p in crown) - min(p.x for p in crown)
        m["длина головы"] = max(p.y for p in crown) - min(p.y for p in crown)

    # СКУЛЫ: самое широкое место лица без ушей, ищем по полосам, а не наугад
    best = 0.0
    zz = z_chin + 0.045
    while zz < z_chin + 0.100:
        band = [p for p in head_noears if abs(p.z - zz) < 0.006]
        if len(band) > 6:
            best = max(best, max(p.x for p in band) - min(p.x for p in band))
        zz += 0.004
    if best:
        m["ширина скул"] = best

    # ОБХВАТ ГОЛОВЫ: срез над бровями, уши включены — так мерят и в ANSUR
    zz = z_chin + 0.115
    band = [p for p in head if abs(p.z - zz) < 0.008]
    if len(band) > 8:
        m["обхват головы"] = _perim(band)

    if ears:
        L = [p for p in ears if p.x > 0]
        if L:
            m["длина уха"] = max(p.z for p in L) - min(p.z for p in L)
            m["ширина уха"] = max(p.y for p in L) - min(p.y for p in L)
            m["ухо-макушка"] = top - (sum(p.z for p in L) / len(L))
            m["_вершин уха"] = len(L)

    if lips:
        m["ширина рта"] = max(p.x for p in lips) - min(p.x for p in lips)

    if eyes is not None:
        dg = bpy.context.evaluated_depsgraph_get()
        ev = eyes.evaluated_get(dg)
        em = ev.to_mesh()
        Me = eyes.matrix_world
        ep = [Me @ v.co for v in em.vertices]
        ev.to_mesh_clear()
        L = [p for p in ep if p.x > 0]
        R = [p for p in ep if p.x < 0]
        if L and R:
            cl = sum(L, Vector()) / len(L)
            cr = sum(R, Vector()) / len(R)
            m["межзрачковое"] = (cl - cr).length
    m["_рост"] = H
    return m


def report(body, eyes=None, note=""):
    m = measure(body, eyes)
    H = m["_рост"]
    print("\n=== ГОЛОВА И ЛИЦО %s (рост %.3f м) ===" % (note, H))
    # САМОПРОВЕРКА ИНСТРУМЕНТА: если подбородок или высота головы вышли
    # неправдоподобными, всё остальное считать нельзя — оно от них отсчитано.
    print("  опоры: подбородок z=%.3f, высота головы %.0f мм (у человека "
          "около %.0f), вершин уха %d"
          % (m.get("_подбородок", 0), m.get("высота головы", 0) * 1000,
             0.1333 * H * 1000, m.get("_вершин уха", 0)))
    print("  %-22s %8s %8s %8s" % ("промер", "наше", "норма", "промах"))
    bad = []
    for k, (frac, mm) in TARGET.items():
        if k not in m:
            print("  %-22s %8s   не снялся" % (k, "—"))
            continue
        got, tgt = m[k] * 1000, frac * H * 1000
        d = (got - tgt) / tgt * 100
        mark = "" if abs(d) < 6 else ("  — МЕНЬШЕ" if d < 0 else "  — БОЛЬШЕ")
        if abs(d) >= 6:
            bad.append((abs(d), k, d))
        print("  %-22s %8.1f %8.1f %+7.1f%%%s" % (k, got, tgt, d, mark))
    for k, mm in TARGET_OTHER.items():
        if k in m:
            tgt = mm * H / 1.756
            got = m[k] * 1000
            print("  %-22s %8.1f %8.1f %+7.1f%%   (не ANSUR)"
                  % (k, got, tgt, (got - tgt) / tgt * 100))
    if bad:
        bad.sort(reverse=True)
        print("  ХУЖЕ ВСЕГО: " + ", ".join("%s %+.0f%%" % (k, d) for _, k, d in bad[:4]))
    return m
