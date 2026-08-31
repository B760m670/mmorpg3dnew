#!/usr/bin/env python3
"""СТОЯНИЕ: своя нейтральная стойка плюс живое покачивание из записи.

ПОЧЕМУ ПРЕДЫДУЩИЙ ПОДХОД БЫЛ НЕВЕРЕН В ОСНОВЕ. Я брал кадр из записи «человек
стоит» и правил его доворотами костей, пока сходились отдельные числа —
стопы врозь, просвет под рукой. Числа сходились, а стойка оставалась негодной,
и заказчик это видел сразу. Причина простая: ЗАПИСАННЫЙ ЧЕЛОВЕК В ТОТ МОМЕНТ
НЕ СТОЯЛ РОВНО. У него одна нога выставлена вперёд, корпус подкручен, голова
повёрнута в сторону — обычная живая поза человека, который стоит и смотрит по
сторонам. Из неё нейтральной стойки не сделать никакими доворотами: доворот
меняет углы, а не замысел позы.

И ещё: по фронтальному силуэту разницы не видно вовсе. Нога, выставленная
ВПЕРЁД, в силуэте выглядит точно так же, как отставленная ВБОК. Мой прибор
мерил именно силуэт — и честно показывал «сходится».

КАК ПРАВИЛЬНО, и это описано в любом руководстве по игровой анимации:
  БАЗОВАЯ ПОЗА задаётся явно — она нейтральная, симметричная, выверенная;
  ЖИВОЕ КЛАДЁТСЯ ПОВЕРХ РАЗНОСТЬЮ: из записи берётся не сама поза, а её
  отклонение от собственного среднего, и это отклонение добавляется к нашей
  базе. Тогда сохраняется всё, чего не сочинить (покачивание, перенос веса,
  мелкие поправки равновесия), и не наследуется чужая поза.

ЧТО СЧИТАЕТСЯ НЕЙТРАЛЬНОЙ СТОЙКОЙ (по фотографии спокойно стоящего мужчины и
по анатомии):
  стопы на одной линии, врозь примерно на 0.19 роста, носки наружу 5–10°;
  колени прямые и над стопами, без завала внутрь;
  таз и плечи развёрнуты одинаково, корпус не подкручен;
  руки висят вдоль тела с небольшим просветом, локти чуть согнуты,
    ладони обращены к бёдрам, пальцы слегка подобраны;
  голова прямо.

ПОЗА ПОКОЯ НАШЕГО РИГА УЖЕ БЛИЗКА К ЭТОМУ по ногам: стопы в ней врозь на
380 мм (0.22 роста), носки наружу на 5.3°. Неверны в ней только руки —
они разведены в стороны под 45°, потому что это поза для моделирования.
Значит база = поза покоя + опущенные руки, и всё.
"""
import math

import bpy
from mathutils import Quaternion, Vector

# КУДА СМОТРИТ КОСТЬ, а не «повернуть на N градусов».
#
# ПЕРВЫЙ ВАРИАНТ ЗАДАВАЛ УГЛЫ, И ЭТО БЫЛО НЕВЕРНО. У позы покоя руки разведены
# под 45°, и поворот вокруг локальной оси Z опускает руку не вниз, а вниз-и-
# вперёд: кисти уехали на 211 мм перед бёдрами и повисли ладонями вперёд.
# Подбирать угол бесполезно — ось не та, а какая та, зависит от крена кости.
#
# Поэтому поза задаётся НАПРАВЛЕНИЯМИ в мире: «плечо смотрит вниз и чуть
# наружу», «предплечье вниз и чуть вперёд». Это ровно то, как позу описал бы
# человек, и это не зависит ни от крена, ни от того, какая поза покоя.
# Направления даны в осях тела: up — вверх, lat — в сторону своей руки,
# fwd — куда человек смотрит.
#
# Числа — анатомия спокойно стоящего человека: плечевая кость отклонена от
# вертикали на 6–8°, локоть в покое согнут на 5–10° (рука не палка), кисть
# продолжает предплечье, пальцы подобраны.
AIM = {
    "Arm":        (0.11, 0.00, -0.99),
    "ForeArm":    (0.07, 0.06, -0.99),
    "Hand":       (0.05, 0.10, -0.99),
    "FingerBase": (0.04, 0.22, -0.97),
    "HandFinger1": (0.03, 0.34, -0.94),
}
# Разворот ладони: у спокойно стоящего человека ладонь обращена к бедру.
PALM_INWARD = True

