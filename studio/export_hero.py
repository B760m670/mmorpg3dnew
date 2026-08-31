#!/usr/bin/env python3
"""ГЕРОЙ В ИГРУ: сборка, ходьба, постановка на землю, вывод в glTF.

ЗАЧЕМ ОТДЕЛЬНЫЙ ФАЙЛ. До сих пор человек существовал только в Блендере: в
`game2/` персонажа нет вовсе. Пока он не в игре, всё сделанное — картинки.
Здесь собирается ровно то, что игра может открыть: один .glb со скелетом,
одеждой и одним циклом ходьбы.

ЦИКЛ, А НЕ ОТРЕЗОК. Из записи вырезается кусок от постановки левой стопы до
следующей постановки левой — тогда клип крутится петлёй.
ИЗМЕРЕНО на записи CMU 07_01: цикл 1.12 с, шаг 1.515 м, скорость 1.35 м/с,
шов петли в среднем 3.4°, худшая кость 12°. Это ходьба взрослого человека
(норма 1.0–1.2 с и 1.2–1.4 м/с) — и это единственная независимая проверка
того, что перенос движения не врёт: числа походки не подгонялись ни под что.

НА МЕСТЕ, А НЕ С ПЕРЕМЕЩЕНИЕМ. Горизонтальный ход из клипа вычитается: пусть
персонажа двигает игра, а анимация только шагает. Так походка сцепляется со
скоростью (шаг ускоряется — значит и ноги), и так проще с физикой и склонами.
Боковое покачивание таза при этом остаётся: оно настоящее.

Запуск:
  LIBGL_ALWAYS_SOFTWARE=1 xvfb-run -a /opt/blender/blender -b -noaudio \
      -P studio/export_hero.py -- --out game2/assets/hero/hero.glb [--nude]
"""
import math
import os
import sys

import bpy
from mathutils import Quaternion, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ground   # noqa: E402
import hero     # noqa: E402
import mocap    # noqa: E402

ASF = os.environ.get("CMU_ASF", "/tmp/claude-live/mocap/07.asf")
AMC = os.environ.get("CMU_AMC", "/tmp/claude-live/mocap/07_01.amc")
STEP = 3          # 120 к/с записи -> 40 к/с клипа
CLIP = "ходьба"


def inplace(arm, f0, f1, root="Hips"):
    """Вычесть из корня равномерный горизонтальный ход за цикл.

    Вычитается именно ПРЯМАЯ между началом и концом цикла, а не всё движение:
    покачивание таза вбок и вверх-вниз — часть настоящей походки, его трогать
    нельзя. Уходит только равномерный проезд вперёд.
    """
    pb = arm.pose.bones[root]
    rest = arm.data.bones[root].matrix_local.to_3x3()
    Wi = arm.matrix_world.to_3x3().inverted()
    pts = {}
    for f in (f0, f1):
        bpy.context.scene.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        pts[f] = arm.evaluated_get(dg).pose.bones[root].head.copy()
    d = pts[f1] - pts[f0]
    d.z = 0.0
    for f in range(f0, f1 + 1):
        bpy.context.scene.frame_set(f)
        w = (f - f0) / max(1, f1 - f0)
        pb.location = pb.location - rest.transposed() @ (Wi @ (d * w))
        pb.keyframe_insert("location", frame=f)
    bpy.context.view_layer.update()
    print("[клип] ход вперёд вычтен: %.3f м за %d кадров" % (d.length, f1 - f0))
    return d.length


def trim(arm, f0, f1, имя=None):
    """Оставить в действии только кадры цикла и подвинуть их к единице."""
    act = arm.animation_data.action
    for fc in list(act.fcurves):
        keep = [kp for kp in fc.keyframe_points if f0 <= kp.co.x <= f1]
        if not keep:
            act.fcurves.remove(fc)
            continue
        vals = [(kp.co.x - f0 + 1, kp.co.y) for kp in keep]
        for _ in range(len(fc.keyframe_points)):
            fc.keyframe_points.remove(fc.keyframe_points[0], fast=True)
        fc.keyframe_points.add(len(vals))
        for kp, (x, y) in zip(fc.keyframe_points, vals):
            kp.co = (x, y)
            kp.interpolation = 'LINEAR'
        fc.update()
    act.name = имя or CLIP
    if hasattr(act, "use_frame_range"):
        act.use_frame_range = True
        act.frame_start = 1
        act.frame_end = f1 - f0 + 1
    sc = bpy.context.scene
    sc.frame_start = 1
    sc.frame_end = f1 - f0 + 1
    print("[клип] обрезан до %d кадров, назван «%s»" % (sc.frame_end, act.name))
    return act


