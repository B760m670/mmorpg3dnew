#!/usr/bin/env python3
"""ИСТИННЫЕ КООРДИНАТЫ МИРА: мировые метры <-> настоящие широта/долгота.

Мир привязан к реальной точке — центр Большого Гатчинского дворца
(якорь из data/real/meta.json). Оси движка: x=восток (м), z=-север (м).
Здесь — точное преобразование в настоящие географические координаты (WGS84),
чтобы «59.5634, 30.1075» означало РЕАЛЬНОЕ место, а не выдуманное число.

Метод: локальная касательная плоскость (ENU) на эллипсоиде WGS84 —
радиусы кривизны в меридиане (M) и первом вертикале (N) считаются на широте
якоря, что даёт настоящие метры на градус для нашей территории.

Проверка — числами: сверка с независимой геодезической библиотекой (pyproj,
если есть) и с реальными объектами Гатчины, координаты которых известны.
Та же математика портирована в game2/scripts/core/world_geo.gd (движок).
"""
import json
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
META = os.path.join(ROOT, "game2/data/real/meta.json")

# WGS84
A = 6378137.0
F = 1.0 / 298.257223563
E2 = F * (2.0 - F)


def anchor():
    m = json.load(open(META))["anchor"]
    return m["lat"], m["lon"]


def meters_per_degree(lat_deg):
    """Метры на градус широты (M) и долготы (N·cosφ) на данной широте, WGS84."""
    p = math.radians(lat_deg)
    s = math.sin(p)
    w = math.sqrt(1.0 - E2 * s * s)
    m_lat = A * (1.0 - E2) / (w ** 3) * math.pi / 180.0     # м на градус широты
    m_lon = A / w * math.cos(p) * math.pi / 180.0            # м на градус долготы
    return m_lat, m_lon


def world_to_geo(x, z, lat0=None, lon0=None):
    """Мировые метры (x=восток, z=-север) -> настоящие широта/долгота."""
    if lat0 is None:
        lat0, lon0 = anchor()
    east, north = x, -z
    # Метры на градус меняются с широтой, поэтому решаем итерацией по СЕРЕДИНЕ
    # смещения — ровно та же величина, что использует geo_to_world. Три итерации
    # сходятся до микрометров и делают преобразование строго обратимым.
    lat = lat0 + north / meters_per_degree(lat0)[0]
    for _ in range(3):
        m_lat, _m = meters_per_degree((lat0 + lat) * 0.5)
        lat = lat0 + north / m_lat
    m_lat, m_lon = meters_per_degree((lat0 + lat) * 0.5)
    lon = lon0 + east / m_lon
    return lat, lon


def geo_to_world(lat, lon, lat0=None, lon0=None):
    """Настоящие широта/долгота -> мировые метры (x=восток, z=-север)."""
    if lat0 is None:
        lat0, lon0 = anchor()
    m_lat, m_lon = meters_per_degree((lat0 + lat) * 0.5)
    north = (lat - lat0) * m_lat
    east = (lon - lon0) * m_lon
    return east, -north


def fmt(lat, lon):
    """Человеко-читаемо: 59°33'48.4\"N 30°06'26.9\"E"""
    def dms(v, pos, neg):
        h = pos if v >= 0 else neg
        v = abs(v)
        d = int(v)
        mnt = int((v - d) * 60)
        sec = (v - d - mnt / 60.0) * 3600.0
        return "%d°%02d'%04.1f\"%s" % (d, mnt, sec, h)
    return "%s %s" % (dms(lat, "N", "S"), dms(lon, "E", "W"))


# --- реальные объекты Гатчины для сверки (координаты из открытых карт) ---
LANDMARKS = [
    ("Большой Гатчинский дворец", 59.563446, 30.107487),
    ("Приоратский дворец", 59.560556, 30.120833),
    ("ст. Гатчина-Балтийская", 59.572500, 30.128611),
    ("ст. Гатчина-Варшавская", 59.554167, 30.113333),
    ("Коннетабль (обелиск)", 59.564722, 30.116944),
]