# РАЗВОРОТ СТОП НАРУЖУ. ИЗМЕРЕНО по сетке стопы (главная компонента облака её
# вершин в плоскости пола, только на опорных кадрах): в покое носок был
# +0.0° слева и −0.0° справа, то есть стопы стояли строго параллельно. У
# человека они разведены наружу на 5–15° (угол Фика около 7°), и идеально
# параллельные стопы читаются неживыми — заказчик назвал это «ноги
# притуплены». Близкая камера это ещё усиливает: при стопах врозь на 0.2 м и
# камере в 2.6 м перспектива сводит их наружные края.
#
# Разворот делается БЕДРОМ, а не стопой: у стоящего человека носки разводит
# наружная ротация в тазобедренном суставе, и поворачивается вся нога целиком.
# Крутить одну стопу значило бы сломать голеностоп.
TOE_OUT = 8.0



def _axes(arm):
    """Оси тела: вбок (к левой руке), вперёд, вверх."""
    lat = (arm.data.bones["LeftUpLeg"].head_local -
           arm.data.bones["RightUpLeg"].head_local)
    lat.z = 0.0
    lat.normalize()
    fwd = Vector((-lat.y, lat.x, 0.0))
    toe = (arm.data.bones["LeftToeBase"].head_local -
           arm.data.bones["LeftFoot"].head_local)
    if toe.dot(fwd) < 0:
        fwd = -fwd
    return lat, fwd, Vector((0.0, 0.0, 1.0))


def aim(pb, target):
    """Повернуть кость так, чтобы она смотрела в заданную сторону мира.

    Кручение вокруг собственной оси не задаётся: берётся кратчайший поворот,
    то есть крен кости остаётся прежним. Иначе кисть начинает вертеться
    вместе с наведением.
    """
    cur = (pb.tail - pb.head)
    if cur.length < 1e-9:
        return
    q = cur.normalized().rotation_difference(Vector(target).normalized())
    M = pb.matrix.copy()
    t = M.translation.copy()
    M.translation = (0.0, 0.0, 0.0)
    M = q.to_matrix().to_4x4() @ M
    M.translation = t
    pb.matrix = M
    bpy.context.view_layer.update()


def twist(pb, deg):
    """Кручение вокруг собственной оси кости — пронация предплечья."""
    ax = (pb.tail - pb.head).normalized()
    q = Quaternion(ax, math.radians(deg))
    M = pb.matrix.copy()
    t = M.translation.copy()
    M.translation = (0.0, 0.0, 0.0)
    M = q.to_matrix().to_4x4() @ M
    M.translation = t
    pb.matrix = M
    bpy.context.view_layer.update()


def spin(pb, deg):
    """Развернуть кость и всё, что под ней, вокруг вертикали (наружная ротация)."""
    q = Quaternion((0.0, 0.0, 1.0), math.radians(deg))
    M = pb.matrix.copy()
    t = M.translation.copy()
    M.translation = (0.0, 0.0, 0.0)
    M = q.to_matrix().to_4x4() @ M
    M.translation = t
    pb.matrix = M
    bpy.context.view_layer.update()