# НАБОР ДВИЖЕНИЙ, А НЕ ОДИН КЛИП.
#
# Заказчик сказал: ходит как манекен. Причин оказалось четыре, и «взять ассеты»
# лечит не все:
#   1. ОДИН клип на всё. Скорость отрабатывалась растяжением времени
#      (speed_scale = v/1.294), и при 0.5 м/с это 0.39x — ЗАМЕДЛЕННАЯ СЪЁМКА
#      шага, а не медленный шаг. У человека медленный шаг это другая поза,
#      другая длина шага и другой мах руки.
#   2. Стойка сделана РУКАМИ (idle.py: наведение костей плюс синус дыхания).
#      Это ровно определение манекена: поза, вычисленная из чисел. Всё
#      остальное в проекте мы берём у живых людей.
#   3. Поворота не было вовсе: тело крутилось целиком под клип прямой ходьбы,
#      и стопы ехали вбок.
#   4. Нет перехода шаг->остановка, переноса веса, движения головы.
#
# КЛИПЫ БЕРУТСЯ У ОДНОГО ЧЕЛОВЕКА. Смешивать записи разных людей можно —
# перенос идёт локальными поворотами, — но смешиваются они плохо: у каждого
# своя манера. Субъект 141 («General Subject Capture», 34 записи) даёт разом
# стойку, шаг, медленный шаг и поворот на месте. Мужской ли он — проверено
# замером скелета: размах ключиц к росту 0.281 при мужской норме 0.26-0.28
# (у субъектов 91 и 143, которые сперва казались подходящими, 0.227 и 0.211,
# то есть женское сложение, и манера движения там женская).
#
# Стойка взята у субъекта 13: у 141 она всего 2.3 с, а дыхание — 4 с на цикл.
# 13_07 стоит 12.1 с и почти не смещается: путь 0.22 м, 0.02 м/с.
# У КАЖДОГО КЛИПА НЕСКОЛЬКО ЗАПИСЕЙ-КАНДИДАТОВ. Не всякая запись поддаётся:
# постановка на землю требует опорных кадров, и на 141_20 их не нашлось вовсе
# («опорных кадров не нашлось — нечем ставить на землю»). Одна негодная запись
# не должна ронять весь набор — берём следующую.
НАБОР = [
    # имя клипа       кандидаты                        род        длина, с
    ("покой",        ["13_07", "79_05", "141_21"],     "стойка",   6.0),
    # 07_01 оставлен последним кандидатом: это проверенная запись, на которой
    # цикл выходит 1.42 м за 1.10 с при шве 2.2°. Если ни одна запись субъекта
    # 141 не даст годного цикла, лучше взять чужого человека, чем остаться без
    # шага вовсе.
    # ТРИ СКОРОСТИ, А НЕ ОДНА РАСТЯНУТАЯ. Ради этого всё и затевалось: клип
    # нельзя «замедлить» — у медленного шага другая длина шага, другая поза и
    # другой мах руки. ИЗМЕРЕНО на вырезанных циклах: 0.38, 1.29 и 1.89 м/с.
    ("шаг",          ["07_01", "141_08", "141_19"],   "цикл",     0.0),
    ("шаг быстро",   ["141_09", "141_22", "141_24"],  "цикл",     0.0),
    # МЕДЛЕННЫЙ ШАГ ВЫБИРАЛСЯ ПО СКОРОСТИ ВСЕЙ ЗАПИСИ, и это подвело: у 141_33
    # запись идёт 0.97 м/с, а вырезанный из неё ЦИКЛ дал 1.26 м/с — человек
    # часть записи стоял, и средняя скорость записи оказалась ниже скорости
    # самого шага. Судить надо по циклу, а не по записи; здесь просто взяты
    # записи, которые медленнее втрое.
    ("шаг медленно", ["141_11", "141_12", "141_20", "141_16"], "цикл",  0.0),
    ("поворот",      ["141_18", "141_14", "141_27"],   "окно",     3.0),
]
ПАПКА = os.environ.get("CMU_DIR", "/tmp/claude-live/mocap")


def _позы(arm, F):
    """Поза каждого кадра как список кватернионов костей."""
    из = []
    for f in F:
        bpy.context.scene.frame_set(f)
        bpy.context.view_layer.update()
        из.append([pb.matrix.to_quaternion() for pb in arm.pose.bones])
    return из


def _разница(a, b):
    """Средний угол между двумя позами, градусы."""
    return sum(math.degrees(x.rotation_difference(y).angle)
               for x, y in zip(a, b)) / max(1, len(a))


