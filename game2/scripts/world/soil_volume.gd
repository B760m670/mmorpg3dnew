class_name SoilVolume
extends Node3D
## НАСТОЯЩАЯ ПОЧВА КАК ОБЪЁМ — не покраска поверхности.
##
## Земля здесь — вещество с глубиной: под каждой точкой лежит НАСТОЯЩИЙ профиль
## (tools/soil_profile.py: O -> A -> E -> B -> C -> Cg -> R, 50 м), срезанный по
## катене (tools/build_soil_horizons.py). Почву можно КОПАТЬ: вынутый грунт
## исчезает из объёма, в стенке ямы обнажаются НАСТОЯЩИЕ слои — не нарисованные,
## а геометрия с материалом своего горизонта.
##
## Физика (испытана в tools/soil_test.py, сверена со справочниками):
##  - стенки осыпаются, если круче УГЛА ЕСТЕСТВЕННОГО ОТКОСА своего слоя
##    (φ: гумус 28°, подзол 32°, глина 16°) — яма сама заплывает;
##  - вынутый грунт РАЗРЫХЛЯЕТСЯ (bulking): отвал больше вынутого объёма;
##  - копать тяжелее с глубиной (плотность и сцепление растут).
##
## Почему так, а не воксели по всей карте: воксель 10 см на 16.4 x 16.4 км x 50 м
## = 13 ТБ (посчитано). Поэтому объём живёт ЛОКАЛЬНО — окно вокруг игрока
## (WINDOW_M), где копание реально; за окном земля описана тем же профилем.

const WINDOW_M := 24.0            # сторона окна копания, м
const CELL_M := 0.25              # ячейка объёма, м (26 см — размер лопаты)
const N := int(WINDOW_M / CELL_M) # 96 x 96 столбцов
const MAX_DIG_M := 6.0            # глубже пока не копаем (хватает на погреб/окоп)

var profile: Array = []           # горизонты из soil_profile.json
var _tops := PackedFloat32Array() # глубина верха каждого горизонта, м
var _center := Vector2.ZERO       # центр окна в мире (x, z)
var _surf := PackedFloat32Array() # текущая поверхность (просадка от исходной), м
var _cut := PackedFloat32Array()  # срез профиля в этой точке (катена), м
var _dirty := false
var last_collapse_ms: float = 0.0   # замер решателя осыпания
var last_mesh_ms: float = 0.0       # замер построения геометрии

var _mesh_inst: MeshInstance3D
var _mat: ShaderMaterial

func _ready() -> void:
	_load_profile()
	_surf.resize(N * N)
	_cut.resize(N * N)
	_surf.fill(0.0)
	_cut.fill(0.0)
	_mesh_inst = MeshInstance3D.new()
	_mesh_inst.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	add_child(_mesh_inst)
	_mat = ShaderMaterial.new()
	_mat.shader = load("res://shaders/world/soil_volume.gdshader")
	_apply_palette()
	_mesh_inst.material_override = _mat

func _load_profile() -> void:
	var f := FileAccess.open("res://data/real/soil_profile.json", FileAccess.READ)
	if f == null:
		push_warning("[soil] нет профиля почвы")
		return
	var d: Variant = JSON.parse_string(f.get_as_text())
	if d is Dictionary and d.has("horizons"):
		profile = d["horizons"]
	var z := 0.0
	for h in profile:
		_tops.append(z)
		z += float(h["thick_m"])

## горизонт на глубине depth от ИСХОДНОЙ поверхности (с учётом среза катены)
func horizon_at(depth_m: float, cut_m: float) -> int:
	var d := depth_m + maxf(cut_m, 0.0)
	for i in range(profile.size() - 1, -1, -1):
		if d >= _tops[i]:
			return i
	return 0

## угол естественного откоса слоя (град) — по нему осыпаются стенки
func repose_of(hz: int) -> float:
	if hz < 0 or hz >= profile.size():
		return 30.0
	return float(profile[hz]["repose_deg"])