def apply_base(arm, extra=None, verbose=False):
    """Поставить нейтральную стойку поверх позы покоя."""
    for pb in arm.pose.bones:
        pb.rotation_mode = 'QUATERNION'
        pb.rotation_quaternion = Quaternion()
        pb.location = Vector()
    bpy.context.view_layer.update()
    lat, fwd, up = _axes(arm)
    for side, sgn in (("Left", 1.0), ("Right", -1.0)):
        for part, (a, b, c) in AIM.items():
            pb = arm.pose.bones.get(side + part)
            if pb is not None:
                aim(pb, lat * (a * sgn) + fwd * b + up * c)
    if PALM_INWARD:
        # РАЗВОРОТ ЛАДОНИ РЕШАЕТСЯ ОДИН РАЗ И ЗЕРКАЛИТСЯ.
        #
        # Прежде поиск шёл отдельно для каждой руки, и стороны разошлись: у
        # правой он находил другой минимум, плечо уезжало в чужой угол, и в
        # кадре рука выглядела сломанной и размазанной, тогда как левая
        # получалась хорошо. Симметричную позу нельзя ПОЛУЧАТЬ поиском по
        # обеим сторонам — её надо СТРОИТЬ симметричной: решить слева и
        # отразить. Тогда расхождение не «мало», а равно нулю по построению.
        fore = arm.pose.bones.get("LeftArm")
        hand = arm.pose.bones.get("LeftHand")
        bq = 0.0
        if fore is not None and hand is not None:
            inward = -lat
            best = None
            start = fore.rotation_quaternion.copy()
            for d in range(-100, 101, 5):
                fore.rotation_quaternion = start
                bpy.context.view_layer.update()
                twist(fore, float(d))
                v = hand.x_axis.dot(inward)
                if best is None or v > best:
                    best, bq = v, float(d)
            fore.rotation_quaternion = start
            bpy.context.view_layer.update()
            twist(fore, bq)
            if verbose:
                print("[стойка] кручение плеча %.0f° (решено слева, "
                      "зеркалится направо), ладонь к бедру %.2f" % (bq, best))
        r = arm.pose.bones.get("RightArm")
        if r is not None:
            twist(r, -bq)

    if TOE_OUT:
        # ЗНАК ПРОВЕРЕН ЗАМЕРОМ, А НЕ ВЫВЕДЕН. С обратным знаком обе стопы
        # уходили внутрь на 8° — то есть косолапие становилось вдвое хуже,
        # а число «8°» в коде выглядело бы столь же убедительно.
        for side, sgn in (("Left", -1.0), ("Right", 1.0)):
            pb = arm.pose.bones.get(side + "UpLeg")
            if pb is not None:
                spin(pb, TOE_OUT * sgn)
        if verbose:
            print("[стойка] носки разведены наружу на %.0f°" % TOE_OUT)

    for bone, turns in (extra or {}).items():
        pb = arm.pose.bones.get(bone)
        if pb is None:
            continue
        q = Quaternion()
        for ax, deg in turns:
            v = {'X': (1, 0, 0), 'Y': (0, 1, 0), 'Z': (0, 0, 1)}[ax]
            q = q @ Quaternion(v, math.radians(deg))
        pb.rotation_quaternion = pb.rotation_quaternion @ q
    bpy.context.view_layer.update()


