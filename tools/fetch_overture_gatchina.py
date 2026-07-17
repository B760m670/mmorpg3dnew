#!/usr/bin/env python3
"""РЕАЛЬНЫЕ векторные данные Гатчины из Overture Maps (S3, разрешённый путь).

Слои: вода (контуры озёр/рек), землепользование (парки/лес), транспорт
(улицы и железные дороги), здания. Якорь мира — Большой Гатчинский дворец,
координаты берутся ИЗ ДАННЫХ (centroid здания дворца), не по памяти.

Выход: game2/data/real/*.json — координаты в метрах от якоря
(x=восток, y=север), полигоны упрощены до 1.5 м.

Запуск: python3 tools/fetch_overture_gatchina.py
"""
import json
import math
import os

import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.fs as pafs
from shapely import wkb as shp_wkb
from shapely.geometry import mapping

RELEASE = "overturemaps-us-west-2/release/2026-06-17.0"
BBOX = (30.02, 59.52, 30.25, 59.62)         # lon_min, lat_min, lon_max, lat_max
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "game2", "data", "real")
M_PER_DEG_LAT = 111320.0
KEEP_RADIUS_M = 6500.0                       # хранить объекты в этом радиусе от якоря

_fs = pafs.S3FileSystem(anonymous=True, region="us-west-2")


def bbox_filter():
    return (pc.field("bbox", "xmin") < BBOX[2]) & (pc.field("bbox", "xmax") > BBOX[0]) \
        & (pc.field("bbox", "ymin") < BBOX[3]) & (pc.field("bbox", "ymax") > BBOX[1])


def load(theme_type, columns, extra_filter=None):
    d = ds.dataset(f"{RELEASE}/{theme_type}/", filesystem=_fs, format="parquet")
    f = bbox_filter()
    if extra_filter is not None:
        f = f & extra_filter
    return d.to_table(filter=f, columns=columns)


class Local:
    """перевод (lon,lat) → метры от якоря"""
    def __init__(self, lat0, lon0):
        self.lat0 = lat0
        self.lon0 = lon0
        self.mlon = M_PER_DEG_LAT * math.cos(math.radians(lat0))

    def xy(self, lon, lat):
        return ((lon - self.lon0) * self.mlon, (lat - self.lat0) * M_PER_DEG_LAT)


def geom_to_local(geom, loc, tol=1.5):
    """shapely-геометрия → списки колец/линий в метрах (упрощённо)"""
    g = geom.simplify(tol / M_PER_DEG_LAT * 1.5)   # допуск в градусах ~ tol метров
    def ring(coords):
        return [[round(x, 1), round(y, 1)] for x, y in
                (loc.xy(lon, lat) for lon, lat in coords)]
    m = mapping(g)
    t = m["type"]
    if t == "Polygon":
        return {"polys": [[ring(r) for r in m["coordinates"]]]}
    if t == "MultiPolygon":
        return {"polys": [[ring(r) for r in poly] for poly in m["coordinates"]]}
    if t == "LineString":
        return {"lines": [ring(m["coordinates"])]}
    if t == "MultiLineString":
        return {"lines": [ring(l) for l in m["coordinates"]]}
    return {}


