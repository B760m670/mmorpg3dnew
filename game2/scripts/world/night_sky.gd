class_name NightSky
extends Node3D
## НАСТОЯЩЕЕ НОЧНОЕ НЕБО над Гатчиной — с ПОВЕРХНОСТИ, в масштабе игры.
## Не купол-картинка и не «космос за куполом» (тот путь мы уже похоронили):
## светила стоят на небесной сфере на бесконечности в СВОИХ настоящих видимых
## положениях, а атмосфера (небо) — слой перед ними.
##
## Звёзды: реальный каталог Yale Bright Star (stars.bin, 8404 звезды ≤6.5m) —
##   настоящие RA/Dec (J2000), яркость из видимой величины, цвет из настоящей
##   цветовой температуры. Единый экваториальный купол крутится матрицей
##   экватор→горизонт по ЗВЁЗДНОМУ времени (WorldClock) — звёзды всходят/заходят
##   как в реальности. Матрица сверена с формулой alt/az до 1e-16.
## Луна: настоящая орбита (Meeus) → положение; ФАЗА рождается сама — сфера Луны
##   освещается настоящим направлением на Солнце (терминатор верен).
## Видимость: из высоты Солнца (сумерки civil/nautical/astronomical) — звёзды
##   проступают, когда небо темнеет. Дымка у горизонта гасит низкие светила.

const STARS_PATH := "res://data/real/stars.bin"
const R_SKY := 9000.0        # радиус небесной сферы: < far(22000), > купол облаков(5000)

@export var sun: DirectionalLight3D
@export var clock: WorldClock

var _stars_mi: MeshInstance3D
var _stars_mat: ShaderMaterial
var _moon: MeshInstance3D
var _moon_mat: ShaderMaterial
const RAD := PI / 180.0

func build() -> void:
	_build_stars()
	_build_moon()

# --- купол звёзд из реального каталога ---
func _build_stars() -> void:
	var f := FileAccess.open(STARS_PATH, FileAccess.READ)
	if f == null:
		push_warning("[stars] нет каталога %s" % STARS_PATH)
		return
	if f.get_buffer(4).get_string_from_ascii() != "STAR":
		push_warning("[stars] плохой формат каталога")
		return
	var n := f.get_32()
	var verts := PackedVector3Array(); verts.resize(n)
	var cols := PackedColorArray(); cols.resize(n)
	var uvs := PackedVector2Array(); uvs.resize(n)
	for i in range(n):
		var x := f.get_float(); var y := f.get_float(); var z := f.get_float()
		var mag := f.get_float()
		var r := f.get_8(); var g := f.get_8(); var b := f.get_8(); f.get_8()
		# экваториальный единичный вектор × радиус (движок: X, Y, Z);
		# ориентацию задаст матрица экватор→горизонт в _process
		verts[i] = Vector3(x, y, z) * R_SKY
		cols[i] = Color8(r, g, b)
		uvs[i] = Vector2(mag, 0.0)          # величина → размер/яркость в шейдере
	var arr := []
	arr.resize(Mesh.ARRAY_MAX)
	arr[Mesh.ARRAY_VERTEX] = verts
	arr[Mesh.ARRAY_COLOR] = cols
	arr[Mesh.ARRAY_TEX_UV] = uvs
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_POINTS, arr)
	mesh.custom_aabb = AABB(Vector3(-R_SKY, -R_SKY, -R_SKY), Vector3(2 * R_SKY, 2 * R_SKY, 2 * R_SKY))
	_stars_mat = ShaderMaterial.new()
	_stars_mat.shader = load("res://shaders/world/stars.gdshader")
	_stars_mi = MeshInstance3D.new()
	_stars_mi.mesh = mesh
	_stars_mi.material_override = _stars_mat
	_stars_mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_stars_mi.custom_aabb = mesh.custom_aabb
	add_child(_stars_mi)
	print("[stars] купол: %d настоящих звёзд (Yale BSC, RA/Dec J2000, цвет из T)" % n)

# --- Луна как настоящая сфера: реальная поверхность + либрация + фаза ---
func _mip_tex(path: String) -> Texture2D:
	var res := load(path)
	if not (res is Texture2D):
		return null
	var img := (res as Texture2D).get_image()
	if img == null:
		return res
	if not img.has_mipmaps():
		img.generate_mipmaps()
	return ImageTexture.create_from_image(img)