def _тише_всего(arm, F, длина_кадров, root="Hips"):
    """Окно спокойной стойки — по ПОЗЕ, а не по неподвижности таза.

    ПЕРВЫЙ ЗАХОД ИСКАЛ ОКНО, ГДЕ МЕНЬШЕ ВСЕГО ГУЛЯЕТ КОРЕНЬ. Ответ вышел
    правдоподобный и негодный: таз гулял на 10 мм, а шов петли получился
    304° при среднем 59°. Причина простая и её стоит запомнить: НЕПОДВИЖНОСТЬ
    КОРНЯ — НЕ НЕПОДВИЖНОСТЬ ТЕЛА. Человек стоит на месте и при этом машет
    руками, чешет затылок, поворачивает голову; таз при этом почти не едет.

    Теперь окно выбирается по двум числам сразу: ШОВ (насколько первый кадр
    похож на последний — от него зависит, можно ли крутить петлёй) и
    ШЕВЕЛЕНИЕ внутри окна (чтобы не взять кусок, где человек застыл истуканом
    — дышать он всё-таки должен). Берём наименьший шов среди окон, где
    шевеление не нулевое.
    """
    поз = _позы(arm, F)
    # ПУТЬ КОРНЯ ПО КАДРАМ — второе обязательное условие. Без него окно
    # выбралось по одной лишь похожести поз, и выбрало кусок ХОДЬБЫ: шаг
    # повторяется, поэтому первый кадр похож на последний, а человек за это
    # окно прошёл 5.8 метра. Стойка — это когда И поза повторяется, И корень
    # стоит.
    корень = []
    for f in F:
        bpy.context.scene.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        корень.append(arm.evaluated_get(dg).pose.bones[root].head.copy())
    n = len(поз)
    if n <= длина_кадров + 2:
        return F[0], F[-1], 0.0
    # шевеление внутри окна — накопленная разница соседних кадров
    шаг = [0.0] + [_разница(поз[i], поз[i + 1]) for i in range(n - 1)]
    сум = [0.0]
    for x in шаг[1:]:
        сум.append(сум[-1] + x)
    best = None
    for i in range(0, n - длина_кадров):
        j = i + длина_кадров
        шов_ = _разница(поз[i], поз[j])
        движ = сум[j] - сум[i]
        if движ < 1.0:                      # застывший кусок: не дышит вовсе
            continue
        окно = корень[i:j + 1]
        c = sum(окно, Vector()) / len(окно)
        разброс = max((p - c).length for p in окно)
        if разброс > 0.25:                  # четверть метра — уже не стойка
            continue
        оценка = шов_
        if best is None or оценка < best[0]:
            best = (оценка, i, j, движ, разброс)
    if best is None:
        return F[0], F[длина_кадров], 0.0
    _, i, j, движ, разброс = best
    print("[клип] окно стойки: шов %.1f°, шевеление за окно %.0f°, "
          "корень гуляет %.0f мм" % (best[0], движ, разброс * 1000))
    return F[i], F[j], разброс


def _больше_всего_поворота(arm, F, длина_кадров, root="Hips"):
    """Окно с наибольшим разворотом корня — это поворот на месте."""
    углы = []
    for f in F:
        bpy.context.scene.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        m = arm.evaluated_get(dg).pose.bones[root].matrix.to_3x3()
        v = m @ Vector((0.0, 0.0, 1.0))
        углы.append(math.atan2(v.x, v.y))
    best, bi = None, 0
    for i in range(0, max(1, len(углы) - длина_кадров)):
        a, b = углы[i], углы[i + длина_кадров - 1]
        d = abs((b - a + math.pi) % (2 * math.pi) - math.pi)
        if best is None or d > best:
            best, bi = d, i
    return F[bi], F[min(len(F) - 1, bi + длина_кадров)], math.degrees(best or 0)


def шов(act, f0, f1):
    """Расхождение первого и последнего кадра ПО КЛЮЧАМ ДЕЙСТВИЯ, градусы.

    ПЕРВЫЙ ЗАХОД ЧИТАЛ ПОЗУ АРМАТУРЫ (pb.matrix на двух кадрах) и врал: на
    цикле шага он давал 114° среднего там, где ground.cycle на том же цикле
    насчитал 2.2°. Числа расходились в полсотни раз, и доверять надо было не
    тому, что новее, а тому, что сходится с независимым замером.
    Здесь берутся сами ключи действия — четыре канала кватерниона на кость, —
    и никакой пересчёт позы в это не вмешивается.
    """
    из = {}
    for fc in act.fcurves:
        if not fc.data_path.endswith("rotation_quaternion"):
            continue
        кость = fc.data_path.split('"')[1] if '"' in fc.data_path else fc.data_path
        пара = из.setdefault(кость, [[0.0] * 4, [0.0] * 4])
        for kp in fc.keyframe_points:
            if abs(kp.co.x - f0) < 0.5:
                пара[0][fc.array_index] = kp.co.y
            if abs(kp.co.x - f1) < 0.5:
                пара[1][fc.array_index] = kp.co.y
    d = []
    for кость, (a, b) in из.items():
        qa, qb = Quaternion(a), Quaternion(b)
        if qa.magnitude < 1e-6 or qb.magnitude < 1e-6:
            continue
        qa.normalize(); qb.normalize()
        d.append(math.degrees(qa.rotation_difference(qb).angle))
    if not d:
        return 0.0, 0.0, ""
    имена = list(из.keys())
    i = max(range(len(d)), key=lambda k: d[k])
    return max(d), sum(d) / len(d), имена[i]


