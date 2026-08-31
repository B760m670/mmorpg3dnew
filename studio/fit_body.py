#!/usr/bin/env python3
"""ПОДГОНКА ФИГУРЫ ПО ПРОМЕРАМ. Не на глаз и не ползунками наугад.

ЧТО ЗДЕСЬ ПРОИСХОДИТ. У MakeHuman, кроме крупных ползунков (пол, возраст,
мышцы, вес), есть отдельный набор целей ИМЕННО ДЛЯ ПРОМЕРОВ: обхват груди,
талии, бедра, голени, шеи, ширина плеч, длина плеча и предплечья. Они так и
называются — measure-*. То есть инструмент для того, что нам нужно, уже
существует; надо только знать, к какому числу вести.

К КАКОМУ ЧИСЛУ ВЕСТИ — берётся из ANSUR II (4082 мужчины), см.
studio/measure_body.py. Подгонка — обычный секущий поиск: поставили значение,
померили, посчитали промах, сдвинули. Три-четыре шага на промер, два прохода
по всем промерам, потому что промеры связаны: расширишь плечи — изменится
обхват груди.

ДЛИНА РУКИ ПРОВЕРЯЕТСЯ ОСОБЫМ СПОСОБОМ, и это важно. Сравнивать нашу кость
«плечо» с ANSUR-овским промером «акромион-радиале» нельзя: у нас это сустав
внутри тела, у них костный выступ на поверхности, разница около четырёх
сантиметров, и она даёт постоянный ложный промах в четверть. Поэтому берётся
признак, который не зависит от определений: У СТОЯЩЕГО ЧЕЛОВЕКА ЗАПЯСТЬЕ
ПРИХОДИТСЯ РОВНО НА ВЫСОТУ ПРОМЕЖНОСТИ. В ANSUR это 848 и 846 мм — разница
0.3%. Значит длина руки от сустава плеча до запястья обязана равняться
разнице высот плеча и промежности, померенных на НАШЕМ же теле.
"""
import importlib

import bpy

ADDON = "bl_ext.user_default.mpfb"

# промер -> имя пары целей MakeHuman
FIT = {
    # ВЕДЁМ ПО МЯСУ, А НЕ ПО КОСТИ. Ширина между суставами сошлась в −1.2%, а
    # в кадре плечи всё равно «широкие и растянутые»: поверх скелета лежат
    # дельты, и глаз видит именно их. Бидельтоидная ширина была у меня в
    # справочных — потому что в позе покоя руки разведены и мерить нельзя. В
    # нейтральной стойке руки висят, и мерить можно.
    "плечи по мясу":    "measure-shoulder-dist",
    "обхват груди":     "measure-bust-circ",
    "обхват талии":     "measure-waist-circ",
    "обхват бедра":     "measure-thigh-circ",
    "обхват таза":      "measure-hips-circ",
    "обхват голени":    "measure-calf-circ",
    # ШЕЯ ТЯНЕТ ЗА ДВА ПОЛЗУНКА СРАЗУ. Одной цели measure-neck-circ не
    # хватило: она упёрлась в предел −1.0, а обхват остался на 15% больше
    # человеческого. Поэтому к ней добавлено сжатие шеи по ширине и глубине —
    # это не обход ограничения, а разные оси одного и того же.
    "обхват шеи":       "measure-neck-circ",
    "длина руки":       ("measure-upperarm-length", "measure-lowerarm-length"),
}
LIMIT = 1.0        # дальше цели MakeHuman начинают ломать форму
STEPS = 4


def _svc(name):
    return importlib.import_module("%s.services.%s" % (ADDON, name))


def _apply(body, base, value):
    """Поставить парную цель: >0 — увеличить, <0 — уменьшить."""
    TargetService = _svc("targetservice").TargetService
    for suffix, v in (("-incr", max(0.0, value)), ("-decr", max(0.0, -value))):
        name = base + suffix
        if not TargetService.has_target(body, name):
            if v <= 0.0:
                continue
            TargetService.bulk_load_targets(body, [{"target": name, "value": v}])
        else:
            TargetService.set_target_value(body, name, v)
    bpy.context.view_layer.update()


def arm_goal(m):
    """Куда вести длину руки: запястье на высоте промежности."""
    if m.get("высота плеча") is None or m.get("высота промежн.") is None:
        return None
    return m["высота плеча"] - m["высота промежн."]


def fit(body, arm, passes=3, verbose=True, rebuild_rig=None, init=None):
    """Подогнать фигуру. rebuild_rig — как пересобрать скелет между проходами.

    СКЕЛЕТ НЕ СЛЕДУЕТ ЗА ФОРМОЙ, и на этом первый заход подгонки встал.
    Цели MakeHuman двигают сетку через ключи формы, а кости считаются по телу
    ОДИН раз, при постановке скелета. Значит все промеры, снятые с костей —
    ширина плеч, длины плеча и предплечья, высота сустава, — после подгонки
    показывают старое тело. Ползунок плеч уезжал до +0.8, а число стояло на
    364 мм как вкопанное. Поэтому между проходами скелет пересобирается по
    новой форме, и второй проход видит уже правду.
    """
    import measure_body as mb
    state = {k: 0.0 for k in FIT}
    if init:
        state.update({k: v for k, v in init.items() if k in state})

    def measure():
        m = mb.measure(body, arm)
        m["длина руки"] = (m.get("длина плеча", 0.0) +
                           m.get("длина предплечья", 0.0))
        return m

    def goal(m, k):
        if k == "длина руки":
            return arm_goal(m)
        want = mb.TARGET[k][1]
        return want * m["рост"]

    for p in range(passes):
        if p and rebuild_rig is not None:
            arm = rebuild_rig()
            if verbose:
                print("  [проход %d] скелет пересобран по новой форме" % (p + 1))
        for k, base in FIT.items():
            bases = base if isinstance(base, tuple) else (base,)
            m = measure()
            g = goal(m, k)
            if g is None or m.get(k) is None:
                continue
            v0, e0 = state[k], m[k] - g
            if abs(e0) / g < 0.02:
                continue
            v1 = max(-LIMIT, min(LIMIT, v0 + (0.4 if e0 < 0 else -0.4)))
            for _ in range(STEPS):
                for b in bases:
                    _apply(body, b, v1)
                state[k] = v1
                m = measure()
                e1 = m[k] - g
                if abs(e1) / g < 0.015 or abs(v1 - v0) < 1e-3:
                    break
                dv = (v1 - v0)
                de = (e1 - e0)
                if abs(de) < 1e-9:
                    break
                v2 = v1 - e1 * dv / de
                v0, e0 = v1, e1
                v1 = max(-LIMIT, min(LIMIT, v2))
            if verbose:
                print("  %-18s цель %6.0f мм -> %6.0f мм, ползунок %+.2f"
                      % (k, g * 1000, measure()[k] * 1000, state[k]))
    return state
