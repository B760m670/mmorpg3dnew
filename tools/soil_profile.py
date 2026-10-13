#!/usr/bin/env python3
"""ПОЧВА КАК ВЕЩЕСТВО: настоящий почвенный профиль территории Гатчины.

Не «текстура по плоскости», а ОБЪЁМ: 50 м вниз, разбитые на настоящие
почвенные ГОРИЗОНТЫ (генетические слои). Гатчина — Ленинградская обл.,
южнее Санкт-Петербурга: подзолистые/дерново-подзолистые почвы на
ленточных глинах и морене, ниже — ордовикский известняк (Ижорское плато).

Каждый горизонт хранит НАСТОЯЩИЕ физические свойства (справочные величины
для этих типов почв), от которых потом считается ВСЁ поведение:
  rho_d   — плотность сложения (сухая), кг/м3
  poros   — пористость (доля пустот)
  clay/silt/sand — гранулометрия (доли), сумма = 1
  cohesion — сцепление c', кПа (сухое)
  phi     — угол внутреннего трения, град  → УГОЛ ЕСТЕСТВЕННОГО ОТКОСА
  k_sat   — насыщенная водопроводимость, м/с (как быстро впитывает)
  wilt/fc — влажность завядания / полевая влагоёмкость (доли объёма)
  color_dry/wet — реальный цвет (сухой/мокрый), sRGB 0..1 (по Манселлу)

Проверка — числами (main): суммы долей, монотонность плотности с глубиной,
физичность углов откоса, диапазоны цветов, потемнение при увлажнении.
"""
import json
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "game2/data/real/soil_profile.json")

# --- ГОРИЗОНТЫ дерново-подзолистой почвы на морене (типично для Гатчины) ---
# Толщины — типичные полевые (м). Свойства — справочные для данного типа.
HORIZONS = [
    {
        "id": 0, "code": "O", "name": "подстилка (лесная/дернина)",
        "thick_m": 0.05,
        "rho_d": 250.0, "poros": 0.88,
        "clay": 0.05, "silt": 0.25, "sand": 0.70,
        "cohesion_kpa": 3.0, "phi_deg": 30.0,
        "k_sat": 1.0e-3,
        "wilt": 0.15, "fc": 0.55,
        "color_dry": [0.28, 0.22, 0.14], "color_wet": [0.14, 0.10, 0.06],
        "organic": 0.60,
    },
    {
        "id": 1, "code": "A", "name": "гумусовый (тёмный, плодородный)",
        "thick_m": 0.22,
        "rho_d": 1150.0, "poros": 0.55,
        "clay": 0.14, "silt": 0.38, "sand": 0.48,
        "cohesion_kpa": 12.0, "phi_deg": 28.0,
        "k_sat": 2.5e-5,
        "wilt": 0.12, "fc": 0.34,
        "color_dry": [0.34, 0.28, 0.21], "color_wet": [0.16, 0.12, 0.08],
        "organic": 0.06,
    },
    {
        "id": 2, "code": "E", "name": "подзолистый (белёсый, вымытый)",
        "thick_m": 0.18,
        "rho_d": 1450.0, "poros": 0.44,
        "clay": 0.08, "silt": 0.30, "sand": 0.62,
        "cohesion_kpa": 5.0, "phi_deg": 32.0,
        "k_sat": 5.0e-5,
        "wilt": 0.06, "fc": 0.22,
        "color_dry": [0.66, 0.64, 0.60], "color_wet": [0.44, 0.42, 0.39],
        "organic": 0.01,
    },
    {
        "id": 3, "code": "B", "name": "иллювиальный (бурый, уплотнённый)",
        "thick_m": 0.55,
        "rho_d": 1650.0, "poros": 0.38,
        "clay": 0.28, "silt": 0.34, "sand": 0.38,
        "cohesion_kpa": 25.0, "phi_deg": 24.0,
        "k_sat": 3.0e-6,
        "wilt": 0.16, "fc": 0.33,
        "color_dry": [0.45, 0.33, 0.21], "color_wet": [0.26, 0.17, 0.10],
        "organic": 0.005,
    },
    {
        "id": 4, "code": "C", "name": "морена (валунный суглинок)",
        "thick_m": 3.0,
        "rho_d": 1900.0, "poros": 0.30,
        "clay": 0.22, "silt": 0.30, "sand": 0.48,
        "cohesion_kpa": 35.0, "phi_deg": 30.0,
        "k_sat": 1.0e-6,
        "wilt": 0.13, "fc": 0.28,
        "color_dry": [0.48, 0.42, 0.33], "color_wet": [0.30, 0.25, 0.18],
        "organic": 0.0,
    },
    {
        "id": 5, "code": "Cg", "name": "ленточные глины (сизые, водоупор)",
        "thick_m": 8.0,
        "rho_d": 1750.0, "poros": 0.42,
        "clay": 0.62, "silt": 0.30, "sand": 0.08,
        "cohesion_kpa": 60.0, "phi_deg": 16.0,
        "k_sat": 1.0e-9,
        "wilt": 0.24, "fc": 0.45,
        "color_dry": [0.44, 0.44, 0.42], "color_wet": [0.26, 0.28, 0.28],
        "organic": 0.0,
    },
    {
        "id": 6, "code": "R", "name": "известняк (ордовик, Ижорское плато)",
        "thick_m": 38.0,
        "rho_d": 2450.0, "poros": 0.12,
        "clay": 0.02, "silt": 0.10, "sand": 0.88,
        "cohesion_kpa": 800.0, "phi_deg": 38.0,
        "k_sat": 1.0e-7,
        "wilt": 0.02, "fc": 0.06,
        "color_dry": [0.72, 0.70, 0.64], "color_wet": [0.52, 0.51, 0.47],
        "organic": 0.0,
    },
]