def сделать_клип(body, arm, имя, запись, род, длина, fps=40):
    """Собрать один клип набора и оставить его жить отдельным действием."""
    subj = запись.split("_")[0]
    asf = os.path.join(ПАПКА, "%s.asf" % subj)
    amc = os.path.join(ПАПКА, "%s.amc" % запись)
    if not (os.path.exists(asf) and os.path.exists(amc)):
        print("[клип] «%s»: нет записи %s — пропускаю "
              "(качается tools/fetch_mocap.py)" % (имя, запись))
        return None
    n = mocap.load_cmu(arm, asf, amc, start=1, count=0, step=STEP)
    F = list(range(1, n + 1))
    ground.lock(body, arm, F)
    ground.lock(body, arm, F)
    if род == "цикл":
        c = ground.cycle(body, arm, F)
        if not c:
            print("[клип] «%s»: цикл шага не найден" % имя)
            return None
        f0, f1, dist, dur, _ = c
        # ЦИКЛ НАДО ПРОВЕРИТЬ НА ГОДНОСТЬ, А НЕ ПРОСТО ВЗЯТЬ НАЙДЕННОЕ.
        # Из 141_10 «цикл» вышел в 27 кадров с шагом 58 мм и скоростью
        # 0.09 м/с — это не шаг, а две постановки стопы, случайно попавшие
        # рядом. У человека шаг 0.8-1.8 м за 0.7-1.8 с; всё вне этих границ
        # означает, что искатель зацепился не за то, и надо брать следующую
        # запись, а не подгонять.
        # СУДИМ ПО СКОРОСТИ, А НЕ ПО ДЛИНЕ ШАГА. Первый вариант проверки
        # требовал 0.5-2.2 м за 0.6-1.9 с и отверг годные записи: на 141_32
        # искатель взял ДВА шага подряд — 3.99 м за 2.73 с, что даёт те же
        # 1.46 м/с. Два цикла кольцуются не хуже одного, а вот скорость 0.09
        # или 3 м/с означала бы, что зацепились не за то.
        v = dist / dur if dur else 0.0
        if not (0.2 <= v <= 2.2 and 0.5 <= dist <= 5.0 and 0.5 <= dur <= 3.5):
            print("[клип] «%s» из %s: цикл негоден — %.3f м за %.2f с (%.2f м/с)"
                  % (имя, запись, dist, dur, v))
            return None
        inplace(arm, f0, f1)
        act = trim(arm, f0, f1, имя)
        act["шаг_м"] = dist
        act["скорость"] = dist / dur if dur else 0.0
    else:
        кадров = int(round((длина or 4.0) * fps))
        if род == "стойка":
            f0, f1, разброс = _тише_всего(arm, F, кадров)
            print("[клип] «%s»: окно %d..%d, корень гуляет %.0f мм"
                  % (имя, f0, f1, разброс * 1000))
        else:
            f0, f1, гр = _больше_всего_поворота(arm, F, кадров)
            print("[клип] «%s»: окно %d..%d, разворот %.0f°" % (имя, f0, f1, гр))
        inplace(arm, f0, f1)
        act = trim(arm, f0, f1, имя)
    м, ср, худшая = шов(act, 1, int(act.frame_end))
    # ШОВ ПО КОРНЮ — ОТДЕЛЬНАЯ ПРОВЕРКА ДЛЯ ЦИКЛОВ. У «шага» из 141_29 худшей
    # костью вышли Hips с 97°: цикл был вырезан из записи, где человек шёл ПО
    # ДУГЕ, и за один шаг разворачивался почти на сто градусов. Такой цикл не
    # закольцуешь — на стыке персонажа рвёт. Петля обязана возвращать корпус
    # туда же, откуда он вышел.
    if род == "цикл" and худшая == "Hips" and м > 25.0:
        print("[клип] «%s» из %s: корпус за цикл разворачивается на %.0f° — "
              "запись идёт по дуге, беру следующую" % (имя, запись, м))
        bpy.data.actions.remove(act)
        return None
    act.use_fake_user = True
    print("[клип] «%s»: %d кадров, шов петли %.1f° (средний %.1f°, "
          "худшая кость %s)" % (имя, int(act.frame_end), м, ср, худшая))
    return act


def набор(body, arm):
    """Собрать все клипы набора. Возвращает список действий."""
    из = []
    for имя, кандидаты, род, длина in НАБОР:
        a = None
        for запись in кандидаты:
            try:
                a = сделать_клип(body, arm, имя, запись, род, длина)
            except Exception as e:
                print("[клип] «%s» из %s не вышел: %s" % (имя, запись, str(e)[:70]))
                a = None
            if a is not None:
                break
        if a is not None:
            из.append(a)
        else:
            print("[клип] «%s»: НИ ОДНА запись не подошла" % имя)
    print("[набор] клипов собрано: %d — %s"
          % (len(из), ", ".join("«%s»" % a.name for a in из)))
    return из


IDLE = "покой"
# ДЫХАНИЕ. ИЗМЕРЕНО у взрослых в покое: 12–20 вдохов в минуту; берём 15, то
# есть 4 секунды на вдох-выдох. Ход грудной клетки при спокойном дыхании
# 1–2 см; в кадре через плечо видно верх спины, и полсантиметра подъёма плеч
# читается, а сантиметр уже похож на вздох.
IDLE_BREATH_S = 4.0
IDLE_RISE = 0.005          # на сколько поднимается грудь, м
IDLE_SWAY = 0.004          # боковое качание таза, м — человек не статуя


