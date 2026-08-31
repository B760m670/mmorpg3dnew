class_name WorldGeo
extends RefCounted
## ИСТИННЫЕ КООРДИНАТЫ МИРА: мировые метры <-> настоящие широта/долгота (WGS84).
##
## Мир привязан к РЕАЛЬНОЙ точке — центр Большого Гатчинского дворца
## (якорь из data/real/meta.json). Оси движка: x=восток (м), z=-север (м).
## Поэтому «59.5634, 30.1075» в игре означает то же место, что на настоящей карте.
##
## Метод: локальная касательная плоскость (ENU) на эллипсоиде WGS84 — радиусы
## кривизны считаются на широте точки, что даёт настоящие метры на градус.
## Та же математика, что в tools/geo.py; сверена с геодезией (pyproj):
## расхождение 0.25 м на 42 км, преобразование строго обратимо.

const LAT0 := 59.56344564515459      # Большой Гатчинский дворец (Overture)
const LON0 := 30.10748733007132
const A := 6378137.0                  # большая полуось WGS84
const F := 1.0 / 298.257223563
const E2 := F * (2.0 - F)

## метры на градус широты (x) и долготы (y) на данной широте
static func meters_per_degree(lat_deg: float) -> Vector2:
	var p := deg_to_rad(lat_deg)
	var s := sin(p)
	var w := sqrt(1.0 - E2 * s * s)
	var m_lat := A * (1.0 - E2) / pow(w, 3.0) * PI / 180.0
	var m_lon := A / w * cos(p) * PI / 180.0
	return Vector2(m_lat, m_lon)

## мировые метры (x=восток, z=-север) -> широта/долгота (x=lat, y=lon)
static func world_to_geo(x: float, z: float) -> Vector2:
	var north := -z
	var lat := LAT0 + north / meters_per_degree(LAT0).x
	for i in 3:                                    # итерация по середине смещения
		lat = LAT0 + north / meters_per_degree((LAT0 + lat) * 0.5).x
	var mpd := meters_per_degree((LAT0 + lat) * 0.5)
	var lon := LON0 + x / mpd.y
	return Vector2(lat, lon)

## широта/долгота -> мировые метры (x=восток, z=-север движка)
static func geo_to_world(lat: float, lon: float) -> Vector2:
	var mpd := meters_per_degree((LAT0 + lat) * 0.5)
	return Vector2((lon - LON0) * mpd.y, -(lat - LAT0) * mpd.x)

## «59°33'48.4"N 30°06'27.0"E» — как на настоящей карте
static func to_dms(lat: float, lon: float) -> String:
	return "%s %s" % [_dms(lat, "N", "S"), _dms(lon, "E", "W")]

static func _dms(v: float, pos: String, neg: String) -> String:
	var h := pos if v >= 0.0 else neg
	var a := absf(v)
	var d := int(a)
	var m := int((a - float(d)) * 60.0)
	var s := (a - float(d) - float(m) / 60.0) * 3600.0
	return "%d°%02d'%04.1f\"%s" % [d, m, s, h]