## сопротивление копанию (0 легко .. 1 почти не берётся)
func dig_resistance(hz: int) -> float:
	if hz < 0 or hz >= profile.size():
		return 0.5
	return 1.0 - float(profile[hz]["diggability"])

func _idx(ix: int, iy: int) -> int:
	return iy * N + ix

## центрировать окно копания на точке мира (вызывать при переходе игрока)
func center_on(world_x: float, world_z: float, terrain: Terrain) -> void:
	_center = Vector2(world_x, world_z)
	global_position = Vector3(world_x, 0.0, world_z)
	# запомнить срез профиля (катену) в каждой ячейке — чтобы знать, какой слой
	# лежит сверху именно здесь
	for iy in N:
		for ix in N:
			var wx := world_x + (float(ix) - N * 0.5) * CELL_M
			var wz := world_z + (float(iy) - N * 0.5) * CELL_M
			_cut[_idx(ix, iy)] = terrain.soil_cut_at(wx, wz) if terrain != null else 0.0
	_surf.fill(0.0)
	_dirty = true

## КОПАТЬ: снять грунт в круге радиуса r с глубиной depth (м).
## Возвращает ОБЪЁМ вынутого грунта (м3) — с учётом разрыхления.
func dig(world_x: float, world_z: float, r_m: float, depth_m: float) -> float:
	var moved := 0.0
	var cell_area := CELL_M * CELL_M
	for iy in N:
		for ix in N:
			var wx := _center.x + (float(ix) - N * 0.5) * CELL_M
			var wz := _center.y + (float(iy) - N * 0.5) * CELL_M
			var d := Vector2(wx - world_x, wz - world_z).length()
			if d > r_m:
				continue
			# лопата снимает больше в середине — форма выемки, а не цилиндр
			var k := 1.0 - (d / r_m) * (d / r_m)
			var i := _idx(ix, iy)
			var cur := _surf[i]
			var want := cur + depth_m * k
			# глубже — тяжелее: плотные слои поддаются хуже
			var hz := horizon_at(cur, _cut[i])
			want = cur + (want - cur) * (1.0 - dig_resistance(hz) * 0.75)
			want = minf(want, MAX_DIG_M)
			moved += (want - cur) * cell_area
			_surf[i] = want
	if moved > 0.0:
		# ЗАМЕР: решатель осыпания — самый тяжёлый цикл. Числа решают, нужен ли
		# перенос в C++/GPU-compute (в AAA это делают компьют-шейдером).
		var t0 := Time.get_ticks_usec()
		_collapse()
		last_collapse_ms = float(Time.get_ticks_usec() - t0) / 1000.0
		var t1 := Time.get_ticks_usec()
		_rebuild_mesh()
		last_mesh_ms = float(Time.get_ticks_usec() - t1) / 1000.0
		_dirty = false
	# РАЗРЫХЛЕНИЕ: вынутый грунт занимает больше места, чем в массиве
	return moved * 1.25

## ОСЫПАНИЕ СТЕНОК: если сосед круче угла естественного откоса своего слоя —
## грунт сползает. Настоящая физика: яма сама заплывает до устойчивого угла.
func _collapse() -> void:
	# 8 НАПРАВЛЕНИЙ (оси + диагонали с их настоящим расстоянием). Ограничение
	# только по 4 осям оставляет диагональ круче в sqrt(2) раз: 30° по осям дают
	# 39° по диагонали — это поймало испытание (tools/soil_dig_test.py).
	var dirs := [
		Vector3(1, 0, 1.0), Vector3(-1, 0, 1.0), Vector3(0, 1, 1.0), Vector3(0, -1, 1.0),
		Vector3(1, 1, sqrt(2.0)), Vector3(1, -1, sqrt(2.0)),
		Vector3(-1, 1, sqrt(2.0)), Vector3(-1, -1, sqrt(2.0)),
	]
	# ОПТИМИЗАЦИЯ горячего цикла: тангенсы углов откоса считаем ОДИН раз, горизонт
	# каждой ячейки — один раз за проход (а не 8 раз, по разу на направление).
	# Замер до: 2775 мс на одно копание (игра замирала на 3 с).
	var tan_rep := PackedFloat32Array()
	for h in profile:
		tan_rep.append(tan(deg_to_rad(float(h["repose_deg"]))))
	var lim_cell := PackedFloat32Array()
	lim_cell.resize(N * N)
	for pass_i in 24:
		for i in range(N * N):
			lim_cell[i] = tan_rep[horizon_at(_surf[i], _cut[i])] * CELL_M
		var moved := false
		for d in dirs:
			var ox := int(d.x)
			var oy := int(d.y)
			var step := oy * N + ox
			var dist: float = d.z
			for iy in range(1, N - 1):
				var row := iy * N
				for ix in range(1, N - 1):
					var i := row + ix
					var excess := (_surf[i] - _surf[i + step]) - lim_cell[i] * dist
					if excess > 0.0:
						var give := excess * 0.4
						_surf[i] -= give
						_surf[i + step] += give
						moved = true
		if not moved:
			break

