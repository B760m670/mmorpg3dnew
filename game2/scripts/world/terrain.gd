class_name Terrain
extends Node3D
## Ф3.1 «Земля» — настоящий рельеф в РЕАЛЬНОМ масштабе (1 юнит = 1 метр).
## Чанковый heightfield: пологая парковая равнина Гатчины с озёрной впадиной.
## Высота задаётся аналитически (height()), нормали — точным конечным разностям,
## поэтому объекты можно сажать ровно на поверхность. Масштаб/рельеф проверяем
## числами (report()): протяжённость в метрах, перепад высот, число треугольников.

@export var world_size_m: float = 1024.0        # квадрат 1×1 км вокруг начала
@export var chunks_per_side: int = 8             # 8×8 чанков → чанк 128 м
@export var chunk_res: int = 32                  # 32 квада/чанк → шаг ~4 м
@export var tile_m: float = 4.0                  # масштаб тайла материала, м

var _noise: FastNoiseLite
var _ridge: FastNoiseLite
var tri_count: int = 0
var min_h: float = INF
var max_h: float = -INF

# озёрная впадина (Белое озеро Гатчины — условно)
const LAKE_CENTER := Vector2(210.0, -150.0)
const LAKE_RADIUS := 170.0
const LAKE_DEPTH := 9.0
const WATER_LEVEL := -3.0

func _init() -> void:
	_noise = FastNoiseLite.new()
	_noise.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	_noise.frequency = 0.0016                     # крупные пологие холмы
	_noise.fractal_octaves = 5
	_noise.fractal_lacunarity = 2.1
	_noise.fractal_gain = 0.5
	_ridge = FastNoiseLite.new()
	_ridge.noise_type = FastNoiseLite.TYPE_SIMPLEX
	_ridge.frequency = 0.02                        # мелкая неровность грунта
	_ridge.fractal_octaves = 3

## высота поверхности (м) в точке мира
func height(x: float, z: float) -> float:
	var h := _noise.get_noise_2d(x, z) * 14.0            # ±14 м крупных холмов
	h += _noise.get_noise_2d(x * 3.7 + 100.0, z * 3.7) * 4.0   # ±4 м средних всхолмлений
	h += _ridge.get_noise_2d(x, z) * 0.6                 # ±0.6 м микрорельеф
	# озёрная впадина: плавное понижение к центру
	var d := Vector2(x, z).distance_to(LAKE_CENTER)
	h -= smoothstep(LAKE_RADIUS, LAKE_RADIUS * 0.25, d) * LAKE_DEPTH
	return h

func normal_at(x: float, z: float) -> Vector3:
	var e := 1.0
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
	print("[terrain] %.0f×%.0f м, чанков %d², шаг %.1f м, перепад %.1f..%.1f м, △=%d" % [
		world_size_m, world_size_m, chunks_per_side, chunk / float(chunk_res),
		min_h, max_h, tri_count])

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
			var n := normal_at(x, z)
			st.set_normal(n)
			st.set_color(_ground_color(x, z, y, n))
			st.set_uv(Vector2(x, z) / tile_m)
			st.add_vertex(Vector3(x, y, z))
	var row := res + 1
	for j in range(res):
		for i in range(res):
			var a := j * row + i
			var b := a + 1
			var c := a + row
			var d := c + 1
			st.add_index(a); st.add_index(c); st.add_index(b)
			st.add_index(b); st.add_index(c); st.add_index(d)
			tri_count += 2
	return st.commit()

## цвет земли по склону и высоте: трава на пологом, грунт на склонах,
## сырой тёмный у озёрного дна — через вершинные цвета (без шейдера)
func _ground_color(x: float, z: float, y: float, n: Vector3) -> Color:
	var grass := Color(0.24, 0.32, 0.14)
	var earth := Color(0.32, 0.25, 0.16)
	var wet := Color(0.16, 0.19, 0.15)
	var slope := clampf((1.0 - n.y) * 3.5, 0.0, 1.0)     # 0 плоско, 1 круто
	var col := grass.lerp(earth, slope)
	# лёгкая пятнистость травы
	var v := _ridge.get_noise_2d(x * 0.7, z * 0.7) * 0.5 + 0.5
	col = col.lerp(col.darkened(0.18), v * 0.5)
	# у озёрного дна — сырой тёмный грунт
	if y < WATER_LEVEL + 2.5:
		col = col.lerp(wet, clampf((WATER_LEVEL + 2.5 - y) / 4.0, 0.0, 1.0))
	return col

func _ground_material() -> ShaderMaterial:
	# специальный террейн-шейдер: диффуз без зеркалки (убирает френелевскую
	# белую кайму у горизонта), цвет из вершинного COLOR (склон/высота)
	var m := ShaderMaterial.new()
	m.shader = load("res://shaders/world/terrain.gdshader")
	return m

func report() -> Dictionary:
	return {"size_m": world_size_m, "relief_m": max_h - min_h,
		"min_h": min_h, "max_h": max_h, "tris": tri_count}
