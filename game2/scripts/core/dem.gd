class_name Dem
extends RefCounted
## Загрузчик НАСТОЯЩИХ высот Земли (E3). Читает сырой int16-грид (Web Mercator),
## собранный из реальных измерений (SRTM/ASTER + GEBCO/ETOPO). Точные значения,
## без потерь от импорта текстур. elevation(lat,lon) → метры (море = 0, дно < 0).

const W := 1024
const H := 1024
const LAT_LIMIT := 85.0511

var _data: PackedByteArray
var loaded: bool = false

func load_global() -> bool:
	var f := FileAccess.open("res://assets/dem/earth_i16.bin", FileAccess.READ)
	if f == null:
		return false
	_data = f.get_buffer(W * H * 2)
	loaded = _data.size() == W * H * 2
	return loaded

func _at(xi: int, yi: int) -> float:
	xi = ((xi % W) + W) % W
	yi = clampi(yi, 0, H - 1)
	return float(_data.decode_s16((yi * W + xi) * 2))

## высота поверхности Земли (м) в точке (широта°, долгота°) — билинейно
func elevation(lat_deg: float, lon_deg: float) -> float:
	if not loaded:
		return 0.0
	var lat := clampf(lat_deg, -LAT_LIMIT, LAT_LIMIT)
	var x := (lon_deg + 180.0) / 360.0 * float(W)
	var latr := lat * PI / 180.0
	var y := (1.0 - asinh(tan(latr)) / PI) / 2.0 * float(H)
	var xi := int(floor(x))
	var yi := int(floor(y))
	var fx := x - float(xi)
	var fy := y - float(yi)
	var h00 := _at(xi, yi)
	var h10 := _at(xi + 1, yi)
	var h01 := _at(xi, yi + 1)
	var h11 := _at(xi + 1, yi + 1)
	return lerp(lerp(h00, h10, fx), lerp(h01, h11, fx), fy)
