class_name Terrain
extends Node3D
## Земля игры — РЕАЛЬНЫЙ рельеф территории Гатчины (1 юнит = 1 метр).
## Высоты — из настоящих измерений (SRTM/ASTER, terrarium z13 ≈10 м/пиксель),
## собраны конвейером tools/fetch_dem_gatchina.py в сетку int16-см
## (513×513 × 32 м = 16384 м; высоты 62–142 м — Гатчинская равнина).
## Начало координат мира — центр территории (высота там = 0), сетка даёт
## height(x,z) билинейно; поверх — микрорельеф-шум ±0.5 м как слой детализации
## (разрешение DEM ~10 м, вблизи нужна мелкая неровность грунта).
## Если файла данных нет — честный фолбэк на процедурный рельеф с пометкой.

@export var world_size_m: float = 12288.0       # территория 12.3×12.3 км
@export var chunks_per_side: int = 12            # чанк 1024 м
@export var chunk_res: int = 32                  # 32 квада/чанк → шаг 32 м
@export var tile_m: float = 4.0                  # масштаб тайла материала, м

const DEM_PATH := "res://assets/dem/gatchina_cm.bin"
const DEM_N := 513
const DEM_STEP := 32.0
const DEM_HALF := (DEM_N - 1) * DEM_STEP * 0.5   # 8192 м

var real_dem: bool = false
var _dem: PackedByteArray
var _h_ref: float = 0.0                          # высота центра (дворец) — ноль мира
var abs_min: float = 0.0                         # реальные высоты территории, м
var abs_max: float = 0.0

var _noise: FastNoiseLite
var _ridge: FastNoiseLite
var tri_count: int = 0
var min_h: float = INF
var max_h: float = -INF

func _init() -> void:
	_noise = FastNoiseLite.new()
	_noise.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	_noise.frequency = 0.0016
	_noise.fractal_octaves = 5
	_noise.fractal_lacunarity = 2.1
	_noise.fractal_gain = 0.5
	_ridge = FastNoiseLite.new()
	_ridge.noise_type = FastNoiseLite.TYPE_SIMPLEX
	_ridge.frequency = 0.02                        # мелкая неровность грунта
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
	for k in range(0, DEM_N * DEM_N, 7):          # быстрая выборка статистики
		var v := float(_dem.decode_s16(k * 2)) / 100.0
		abs_min = minf(abs_min, v)
		abs_max = maxf(abs_max, v)

func _dem_at(i: int, j: int) -> float:
	i = clampi(i, 0, DEM_N - 1)
	j = clampi(j, 0, DEM_N - 1)
	return float(_dem.decode_s16((j * DEM_N + i) * 2)) / 100.0

## реальная высота из сетки (билинейно). x=восток, z=юг (строка 0 — север).
func _dem_height(x: float, z: float) -> float:
	var u := (x + DEM_HALF) / DEM_STEP
	var v := (z + DEM_HALF) / DEM_STEP
	var i := int(floor(u))
	var j := int(floor(v))
	var fx := u - float(i)
	var fy := v - float(j)
	var h00 := _dem_at(i, j)
	var h10 := _dem_at(i + 1, j)
	var h01 := _dem_at(i, j + 1)
	var h11 := _dem_at(i + 1, j + 1)
	return lerp(lerp(h00, h10, fx), lerp(h01, h11, fx), fy)

## высота поверхности мира (м); 0 — уровень центра территории.
## Гладкий DEM без шума: видимая поверхность, коллизия и вода согласованы;
## мелкая неровность грунта — пиксельными нормалями в шейдере (без смещения).
func height(x: float, z: float) -> float:
	if real_dem:
		return _dem_height(x, z) - _h_ref
	# фолбэк: процедурная равнина (ИМИТАЦИЯ, помечено)
	var hp := _noise.get_noise_2d(x, z) * 14.0
	hp += _noise.get_noise_2d(x * 3.7 + 100.0, z * 3.7) * 4.0
	return hp

func normal_at(x: float, z: float) -> Vector3:
	var e := 8.0 if real_dem else 1.0              # шаг производной ~ разрешению данных
	var hl := height(x - e, z)
	var hr := height(x + e, z)
	var hd := height(x, z - e)
	var hu := height(x, z + e)
	return Vector3(hl - hr, 2.0 * e, hd - hu).normalized()

