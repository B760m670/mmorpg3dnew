class_name Terrain
extends Node3D
## Земля игры — РЕАЛЬНЫЙ рельеф Гатчины, отрисовка КЛИПМАП-КОЛЬЦАМИ
## (детализация = функция расстояния, как в больших открытых мирах):
##   центр 128×128 ячеек по 2 м (±128 м вокруг наблюдателя) + 6 колец с
##   удвоением ячейки (4→128 м) до ±8192 м — вся сетка данных 16.4 км.
## Кольца следуют за камерой (снап к шагу ячейки), высоты выбираются в
## ВЕРШИННОМ шейдере из текстуры высот (mip по уровню кольца — дальняя
## геометрия сглажена «в источнике»), стыки уровней прячут юбки по краям.
## Треугольников ~70k против 295k у старой равномерной сетки — при детали
## у ног 2 м вместо 32 м.
##
## Данные: tools/fetch_dem_gatchina.py → сетка int16-см 513×513×32 м
## (SRTM/ASTER, якорь — Гатчинский дворец). CPU height() — та же сетка:
## по ней физика (heightmap-коллизия), вода и посадка объектов.

const DEM_PATH := "res://assets/dem/gatchina_cm.bin"
const DEM_N := 513
const DEM_STEP := 32.0
const DEM_HALF := (DEM_N - 1) * DEM_STEP * 0.5   # 8192 м

# клипмап
const BASE_CELL := 2.0            # ячейка у ног, м
const LEVELS := 7                 # 0-центр + 6 колец (2,4,8,16,32,64,128 м)
const GRID_N := 128               # ячеек по стороне уровня (кольца — с дырой)
const SKIRT_MARK := -1000.0       # маркер вершин-юбок (в локальном y)

@export var world_size_m: float = 12288.0        # зона карт землепользования
@export var collision_res: int = 384             # сетка физики (шаг 32 м)

var real_dem: bool = false
var _dem: PackedByteArray
var _h_ref: float = 0.0                          # высота дворца — ноль мира
var abs_min: float = 0.0
var abs_max: float = 0.0
var tri_count: int = 0
var min_h: float = INF
var max_h: float = -INF

var _noise: FastNoiseLite
var _ridge: FastNoiseLite
var _rings: Array[MeshInstance3D] = []

func _init() -> void:
	_noise = FastNoiseLite.new()
	_noise.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	_noise.frequency = 0.0016
	_noise.fractal_octaves = 5
	_ridge = FastNoiseLite.new()
	_ridge.noise_type = FastNoiseLite.TYPE_SIMPLEX
	_ridge.frequency = 0.02
	_ridge.fractal_octaves = 3
	_load_dem()

func _load_dem() -> void:
	var f := FileAccess.open(DEM_PATH, FileAccess.READ)
	if f == null:
		push_warning("[terrain] нет данных рельефа (%s) — процедурный фолбэк" % DEM_PATH)
		return
	_dem = f.get_buffer(DEM_N * DEM_N * 2)
	if _dem.size() != DEM_N * DEM_N * 2:
		push_warning("[terrain] файл рельефа неполный — процедурный фолбэк")
		return
	real_dem = true
	_h_ref = _dem_at(DEM_N / 2, DEM_N / 2)
	abs_min = INF; abs_max = -INF
	for k in range(0, DEM_N * DEM_N, 7):
		var v := float(_dem.decode_s16(k * 2)) / 100.0
		abs_min = minf(abs_min, v)
		abs_max = maxf(abs_max, v)
	min_h = abs_min - _h_ref
	max_h = abs_max - _h_ref

func _dem_at(i: int, j: int) -> float:
	i = clampi(i, 0, DEM_N - 1)
	j = clampi(j, 0, DEM_N - 1)
	return float(_dem.decode_s16((j * DEM_N + i) * 2)) / 100.0

func _dem_height(x: float, z: float) -> float:
	var u := (x + DEM_HALF) / DEM_STEP
	var v := (z + DEM_HALF) / DEM_STEP
	var i := int(floor(u))
	var j := int(floor(v))
	var fx := u - float(i)
	var fy := v - float(j)
	return lerpf(lerpf(_dem_at(i, j), _dem_at(i + 1, j), fx),
		lerpf(_dem_at(i, j + 1), _dem_at(i + 1, j + 1), fx), fy)

## высота мира (м); 0 — уровень дворца. По ней — физика, вода, объекты.
func height(x: float, z: float) -> float:
	if real_dem:
		return _dem_height(x, z) - _h_ref
	var hp := _noise.get_noise_2d(x, z) * 14.0
	hp += _noise.get_noise_2d(x * 3.7 + 100.0, z * 3.7) * 4.0
	return hp