func _build_moon() -> void:
	var sph := SphereMesh.new()
	sph.radius = 1.0                         # единичная; масштаб = угловой размер (в _process)
	sph.height = 2.0
	sph.radial_segments = 48
	sph.rings = 24
	_moon_mat = ShaderMaterial.new()
	_moon_mat.shader = load("res://shaders/world/moon.gdshader")
	_moon_mat.set_shader_parameter("albedo_tex", _mip_tex("res://assets/sky/moon_albedo.png"))
	_moon = MeshInstance3D.new()
	_moon.mesh = sph
	_moon.material_override = _moon_mat
	_moon.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_moon.custom_aabb = AABB(Vector3(-100, -100, -100), Vector3(200, 200, 200))
	add_child(_moon)

# --- матрица экватор(J2000)→горизонт(движок) по звёздному времени ---
# Порт из tools/verify_night_sky.py (сверено с alt/az до 1e-16).
# Горизонт(X=восток,Y=верх,север=−Z) = B · экв_вектор.
func _equ_to_horizon_basis(unix: float) -> Basis:
	var phi := clock.latitude_deg * RAD
	var lst := clock.local_sidereal_deg(unix) * RAD
	var cp := cos(phi); var sp := sin(phi)
	# R: часовой-угол-кадр → движок
	var R := Basis(Vector3(0.0, cp, sp), Vector3(-1.0, 0.0, 0.0), Vector3(0.0, sp, -cp))
	# Basis(x_col, y_col, z_col): столбцы — образы ортов q. Проверено ниже числами.
	# q = FY · Rz(−LST) · v0  (y-флип, т.к. H = LST − RA)
	var c := cos(-lst); var s := sin(-lst)
	var RzL := Basis(Vector3(c, s, 0.0), Vector3(-s, c, 0.0), Vector3(0.0, 0.0, 1.0))
	var FY := Basis(Vector3(1.0, 0.0, 0.0), Vector3(0.0, -1.0, 0.0), Vector3(0.0, 0.0, 1.0))
	return R * FY * RzL

func _process(_delta: float) -> void:
	if clock == null or _stars_mi == null:
		return
	var cam := get_viewport().get_camera_3d()
	if cam != null:
		global_position = cam.global_position            # небо «на бесконечности»
	var unix := clock.utc_unix
	var basis := _equ_to_horizon_basis(unix)
	_stars_mi.transform.basis = basis

	# видимость ночного неба из высоты Солнца (сумерки): звёзды проступают
	# на гражданских сумерках, полны к астрономическим (−18°).
	var elev := clock.sun_elevation_deg
	var night := clampf((-elev - 4.0) / 14.0, 0.0, 1.0)
	_stars_mat.set_shader_parameter("night", night)

	# Луна: настоящее положение + НАСТОЯЩАЯ ОРИЕНТАЦИЯ (ось по позиционному углу P,
	# либрация l/b) + фаза (освещение настоящим Солнцем) + настоящий угловой размер.
	var m := clock.moon_state(unix)
	var ra := float(m["ra_deg"]) * RAD; var dec := float(m["dec_deg"]) * RAD
	var v_eq := Vector3(cos(dec) * cos(ra), cos(dec) * sin(ra), sin(dec))
	var mdir := (basis * v_eq).normalized()              # мир: направление на Луну
	if _moon != null and _moon_mat != null:
		_moon.visible = mdir.y > -0.03                    # над горизонтом
		_moon.position = mdir * R_SKY
		# ось Луны на небе: небесный север, повёрнутый на позиционный угол P
		var ncp := (basis * Vector3(0.0, 0.0, 1.0)).normalized()
		var north_tan := (ncp - ncp.dot(mdir) * mdir).normalized()
		var perp := mdir.cross(north_tan).normalized()    # в плоскости диска, ⟂ север
		var pang := float(m["pos_angle"]) * RAD
		var axis := (north_tan * cos(pang) + perp * sin(pang)).normalized()
		# селенографический фрейм: prime = к Земле (−mdir) ⟂ оси; east = ось×prime
		var to_earth := -mdir
		var prime := (to_earth - to_earth.dot(axis) * axis).normalized()
		var east := axis.cross(prime).normalized()
		_moon_mat.set_shader_parameter("moon_axis", axis)
		_moon_mat.set_shader_parameter("moon_prime", prime)
		_moon_mat.set_shader_parameter("moon_east", east)
		_moon_mat.set_shader_parameter("libration", Vector2(float(m["lib_l"]), float(m["lib_b"])))
		# настоящий угловой размер (перигей/апогей): радиус на дистанции R_SKY
		var ang_r := float(m["ang_diam_deg"]) * 0.5 * RAD
		_moon.scale = Vector3.ONE * (R_SKY * tan(ang_r))
		var moon_vis := clampf((-elev + 2.0) / 10.0, 0.15, 1.0)
		_moon_mat.set_shader_parameter("night", moon_vis)
		if sun != null:
			_moon_mat.set_shader_parameter("sun_dir", sun.global_transform.basis.z.normalized())