def idle_clip(arm, fps=40):
    """Отдельный клип СТОЯНИЯ. Без него человек в покое замирает в шаге.

    ЗАЧЕМ ОТДЕЛЬНЫЙ КЛИП, А НЕ «нулевой кадр ходьбы». Нулевой кадр записи —
    это момент постановки стопы: ноги врозь, вес на одной. Остановившийся на
    нём человек выглядит выключенным в полушаге, и это первое, что видно в
    игре. Стойка — отдельное состояние, а не точка внутри шага.

    Поза берётся из studio/idle.py: она построена наведением костей на
    направления (не поворотом на углы, потому что покой у нашей сетки —
    А-поза), решена на левой стороне и отзеркалена на правую, отчего
    расхождение сторон ровно 0.0 мм.
    """
    import idle
    import math as _m
    sc = bpy.context.scene
    n = max(2, int(round(IDLE_BREATH_S * fps)))
    if arm.animation_data is None:
        arm.animation_data_create()
    act = bpy.data.actions.new(IDLE)
    prev = arm.animation_data.action
    arm.animation_data.action = act

    idle.apply_base(arm)
    base_loc = {pb.name: pb.location.copy() for pb in arm.pose.bones}
    base_rot = {pb.name: pb.rotation_quaternion.copy() for pb in arm.pose.bones}

    root = arm.pose.bones.get("Hips")
    chest = arm.pose.bones.get("Spine1") or arm.pose.bones.get("Spine")
    for i in range(n + 1):
        f = 1 + i
        t = (i % n) / float(n)
        # дыхание — один полный цикл на клип; качание вдвое медленнее, чтобы
        # два движения не совпадали по фазе и не читались как один толчок
        br = (1.0 - _m.cos(2.0 * _m.pi * t)) * 0.5
        sw = _m.sin(2.0 * _m.pi * t * 0.5)
        for pb in arm.pose.bones:
            pb.location = base_loc[pb.name].copy()
            pb.rotation_quaternion = base_rot[pb.name].copy()
        if chest is not None:
            chest.location = base_loc[chest.name] + Vector((0.0, IDLE_RISE * br, 0.0))
        if root is not None:
            root.location = base_loc[root.name] + Vector((IDLE_SWAY * sw, 0.0, 0.0))
        for pb in arm.pose.bones:
            pb.keyframe_insert("location", frame=f)
            pb.keyframe_insert("rotation_quaternion", frame=f)
    for fc in act.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = 'LINEAR'
        fc.update()
    if hasattr(act, "use_frame_range"):
        act.use_frame_range = True
        act.frame_start = 1
        act.frame_end = n + 1
    arm.animation_data.action = prev
    # ДЕЙСТВИЕ НАДО УДЕРЖАТЬ ОТ СБОРЩИКА: у действия без пользователей счётчик
    # нулевой, и до экспорта оно не доживёт.
    act.use_fake_user = True
    print("[клип] «%s»: %d кадров, дыхание %.1f с, подъём груди %.0f мм, "
          "качание таза %.0f мм" % (IDLE, n + 1, IDLE_BREATH_S,
                                     IDLE_RISE * 1000, IDLE_SWAY * 1000))
    return act


# ПРЕДЕЛ РАЗМЕРА ТЕКСТУРЫ, в пикселях. Первый вывод весил 80 МБ, из них 46 —
# две карты пальто по 4096². На телефоне такая карта занимает столько же
# видеопамяти, сколько весь остальной герой, а на экране 6.9 дюйма её никто
# не различит. Лицо — исключение: камера через плечо смотрит на затылок и
# щёку вплотную, поэтому коже оставляем 2048.
CAP = [("Jartur", 2048), ("eye", 512), ("eyelash", 256), ("eyebrow", 256),
       ("teeth", 256), ("tongue", 256), ("short02", 1024)]
CAP_DEFAULT = 1024


def shrink():
    """Ужать текстуры до разумного и заставить экспортёр их пережать."""
    было = после = 0
    for im in bpy.data.images:
        # В фоновом Блендере картинка не загружена, пока её не тронешь:
        # has_data лжёт False, size показывает нули. Поэтому сначала reload.
        if im.size[0] == 0:
            try:
                im.reload()
            except Exception:
                pass
        w, h = im.size
        if w == 0:
            continue
        было += w * h
        cap = CAP_DEFAULT
        for key, c in CAP:
            if key.lower() in im.name.lower():
                cap = c
                break
        k = max(w, h) / float(cap)
        if k > 1.0:
            im.scale(max(1, int(w / k)), max(1, int(h / k)))
            print("[текстуры] %-46s %dx%d -> %dx%d"
                  % (im.name[:46], w, h, im.size[0], im.size[1]))
        после += im.size[0] * im.size[1]
    print("[текстуры] пикселей всего: %.1f -> %.1f млн"
          % (было / 1e6, после / 1e6))


def bake_helpers(ob, verbose=True):
    """Выбросить служебную оболочку НАСОВСЕМ, а не прятать её модификатором.

    У тела MakeHuman поверх сетки лежит служебная оболочка, и её скрывает
    модификатор «маска». Модификатор нельзя ни применить к сетке с ключами
    формы, ни оставить: экспорт с применением модификаторов ключи вырезает.
    Выход — удалить эти вершины по-настоящему. Удаление вершин ключи формы
    переживают: Блендер вычёркивает вершину из каждого ключа разом.
    """
    import bmesh
    m = next((x for x in ob.modifiers if x.type == 'MASK'), None)
    if m is None or not m.vertex_group or m.vertex_group not in ob.vertex_groups:
        return 0
    gi = ob.vertex_groups[m.vertex_group].index
    inv = getattr(m, "invert_vertex_group", False)
    kill = []
    for v in ob.data.vertices:
        w = any(g.group == gi and g.weight > 0.0 for g in v.groups)
        keep = (not w) if inv else w
        if not keep:
            kill.append(v.index)
    if kill:
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bm.verts.ensure_lookup_table()
        bmesh.ops.delete(bm, geom=[bm.verts[i] for i in kill], context='VERTS')
        bm.to_mesh(ob.data)
        bm.free()
    ob.modifiers.remove(m)
    if verbose:
        print("[экспорт] %s: служебных вершин удалено %d, осталось %d"
              % (ob.name, len(kill), len(ob.data.vertices)))
    return len(kill)


