# class_name НЕ объявляем: имя класса берётся из кэша проекта, а на свежем
# запуске он про новый файл ещё не знает — тогда сцена не грузится вовсе.
# Подключаемся через preload (та же грабля уже ловила нас трижды).
extends Node3D
## БЛИЖНЯЯ ВОДА — ПОЛЕ, А НЕ ПЛИТА.
##
## Что это заменяет. Дальняя вода (water_real.gd) — запечённые прямоугольники по
## осям: 7292 плиты, 75 плоских уровней, одна вершина на 33 м², шаг запекания
## 2 м. Берег там лестница, поверхность двигаться не может, а глубина считается
## как «урез минус рельеф» — оба слагаемых постоянны. Для задника это годится.
## Для воды, к которой игрок подходит, — нет.
##
## Здесь над игровым срезом стоит ПОЛЕ (C++, water_field.h): высота столба
## h(x,z) как состояние, дно из нашего рельефа, поверхность = дно + h. Меш —
## сетка с вершиной в КАЖДОМ узле поля, и вершина ставится на отметку, которую
## посчитал решатель. Берег — изолиния, а не многоугольник.
##
## РАЗМЕР СРЕЗА выбран по цене, а не на глаз. ИЗМЕРЕНО (tests/wf_test.cpp, один
## подшаг): 128² — 0.7 мс, 256² — 2.5 мс, 512² — 9.7 мс на кадр. 256 ячеек по
## метру — это срез 256 м за 2.5 мс, и метровая ячейка согласуется с нашей
## батиметрией (растр уреза 2 м, метровый DEM парка).

const SIDE := 256              # ячеек
const CELL := 1.0              # м на ячейку
const SIZE := SIDE * CELL      # сторона окна, м

var terrain: Terrain
var center := Vector2(-16.0, -640.0)   # где стоит срез (Белое озеро у дворца)
var rest_level := 0.0                  # отметка покоя, м (берётся из батиметрии)

var vol: RefCounted                    # WaterVolume, если модуль есть
var _mat: ShaderMaterial
var _mi: MeshInstance3D
var _origin := Vector2.ZERO
var _t := 0.0
var _logged := false

func available() -> bool:
	return vol != null

func build() -> bool:
	if not ClassDB.class_exists("WaterVolume"):
		print("[поле воды] модуля нет — ближняя вода остаётся плитами задника")
		return false
	if terrain == null:
		return false
	_origin = center - Vector2(SIZE, SIZE) * 0.5
	vol = ClassDB.instantiate("WaterVolume")
	vol.setup(SIDE, CELL)
	vol.set_origin(_origin)
	vol.set_manning(0.03)

	# --- ДНО ИЗ НАШЕГО ЖЕ РЕЛЬЕФА ---
	# 65 536 обращений к terrain.height один раз на старте. Это дорого в кадре,
	# но здесь кадра ещё нет, а разрешение поля должно совпадать с сеткой —
	# усреднять тут нечего.
	var t0 := Time.get_ticks_usec()
	var bed := PackedFloat32Array()
	bed.resize(SIDE * SIDE)
	var lvl_sum := 0.0
	var lvl_n := 0
	for j in range(SIDE):
		var wz := _origin.y + float(j) * CELL
		for i in range(SIDE):
			var wx := _origin.x + float(i) * CELL
			bed[j * SIDE + i] = terrain.height(wx, wz)
	var bed_ms := float(Time.get_ticks_usec() - t0) / 1000.0

	# --- ОТМЕТКА ПОКОЯ ИЗ БАТИМЕТРИИ ---
	# Уровень не назначается: он берётся из того же уреза, которым вода
	# нарисована в задник, — иначе ближняя и дальняя вода разошлись бы по высоте
	# и на стыке был бы уступ.
	var wr := get_parent().get_node_or_null("WaterReal") as WaterReal
	for j in range(0, SIDE, 4):
		var wz2 := _origin.y + float(j) * CELL
		for i in range(0, SIDE, 4):
			var wx2 := _origin.x + float(i) * CELL
			var lv := _level_probe(wr, wx2, wz2)
			if not is_nan(lv):
				lvl_sum += lv
				lvl_n += 1
	if lvl_n == 0:
		print("[поле воды] в срезе X%.0f Z%.0f воды нет — поле не поднимаю"
			% [center.x, center.y])
		vol = null
		return false
	rest_level = lvl_sum / float(lvl_n)

	vol.set_bed(bed)
	# Наливаем только там, где дно ниже уреза: иначе зальёт весь срез.
	vol.fill_region(rest_level, rest_level)
	# Окно вырезано из БОЛЬШЕГО озера, поэтому граница открытая: волна уходит,
	# а не отражается от берега, которого нет.
	vol.set_open_boundary(true, rest_level)

	_build_mesh()
	var r: Dictionary = vol.report()
	print("[поле воды] срез %.0f м, сетка %d×%d по %.2f м, урез %.2f м" \
		% [SIZE, SIDE, SIDE, CELL, rest_level])
	print("[поле воды] дно из рельефа за %.0f мс; воды %.0f м³ на %.0f м²; △ %d" \
		% [bed_ms, r["volume_m3"], r["wet_area_m2"], (SIDE - 1) * (SIDE - 1) * 2])
	return true