func normal_at(x: float, z: float) -> Vector3:
	var e := 8.0
	return Vector3(height(x - e, z) - height(x + e, z), 2.0 * e,
		height(x, z - e) - height(x, z + e)).normalized()

# ------------------------------------------------------------------ построение
var ground_mat: ShaderMaterial          # общий материал колец (для деформации)

func build() -> void:
	var mat := _ground_material()
	ground_mat = mat
	tri_count = 0
	for lv in range(LEVELS):
		var mi := MeshInstance3D.new()
		mi.mesh = _build_level_mesh(lv)
		mi.material_override = mat
		# меш смещается за камерой — граница отсечения должна быть широкой
		mi.custom_aabb = AABB(Vector3(-DEM_HALF, -200, -DEM_HALF),
			Vector3(DEM_HALF * 2, 600, DEM_HALF * 2))
		mi.set_instance_shader_parameter("clip_level", float(lv))
		add_child(mi)
		_rings.append(mi)
	print("[terrain] клипмап: %d уровней, ячейка %s..%s м, охват ±%.0f м, △=%d, рельеф=%s %.0f..%.0f м" % [
		LEVELS, str(BASE_CELL), str(BASE_CELL * pow(2, LEVELS - 1)), DEM_HALF,
		tri_count, "РЕАЛЬНЫЙ (Гатчина)" if real_dem else "процедурный(фолбэк!)",
		abs_min, abs_max])

## уровень lv: сетка GRID_N×GRID_N ячеек размером cell(lv); у колец — дыра
## GRID_N/2 в центре; по внешнему И внутреннему краю — юбки (маркер y).
func _build_level_mesh(lv: int) -> ArrayMesh:
	var cell := BASE_CELL * pow(2.0, lv)
	var n := GRID_N
	var half := n / 2
	var hole_half := n / 4                     # дыра под более мелкий уровень
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var idx: Dictionary = {}

	var add_v := func(i: int, j: int, skirt: bool) -> int:
		var key := i * 10000 + j + (100000000 if skirt else 0)
		if idx.has(key):
			return idx[key]
		var x := float(i - half) * cell
		var z := float(j - half) * cell
		st.set_uv(Vector2(x, z))               # локальный XZ (мир добавит шейдер)
		st.add_vertex(Vector3(x, SKIRT_MARK if skirt else 0.0, z))
		var id: int = idx.size()
		idx[key] = id
		return id

	var quad := func(a: int, b: int, c: int, d: int) -> void:
		# a—b (север), c—d (юг): лицо вверх
		st.add_index(a); st.add_index(b); st.add_index(c)
		st.add_index(b); st.add_index(d); st.add_index(c)
		tri_count += 2

	for j in range(n):
		for i in range(n):
			if lv > 0:
				var in_hole := (i >= half - hole_half and i < half + hole_half
					and j >= half - hole_half and j < half + hole_half)
				if in_hole:
					continue
			var a: int = add_v.call(i, j, false)
			var b: int = add_v.call(i + 1, j, false)
			var c: int = add_v.call(i, j + 1, false)
			var d: int = add_v.call(i + 1, j + 1, false)
			quad.call(a, b, c, d)

	# юбки: внешний периметр всех уровней + внутренний периметр колец
	var edges: Array = [[0, n, 0, n, true]]
	if lv > 0:
		edges.append([half - hole_half, half + hole_half,
			half - hole_half, half + hole_half, false])
	for e in edges:
		var i0: int = e[0]; var i1: int = e[1]
		var j0: int = e[2]; var j1: int = e[3]
		var outward: bool = e[4]
		for i in range(i0, i1):
			var a1: int = add_v.call(i, j0, false)
			var b1: int = add_v.call(i + 1, j0, false)
			var a2: int = add_v.call(i, j0, true)
			var b2: int = add_v.call(i + 1, j0, true)
			if outward: quad.call(a2, b2, a1, b1)
			else: quad.call(a1, b1, a2, b2)
			var c1: int = add_v.call(i, j1, false)
			var d1: int = add_v.call(i + 1, j1, false)
			var c2: int = add_v.call(i, j1, true)
			var d2: int = add_v.call(i + 1, j1, true)
			if outward: quad.call(c1, d1, c2, d2)
			else: quad.call(c2, d2, c1, d1)
		for j in range(j0, j1):
			var a1: int = add_v.call(i0, j, false)
			var b1: int = add_v.call(i0, j + 1, false)
			var a2: int = add_v.call(i0, j, true)
			var b2: int = add_v.call(i0, j + 1, true)
			if outward: quad.call(a1, b1, a2, b2)
			else: quad.call(a2, b2, a1, b1)
			var c1: int = add_v.call(i1, j, false)
			var d1: int = add_v.call(i1, j + 1, false)
			var c2: int = add_v.call(i1, j, true)
			var d2: int = add_v.call(i1, j + 1, true)
			if outward: quad.call(c2, d2, c1, d1)
			else: quad.call(c1, d1, c2, d2)

	return st.commit()