def bake_shape_basis(ob, keep, verbose=True):
    """Впечь формообразующие ключи в базис, оставить только нужные игре.

    ЗАЧЕМ. Тело MakeHuman собрано ключами формы: пол, возраст, мышцы, все
    measure-*, наши правки подбородка и ушей. В .glb они уезжают как цели
    морфа с постоянными весами — то есть игра обязана каждый кадр держать
    полсотни морфов только для того, чтобы человек оставался собой. Это и
    лишний вес файла, и лишняя работа на телефоне, и ловушка: движок, который
    веса по умолчанию не применит, покажет неподогнанную болванку.

    ПОЧЕМУ НЕЛЬЗЯ ПРОСТО ПОДМЕНИТЬ БАЗИС. Ключ хранит АБСОЛЮТНЫЕ положения, а
    работает разностью «ключ минус базис». Сдвинешь базис — все лицевые ключи
    поедут на ту же величину в обратную сторону. Поэтому дельта прибавляется
    и к базису, И К КАЖДОМУ оставляемому ключу: разность тогда сохраняется.
    """
    sk = ob.data.shape_keys
    if sk is None:
        return 0
    kb = sk.key_blocks
    basis = kb[0]
    n = len(basis.data)
    drop = [k for k in kb[1:] if k.name not in keep]
    if not drop:
        return 0
    delta = [Vector((0.0, 0.0, 0.0)) for _ in range(n)]
    for k in drop:
        v = k.value
        if abs(v) < 1e-6:
            continue
        for i in range(n):
            d = k.data[i].co - basis.data[i].co
            if d.length_squared > 1e-14:
                delta[i] += d * v
    for i in range(n):
        basis.data[i].co = basis.data[i].co + delta[i]
    for k in kb[1:]:
        if k.name in keep:
            for i in range(n):
                k.data[i].co = k.data[i].co + delta[i]
    for k in drop:
        ob.shape_key_remove(k)
    for i, v in enumerate(ob.data.vertices):
        v.co = basis.data[i].co
    if verbose:
        print("[экспорт] %s: впечено в базис %d ключей, осталось %d"
              % (ob.name, len(drop), len(ob.data.shape_keys.key_blocks) - 1))
    return len(drop)


def bake_all_shapes(verbose=True):
    """Оставить в файле только лицевые ключи: мимику и речь."""
    try:
        import face as face_mod
        import importlib
        fs = importlib.import_module("bl_ext.user_default.mpfb.services.faceservice")
        keep = set(fs.ARKIT_FACEUNITS + fs.MICROSOFT_VISEMES + fs.META_VISEMES)
    except Exception as e:
        print("[экспорт] список лицевых не собрался (%s) — ключи не трогаем"
              % str(e)[:50])
        return 0
    total = 0
    for ob in bpy.data.objects:
        if ob.type == 'MESH' and ob.data.shape_keys:
            total += bake_shape_basis(ob, keep, verbose=verbose)
    if verbose:
        print("[экспорт] формообразующих ключей впечено всего: %d" % total)
    return total


def bake_modifiers(verbose=True):
    """Запечь модификаторы ДО экспорта, по-разному для двух видов сеток.

    ПОЧЕМУ НЕ ПОЛАГАТЬСЯ НА ГАЛОЧКУ ЭКСПОРТЁРА. `export_apply` в Блендере
    описан прямым текстом: «WARNING: prevents exporting shape keys», и в коде
    экспортёра стоит «shape keys are not preserved if we apply modifiers».
    То есть с ней все 89 лицевых ключей в .glb не попадут и лицо в игре
    останется неподвижным. А без неё одежда потеряет смещение слоёв и толщину.
    Поэтому: у кого ключей нет (одежда) — модификаторы применяются
    разрушительно; у кого есть (тело, зубы, язык, глаза, брови, ресницы,
    волосы) — маска выпекается удалением вершин, остальное снимается.
    Арматуру не трогаем ни у кого: её экспортёр везёт сам.
    """
    applied = stripped = 0
    for ob in list(bpy.data.objects):
        if ob.type != 'MESH':
            continue
        has_keys = ob.data.shape_keys is not None
        if has_keys:
            bake_helpers(ob, verbose=verbose)
            for m in list(ob.modifiers):
                if m.type == 'ARMATURE':
                    continue
                # остальное к сетке с ключами не применить — снимаем
                if verbose:
                    print("[экспорт] %s: снят модификатор %s (сетка с ключами)"
                          % (ob.name, m.type))
                ob.modifiers.remove(m)
                stripped += 1
            continue
        bpy.context.view_layer.objects.active = ob
        for m in list(ob.modifiers):
            if m.type == 'ARMATURE':
                continue
            # МОДИФИКАТОР, ВЫКЛЮЧЕННЫЙ ВО ВЬЮПОРТЕ, НЕ ПРИМЕНЯЕТСЯ ВОВСЕ:
            # «Modifier is disabled, skipping apply». MPFB вешает на одежду
            # подразделение только для рендера, и в игру одежда уезжала гранёной
            # — пять предметов из пяти. Включаем показ перед применением.
            m.show_viewport = True
            try:
                bpy.ops.object.modifier_apply(modifier=m.name)
                applied += 1
            except Exception as e:
                print("[экспорт] %s: %s не применился (%s)"
                      % (ob.name, m.type, str(e)[:40]))
    if verbose:
        print("[экспорт] модификаторов применено %d, снято %d" % (applied, stripped))
    return applied, stripped


