class_name WaterBodies
extends Node3D
## Шаг 1 генплана: ВОДА по реальным контурам (game2/data/real/water.json —
## Белое/Серебряное/Чёрное озёра, Карпин пруд, каналы; Overture Maps).
## Каждый водоём — меш зеркала воды, триангулированный из реального полигона;
## уровень = медиана высоты рельефа по контуру (в DEM гладь воды и есть уровень)
## + 0.15 м над дном, чтобы читалась поверх террейна. Реки-линии — позже.

const WATER_JSON := "res://data/real/water.json"
const LIFT := 0.15                  # подъём зеркала над рельефом дна, м

var terrain: Terrain
var count_built: int = 0
var lake_levels: Dictionary = {}    # имя → уровень (м мира)

func build() -> void:
	var f := FileAccess.open(WATER_JSON, FileAccess.READ)
	if f == null:
		push_warning("[water] нет данных воды (%s)" % WATER_JSON)
		return
	var arr: Array = JSON.parse_string(f.get_as_text())
	if arr == null:
		push_warning("[water] не разобрался JSON")
		return
	var mat := _water_material()
	var skipped := 0
	for rec_v in arr:
		var rec: Dictionary = rec_v
		if not rec.has("polys"):
			continue
		for poly in rec["polys"]:
			var outer: Array = poly[0]          # внешнее кольцо (дырки позже)
			if outer.size() < 3:
				continue
			# мега-объекты (Финский залив, длинные реки): контур уходит за
			# пределы сетки высот → уровень по краевым значениям ложится ВЫШЕ
			# рельефа и лист накрывает мир. Пропускаем; реки — отдельным слоем.
			if _ring_out_of_bounds(outer):
				skipped += 1
				continue
			var mesh := _build_surface_mesh(outer, rec.get("name"))
			if mesh != null:
				var mi := MeshInstance3D.new()
				mi.mesh = mesh
				mi.material_override = mat
				add_child(mi)
				count_built += 1
	print("[water] зеркал воды: %d (реальные контуры); пропущено мега/внешних: %d" % [
		count_built, skipped])

const BOUND_M := 6800.0             # в пределах территории и сетки высот
const MAX_DIM_M := 3500.0           # крупнее — не озеро Гатчины (залив/река)

func _ring_out_of_bounds(ring: Array) -> bool:
	var minx := INF; var maxx := -INF
	var miny := INF; var maxy := -INF
	for p in ring:
		minx = minf(minx, p[0]); maxx = maxf(maxx, p[0])
		miny = minf(miny, p[1]); maxy = maxf(maxy, p[1])
	if minx < -BOUND_M or maxx > BOUND_M or miny < -BOUND_M or maxy > BOUND_M:
		return true
	return (maxx - minx) > MAX_DIM_M or (maxy - miny) > MAX_DIM_M

func _build_surface_mesh(ring: Array, name_v) -> ArrayMesh:
	# уровень зеркала: медиана рельефа по контуру
	var hs: Array[float] = []
	var pts2 := PackedVector2Array()
	var n := ring.size()
	# GeoJSON-кольцо замкнуто (последняя точка = первой) — убираем дубль
	if n > 1 and ring[0][0] == ring[n - 1][0] and ring[0][1] == ring[n - 1][1]:
		n -= 1
	for k in range(n):
		var p: Array = ring[k]
		var x: float = p[0]
		var z: float = -p[1]                    # y=север → z=-север
		pts2.append(Vector2(x, z))
		hs.append(terrain.height(x, z) if terrain != null else 0.0)
	hs.sort()
	var level: float = hs[hs.size() / 2] + LIFT
	if name_v != null:
		lake_levels[name_v] = level

	var idx := Geometry2D.triangulate_polygon(pts2)
	if idx.is_empty():
		# попробуем обратный обход
		pts2.reverse()
		idx = Geometry2D.triangulate_polygon(pts2)
		if idx.is_empty():
			return null
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	for p in pts2:
		st.set_normal(Vector3.UP)
		st.set_uv(Vector2(p.x, p.y) * 0.05)
		st.add_vertex(Vector3(p.x, level, p.y))
	for i in idx:
		st.add_index(i)
	return st.commit()

func _water_material() -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = Color(0.04, 0.10, 0.12)    # тёмная северная вода
	m.roughness = 0.04                           # зеркальное отражение неба
	m.metallic = 0.0
	m.metallic_specular = 0.7
	return m