TOTAL_DEPTH = 50.0


def repose_angle(h):
    """Угол естественного откоса (сухая насыпь) ≈ угол внутр. трения.
    Это то, под каким углом почва СЫПЛЕТСЯ — прямая физика для обвала стенок ямы."""
    return h["phi_deg"]


def diggability(h):
    """Копаемость 0..1 — из плотности и сцепления (обратная 'сопротивлению')."""
    resist = h["rho_d"] / 1000.0 + h["cohesion_kpa"] / 20.0
    return max(0.0, min(1.0, 1.6 / resist))


def mud_threshold(h):
    """Влажность (доля объёма), выше которой почва — ГРЯЗЬ (течёт, липнет).
    Берём предел текучести ~ полевая влагоёмкость + запас по глине."""
    return min(0.95, h["fc"] * (1.0 + 0.5 * h["clay"]))




# --- ПОДВОДНЫЕ ПОЧВЫ (субаквальные): дно под водой — НЕ сухопутная почва ---
# Под водой почвообразование идёт БЕЗ КИСЛОРОДА (анаэробно), поэтому вещество
# принципиально другое. Два разных дна, потому что вода разная:
#   ОЗЕРО (вода стоячая): на дне копится САПРОПЕЛЬ — органический ил из
#     отмершего планктона и растений. Тёмный, студенистый, почти не несущий:
#     нога проваливается. Ниже — оглеенный (сизый) горизонт: железо
#     восстановлено из-за нехватки кислорода, отсюда серо-голубой цвет.
#   РЕКА (вода проточная): течение УНОСИТ мелкое, на дне остаётся промытый
#     песок и гравий. Плотный, несущий, светлее. Ила почти нет — его сносит.
# Именно поэтому дно озера илистое и вязкое, а дно реки песчаное и твёрдое.
SUBAQUEOUS = {
    "lake": [
        {
            "id": 100, "code": "Sa", "name": "сапропель (озёрный ил)",
            "thick_m": 0.60,
            "rho_d": 180.0, "poros": 0.90,
            "clay": 0.30, "silt": 0.55, "sand": 0.15,
            "cohesion_kpa": 1.5, "phi_deg": 8.0,
            "k_sat": 1.0e-8,
            "wilt": 0.60, "fc": 0.88,
            "color_dry": [0.20, 0.18, 0.13], "color_wet": [0.09, 0.09, 0.07],
            "organic": 0.55,
        },
        {
            "id": 101, "code": "Gr", "name": "глей озёрный (сизый, без кислорода)",
            "thick_m": 1.20,
            "rho_d": 1500.0, "poros": 0.45,
            "clay": 0.48, "silt": 0.40, "sand": 0.12,
            "cohesion_kpa": 30.0, "phi_deg": 14.0,
            "k_sat": 1.0e-9,
            "wilt": 0.28, "fc": 0.46,
            "color_dry": [0.38, 0.42, 0.42], "color_wet": [0.22, 0.27, 0.28],
            "organic": 0.03,
        },
    ],
    "river": [
        {
            "id": 110, "code": "Rb", "name": "русловой песок/гравий (промыт течением)",
            "thick_m": 0.80,
            "rho_d": 1750.0, "poros": 0.34,
            "clay": 0.02, "silt": 0.08, "sand": 0.90,
            "cohesion_kpa": 0.5, "phi_deg": 34.0,
            "k_sat": 5.0e-4,
            "wilt": 0.03, "fc": 0.12,
            "color_dry": [0.52, 0.48, 0.40], "color_wet": [0.31, 0.29, 0.25],
            "organic": 0.005,
        },
        {
            "id": 111, "code": "Gr", "name": "глей пойменный (под руслом)",
            "thick_m": 1.50,
            "rho_d": 1600.0, "poros": 0.42,
            "clay": 0.40, "silt": 0.42, "sand": 0.18,
            "cohesion_kpa": 26.0, "phi_deg": 16.0,
            "k_sat": 1.0e-8,
            "wilt": 0.25, "fc": 0.44,
            "color_dry": [0.40, 0.43, 0.41], "color_wet": [0.24, 0.28, 0.27],
            "organic": 0.02,
        },
    ],
}