def check_glb(path):
    """Доехали ли ключи формы. Смотрим в сам файл, а не верим экспортёру."""
    import json
    import struct
    with open(path, "rb") as f:
        magic, ver, total = struct.unpack("<III", f.read(12))
        if magic != 0x46546C67:
            print("[проверка] это не glb")
            return None
        ln, kind = struct.unpack("<II", f.read(8))
        js = json.loads(f.read(ln).decode("utf-8"))
    tgt = 0
    named = []
    for me in js.get("meshes", []):
        for p in me.get("primitives", []):
            tgt += len(p.get("targets", []))
        if me.get("extras", {}).get("targetNames"):
            named = me["extras"]["targetNames"]
    print("[проверка] в файле сеток %d, целей морфа %d"
          % (len(js.get("meshes", [])), tgt))
    if named:
        face = [n for n in named if n in ("jawOpen", "eyeBlinkLeft",
                                          "mouthSmileLeft", "viseme_aa")]
        print("[проверка] лицевые на месте: %s"
              % (", ".join(face) if face else "НЕТ НИ ОДНОЙ"))
    return tgt


# ПРОЗРАЧНОСТЬ РАЗДАЁТСЯ ПОИМЕННО, А НЕ ВСЕМ ПОДРЯД.
#
# В игре пальто пропало. В файле оно было — меш на месте, цвет 0.17 записан, —
# а в кадре его не было. Причина нашлась в JSON выведенного файла: У ВСЕХ
# ВОСЕМНАДЦАТИ материалов стоял alphaMode = BLEND, включая кожу, сапоги и
# штаны. Прозрачное смешение не пишет глубину: слои перестают закрывать друг
# друга, порядок отрисовки решается сортировкой по расстоянию и пляшет от угла
# камеры. Одежда тонула в теле, тело в одежде.
#
# ОТКУДА ВЗЯЛОСЬ: у mhmat-файлов почти всегда стоит transparent True и
# alphaToCoverage True — это верно для волос и ресниц, где вырез делается
# альфой, и бессмысленно для сукна. MakeSkin переносит флаг как есть, а
# экспортёр — дальше в файл.
#
# ПРОЗРАЧНОСТЬ НУЖНА РОВНО ТАМ, ГДЕ ФОРМА ЗАДАНА ВЫРЕЗОМ В КАРТИНКЕ: волосы,
# брови, ресницы. Им ставим MASK (порог, глубина пишется), остальным OPAQUE.
ALPHA_MASK = ("short01", "eyebrow", "eyelash", "hair")
# А ВОТ ГЛАЗУ ПРОЗРАЧНОСТЬ НУЖНА НАСТОЯЩАЯ, И ЭТО МОЯ ЖЕ ОШИБКА, ПОЙМАННАЯ
# КРУПНЫМ ПЛАНОМ. У высокополигонального глаза MPFB две оболочки на одном
# материале: само яблоко с радужкой и поверх него роговица. На развёртке
# роговице отведён белый круг в углу картинки, и держится она только альфой.
# Переведя ВСЕ материалы в непрозрачные, я накрыл радужку белым куполом:
# в кадре у человека вместо глаз были плоские голубые миндалины без зрачка.
# Порога тут мало — роговица полупрозрачна по всей площади, а не вырезана.
ALPHA_BLEND = ("high-poly", "cornea")


def fix_alpha(path):
    """Переписать alphaMode в готовом glb. Правится файл, а не Блендер.

    Так честнее: между материалом Блендера и записью в файле стоит экспортёр
    со своими правилами, и проверять надо то, что уехало, а не то, что задано.
    """
    import json
    import struct
    with open(path, "rb") as f:
        data = f.read()
    magic, ver, total = struct.unpack("<III", data[:12])
    if magic != 0x46546C67:
        print("[прозрачность] это не glb")
        return
    ln, kind = struct.unpack("<II", data[12:20])
    js = json.loads(data[20:20 + ln].decode("utf-8"))
    rest = data[20 + ln:]
    было = {}
    for m in js.get("materials", []):
        было[m.get("alphaMode", "OPAQUE")] = было.get(
            m.get("alphaMode", "OPAQUE"), 0) + 1
        name = (m.get("name") or "").lower()
        if any(k in name for k in ALPHA_MASK):
            m["alphaMode"] = "MASK"
            m["alphaCutoff"] = 0.35
        elif any(k in name for k in ALPHA_BLEND):
            m["alphaMode"] = "BLEND"
            m.pop("alphaCutoff", None)
        else:
            m["alphaMode"] = "OPAQUE"
            m.pop("alphaCutoff", None)
    стало = {}
    for m in js.get("materials", []):
        стало[m["alphaMode"]] = стало.get(m["alphaMode"], 0) + 1
    blob = json.dumps(js, ensure_ascii=False).encode("utf-8")
    blob += b" " * ((4 - len(blob) % 4) % 4)
    out = (struct.pack("<III", magic, ver, 12 + 8 + len(blob) + len(rest))
           + struct.pack("<II", len(blob), kind) + blob + rest)
    with open(path, "wb") as f:
        f.write(out)
    print("[прозрачность] было %s -> стало %s"
          % (", ".join("%s %d" % kv for kv in sorted(было.items())),
             ", ".join("%s %d" % kv for kv in sorted(стало.items()))))


