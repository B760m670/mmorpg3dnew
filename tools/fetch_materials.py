#!/usr/bin/env python3
"""НАСТОЯЩИЕ МАТЕРИАЛЫ — загрузка отсканированных поверхностей (CC0).

ЗАЧЕМ. У нас вся земля — один перекрашенный шум, а здания без текстур вовсе.
Фотореализм начинается не с шейдера, а с ФОТОГРАММЕТРИИ настоящих поверхностей:
так сделаны и RDR2, и The Last of Us. Снять Гатчину самим мы не можем, поэтому
берём отсканированные материалы того же рода из общественного достояния.

ЛИЦЕНЗИЯ (проверено по docs.ambientcg.com/license): все материалы ambientCG —
CC0 1.0, общественное достояние. Указание авторства НЕ требуется, коммерческое
использование без ограничений. Это единственная причина, по которой они здесь:
Megascans, например, взять нельзя — их лицензия привязана к Unreal.

ПРО КАМЕНЬ ДВОРЦА — это не догадка. Фасады Большого Гатчинского дворца
облицованы МЕСТНЫМ камнем: пудостским известковым туфом (травертином) из
Пудости, парицкой плитой и черницким доломитом; кирпичная кладка спрятана под
ними. Поэтому в списке травертин, а не гладкий известняк — это порода с
пористой, изъеденной фактурой, и выглядит она совершенно иначе.

ДОСТУП. Из этого окружения ambientcg.com закрыт сетевой политикой (шлюз
отвечает 403 на CONNECT). Инструмент написан заранее и ждёт, когда домен
добавят в разрешённые. Он честно сообщит, если доступа всё ещё нет.

Запуск:  python3 tools/fetch_materials.py            — проверить доступ и план
         python3 tools/fetch_materials.py --go       — качать
         python3 tools/fetch_materials.py --go --res 1K
"""
import argparse
import io
import json
import os
import sys
import urllib.error
import urllib.request
import zipfile

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(ROOT, "game2", "assets", "materials")
API = "https://ambientcg.com/api/v2/full_json?id=%s&include=downloadData"
DIRECT = "https://ambientcg.com/get?file=%s_%s-PNG.zip"

# Что нужно ИГРЕ, а не «красивое вообще». Слева — для чего это в кадре.
WANTED = [
    # --- камень облицовки дворца: пудостский туф = известковый травертин ---
    ("камень дворца (пудостский туф)",      "Travertine001",       "2K"),
    ("камень дворца, другой скол",          "Travertine004",       "2K"),
    ("камень, крупная пористая порода",     "Rocks025",            "2K"),
    # --- кирпич: стены под облицовкой, служебные постройки, город ---
    ("кирпич старый",                       "Bricks038",           "2K"),
    ("кирпич выветренный",                  "Bricks058",           "2K"),
    ("кирпич кладка крупная",               "Bricks085",           "1K"),
    ("кирпич городской",                   "Bricks090",           "1K"),
    # --- штукатурка: флигели, город, ограды ---
    ("штукатурка облупленная",              "Plaster001",          "2K"),
    ("штукатурка гладкая",                  "Plaster003",          "1K"),
    # --- мощение: дворы, площадь перед дворцом ---
    ("брусчатка",                           "PavingStones081",     "2K"),
    # --- ЗЕМЛЯ ПОД НОГАМИ: самое важное, игрок смотрит на неё всегда ---
    ("лесная земля (фотограмметрия)",       "Ground024",           "2K"),
    ("утоптанная земля",                    "Ground037",           "2K"),
    ("грунт с камешками",                   "Ground023",           "2K"),
    ("сухая земля",                         "Ground026",           "1K"),
    ("грязь/ил",                            "Ground030",           "2K"),
    ("гравий дорожки",                      "Ground048",           "2K"),
    # --- покров ---
    ("мох",                                 "Moss001",             "2K"),
    ("трава густая",                        "Grass001",            "2K"),
    ("трава пятном",                        "Grass002",            "1K"),
    ("трава луговая",                       "Grass004",            "2K"),
    # --- дерево ---
    ("кора дерева",                         "Bark001",             "2K"),
]