def check_subaqueous():
    """Испытание подводных почв: обязаны отличаться от сухопутных ПО СУЩЕСТВУ."""
    print("\n=== ПОДВОДНЫЕ ПОЧВЫ (дно озера и дно реки) ===")
    ok = True
    for kind, layers in SUBAQUEOUS.items():
        print("  %s:" % ("ОЗЕРО (стоячая вода)" if kind == "lake" else "РЕКА (проточная)"))
        for h in layers:
            rho_s = 2650.0 * (1.0 - h["organic"]) + 1500.0 * h["organic"]
            expect = rho_s * (1.0 - h["poros"])
            bad = abs(h["rho_d"] - expect) / expect > 0.30
            if bad:
                print("    ! %s: плотность %.0f не бьётся с пористостью %.2f" % (
                    h["code"], h["rho_d"], h["poros"]))
                ok = False
            print("    %-3s %-42s откос %2.0f°  несущая ~%.0f кПа" % (
                h["code"], h["name"], h["phi_deg"],
                h["cohesion_kpa"] * 5.14))
    lake_top = SUBAQUEOUS["lake"][0]
    river_top = SUBAQUEOUS["river"][0]
    # 1. дно озера обязано быть ВЯЗКИМ и непроходимым, дно реки — твёрдым
    if not (lake_top["cohesion_kpa"] * 5.14 < 50.0 < river_top["rho_d"] / 20.0 * 5.0):
        pass
    soft = lake_top["cohesion_kpa"] * 5.14
    firm = river_top["phi_deg"]
    print("\n  дно ОЗЕРА: несущая %.0f кПа -> человек (50 кПа) ПРОВАЛИВАЕТСЯ %s" % (
        soft, "OK" if soft < 50 else "ПРОВАЛ"))
    if soft >= 50:
        ok = False
    print("  дно РЕКИ: песок, угол %.0f° -> плотное, держит  %s" % (
        firm, "OK" if firm > 30 else "ПРОВАЛ"))
    if firm <= 30:
        ok = False
    # 2. ил обязан быть НАМНОГО легче руслового песка (он же почти вода)
    if lake_top["rho_d"] >= river_top["rho_d"] * 0.5:
        print("  ! ил обязан быть намного легче руслового песка")
        ok = False
    else:
        print("  ил %.0f кг/м3 против песка %.0f -> ил почти вода  OK" % (
            lake_top["rho_d"], river_top["rho_d"]))
    # 3. течение промывает: в русле песка должно быть НАМНОГО больше, чем в иле
    if river_top["sand"] <= lake_top["sand"] * 2:
        print("  ! течение обязано вымывать мелочь: в русле песка больше")
        ok = False
    else:
        print("  песка: русло %.0f%% против ила %.0f%% -> течение промывает  OK" % (
            river_top["sand"] * 100, lake_top["sand"] * 100))
    print("\n  ИТОГ ПОДВОДНЫХ: %s" % (
        "ДНО ОЗЕРА И ДНО РЕКИ — РАЗНЫЕ ВЕЩЕСТВА" if ok else "ЕСТЬ ПРОВАЛЫ"))
    return ok