def additive(arm, frames, damp=None, root_sway=True):
    """Наложить на базу ОТКЛОНЕНИЯ записи от её собственного среднего.

    damp — насколько ослабить отклонение по костям (1.0 полностью, 0 совсем
    убрать). Голову приходится придерживать: в записи человек разглядывает
    комнату и поворачивается на полсотни градусов, а нашему герою в кадре это
    ни к чему — он просто стоит.
    """
    damp = damp or {}
    act = arm.animation_data.action if arm.animation_data else None
    if act is None:
        raise RuntimeError("нет записи, из которой брать отклонения")
    sc = bpy.context.scene
    # 1. запоминаем запись
    rec = {}
    for f in frames:
        sc.frame_set(f)
        rec[f] = {pb.name: pb.rotation_quaternion.copy() for pb in arm.pose.bones}
    loc = {}
    for f in frames:
        sc.frame_set(f)
        loc[f] = {pb.name: pb.location.copy() for pb in arm.pose.bones}
    # 2. среднее по записи (нормированная сумма кватернионов — этого хватает,
    #    отклонения малы и знак у всех один)
    mean = {}
    for name in rec[frames[0]]:
        acc = Quaternion((0, 0, 0, 0))
        ref = rec[frames[0]][name]
        for f in frames:
            q = rec[f][name]
            if q.dot(ref) < 0:
                q = Quaternion((-q.w, -q.x, -q.y, -q.z))
            acc.w += q.w; acc.x += q.x; acc.y += q.y; acc.z += q.z
        n = math.sqrt(acc.w**2 + acc.x**2 + acc.y**2 + acc.z**2)
        mean[name] = Quaternion((acc.w/n, acc.x/n, acc.y/n, acc.z/n)) if n > 1e-9 \
            else Quaternion()
    mloc = {}
    for name in loc[frames[0]]:
        s = Vector()
        for f in frames:
            s += loc[f][name]
        mloc[name] = s / len(frames)
    # 3. база
    arm.animation_data_clear()
    apply_base(arm)
    base = {pb.name: pb.rotation_quaternion.copy() for pb in arm.pose.bones}
    # 4. база ∘ отклонение
    worst = 0.0
    for f in frames:
        for pb in arm.pose.bones:
            d = mean[pb.name].inverted() @ rec[f][pb.name]
            k = damp.get(pb.name, 1.0)
            if k != 1.0:
                d = Quaternion().slerp(d, k)
            ang = abs(d.angle)
            worst = max(worst, min(ang, 2 * math.pi - ang))
            pb.rotation_quaternion = base[pb.name] @ d
            pb.keyframe_insert("rotation_quaternion", frame=f)
            if root_sway and pb.name == "Hips":
                pb.location = loc[f][pb.name] - mloc[pb.name]
                pb.keyframe_insert("location", frame=f)
    sc.frame_start, sc.frame_end = frames[0], frames[-1]
    print("[стояние] покачивание наложено на базу: %d кадров, "
          "наибольшее отклонение %.1f°" % (len(frames), math.degrees(worst)))