func build() -> void:
	var mat := _ground_material()
	var half := world_size_m * 0.5
	var chunk := world_size_m / float(chunks_per_side)
	tri_count = 0
	for cj in range(chunks_per_side):
		for ci in range(chunks_per_side):
			var ox := -half + ci * chunk
			var oz := -half + cj * chunk
			var mi := MeshInstance3D.new()
			mi.mesh = _build_chunk_mesh(ox, oz, chunk, chunk_res)
			mi.material_override = mat
			add_child(mi)
	print("[terrain] %.0f×%.0f м, рельеф=%s, абс. высоты %.0f..%.0f м, перепад %.1f м, △=%d" % [
		world_size_m, world_size_m,
		"РЕАЛЬНЫЙ (Гатчина, DEM)" if real_dem else "процедурный (фолбэк!)",
		abs_min, abs_max, max_h - min_h, tri_count])

func _build_chunk_mesh(ox: float, oz: float, size: float, res: int) -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var step := size / float(res)
	for j in range(res + 1):
		for i in range(res + 1):
			var x := ox + i * step
			var z := oz + j * step
			var y := height(x, z)
			min_h = minf(min_h, y)
			max_h = maxf(max_h, y)
			st.add_vertex(Vector3(x, y, z))   # нормали/цвет считает шейдер на пиксель
	var row := res + 1
	for j in range(res):
		for i in range(res):
			var a := j * row + i
			var b := a + 1
			var c := a + row
			var d := c + 1
			# порядок обхода: лицо грани — ВВЕРХ (Godot front = по часовой сверху)
			st.add_index(a); st.add_index(b); st.add_index(c)
			st.add_index(b); st.add_index(d); st.add_index(c)
			tri_count += 2
	return st.commit()

const ZONES_PATH := "res://assets/dem/zones_1024.bin"
const ZONES_N := 1024

## текстура высот для шейдера (RF, с мип-уровнями): пиксельные нормали и
## гладкое освещение дали — из неё
func _height_texture() -> ImageTexture:
	var floats := PackedFloat32Array()
	floats.resize(DEM_N * DEM_N)
	var half := DEM_HALF
	for j in range(DEM_N):
		var z := -half + DEM_STEP * float(j)
		for i in range(DEM_N):
			floats[j * DEM_N + i] = height(-half + DEM_STEP * float(i), z)
	var img := Image.create_from_data(DEM_N, DEM_N, false, Image.FORMAT_RF,
		floats.to_byte_array())
	# R32F не фильтруется линейно на Apple GPU и llvmpipe → half-float (RH):
	# фильтруется везде, точность ~2 см на наших высотах
	img.convert(Image.FORMAT_RH)
	img.generate_mipmaps()
	return ImageTexture.create_from_image(img)

func _ground_material() -> ShaderMaterial:
	# террейн-шейдер: пиксельные нормали из высот + зоны землепользования
	var m := ShaderMaterial.new()
	m.shader = load("res://shaders/world/terrain.gdshader")
	m.set_shader_parameter("height_tex", _height_texture())
	m.set_shader_parameter("dem_half", DEM_HALF)
	var f := FileAccess.open(ZONES_PATH, FileAccess.READ)
	if f != null:
		var bytes := f.get_buffer(ZONES_N * ZONES_N)
		var img := Image.create_from_data(ZONES_N, ZONES_N, false, Image.FORMAT_R8, bytes)
		m.set_shader_parameter("zone_tex", ImageTexture.create_from_image(img))
	else:
		push_warning("[terrain] нет карты зон (%s) — вся земля будет лугом" % ZONES_PATH)
		var img1 := Image.create(4, 4, false, Image.FORMAT_R8)
		m.set_shader_parameter("zone_tex", ImageTexture.create_from_image(img1))
	m.set_shader_parameter("zone_size_m", world_size_m)
	m.set_shader_parameter("wet_level", (abs_min + 6.0) - _h_ref if real_dem else -3.0)
	return m

## ФИЗИКА: рельеф — твёрдое тело (HeightMapShape по той же height()).
## С этого момента мир не декорация: по нему ходят тела, на него падают предметы.
func build_collision() -> void:
	var n := chunks_per_side * chunk_res + 1        # 385 — как сетка рендера
	var cell := world_size_m / float(n - 1)
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
	cs.scale = Vector3(cell, 1.0, cell)             # ячейка сетки → метры
	var body := StaticBody3D.new()
	body.add_child(cs)
	add_child(body)
	print("[terrain] коллизия: heightmap %d² (ячейка %.0f м) — рельеф стал твёрдым" % [n, cell])

func report() -> Dictionary:
	return {"size_m": world_size_m, "relief_m": max_h - min_h,
		"min_h": min_h, "max_h": max_h, "tris": tri_count,
		"real": real_dem, "abs_min": abs_min, "abs_max": abs_max}