def near_anchor(geom, loc):
    c = geom.centroid
    x, y = loc.xy(c.x, c.y)
    return math.hypot(x, y) <= KEEP_RADIUS_M


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    # --- 1) ЯКОРЬ: Большой Гатчинский дворец из данных зданий ---
    pal = load("theme=buildings/type=building", ["names", "geometry"],
               pc.field("names", "primary") == "Гатчинский дворец")
    assert pal.num_rows >= 1, "дворец не найден в данных"
    pg = shp_wkb.loads(pal["geometry"][0].as_py())
    c = pg.centroid
    anchor_lat, anchor_lon = c.y, c.x
    loc = Local(anchor_lat, anchor_lon)
    print("ЯКОРЬ (дворец, из данных): %.6f N  %.6f E" % (anchor_lat, anchor_lon))

    # --- 2) ВОДА ---
    t = load("theme=base/type=water", ["subtype", "class", "names", "geometry"])
    water = []
    for i in range(t.num_rows):
        g = shp_wkb.loads(t["geometry"][i].as_py())
        if not near_anchor(g, loc):
            continue
        nm = (t["names"][i].as_py() or {}).get("primary")
        rec = {"name": nm, "class": t["class"][i].as_py(),
               "subtype": t["subtype"][i].as_py()}
        rec.update(geom_to_local(g, loc))
        if rec.get("polys") or rec.get("lines"):
            water.append(rec)
    json.dump(water, open(os.path.join(OUT_DIR, "water.json"), "w"),
              ensure_ascii=False)
    print("вода: %d объектов" % len(water))

    # --- 3) ЗЕМЛЕПОЛЬЗОВАНИЕ (парки/лес/луга) ---
    t = load("theme=base/type=land_use", ["subtype", "class", "names", "geometry"])
    keep_lu = {"park", "forest", "meadow", "grass", "cemetery", "recreation_ground",
               "garden", "wood", "farmland", "orchard", "military", "residential"}
    landuse = []
    for i in range(t.num_rows):
        cl = t["class"][i].as_py()
        if cl not in keep_lu:
            continue
        g = shp_wkb.loads(t["geometry"][i].as_py())
        if not near_anchor(g, loc):
            continue
        nm = (t["names"][i].as_py() or {}).get("primary")
        rec = {"name": nm, "class": cl}
        rec.update(geom_to_local(g, loc, tol=3.0))
        if rec.get("polys"):
            landuse.append(rec)
    json.dump(landuse, open(os.path.join(OUT_DIR, "landuse.json"), "w"),
              ensure_ascii=False)
    print("землепользование: %d полигонов" % len(landuse))

    # --- 4) ТРАНСПОРТ (дороги + ж/д) ---
    t = load("theme=transportation/type=segment",
             ["subtype", "class", "names", "geometry"])
    keep_road = {"motorway", "trunk", "primary", "secondary", "tertiary",
                 "residential", "unclassified", "living_street", "pedestrian"}
    roads = []
    for i in range(t.num_rows):
        sub = t["subtype"][i].as_py()
        cl = t["class"][i].as_py()
        if sub == "road" and cl not in keep_road:
            continue
        if sub not in ("road", "rail"):
            continue
        g = shp_wkb.loads(t["geometry"][i].as_py())
        if not near_anchor(g, loc):
            continue
        nm = (t["names"][i].as_py() or {}).get("primary")
        rec = {"name": nm, "kind": sub, "class": cl}
        rec.update(geom_to_local(g, loc, tol=2.0))
        if rec.get("lines"):
            roads.append(rec)
    json.dump(roads, open(os.path.join(OUT_DIR, "roads.json"), "w"),
              ensure_ascii=False)
    print("транспорт: %d сегментов" % len(roads))

    # --- 5) ЗДАНИЯ ---
    t = load("theme=buildings/type=building",
             ["names", "class", "height", "geometry"])
    buildings = []
    for i in range(t.num_rows):
        g = shp_wkb.loads(t["geometry"][i].as_py())
        if not near_anchor(g, loc):
            continue
        nm = (t["names"][i].as_py() or {}).get("primary")
        h = t["height"][i].as_py()
        rec = {"name": nm, "class": t["class"][i].as_py(),
               "height_m": round(h, 1) if h else None}
        rec.update(geom_to_local(g, loc, tol=1.0))
        if rec.get("polys"):
            buildings.append(rec)
    json.dump(buildings, open(os.path.join(OUT_DIR, "buildings.json"), "w"),
              ensure_ascii=False)
    print("здания: %d" % len(buildings))

    # --- метаданные якоря ---
    json.dump({
        "anchor": {"lat": anchor_lat, "lon": anchor_lon,
                   "source": "Overture 2026-06-17 (здание «Большой Гатчинский дворец», centroid)"},
        "axes": "x=восток (м), y=север (м); в движке z=-y",
        "layers": ["water.json", "landuse.json", "roads.json", "buildings.json"],
        "simplify_tol_m": {"water": 1.5, "landuse": 3.0, "roads": 2.0, "buildings": 1.0},
        "radius_m": KEEP_RADIUS_M,
    }, open(os.path.join(OUT_DIR, "meta.json"), "w"), ensure_ascii=False, indent=1)
    print("готово ->", OUT_DIR)

    # контрольные числа: именованные озёра
    for w in water:
        if w["name"] in ("Белое озеро", "Серебряное озеро", "Чёрное озеро"):
            pts = w["polys"][0][0]
            xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
            print("  %s: центр (%.0f в, %.0f с) м, габарит %d×%d м, точек %d" % (
                w["name"], sum(xs)/len(xs), sum(ys)/len(ys),
                max(xs)-min(xs), max(ys)-min(ys), len(pts)))


if __name__ == "__main__":
    main()