def stance_report(arm, body=None, frame=None, note=""):
    """ЧИСЛА ПРО САМУ СТОЙКУ — те, что описывают её словами.

    Прежние приборы мерили силуэт и обхваты, и оба честно говорили «сходится»,
    когда стойка была негодной. Причина: во фронтальном силуэте нога,
    выставленная ВПЕРЁД, выглядит так же, как отставленная ВБОК. Здесь мерится
    то, что человек назвал бы, описывая стойку: разнос стоп вдоль и поперёк,
    развёрнутость носков, завал коленей, наклон корпуса, вынос головы.
    """
    sc = bpy.context.scene
    if frame is not None:
        sc.frame_set(frame)
    dg = bpy.context.evaluated_depsgraph_get()
    a = arm.evaluated_get(dg)
    P = {b.name: b.head.copy() for b in a.pose.bones}
    T = {b.name: b.tail.copy() for b in a.pose.bones}
    lat = (P["LeftUpLeg"] - P["RightUpLeg"]); lat.z = 0; lat.normalize()
    fwd = Vector((-lat.y, lat.x, 0.0))
    # вперёд там, куда смотрит стопа
    toe = (T["LeftFoot"] - P["LeftFoot"]) + (T["RightFoot"] - P["RightFoot"])
    if toe.dot(fwd) < 0:
        fwd = -fwd
    H = (max(P["Head"].z, T["Head"].z) - min(P["LeftFoot"].z, P["RightFoot"].z)) / 0.93

    def along(v, d):
        return v.x * d.x + v.y * d.y

    lf, rf = P["LeftFoot"], P["RightFoot"]
    d = {}
    d["разнос стоп вдоль"] = abs(along(lf - rf, fwd))
    d["разнос стоп поперёк"] = abs(along(lf - rf, lat))
    for s2, foot, tb in (("L", "LeftFoot", "LeftToeBase"),
                         ("R", "RightFoot", "RightToeBase")):
        v = P[tb] - P[foot]
        sgn = 1 if s2 == "L" else -1
        d["носок %s наружу°" % s2] = math.degrees(
            math.atan2(sgn * along(v, lat), along(v, fwd)))
    for s2, up, lo, ft in (("L", "LeftUpLeg", "LeftLeg", "LeftFoot"),
                           ("R", "RightUpLeg", "RightLeg", "RightFoot")):
        # завал колена: насколько колено ушло внутрь от линии бедро-щиколотка
        t = (P[lo].z - P[ft].z) / max(1e-6, (P[up].z - P[ft].z))
        line = P[ft] + (P[up] - P[ft]) * t
        sgn = 1 if s2 == "L" else -1
        d["колено %s внутрь" % s2] = -sgn * along(P[lo] - line, lat)
    d["корпус наклон вперёд"] = along(P["Neck"] - P["Hips"], fwd)
    d["голова вынос вперёд"] = along(P["Head"] - P["Neck"], fwd)
    d["плечи против таза°"] = math.degrees(math.asin(max(-1.0, min(1.0,
        lat.cross(((P["LeftArm"] - P["RightArm"])
                   .normalized())).z))))
    print("-" * 62)
    print("СТОЙКА %s" % note)
    good = {"разнос стоп вдоль": (0.0, 0.04), "разнос стоп поперёк": (0.19 * H, 0.05 * H),
            "носок L наружу°": (8, 8), "носок R наружу°": (8, 8),
            "колено L внутрь": (0.0, 0.02), "колено R внутрь": (0.0, 0.02),
            "корпус наклон вперёд": (0.0, 0.05), "голова вынос вперёд": (0.0, 0.05),
            "плечи против таза°": (0, 8)}
    for k, v in d.items():
        want, tol = good.get(k, (None, None))
        unit = "°" if "°" in k else "мм"
        val = v if "°" in k else v * 1000
        w = want if "°" in k else (want * 1000 if want is not None else None)
        t = tol if "°" in k else (tol * 1000 if tol is not None else None)
        mark = ""
        if want is not None and abs(val - w) > t:
            mark = "  <-- надо %.0f±%.0f" % (w, t)
        print("   %-22s %+8.0f %s%s" % (k, val, unit, mark))
    print("-" * 62)
    return d


def symmetry_report(arm, note=""):
    """НАСКОЛЬКО ПОЗА СИММЕТРИЧНА, в миллиметрах.

    Этого прибора не хватало, и его отсутствие стоило дорого: правая рука в
    кадре была сломана и размазана, левая — хороша, а ни один замер этого не
    показывал, потому что все они мерили ОБЩИЕ величины (ширину плеч, просвет
    под рукой) и на разницу сторон слепы.

    Левая точка отражается через срединную плоскость тела и сравнивается с
    правой. Для позы, построенной симметрично, расхождение обязано быть
    нулевым с точностью до счёта.
    """
    dg = bpy.context.evaluated_depsgraph_get()
    a = arm.evaluated_get(dg)
    lat = (a.pose.bones["LeftUpLeg"].head - a.pose.bones["RightUpLeg"].head)
    lat.z = 0.0
    lat.normalize()
    mid = (a.pose.bones["LeftUpLeg"].head + a.pose.bones["RightUpLeg"].head) / 2

    def mirror(p):
        d = p - mid
        return mid + d - 2.0 * d.dot(lat) * lat

    worst, rows = 0.0, []
    for pb in a.pose.bones:
        if not pb.name.startswith("Left"):
            continue
        r = a.pose.bones.get("Right" + pb.name[4:])
        if r is None:
            continue
        e = (mirror(pb.head) - r.head).length
        rows.append((e, pb.name[4:]))
        worst = max(worst, e)
    rows.sort(reverse=True)
    print("-" * 56)
    print("СИММЕТРИЯ ПОЗЫ %s: худшее расхождение %.1f мм%s"
          % (note, worst * 1000, "" if worst < 0.002 else "  — СТОРОНЫ РАЗОШЛИСЬ"))
    for e, n in rows[:5]:
        print("   %-16s %.1f мм" % (n, e * 1000))
    print("-" * 56)
    return worst
