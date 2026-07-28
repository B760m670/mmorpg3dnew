#!/usr/bin/env python3
"""СЖАТИЕ МАТЕРИАЛОВ ДЛЯ СБОРКИ — то, что реально едет на телефон.

ЗАЧЕМ. Скачанная библиотека 2K-PNG весит ~900 МБ. Я исключил её из
репозитория, и сборка для iPhone осталась БЕЗ текстур земли: шейдер получил
пустые сэмплеры, а пустой сэмплер в Godot белый — земля стала белой. Ошибка
моя, и урок простой: если ассет нужен игре, он обязан быть В РЕПОЗИТОРИИ.

ЧТО ДЕЛАЕМ. Кладём в репозиторий не исходники, а рабочую версию:
  - 1024x1024 вместо 2048: на телефоне земля тайлится каждые ~2 м, и 1K на
    таком масштабе неотличим от 2K, а памяти видеокарты ест вчетверо меньше
    (2K RGBA8 = 16 МБ на карту, 1K = 4 МБ);
  - цвет/шероховатость/затенение/высота — JPEG q92: это данные без резких
    краёв, артефактов сжатия на них не видно;
  - НОРМАЛЬ — PNG: в ней закодировано направление, и потери JPEG дают на
    свету рябь. Единственная карта, на которой экономить нельзя.

Итог порядка 40-60 МБ на всю библиотеку — это в репозиторий помещается.

Запуск: python3 tools/pack_materials.py [--res 1024] [--quality 92]
"""
import argparse
import os
import re
import shutil

import numpy as np
from PIL import Image

ROOT = os.path.join(os.path.dirname(__file__), "..")
SRC = os.path.join(ROOT, "game2", "assets", "materials")
DST = os.path.join(ROOT, "game2", "assets", "materials_game")

# какая карта чем становится
AS_PNG = ("NormalGL",)
KEEP = ("Color", "NormalGL", "Roughness", "AmbientOcclusion", "Displacement")

# --- КАЛИБРОВКА АЛЬБЕДО ---
# ЗАЧЕМ. Альбедо — доля отражённого света, величина ИЗМЕРИМАЯ. Фотоснимок ею не
# является: у него нормализованная выдержка, и как альбедо он почти всегда
# завышен. ИЗМЕРЕНО на нашей основной текстуре: яркость 0.298 — это альбедо
# СУХОГО ПЕСКА (0.30-0.40), а не травы по земле (0.18-0.25). Отсюда и жалоба
# «днём земля белеет, как будто отражает солнце»: она буквально отражала
# столько, сколько отражает песок.
#
# Справочные значения (доля отражённого света):
#   влажная почва        0.05-0.10      зелёная трава     0.18-0.25
#   сухая тёмная почва   0.10-0.15      сухая трава       0.25-0.30
#   сухая светлая почва  0.15-0.25      песок сухой       0.30-0.40
#
# Приводим яркость каждой текстуры к её настоящему значению, СОХРАНЯЯ оттенок:
# множитель один на все каналы, цвет снимка не выдумывается.
ALBEDO_TARGET = {
    "Ground037": 0.21,   # трава по влажной земле, июнь
    "Ground023": 0.13,   # сухая бурая земля с листвой
    "Ground024": 0.09,   # сырая лесная подстилка со мхом
    "Ground020": 0.10,
    "Ground030": 0.18,
    "Ground062S": 0.20,  # песчано-гравийная дорожка
    "Moss001": 0.12,
    "Bricks038": 0.18, "Bricks084": 0.28, "Bricks090": 0.18,
    "Bricks085": 0.18, "Bricks100": 0.26,
    "PavingStones138": 0.22, "PavingStones139": 0.20,
    "Rock046L": 0.18, "Rock064": 0.16, "Rocks025": 0.18,
    "PaintedPlaster006": 0.30, "PaintedPlaster018": 0.30, "Concrete040": 0.25,
}


def to_linear(a):
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)


def to_srgb(a):
    return np.where(a <= 0.0031308, a * 12.92, 1.055 * np.power(a, 1 / 2.4) - 0.055)


