#!/usr/bin/env python3
"""НАСТОЯЩИЕ МАТЕРИАЛЫ: скачать сканы вместо того, чтобы рисовать их формулами.

ЗАЧЕМ. Ткань я до этого делал процедурно: волна для саржи, шум для ворса. Это
похоже на ткань ровно настолько, насколько формула похожа на нитку. Настоящее
сукно — это фотограмметрический скан: карта цвета с неровностями крашения,
карта нормалей с каждой ниткой переплетения, карта шероховатости, где ворс
блестит иначе, чем впадины между нитями. Такое не пишется формулой.

ОТКУДА. ambientCG (ранее CC0Textures) — библиотека сканов под лицензией CC0,
то есть без ограничений вообще, включая коммерческие. Каталог живой и
доступен: проверено запросом к api/v2.

ЧТО ИМЕННО ВЗЯТО И ПОЧЕМУ. Выбирал по превью, а не по названию:
  Fabric039 — плотное тёмное сукно. Пальто и картуз: у городского обывателя
    Гатчины 1894 года это валяная шерсть глухого тёмного тона.
  Fabric030 — серая шерсть погрубее. Штаны.
  Fabric066 — небелёный холст. Косоворотка: из-под воротника виден только
    край, но именно он отделяет шею от черноты выреза.
  Leather027 — чёрная кожа мелкой мереи с блеском. Сапоги ваксёные, и в кадре
    от сукна их отличает именно блеск, а не цвет: обе поверхности почти чёрные.
  Leather029 — мелкое зерно. Идёт НЕ как кожа обуви, а как микрорельеф КОЖИ
    ЧЕЛОВЕКА: сканов человеческой кожи под CC0 нет, но пора нужного размера
    берётся отсюда — только карта нормалей, без цвета.

ПОЧЕМУ ФАЙЛЫ НЕ ЛЕЖАТ В РЕПОЗИТОРИИ. Пять наборов по 1K — это около 85 МБ
картинок. Держать их в истории git незачем: они не наши и не меняются. Здесь
скачивание по идентификатору, воспроизводимое и с записанной лицензией.
Для игры их ещё предстоит ужать: 85 МБ на телефон не поедут.

Запуск:  python3 studio/fetch_materials.py [--dir КУДА]
"""
import argparse
import os
import sys
import urllib.request
import zipfile

# идентификатор -> зачем он нам
WANTED = {
    "Fabric039": "сукно пальто и картуза",
    "Fabric030": "шерсть штанов",
    "Fabric066": "холст косоворотки",
    "Leather027": "кожа сапог, ваксёная",
    "Leather029": "зерно кожи человека (только нормаль)",
}
RES = "1K-PNG"
URL = "https://ambientcg.com/get?file=%s_%s.zip"
DEFAULT_DIR = os.environ.get("MAT_DIR", "/tmp/claude-live/mat")

# Карты, которые нас интересуют. Displacement не берём: на телефоне тесселяции
# не будет, а рельеф несёт карта нормалей.
MAPS = ("Color", "NormalGL", "Roughness", "AmbientOcclusion")


def path_of(root, asset, kind):
    return os.path.join(root, asset, "%s_%s_%s.png" % (asset, RES, kind))


def fetch(root=DEFAULT_DIR, force=False):
    os.makedirs(root, exist_ok=True)
    for asset, why in WANTED.items():
        d = os.path.join(root, asset)
        color = path_of(root, asset, "Color")
        if os.path.exists(color) and not force:
            print("[материал] %-11s уже есть — %s" % (asset, why))
            continue
        z = os.path.join(root, asset + ".zip")
        print("[материал] %-11s качаю (%s)" % (asset, why))
        urllib.request.urlretrieve(URL % (asset, RES), z)
        os.makedirs(d, exist_ok=True)
        with zipfile.ZipFile(z) as f:
            f.extractall(d)
        os.remove(z)
        have = [m for m in MAPS if os.path.exists(path_of(root, asset, m))]
        print("           карты: %s" % ", ".join(have))
    with open(os.path.join(root, "ЛИЦЕНЗИЯ.txt"), "w") as f:
        f.write("Материалы взяты с ambientCG (ambientcg.com), лицензия CC0.\n"
                "CC0 — общественное достояние: использование, изменение и\n"
                "распространение без ограничений, в том числе коммерческое,\n"
                "указание авторства не требуется.\n\n")
        for a, why in WANTED.items():
            f.write("%-12s %s\n" % (a, why))
    print("[материал] всё на месте:", root)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=DEFAULT_DIR)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    fetch(a.dir, a.force)
    sys.exit(0)
