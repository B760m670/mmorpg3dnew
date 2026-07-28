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
import shutil

from PIL import Image

ROOT = os.path.join(os.path.dirname(__file__), "..")
SRC = os.path.join(ROOT, "game2", "assets", "materials")
DST = os.path.join(ROOT, "game2", "assets", "materials_game")

# какая карта чем становится
AS_PNG = ("NormalGL",)
KEEP = ("Color", "NormalGL", "Roughness", "AmbientOcclusion", "Displacement")


def role_of(name):
    for k in KEEP:
        if "_" + k in name:
            return k
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--res", type=int, default=1024)
    ap.add_argument("--quality", type=int, default=92)
    args = ap.parse_args()

    if os.path.isdir(DST):
        shutil.rmtree(DST)
    os.makedirs(DST, exist_ok=True)

    total_src = total_dst = 0
    n_mat = n_map = 0
    print("== СЖАТИЕ МАТЕРИАЛОВ ДЛЯ СБОРКИ ==")
    for mat in sorted(os.listdir(SRC)):
        d = os.path.join(SRC, mat)
        if not os.path.isdir(d) or mat in ("created", "real"):
            continue
        out = os.path.join(DST, mat)
        got = []
        for f in sorted(os.listdir(d)):
            r = role_of(f)
            if r is None:
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
                q = os.path.join(out, "%s.jpg" % r)
                im.save(q, quality=args.quality, optimize=True, subsampling=0)
            total_dst += os.path.getsize(q)
            got.append(r)
            n_map += 1
        if got:
            n_mat += 1
            print("  %-18s %s" % (mat, ", ".join(got)))

    print("\nматериалов %d, карт %d" % (n_mat, n_map))
    print("было %.0f МБ  ->  стало %.1f МБ  (в %.0f раз легче)"
          % (total_src / 1048576, total_dst / 1048576,
             total_src / max(total_dst, 1)))
    print("папка сборки:", DST)


if __name__ == "__main__":
    main()