## кольца следуют за камерой: снап к удвоенной ячейке уровня (сохраняет
## совпадение сеток соседних уровней)
func _process(_delta: float) -> void:
	var cam := get_viewport().get_camera_3d()
	if cam == null:
		return
	var cx := cam.global_position.x
	var cz := cam.global_position.z
	for lv in range(LEVELS):
		var s := BASE_CELL * pow(2.0, lv + 1)
		_rings[lv].position = Vector3(floorf(cx / s) * s, 0.0, floorf(cz / s) * s)

# ------------------------------------------------------------------ материал
const ZONES_PATH := "res://assets/dem/zones_1024.bin"
const ZONES_N := 1024

func _height_texture() -> ImageTexture:
	var floats := PackedFloat32Array()
	floats.resize(DEM_N * DEM_N)
	for j in range(DEM_N):
		var z := -DEM_HALF + DEM_STEP * float(j)
		for i in range(DEM_N):
			floats[j * DEM_N + i] = height(-DEM_HALF + DEM_STEP * float(i), z)
	var img := Image.create_from_data(DEM_N, DEM_N, false, Image.FORMAT_RF,
		floats.to_byte_array())
	# ПОЛНАЯ точность высоты (R32F). Прежде понижали до half-float (шаг ~3 см) на
	# допущении «Apple GPU не фильтрует R32F» — но A18 Pro (Apple9) его фильтрует;
	# FP16-ступени давали контурные полосы на пологой земле под острым углом.
	# Если на устройстве вдруг заблочит фильтрацию (блочный рельеф) — вернуть RH
	# и вместо этого дизерить высоту перед квантованием.
	img.generate_mipmaps()
	return ImageTexture.create_from_image(img)

## текстура высот — общая для клипмапа и всего, что облегает рельеф (дороги)
var height_texture: ImageTexture

func _ground_material() -> ShaderMaterial:
	var m := ShaderMaterial.new()
	m.shader = load("res://shaders/world/terrain.gdshader")
	height_texture = _height_texture()
	m.set_shader_parameter("height_tex", height_texture)
	m.set_shader_parameter("dem_half", DEM_HALF)
	var f := FileAccess.open(ZONES_PATH, FileAccess.READ)
	if f != null:
		var bytes := f.get_buffer(ZONES_N * ZONES_N)
		var img := Image.create_from_data(ZONES_N, ZONES_N, false, Image.FORMAT_R8, bytes)
		m.set_shader_parameter("zone_tex", ImageTexture.create_from_image(img))
	else:
		push_warning("[terrain] нет карты зон (%s) — вся земля лугом" % ZONES_PATH)
		var img1 := Image.create(4, 4, false, Image.FORMAT_R8)
		m.set_shader_parameter("zone_tex", ImageTexture.create_from_image(img1))
	m.set_shader_parameter("zone_size_m", world_size_m)
	m.set_shader_parameter("wet_level", (abs_min + 6.0) - _h_ref if real_dem else -3.0)
	# ОСНОВА ЗЕМЛИ = РЕАЛЬНАЯ ПОЧВА везде (травы-раскраски больше нет — плоский
	# скан травы был «обоями»; настоящую траву создадим геометрией отдельным слоем).
	# НАСТОЯЩАЯ почва из ФОТО местной почвы Гатчины, СТРУКТУРНО (набор по полю):
	# база — влажный серо-бурый суглинок (комья), низины — плодородный тёмный гумус,
	# сухие пятна — растрескавшаяся светлая. Рельеф общий (loam). Не песок.
	m.set_shader_parameter("soil_c", load("res://assets/materials/created/soil_loam_clods/Color.png"))
	m.set_shader_parameter("soil_dry_c", load("res://assets/materials/created/soil_gatchina/Color.png"))
	m.set_shader_parameter("soil_wet_c", load("res://assets/materials/created/soil_fertile/Color.png"))
	m.set_shader_parameter("soil_n", load("res://assets/materials/created/soil_loam_clods/Normal.png"))
	m.set_shader_parameter("soil_r", load("res://assets/materials/created/soil_loam_clods/Roughness.png"))
	m.set_shader_parameter("soil_ao", load("res://assets/materials/created/soil_loam_clods/AmbientOcclusion.png"))
	m.set_shader_parameter("soil_h", load("res://assets/materials/created/soil_loam_clods/Height.png"))
	_setup_slice(m)
	_setup_moisture(m)
	return m

