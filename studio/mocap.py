#!/usr/bin/env python3
"""НАСТОЯЩЕЕ ЧЕЛОВЕЧЕСКОЕ ДВИЖЕНИЕ: разбор захвата CMU и надевание его на героя.

ЗАЧЕМ ЭТО, А НЕ САМОДЕЛЬНАЯ ПОХОДКА. Я уже писал цикл шага руками: фаза от
пройденного пути, размах ведёт скорость, руки противоходом. Он лучше, чем
ничего, но это ВЫДУМАННАЯ походка. Настоящая держится на десятках мелочей,
которых не сочинить: таз чуть проседает на опорной ноге, плечи идут против
таза, голова гасит вертикальную качку, стопа перекатывается с пятки на носок,
и всё это чуть-чуть разное на каждом шаге.

БАЗА КАРНЕГИ-МЕЛЛОН — 2500+ записей движения ЖИВЫХ людей, снятых оптическим
захватом: ходьба, бег, повороты, лестница, переноска груза, работа. Открыта и
доступна (mocap.cs.cmu.edu отвечает 200). Субъект 07 — эталонная ходьба.

ПОЧЕМУ ПРИШЛОСЬ ПИСАТЬ РАЗБОР САМОМУ. CMU раздаёт родной формат VICON:
ASF (скелет) и AMC (кадры углов). Блендер читает BVH, а не их; готовые
BVH-конвертации в сети не достались (codeload отдаёт ошибку). Зато скелет
cmu_mb в MPFB назван КОСТЬ В КОСТЬ по этой базе — 31 имя из 31 совпало. То
есть формат надо только прочитать, а сопоставлять нечего: всё уже сходится.

КАК УСТРОЕН ASF/AMC, коротко и по делу:
  У каждой кости есть НАПРАВЛЕНИЕ в позе покоя, ДЛИНА и AXIS — углы поворота
  её собственной системы координат. AMC на каждом кадре даёт углы поворота
  вокруг осей ЭТОЙ системы, а не мировых.
  Отсюда поворот кости относительно родителя:  L = C · R · C⁻¹,
  где C — матрица из axis, R — матрица из углов кадра.
  Ключевое следствие: в позе покоя R единичная, значит и L единичная, значит
  ВСЕ повороты в ASF отсчитываются от нуля. Это сильно упрощает перенос.

ОСИ. У CMU мир Y-вверх (как в Maya), у Блендера Z-вверх. Поворот на +90° по X.
Без него человек идёт лёжа на спине.

Запуск (внутри Блендера, после сборки героя):
  from mocap import load_cmu; load_cmu(armature, "07.asf", "07_01.amc")
"""
import math
import os
import re

from mathutils import Euler, Matrix, Quaternion, Vector

# ASF-имя -> имя кости в риге cmu_mb. Совпало всё, 31 из 31: рига в MPFB так и
# называется — «CMU MotionBuilder».
BONES = {
    "root": "Hips",
    "lhipjoint": "LHipJoint", "lfemur": "LeftUpLeg", "ltibia": "LeftLeg",
    "lfoot": "LeftFoot", "ltoes": "LeftToeBase",
    "rhipjoint": "RHipJoint", "rfemur": "RightUpLeg", "rtibia": "RightLeg",
    "rfoot": "RightFoot", "rtoes": "RightToeBase",
    "lowerback": "LowerBack", "upperback": "Spine", "thorax": "Spine1",
    "lowerneck": "Neck", "upperneck": "Neck1", "head": "Head",
    "lclavicle": "LeftShoulder", "lhumerus": "LeftArm",
    "lradius": "LeftForeArm", "lwrist": "LeftHand",
    "lhand": "LeftFingerBase", "lfingers": "LeftHandFinger1",
    "lthumb": "LThumb",
    "rclavicle": "RightShoulder", "rhumerus": "RightArm",
    "rradius": "RightForeArm", "rwrist": "RightHand",
    "rhand": "RightFingerBase", "rfingers": "RightHandFinger1",
    "rthumb": "RThumb",
}

# Y-вверх (CMU) -> Z-вверх (Блендер)
CV = Matrix.Rotation(math.radians(90.0), 3, 'X')