UA = {"User-Agent": "mmorpg3dnew-asset-fetch/1.0"}


def get(url, timeout=60):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def check_access():
    """Честная проверка: пускает сеть или нет. Без неё непонятно, что чинить."""
    try:
        get("https://ambientcg.com/api/v2/full_json?id=Travertine001", timeout=25)
        return True, "доступ есть"
    except urllib.error.HTTPError as e:
        return False, "сервер ответил HTTP %d" % e.code
    except Exception as e:
        return False, "сеть закрыта (%s)" % type(e).__name__


def resolve(asset_id, res):
    """Ссылка на архив: сначала через каталог, потом прямым именем файла."""
    try:
        j = json.loads(get(API % asset_id, timeout=40).decode("utf-8"))
        for a in j.get("foundAssets", []):
            for fmt, entries in (a.get("downloadFolders", {})
                                 .get("default", {})
                                 .get("downloadFiletypeCategories", {}).items()):
                for f in entries.get("downloads", []):
                    name = f.get("fileName", "")
                    if res in name and name.endswith("-PNG.zip"):
                        return f.get("downloadLink"), name
    except Exception:
        pass
    return DIRECT % (asset_id, res), "%s_%s-PNG.zip" % (asset_id, res)


MAP_ROLE = {
    "_Color": "цвет", "_NormalGL": "нормаль", "_Roughness": "шероховатость",
    "_Displacement": "высота", "_AmbientOcclusion": "затенение",
    "_Metalness": "металл", "_Opacity": "прозрачность",
}


def unpack(blob, asset_id, dest):
    got = {}
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for n in z.namelist():
            if not n.lower().endswith((".png", ".jpg")):
                continue
            role = None
            for key, rus in MAP_ROLE.items():
                if key in n:
                    role = rus
                    break
            if role is None:
                continue
            os.makedirs(dest, exist_ok=True)
            data = z.read(n)
            p = os.path.join(dest, os.path.basename(n))
            with open(p, "wb") as f:
                f.write(data)
            got[role] = len(data)
    return got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--go", action="store_true", help="качать, а не только показать план")
    ap.add_argument("--res", default=None, help="переопределить разрешение (1K/2K/4K)")
    args = ap.parse_args()

    ok, why = check_access()
    print("== НАСТОЯЩИЕ МАТЕРИАЛЫ (CC0, ambientCG) ==")
    print("доступ к ambientcg.com:", why)
    print("в списке %d материалов" % len(WANTED))
    if not ok:
        print("\nСеть окружения закрывает этот домен. Инструмент готов и ждёт:")
        print("нужно разрешить ambientcg.com (и acg-download.struffelproductions.com)")
        print("в сетевой политике окружения, после чего запустить с --go.")
        for role, aid, res in WANTED:
            print("   %-34s %-22s %s" % (role, aid, args.res or res))
        return 1
    if not args.go:
        print("это только план; чтобы качать — добавь --go")
        return 0

    os.makedirs(OUT, exist_ok=True)
    total = 0
    bad = []
    for role, aid, res in WANTED:
        r = args.res or res
        url, name = resolve(aid, r)
        try:
            blob = get(url, timeout=180)
        except Exception as e:
            bad.append((aid, str(e)))
            print("  ! %-34s %-16s НЕ СКАЧАЛСЯ (%s)" % (role, aid, type(e).__name__))
            continue
        try:
            got = unpack(blob, aid, os.path.join(OUT, aid))
        except zipfile.BadZipFile:
            bad.append((aid, "архив битый"))
            print("  ! %-34s %-16s архив битый (%d байт)" % (role, aid, len(blob)))
            continue
        total += len(blob)
        print("  %-34s %-16s %-4s карты: %s"
              % (role, aid, r, ", ".join(sorted(got)) or "НЕТ КАРТ"))
    print("\nскачано %.1f МБ в %s" % (total / 1048576.0, OUT))
    if bad:
        print("не получилось: %d — %s" % (len(bad), ", ".join(a for a, _ in bad)))
    return 0 if not bad else 2


if __name__ == "__main__":
    sys.exit(main())