def calibrate(im, target):
    """Привести альбедо к измеренному значению, не трогая оттенок."""
    a = np.asarray(im, np.float32) / 255.0
    lin = to_linear(a)
    lum = 0.2126 * lin[..., 0] + 0.7152 * lin[..., 1] + 0.0722 * lin[..., 2]
    cur = float(lum.mean())
    if cur <= 1e-6:
        return im, cur, cur
    k = target / cur
    out = np.clip(to_srgb(np.clip(lin * k, 0.0, 1.0)) * 255.0, 0, 255)
    return Image.fromarray(out.astype(np.uint8)), cur, target


def role_of(name):
    for k in KEEP:
        if "_" + k in name:
            return k
    return None


def used_by_game():
    """Что игра ДЕЙСТВИТЕЛЬНО просит — вычитано из кода, а не из списка.

    ЗАЧЕМ. Сначала я положил в сборку всю библиотеку: 24 материала, 120 карт,
    85 МБ. Игра при этом обращалась к СЕМИ файлам. Остальные 113 ехали к
    пользователю на телефон впустую и удлиняли каждую переустановку — а
    переустановка тут полная, у неподписанных IPA частичных обновлений нет.

    Список составляется разбором исходников: ищем строки вида
    "Ground037/NormalGL.png" рядом с путём materials_game. Тогда он не может
    разойтись с кодом — добавил материал в шейдер, он сам попал в сборку.
    """
    pat = re.compile(r'"([A-Za-z0-9_]+)/([A-Za-z]+)\.(?:jpg|png)"')
    used = {}
    for root, _, files in os.walk(os.path.join(ROOT, "game2")):
        for f in files:
            if not f.endswith((".gd", ".gdshader")):
                continue
            p = os.path.join(root, f)
            try:
                txt = open(p, encoding="utf-8").read()
            except Exception:
                continue
            if "materials_game" not in txt:
                continue
            for mat, role in pat.findall(txt):
                used.setdefault(mat, set()).add(role)
    return used


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--res", type=int, default=1024)
    ap.add_argument("--quality", type=int, default=92)
    args = ap.parse_args()

    if os.path.isdir(DST):
        shutil.rmtree(DST)
    os.makedirs(DST, exist_ok=True)

    used = used_by_game()
    total_src = total_dst = 0
    n_mat = n_map = 0
    print("== СЖАТИЕ МАТЕРИАЛОВ ДЛЯ СБОРКИ ==")
    print("код просит %d материалов, %d карт (остальное в сборку НЕ едет)"
          % (len(used), sum(len(v) for v in used.values())))
    for mat in sorted(os.listdir(SRC)):
        d = os.path.join(SRC, mat)
        if not os.path.isdir(d) or mat in ("created", "real"):
            continue
        if mat not in used:
            continue
        out = os.path.join(DST, mat)
        got = []
        note = []
        for f in sorted(os.listdir(d)):
            r = role_of(f)
            if r is None or r not in used[mat]:
                continue
            p = os.path.join(d, f)
            total_src += os.path.getsize(p)
            im = Image.open(p)
            if im.size[0] > args.res:
                im = im.resize((args.res, args.res), Image.LANCZOS)
            os.makedirs(out, exist_ok=True)
            if r in AS_PNG:
                im = im.convert("RGB")
                q = os.path.join(out, "%s.png" % r)
                im.save(q, optimize=True)
            else:
                # цвет в RGB, служебные карты в градациях серого — вчетверо легче
                im = im.convert("RGB" if r == "Color" else "L")
                if r == "Color" and mat in ALBEDO_TARGET:
                    im, was, now = calibrate(im, ALBEDO_TARGET[mat])
                    note.append("альбедо %.3f -> %.3f" % (was, now))
                q = os.path.join(out, "%s.jpg" % r)
                im.save(q, quality=args.quality, optimize=True, subsampling=0)
            total_dst += os.path.getsize(q)
            got.append(r)
            n_map += 1
        if got:
            n_mat += 1
            print("  %-18s %-46s %s" % (mat, ", ".join(got), "; ".join(note)))

    print("\nматериалов %d, карт %d" % (n_mat, n_map))
    print("было %.0f МБ  ->  стало %.1f МБ  (в %.0f раз легче)"
          % (total_src / 1048576, total_dst / 1048576,
             total_src / max(total_dst, 1)))
    print("папка сборки:", DST)


if __name__ == "__main__":
    main()