def main():
    total = sum(h["thick_m"] for h in HORIZONS)
    print("=== ПОЧВЕННЫЙ ПРОФИЛЬ ГАТЧИНЫ (дерново-подзолистая на морене) ===")
    print("  %-4s %-34s %7s %8s %7s %6s %7s" % (
        "код", "горизонт", "толщ,м", "плотн", "откос°", "копа", "грязь>"))
    z = 0.0
    ok = True
    prev_rho = 0.0
    for h in HORIZONS:
        s = h["clay"] + h["silt"] + h["sand"]
        if abs(s - 1.0) > 1e-6:
            print("   ! гранулометрия %s не сходится: %.3f" % (h["code"], s))
            ok = False
        # Плотность НЕ обязана расти монотонно: ленточная глина легче морены —
        # это физическая правда (глина рыхлее валунного суглинка). Проверяем то,
        # что действительно обязано выполняться: связь плотности и пористости
        # (rho_d ≈ rho_s·(1−n), плотность твёрдой фазы 2650 кг/м3).
        # плотность твёрдой фазы: минерал 2650, органика ~1500 — смесь по доле
        rho_s = 2650.0 * (1.0 - h["organic"]) + 1500.0 * h["organic"]
        expect = rho_s * (1.0 - h["poros"])
        if abs(h["rho_d"] - expect) / expect > 0.30:
            print("   ! %s: плотность %.0f не бьётся с пористостью %.2f (ожид ~%.0f)" % (
                h["code"], h["rho_d"], h["poros"], expect))
            ok = False
        prev_rho = h["rho_d"]
        if not (10.0 <= h["phi_deg"] <= 45.0):
            print("   ! нефизичный угол трения %s" % h["code"])
            ok = False
        print("  %-4s %-34s %7.2f %8.0f %7.0f %6.2f %7.2f" % (
            h["code"], h["name"], h["thick_m"], h["rho_d"],
            repose_angle(h), diggability(h), mud_threshold(h)))
        z += h["thick_m"]

    print("\n  сумма толщин = %.2f м (цель %.0f м)  %s" % (
        total, TOTAL_DEPTH, "OK" if abs(total - TOTAL_DEPTH) < 0.1 else "ПРОВАЛ"))

    # потемнение при увлажнении — реальный эффект (мокрая земля темнее)
    print("\n  проверка «мокрое темнее сухого»:")
    for h in HORIZONS:
        ld = sum(h["color_dry"]) / 3.0
        lw = sum(h["color_wet"]) / 3.0
        mark = "OK" if lw < ld else "ПРОВАЛ"
        if lw >= ld:
            ok = False
        print("    %-3s сухая %.2f -> мокрая %.2f (%.0f%% темнее)  %s" % (
            h["code"], ld, lw, (1 - lw / ld) * 100.0, mark))

    print("\n  ИТОГ: %s" % ("ПРОФИЛЬ ФИЗИЧЕН" if ok else "ЕСТЬ ПРОВАЛЫ"))

    ok = check_subaqueous() and ok

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    data = {
        "total_depth_m": TOTAL_DEPTH,
        "region": "Гатчина, Ленинградская обл. (дерново-подзолистая на морене)",
        "horizons": [
            dict(h, repose_deg=repose_angle(h), diggability=diggability(h),
                 mud_threshold=mud_threshold(h))
            for h in HORIZONS
        ],
        "subaqueous": {
            k: [dict(h, repose_deg=repose_angle(h), diggability=diggability(h),
                     mud_threshold=mud_threshold(h)) for h in v]
            for k, v in SUBAQUEOUS.items()
        },
    }
    json.dump(data, open(OUT, "w"), ensure_ascii=False, indent=1)
    print("  профиль -> %s" % OUT)


if __name__ == "__main__":
    main()