## Урез в точке: сначала спрашиваем ту же батиметрию, что у дальней воды.
func _level_probe(wr: WaterReal, x: float, z: float) -> float:
	if wr == null:
		return NAN
	return wr.level_at(x, z)

func _build_mesh() -> void:
	# СЕТКА С ВЕРШИНОЙ В КАЖДОМ УЗЛЕ ПОЛЯ. Вершины несут МИРОВЫЕ x,z, а узел
	# стоит в начале координат — тогда шейдеру не нужно обращать матрицу модели
	# на каждую вершину, чтобы найти своё место в поле.
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	for j in range(SIDE - 1):
		var z0 := _origin.y + float(j) * CELL
		var z1 := z0 + CELL
		for i in range(SIDE - 1):
			var x0 := _origin.x + float(i) * CELL
			var x1 := x0 + CELL
			# высота ставится в шейдере; здесь любая, важен только порядок обхода
			var a := Vector3(x0, 0.0, z0)
			var b := Vector3(x1, 0.0, z0)
			var c := Vector3(x1, 0.0, z1)
			var d := Vector3(x0, 0.0, z1)
			for v in [a, d, c, a, c, b]:
				st.set_normal(Vector3.UP)
				st.add_vertex(v)
	var mesh := st.commit()

	_mat = ShaderMaterial.new()
	_mat.shader = load("res://shaders/world/water_volume.gdshader")
	_mat.set_shader_parameter("field_origin", _origin)
	_mat.set_shader_parameter("field_size", SIZE)
	_mat.render_priority = 1        # поверх плит задника, если где-то совпали

	_mi = MeshInstance3D.new()
	_mi.mesh = mesh
	_mi.material_override = _mat
	_mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	# СВОЙ ОГРАНИЧИВАЮЩИЙ ЯЩИК: вершины лежат в плоскости y=0, а шейдер поднимает
	# их к урезу. Без явного ящика движок отсёк бы меш, когда камера смотрит на
	# воду сбоку — по геометрии, которой в буфере нет.
	_mi.custom_aabb = AABB(
		Vector3(_origin.x, rest_level - 30.0, _origin.y),
		Vector3(SIZE, 60.0, SIZE))
	add_child(_mi)

func set_wind(ms: float) -> void:
	if _mat != null:
		_mat.set_shader_parameter("wind_ms", clampf(ms, 0.0, 20.0))

func set_sky(horizon: Vector3, zenith: Vector3) -> void:
	if _mat != null:
		_mat.set_shader_parameter("sky_horizon", horizon)
		_mat.set_shader_parameter("sky_zenith", zenith)

func set_ssr_steps(n: int) -> void:
	if _mat != null:
		_mat.set_shader_parameter("ssr_steps", n)

## Бросить объём: всплеск, шаг ноги, вытеснение телом. Не «высота волны», а
## КУБОМЕТРЫ — это единственный физический способ тронуть воду снаружи.
func splash(pos: Vector3, volume_m3: float, radius_m: float = 0.5) -> void:
	if vol != null:
		vol.add_volume(pos, radius_m, volume_m3)

func depth_at(x: float, z: float) -> float:
	if vol == null:
		return 0.0
	return vol.depth_at(Vector3(x, 0.0, z))

func surface_at(x: float, z: float) -> float:
	if vol == null:
		return rest_level
	return vol.surface_at(Vector3(x, 0.0, z))

## Точка внутри среза? Снаружи распоряжается дальняя вода.
func covers(x: float, z: float) -> bool:
	return x >= _origin.x and z >= _origin.y \
		and x <= _origin.x + SIZE and z <= _origin.y + SIZE

func _process(delta: float) -> void:
	if vol == null or _mat == null:
		return
	_t += delta
	vol.step(delta)
	_mat.set_shader_parameter("field_tex", vol.get_texture())
	_mat.set_shader_parameter("t_s", _t)
	if not _logged:
		_logged = true
		var r: Dictionary = vol.report()
		print("[поле воды] шаг %.0f мкс, подшагов %d, предел шага %.4f с" \
			% [r["step_usec"], r["substeps"], r["max_dt"]])

func report() -> Dictionary:
	if vol == null:
		return {}
	return vol.report()
