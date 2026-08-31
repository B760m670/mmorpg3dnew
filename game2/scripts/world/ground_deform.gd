class_name GroundDeform
extends Node3D
## ДЕФОРМАЦИЯ ПОЧВЫ под нагрузкой (следы/проседание) — imprint-буфер вокруг
## тела. Каждый кадр под активным телом впечатывается мягкая ямка, ГЛУБИНА ∝
## деформируемости почвы здесь (канал поля почвы: торф-глей мокрый — глубоко,
## сухой камень — почти нет). Буфер отдаётся в шейдер земли (deform_tex), тот
## вычитает вмятину из высоты — настоящая просадка геометрией, не рисунок.
##
## v1 (клипмап 2 м у ног → широкая просадка под телом, не резкий след ботинка;
## резкий отпечаток — отдельная мелкая заплатка под игроком, следующий шаг).
## Пересборка окна очищает дальние следы (персист в пределах ~окна).

const IMG_N := 256
const HALF := 16.0            # полуокно буфера, м
const DEPTH := 0.11           # макс. глубина просадки, м
const RECENTER_AT := 9.0      # смещение тела до пересборки окна, м
const FOOT_R := 0.5           # радиус пятна нагрузки, м
const SOIL_BIN := "res://assets/life/slice_soilfield.bin"
const SOIL_META := "res://assets/life/slice_soilfield.json"

var terrain: Terrain
var target: Node3D

var _img: Image
var _tex: ImageTexture
var _center := Vector2(1e9, 1e9)
var _soil: PackedByteArray
var _soil_n := 0
var _soil_cx := 0.0
var _soil_cy := 0.0
var _soil_half := 0.0

func _ready() -> void:
	_img = Image.create(IMG_N, IMG_N, false, Image.FORMAT_RF)
	_img.fill(Color(0, 0, 0))
	_tex = ImageTexture.create_from_image(_img)
	_load_soil()

func _load_soil() -> void:
	var fm := FileAccess.open(SOIL_META, FileAccess.READ)
	var fb := FileAccess.open(SOIL_BIN, FileAccess.READ)
	if fm == null or fb == null:
		return
	var m: Dictionary = JSON.parse_string(fm.get_as_text())
	_soil_n = int(m["n"])
	_soil_cx = float(m["cx"])
	_soil_cy = float(m["cy"])
	_soil_half = float(m["half_m"])
	_soil = fb.get_buffer(_soil_n * _soil_n * 4)   # RGBA: fert,moist,deform,type
	if _soil.size() != _soil_n * _soil_n * 4:
		_soil = PackedByteArray()

## деформируемость почвы в точке (x=восток, z движка=−север); канал 2
func _deformability(x: float, z: float) -> float:
	if _soil.is_empty():
		return 0.45
	var u := int((x - _soil_cx + _soil_half) / (2.0 * _soil_half) * float(_soil_n))
	var v := int((_soil_cy + _soil_half - (-z)) / (2.0 * _soil_half) * float(_soil_n))
	if u < 0 or v < 0 or u >= _soil_n or v >= _soil_n:
		return 0.45
	return float(_soil[(v * _soil_n + u) * 4 + 2]) / 255.0

func _physics_process(_dt: float) -> void:
	if terrain == null or target == null or terrain.ground_mat == null:
		return
	var p := target.global_position
	var c := Vector2(p.x, p.z)
	if _center.distance_to(c) > RECENTER_AT:
		_center = c
		_img.fill(Color(0, 0, 0))          # пересборка окна: дальние следы уходят

	var dmax := clampf(_deformability(p.x, p.z), 0.0, 1.0)
	if dmax >= 0.03:
		var cu := (c.x - (_center.x - HALF)) / (2.0 * HALF) * float(IMG_N)
		var cv := (c.y - (_center.y - HALF)) / (2.0 * HALF) * float(IMG_N)
		var rad := FOOT_R / (2.0 * HALF) * float(IMG_N)
		var x0 := maxi(int(floor(cu - rad)), 0)
		var x1 := mini(int(ceil(cu + rad)), IMG_N - 1)
		var y0 := maxi(int(floor(cv - rad)), 0)
		var y1 := mini(int(ceil(cv + rad)), IMG_N - 1)
		for yy in range(y0, y1 + 1):
			for xx in range(x0, x1 + 1):
				var dd := Vector2(float(xx) - cu, float(yy) - cv).length() / rad
				if dd > 1.0:
					continue
				var g := 1.0 - dd * dd                     # мягкая ямка
				var cur := _img.get_pixel(xx, yy).r
				_img.set_pixel(xx, yy, Color(maxf(cur, dmax * g), 0.0, 0.0))
	_tex.update(_img)

	var m := terrain.ground_mat
	m.set_shader_parameter("deform_tex", _tex)
	m.set_shader_parameter("deform_center", _center)
	m.set_shader_parameter("deform_half", HALF)
	m.set_shader_parameter("deform_depth", DEPTH)
