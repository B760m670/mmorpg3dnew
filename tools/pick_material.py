#!/usr/bin/env python3
"""ВЫБОР МАТЕРИАЛА ГЛАЗАМИ, а не по названию.

ЗАЧЕМ. Первый список я собрал по заголовкам из поиска и ошибся в двух из
четырёх ключевых материалов: «Ground048 — гравий дорожки» оказался корой-мульчой,
а «Travertine001 — камень дворца» оказался ПОЛИРОВАННОЙ плитой для интерьера,
тогда как пудостский камень пористый и выветренный. Имя материала не говорит,
как он выглядит. Смотреть надо на картинку.

ЧТО ДЕЛАЕТ. Спрашивает каталог ambientCG по слову, забирает превью найденных
материалов и складывает их в один лист-контактку с подписями. Дальше выбор
делается взглядом на лист, а не по имени файла.

Запуск: python3 tools/pick_material.py гравий gravel --out /tmp/sheet.png
        python3 tools/pick_material.py "rock rough" --limit 24
"""
import argparse
import io
import json
import os
import urllib.parse
import urllib.request

from PIL import Image, ImageDraw

API = "https://ambientcg.com/api/v2/full_json"
UA = {"User-Agent": "mmorpg3dnew-pick/1.0"}


def get(url, timeout=60):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA),
                                  timeout=timeout).read()


def search(term, limit):
    q = urllib.parse.urlencode({
        "type": "Material", "q": term, "limit": limit,
        "include": "imageData,tagData", "sort": "popular",
    })
    j = json.loads(get("%s?%s" % (API, q)).decode("utf-8"))
    out = []
    for a in j.get("foundAssets", []):
        imgs = a.get("previewImage", {}) or {}
        url = imgs.get("256-PNG") or imgs.get("128-PNG") or imgs.get("512-PNG")
        if url:
            out.append((a.get("assetId"), url, ", ".join(a.get("tags", [])[:6])))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("terms", nargs="+", help="слова для поиска в каталоге")
    ap.add_argument("--limit", type=int, default=12, help="сколько на слово")
    ap.add_argument("--out", default="/tmp/material_sheet.png")
    args = ap.parse_args()

    found = []
    for t in args.terms:
        try:
            res = search(t, args.limit)
        except Exception as e:
            print("поиск «%s» не удался: %s" % (t, e))
            continue
        print("«%s»: %d материалов" % (t, len(res)))
        found.extend(res)

    seen, uniq = set(), []
    for aid, url, tags in found:
        if aid not in seen:
            seen.add(aid)
            uniq.append((aid, url, tags))
    if not uniq:
        print("ничего не найдено")
        return 1

    cell, cols = 232, 6
    rows = (len(uniq) + cols - 1) // cols
    sheet = Image.new("RGB", (cell * cols, (cell + 20) * rows), (22, 22, 24))
    d = ImageDraw.Draw(sheet)
    for i, (aid, url, tags) in enumerate(uniq):
        try:
            im = Image.open(io.BytesIO(get(url, 45))).convert("RGB")
        except Exception:
            continue
        x, y = (i % cols) * cell, (i // cols) * (cell + 20)
        sheet.paste(im.resize((cell, cell), Image.LANCZOS), (x, y + 20))
        d.text((x + 4, y + 5), aid, fill=(235, 235, 235))
    sheet.save(args.out)
    print("лист из %d материалов -> %s" % (len(uniq), args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