func _process(_delta: float) -> void:
	if _dirty:
		_rebuild_mesh()
		_dirty = false

## построить геометрию: поверхность + СТЕНКИ ямы с настоящими слоями.
## Цвет берётся не «покраской», а из горизонта на ФАКТИЧЕСКОЙ глубине точки.
func _rebuild_mesh() -> void:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var half := N * 0.5
	var any := false
	for iy in range(N - 1):
		for ix in range(N - 1):
			var i00 := _idx(ix, iy)
			var i10 := _idx(ix + 1, iy)
			var i01 := _idx(ix, iy + 1)
			var i11 := _idx(ix + 1, iy + 1)
			# рисуем только там, где копали (иначе земля — обычный террейн)
			if _surf[i00] <= 0.001 and _surf[i10] <= 0.001 \
					and _surf[i01] <= 0.001 and _surf[i11] <= 0.001:
				continue
			any = true
			var p00 := Vector3((ix - half) * CELL_M, -_surf[i00], (iy - half) * CELL_M)
			var p10 := Vector3((ix + 1 - half) * CELL_M, -_surf[i10], (iy - half) * CELL_M)
			var p01 := Vector3((ix - half) * CELL_M, -_surf[i01], (iy + 1 - half) * CELL_M)
			var p11 := Vector3((ix + 1 - half) * CELL_M, -_surf[i11], (iy + 1 - half) * CELL_M)
			_tri(st, p00, i00, p10, i10, p11, i11)
			_tri(st, p00, i00, p11, i11, p01, i01)
	if not any:
		_mesh_inst.mesh = null
		return
	st.generate_normals()
	_mesh_inst.mesh = st.commit()

func _tri(st: SurfaceTool, a: Vector3, ia: int, b: Vector3, ib: int, c: Vector3, ic: int) -> void:
	for pair in [[a, ia], [b, ib], [c, ic]]:
		var p: Vector3 = pair[0]
		var idx: int = pair[1]
		# UV несёт ГЛУБИНУ и НОМЕР ГОРИЗОНТА — шейдер красит вещество, не поверхность
		var depth: float = _surf[idx]
		var hz: float = float(horizon_at(depth, _cut[idx]))
		st.set_uv(Vector2(depth, hz))
		st.add_vertex(p)

func _apply_palette() -> void:
	var dry := PackedColorArray()
	var rough := PackedFloat32Array()
	for h in profile:
		var c: Array = h["color_dry"]
		dry.append(Color(c[0], c[1], c[2]))
		rough.append(clampf(1.0 - float(h["clay"]) * 0.5, 0.55, 1.0))
	if dry.size() >= 7:
		_mat.set_shader_parameter("hz_col", dry)
		_mat.set_shader_parameter("hz_rough", rough)

## сводка для HUD/проверок
func report() -> Dictionary:
	var dug := 0.0
	var deepest := 0.0
	for v in _surf:
		dug += v * CELL_M * CELL_M
		deepest = maxf(deepest, v)
	return {"volume_m3": dug, "deepest_m": deepest, "window_m": WINDOW_M, "cell_m": CELL_M,
		"collapse_ms": last_collapse_ms, "mesh_ms": last_mesh_ms, "cells": N * N}