def export(path):
    shrink()
    bake_modifiers()
    bake_all_shapes()
    # ПРОВЕРКА, ЧТО ЗАПЕЧЁННОЕ ТЕЛО ОСТАЛОСЬ СОБОЙ. Размер файла этого не
    # доказывает: при ошибке в пересчёте базиса в игру уехала бы неподогнанная
    # болванка MakeHuman, и заметили бы это нескоро. Меряем голову после
    # запекания и сверяем с тем же ANSUR, что и в Блендере.
    try:
        import measure_face as mf
        body = next((o for o in bpy.data.objects
                     if o.type == 'MESH' and o.name.startswith("Human")
                     and len(o.data.vertices) > 5000), None)
        eyes = next((o for o in bpy.data.objects
                     if o.type == 'MESH' and "high-poly" in o.name), None)
        if body is not None:
            # МЕРИТЬ НАДО В ПОКОЕ. Первый заход мерил тело прямо в шаге: рост
            # выходил 1.780 вместо 1.736 (в стойке фигура ниже, чем в
            # середине шага), голова наклонена, подбородок не находился вовсе,
            # уши «выросли» на 15%. Числа были не про запекание, а про позу.
            arms = [o for o in bpy.data.objects if o.type == 'ARMATURE']
            was = [(a, a.data.pose_position) for a in arms]
            for a, _ in was:
                a.data.pose_position = 'REST'
            bpy.context.view_layer.update()
            mf.report(body, eyes, "после запекания, в покое")
            for a, p in was:
                a.data.pose_position = p
            bpy.context.view_layer.update()
    except Exception as e:
        print("[экспорт] обмер после запекания не снялся: %s" % str(e)[:60])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.export_scene.gltf(
        filepath=path, export_format='GLB', use_selection=True,
        export_animations=True, export_frame_range=True,
        export_animation_mode='ACTIONS', export_skins=True,
        # export_apply ВЫКЛЮЧЕН НАМЕРЕННО: он вырезает все ключи формы, то есть
        # всю мимику и речь. Модификаторы уже запечены выше, каждый по-своему.
        export_apply=False, export_yup=True,
        export_morph=True, export_morph_normal=False,
        export_image_format='AUTO', export_jpeg_quality=88,
    )
    fix_alpha(path)
    mb = os.path.getsize(path) / 1048576.0
    print("[вывод] %s — %.1f МБ" % (path, mb))
    check_glb(path)
    return mb


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = argv[argv.index("--out") + 1] if "--out" in argv \
        else "game2/assets/hero/hero.glb"
    body = hero.build(skip_clothes=("--nude" in argv))
    arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')

    # НАБОР КЛИПОВ. Каждый строится своим прогоном записи: перенос движения
    # чистит анимацию арматуры целиком, поэтому клипы делаются по очереди, а
    # готовые удерживаются от сборщика (use_fake_user) — иначе до вывода
    # доживёт только последний.
    клипы = набор(body, arm)
    if not клипы:
        # ЗАПАСНОЙ ПУТЬ: если записей нет (чистая машина, не скачано), собираем
        # как прежде — один цикл ходьбы и рукодельная стойка. Лучше, чем ничего.
        print("[набор] записей нет — собираю по-старому")
        n = mocap.load_cmu(arm, ASF, AMC, start=1, count=0, step=STEP)
        F = list(range(1, n + 1))
        ground.lock(body, arm, F)
        ground.lock(body, arm, F)
        ground.report(body, arm, F, "ПЕРЕД ВЫВОДОМ")
        c = ground.cycle(body, arm, F)
        if not c:
            raise SystemExit("цикл шага не найден")
        f0, f1, dist, dur, seam = c
        inplace(arm, f0, f1)
        trim(arm, f0, f1)
        idle_clip(arm)

    tri = sum(len(o.data.loop_triangles) if o.data.loop_triangles else 0
              for o in bpy.data.objects if o.type == 'MESH')
    if not tri:
        for o in bpy.data.objects:
            if o.type == 'MESH':
                o.data.calc_loop_triangles()
        tri = sum(len(o.data.loop_triangles) for o in bpy.data.objects
                  if o.type == 'MESH')
    print("[герой] треугольников %d, объектов %d, костей %d"
          % (tri, len([o for o in bpy.data.objects if o.type == 'MESH']),
             len(arm.data.bones)))
    mb = export(out)
    if клипы:
        for a in клипы:
            v = a.get("скорость")
            print("[итог] «%-13s» %3d кадров%s"
                  % (a.name, int(a.frame_end),
                     ", шаг %.3f м, %.2f м/с" % (a["шаг_м"], v) if v else ""))
        print("[итог] файл %.1f МБ" % mb)
    else:
        print("[итог] клип «%s»: %.2f с, шаг %.3f м, скорость %.2f м/с, "
              "шов %.1f°, файл %.1f МБ"
              % (CLIP, dur, dist, dist / dur, seam, mb))


if __name__ == "__main__":
    main()