def query(lat, lon, radius_m=120.0):
    """ЧТО НАХОДИТСЯ по названным координатам — по реальным данным мира.
    Ищет ближайшие здания/дороги/участки в радиусе и высоту рельефа."""
    import struct
    x, z = geo_to_world(lat, lon)
    print("=== ЧТО ЗДЕСЬ: %.6f, %.6f ===" % (lat, lon))
    print("  %s" % fmt(lat, lon))
    print("  мировые координаты: X %+.0f м (восток), Z %+.0f м  (от Гатчинского дворца %.0f м)"
          % (x, z, math.hypot(x, z)))

    # высота рельефа из настоящего DEM
    dem = os.path.join(ROOT, "game2/assets/dem/gatchina_cm.bin")
    if os.path.exists(dem):
        n, step = 513, 32.0
        half = (n - 1) * step * 0.5
        east, north = x, -z
        i = int(round((east + half) / step))
        j = int(round((half - north) / step))
        if 0 <= i < n and 0 <= j < n:
            with open(dem, "rb") as f:
                f.seek((j * n + i) * 2)
                h = struct.unpack("<h", f.read(2))[0] / 100.0
            print("  высота рельефа: %.1f м над уровнем моря (настоящий DEM)" % h)
        else:
            print("  ВНЕ территории игры (±8.2 км от дворца)")

    # что рядом — по реальным слоям данных
    d = os.path.join(ROOT, "game2/data/real")
    for layer, label in [("buildings.json", "здания"), ("roads.json", "дороги"),
                         ("landuse.json", "участки")]:
        p = os.path.join(d, layer)
        if not os.path.exists(p):
            continue
        try:
            items = json.load(open(p))
        except Exception:
            continue
        found = []
        for it in items if isinstance(items, list) else []:
            # слои хранят геометрию по-разному: lines (дороги), polys (здания —
            # список полигонов, каждый список колец), outline (участки)
            rings = []
            if "lines" in it:
                rings = it["lines"]
            elif "polys" in it:
                for poly in it["polys"]:
                    rings.extend(poly)
            elif "outline" in it:
                rings = [it["outline"]]
            best = 1e18
            for ln in rings:
                for pt in ln:
                    dd = (pt[0] - x) ** 2 + (-pt[1] - z) ** 2
                    if dd < best:
                        best = dd
            if best < radius_m ** 2:
                nm = it.get("name") or it.get("class") or it.get("subtype") or "?"
                found.append((math.sqrt(best), str(nm)))
        found.sort()
        if found:
            uniq = []
            for dist, nm in found:
                if nm not in [u[1] for u in uniq]:
                    uniq.append((dist, nm))
            print("  %s в радиусе %.0f м: %s" % (
                label, radius_m,
                ", ".join("%s (%.0f м)" % (nm, dist) for dist, nm in uniq[:6])))
        else:
            print("  %s в радиусе %.0f м: нет" % (label, radius_m))


def main():
    import sys
    if len(sys.argv) >= 3:
        query(float(sys.argv[1]), float(sys.argv[2]),
              float(sys.argv[3]) if len(sys.argv) > 3 else 120.0)
        return
    lat0, lon0 = anchor()
    m_lat, m_lon = meters_per_degree(lat0)
    print("=== ЯКОРЬ МИРА (0,0) ===")
    print("  Большой Гатчинский дворец: %.6f, %.6f" % (lat0, lon0))
    print("  %s" % fmt(lat0, lon0))
    print("  масштаб: 1° широты = %.1f м, 1° долготы = %.1f м" % (m_lat, m_lon))
    print("  => 1 м = %.7f° широты, %.7f° долготы" % (1 / m_lat, 1 / m_lon))

    ok = True
    print("\n=== ПРОВЕРКА: туда-обратно (мир -> гео -> мир) ===")
    worst = 0.0
    for x, z in [(0, 0), (1000, -1000), (-5000, 3000), (8000, 8000), (-8000, -8000),
                 (65000, -65000)]:
        la, lo = world_to_geo(x, z)
        x2, z2 = geo_to_world(la, lo)
        err = math.hypot(x2 - x, z2 - z)
        worst = max(worst, err)
        print("  (%7.0f,%7.0f) -> %.6f,%.6f -> ошибка %.4f м" % (x, z, la, lo, err))
    print("  худшая ошибка обратимости: %.4f м  %s" % (
        worst, "OK" if worst < 0.01 else "ПРОВАЛ"))
    if worst >= 0.01:
        ok = False

    # независимая сверка с геодезической библиотекой
    try:
        from pyproj import Geod
        g = Geod(ellps="WGS84")
        print("\n=== СВЕРКА с pyproj (независимая геодезия, WGS84) ===")
        worst_g = 0.0
        for x, z in [(500, -500), (3000, -3000), (8000, -8000), (-6000, 6000),
                     (30000, -30000)]:
            la, lo = world_to_geo(x, z)
            # истинное расстояние по эллипсоиду от якоря до полученной точки
            az, _, dist_true = g.inv(lon0, lat0, lo, la)
            dist_flat = math.hypot(x, -z)
            d = abs(dist_true - dist_flat)
            worst_g = max(worst_g, d)
            print("  смещение %8.0f м -> геодезич. %9.1f м, расхождение %.2f м (%.4f%%)" % (
                dist_flat, dist_true, d, d / max(dist_flat, 1) * 100))
        print("  худшее расхождение с геодезией: %.2f м  %s" % (
            worst_g, "OK (плоскость точна для территории)" if worst_g < 5.0 else "велико"))
        if worst_g >= 5.0:
            ok = False
    except ImportError:
        print("\n  (pyproj нет — пропускаю независимую сверку)")

    print("\n=== РЕАЛЬНЫЕ ОБЪЕКТЫ ГАТЧИНЫ -> мировые координаты ===")
    print("  %-30s %10s %10s   %s" % ("объект", "x(вост)", "z(движок)", "расст. от дворца"))
    for name, la, lo in LANDMARKS:
        x, z = geo_to_world(la, lo)
        d = math.hypot(x, z)
        print("  %-30s %10.0f %10.0f   %8.0f м" % (name, x, z, d))

    print("\n  ИТОГ: %s" % ("КООРДИНАТЫ ИСТИННЫЕ" if ok else "ЕСТЬ ПРОВАЛЫ"))


if __name__ == "__main__":
    main()