def parse_asf(path):
    """Прочитать скелет: направление, длина, ось и степени свободы каждой кости."""
    txt = open(path).read()
    scale = 1.0
    m = re.search(r":units(.*?):", txt, re.S)
    if m:
        u = re.search(r"length\s+([-\d.eE+]+)", m.group(1))
        if u:
            # CMU меряет в единицах по 0.45 дюйма. В метры: /0.45 * 0.0254
            scale = 0.0254 / float(u.group(1))
    bones = {}
    for blk in re.findall(r"begin(.*?)end", txt, re.S):
        nm = re.search(r"name\s+(\S+)", blk)
        if not nm:
            continue
        name = nm.group(1)
        d = re.search(r"direction\s+([-\d.eE+\s]+)", blk)
        ln = re.search(r"length\s+([-\d.eE+]+)", blk)
        ax = re.search(r"axis\s+([-\d.eE+\s]+?)\s+([XYZ]{3})", blk)
        dof = re.findall(r"\b(r[xyz])\b", blk.split("limits")[0]) or []
        bones[name] = {
            "dir": Vector([float(x) for x in d.group(1).split()[:3]]) if d else Vector(),
            "len": float(ln.group(1)) if ln else 0.0,
            "axis": [float(x) for x in ax.group(1).split()[:3]] if ax else [0, 0, 0],
            "order": ax.group(2) if ax else "XYZ",
            "dof": dof,
        }
    bones["root"] = {"dir": Vector(), "len": 0.0, "axis": [0, 0, 0],
                     "order": "XYZ", "dof": ["rx", "ry", "rz"]}
    par = {}
    h = re.search(r":hierarchy(.*?)(?::|$)", txt, re.S)
    if h:
        for line in h.group(1).splitlines():
            w = line.split()
            if len(w) >= 2 and w[0] != "begin" and w[0] != "end":
                for c in w[1:]:
                    par[c] = w[0]
    return bones, par, scale


def parse_amc(path):
    """Прочитать кадры: имя кости -> список углов."""
    frames = []
    cur = None
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#") or line.startswith(":"):
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


def _C(bone):
    e = Euler([math.radians(a) for a in bone["axis"]], bone["order"])
    return e.to_matrix()


def _R(bone, vals):
    """Матрица поворота кадра.

    ЗДЕСЬ БЫЛА ОШИБКА, КОТОРАЯ ПРЯТАЛАСЬ ДВЕ НЕДЕЛИ. Я складывал повороты в
    порядке Rx·Ry·Rz, а в ASF порядок обратный: Rz·Ry·Rx (углы перечислены
    как rx, ry, rz, но применяются к неподвижным осям — сначала X, потом Y,
    потом Z). У субъекта 07 углы корня меньше 6°, и разницы между двумя
    свёртками почти не было — ошибка сидела тихо и портила позу понемногу.
    Видно её стало на записи, содержание которой известно заранее: человек
    СТОИТ. При моём порядке его стопы улетали на 1.75 м вверх при неподвижном
    тазе, при правильном остались на полу (−18..+9 мм). Проверять надо на
    том, чей ответ известен, — иначе неверное и правдоподобное неотличимы.

    Соседняя функция _C всё это время считала ПРАВИЛЬНО, потому что
    пользовалась Эйлером Блендера, где порядок 'XYZ' и означает Rz·Ry·Rx.
    Две функции в одном файле противоречили друг другу.
    """
    if not vals:
        return Matrix.Identity(3)
    e = Euler((0.0, 0.0, 0.0), bone["order"])
    slot = {"rx": 0, "ry": 1, "rz": 2}
    for name, v in zip(bone["dof"] or ["rx", "ry", "rz"], vals):
        e[slot[name]] = math.radians(v)
    return e.to_matrix()


def offset(arm, bone, axis, deg):
    """Добавить ПОСТОЯННЫЙ доворот кости во всех кадрах записи.

    ЗАЧЕМ ЭТО НУЖНО И ПОЧЕМУ ЭТО НЕ ПОДДЕЛКА. Записанный человек стоял так,
    как стоял он: стопы почти вместе, руки прижаты к бокам. Наш герой —
    другой человек, и стойка у него должна быть своя. Сравнение силуэтов с
    фотографией стоящего мужчины дало числа: у него стопы врозь на 0.198
    роста и просвет под рукой 0.055 роста, у нас 0.110 и ноль.
    Постоянный доворот бедра и плеча меняет ИМЕННО стойку, не трогая ни
    покачивания, ни переноса веса, ни дыхания — всё живое из записи остаётся.
    Величина доворота не выдумана, а решена под замеренную цель.
    """
    pb = arm.pose.bones.get(bone)
    if pb is None or arm.animation_data is None:
        return
    q = Quaternion(axis, math.radians(deg))
    act = arm.animation_data.action
    path = pb.path_from_id("rotation_quaternion")
    fcs = [fc for fc in act.fcurves if fc.data_path == path]
    if not fcs:
        return
    by_index = {fc.array_index: fc for fc in fcs}
    frames = sorted({int(round(kp.co.x)) for fc in fcs for kp in fc.keyframe_points})
    for f in frames:
        cur = Quaternion([by_index[i].evaluate(f) if i in by_index else
                          (1.0 if i == 0 else 0.0) for i in range(4)])
        new = cur @ q
        for i in range(4):
            fc = by_index.get(i)
            if fc is None:
                continue
            for kp in fc.keyframe_points:
                if int(round(kp.co.x)) == f:
                    kp.co.y = new[i]
                    kp.handle_left.y = kp.handle_right.y = new[i]
    for fc in fcs:
        fc.update()