# ВЛАЖНОСТЬ почвы: канал 1 поля почвы (build_soilfield) → R8-текстура для шейдера
# (мокрая земля темнее/глянцевее). Центр/охват — как у среза.
const SOILF_BIN := "res://assets/life/slice_soilfield.bin"
const SOILF_META := "res://assets/life/slice_soilfield.json"

func _setup_moisture(m: ShaderMaterial) -> void:
	var fm := FileAccess.open(SOILF_META, FileAccess.READ)
	var fb := FileAccess.open(SOILF_BIN, FileAccess.READ)
	if fm == null or fb == null:
		m.set_shader_parameter("moisture_half", 0.0)
		return
	var meta: Dictionary = JSON.parse_string(fm.get_as_text())
	var n := int(meta["n"])
	var raw := fb.get_buffer(n * n * 4)
	if raw.size() != n * n * 4:
		m.set_shader_parameter("moisture_half", 0.0)
		return
	var ch := PackedByteArray()
	ch.resize(n * n)
	for k in range(n * n):
		ch[k] = raw[k * 4 + 1]                 # канал 1 = текущая влага
	var img := Image.create_from_data(n, n, false, Image.FORMAT_R8, ch)
	m.set_shader_parameter("moisture_tex", ImageTexture.create_from_image(img))
	m.set_shader_parameter("moisture_center", Vector2(float(meta["cx"]), float(meta["cy"])))
	m.set_shader_parameter("moisture_half", float(meta["half_m"]))
	print("[terrain] влажность почвы: поле %d² подключено (мокрая земля темнее)" % n)

# --- ВЕРТИКАЛЬНЫЙ СРЕЗ: детальная карта поверхностей Дворцового парка ---
const SLICE_BIN := "res://assets/dem/slice_palace.bin"
const SLICE_META := "res://assets/dem/slice_palace.json"

func _setup_slice(m: ShaderMaterial) -> void:
	var fm := FileAccess.open(SLICE_META, FileAccess.READ)
	var fb := FileAccess.open(SLICE_BIN, FileAccess.READ)
	if fm == null or fb == null:
		m.set_shader_parameter("slice_half", 0.0)     # срез выключен
		return
	var meta: Dictionary = JSON.parse_string(fm.get_as_text())
	var n := int(meta["n"])
	var bytes := fb.get_buffer(n * n)
	if bytes.size() != n * n:
		m.set_shader_parameter("slice_half", 0.0)
		return
	var img := Image.create_from_data(n, n, false, Image.FORMAT_R8, bytes)
	m.set_shader_parameter("slice_tex", ImageTexture.create_from_image(img))
	m.set_shader_parameter("slice_center", Vector2(float(meta["cx"]), float(meta["cy"])))
	m.set_shader_parameter("slice_half", float(meta["half_m"]))
	print("[terrain] срез «Дворцовый парк»: %d² (%.0f м/пкс), центр (%.0f,%.0f), ±%.0f м" % [
		n, float(meta["mpp"]), float(meta["cx"]), float(meta["cy"]), float(meta["half_m"])])

# ------------------------------------------------------------------ физика
## рельеф — твёрдое тело: heightmap по той же height()
func build_collision() -> void:
	var n := collision_res + 1
	var cell := world_size_m / float(collision_res)
	var heights := PackedFloat32Array()
	heights.resize(n * n)
	var half := world_size_m * 0.5
	for j in range(n):
		for i in range(n):
			heights[j * n + i] = height(-half + i * cell, -half + j * cell)
	var shape := HeightMapShape3D.new()
	shape.map_width = n
	shape.map_depth = n
	shape.map_data = heights
	var cs := CollisionShape3D.new()
	cs.shape = shape
	cs.scale = Vector3(cell, 1.0, cell)
	var body := StaticBody3D.new()
	body.add_child(cs)
	add_child(body)
	print("[terrain] коллизия: heightmap %d² (ячейка %.0f м) — рельеф твёрдый" % [n, cell])

func report() -> Dictionary:
	return {"size_m": DEM_HALF * 2.0, "relief_m": max_h - min_h,
		"min_h": min_h, "max_h": max_h, "tris": tri_count,
		"real": real_dem, "abs_min": abs_min, "abs_max": abs_max,
		"clip_levels": LEVELS, "base_cell": BASE_CELL}