# СТОЙКА НАШЕГО ГЕРОЯ, решённая под замеренную цель.
#
# Записанный человек в клипе стояния держал стопы почти вместе (0.110 роста) и
# руки вплотную к телу (просвет ноль). Фотография спокойно стоящего мужчины
# даёт 0.198 и 0.055. Разница видна сразу: узкая стойка читается как «человек
# позирует», а не «человек стоит».
#
# Отведение бедра и плеча подобрано ПО СИЛУЭТУ, а не на глаз: перебором сняты
# зависимости (нога: 26.5 мм разведения стоп на градус; рука: 0.010 роста
# просвета на градус) и решено под цель. ИЗМЕРЕНО после: стопы 0.194 против
# 0.198 у образца, просвет 0.067 против 0.055.
#
# Ось Z — та, что разводит, и это тоже проверено перебором, а не выведено:
# по оси X доворот даёт другое движение (стопы 332 против 402 мм).
STANCE = {"LeftUpLeg": -6.5, "RightUpLeg": 6.5, "LeftArm": 5.5, "RightArm": -5.5}


def stance(arm, k=1.0):
    """Поставить герою его собственную стойку поверх записи."""
    for bone, deg in STANCE.items():
        offset(arm, bone, (0, 0, 1), deg * k)
    print("[стойка] отведение: бедро %.1f°, плечо %.1f°"
          % (STANCE["LeftUpLeg"] * k, STANCE["LeftArm"] * k))


def load_cmu(arm, asf_path, amc_path, start=1, count=0, fps=120, step=1,
             align=True):
    """Надеть запись движения на арматуру.

    ПЕРЕНОС ИДЁТ ЧЕРЕЗ ЛОКАЛЬНЫЙ ПОВОРОТ, а не через мировую матрицу. Мировая
    заставила бы кости встать в чужие места: у записанного человека своя длина
    ног, у нашего своя. Локальный поворот переносит ДВИЖЕНИЕ, оставляя
    пропорции наши, — только поэтому запись чужого тела годится нашему.
    """
    import bpy
    bones, par, scale = parse_asf(asf_path)
    frames = parse_amc(amc_path)
    if count:
        frames = frames[start - 1:start - 1 + count]
    else:
        frames = frames[start - 1:]
    frames = frames[::step]
    print("[захват] %s: костей %d, кадров %d (шаг %d), масштаб %.5f м/ед."
          % (os.path.basename(amc_path), len(bones), len(frames), step, scale))

    missing = [b for b in bones if BONES.get(b) not in arm.data.bones]
    if missing:
        print("[захват] нет в риге: %s" % ", ".join(missing))

    # порядок обхода: родитель раньше ребёнка
    order = []
    seen = set()

    def walk(b):
        if b in seen:
            return
        seen.add(b)
        order.append(b)
        for c, p in par.items():
            if p == b:
                walk(c)
    walk("root")

    # ДВЕ ПОЗЫ ПОКОЯ, И ОНИ РАЗНЫЕ. Это оказалось главной ошибкой переноса.
    #
    # У скелета CMU бедро в покое отклонено от вертикали на 20° наружу
    # (направление 0.342, -0.9397, 0), у нашего рига — на 5.7°. Голень так же.
    # Записанные углы отсчитываются ОТ ЭТОЙ разведённой базы; если применить
    # их к нашей, почти вертикальной, нога приедет не туда — и по-разному на
    # левой и правой, потому что в каждом кадре повороты у ног разные.
    # Замер это и показал: сама запись симметрична (низшая точка левого и
    # правого носка расходится на 3.9 мм, посчитано прямой кинематикой по
    # ASF), а у нас правая подошва вставала на 55 мм выше левой.
    #
    # ЧИНИТСЯ ВЫРАВНИВАНИЕМ БАЗЫ. Для каждой кости берём НАШУ систему
    # координат покоя и доворачиваем её кратчайшим поворотом так, чтобы ось
    # кости смотрела туда же, куда смотрит кость в покое у CMU. Крен (поворот
    # вокруг самой кости) при этом остаётся наш — кратчайший поворот его не
    # трогает. Дальше записанный поворот применяется уже к правильной базе.
    #
    # Ключи в Блендере всё равно отсчитываются от НАШЕЙ позы покоя — иначе
    # сетка поедет от привязки. Поэтому баз две: выровненная участвует в
    # вычислении мировой ориентации, наша собственная — в переводе результата
    # в ключ кости.
    rest = {}      # наша поза покоя: в ней записаны ключи
    base = {}      # выровненная под CMU: в ней считается мировая ориентация
    for asf_n, bl_n in BONES.items():
        bb = arm.data.bones.get(bl_n)
        if not bb:
            continue
        R = bb.matrix_local.to_3x3()
        rest[asf_n] = R
        d = bones.get(asf_n, {}).get("dir", Vector())
        if align and d.length > 1e-6:
            want = (CV @ d.normalized())
            axis = R @ Vector((0.0, 1.0, 0.0))
            base[asf_n] = axis.rotation_difference(want).to_matrix() @ R
        else:
            base[asf_n] = R.copy()
    dev = []
    for asf_n in ("lfemur", "ltibia", "rfemur", "rtibia"):
        if asf_n in rest:
            a = (rest[asf_n] @ Vector((0, 1, 0)))
            b = (base[asf_n] @ Vector((0, 1, 0)))
            dev.append("%s %.1f°" % (asf_n, math.degrees(a.angle(b))))
    if dev:
        print("[захват] база выровнена: %s" % ", ".join(dev))

    arm.animation_data_clear()
    for pb in arm.pose.bones:
        pb.rotation_mode = 'QUATERNION'

    sc = bpy.context.scene
    sc.frame_start = 1
    sc.frame_end = len(frames)
    # запись CMU идёт 120 кадров в секунду; при шаге step получаем fps/step
    sc.render.fps = max(1, int(round(fps / step)))

    for fi, fr in enumerate(frames, start=1):
        A = {}
        for b in order:
            if b not in bones:
                continue
            bd = bones[b]
            vals = fr.get(b, [])
            if b == "root":
                # у корня первые три числа — сдвиг, дальше поворот
                rot = _R(bd, vals[3:6] if len(vals) >= 6 else [])
                A[b] = CV @ rot @ CV.transposed()
            else:
                C = _C(bd)
                L = C @ _R(bd, vals) @ C.transposed()
                A[b] = A.get(par.get(b), Matrix.Identity(3)) @ (CV @ L @ CV.transposed())

        for b in order:
            bl = BONES.get(b)
            if bl is None or bl not in arm.pose.bones or b not in A:
                continue
            pb = arm.pose.bones[bl]
            Rb = rest.get(b)
            if Rb is None:
                continue
            p = par.get(b)
            Gp = A.get(p, Matrix.Identity(3)) @ base.get(p, Matrix.Identity(3)) \
                if p else Matrix.Identity(3)
            Rp = rest.get(p, Matrix.Identity(3)) if p else Matrix.Identity(3)
            Gb = A[b] @ base[b]
            local_pose = Gp.transposed() @ Gb
            local_rest = Rp.transposed() @ Rb
            pb.rotation_quaternion = (local_rest.transposed() @ local_pose).to_quaternion()
            pb.keyframe_insert("rotation_quaternion", frame=fi)

        # сдвиг корня: в метрах и в осях Блендера
        rv = fr.get("root", [])
        if len(rv) >= 3:
            pb = arm.pose.bones[BONES["root"]]
            w = CV @ (Vector(rv[:3]) * scale)
            rest_head = arm.data.bones[BONES["root"]].head_local
            pb.location = arm.data.bones[BONES["root"]].matrix_local.to_3x3().transposed() \
                @ (w - rest_head)
            pb.keyframe_insert("location", frame=fi)

    print("[захват] надето: %d кадров при %d к/с" % (len(frames), sc.render.fps))
    return len(frames)
