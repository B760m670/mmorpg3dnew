class_name WaterReal
extends Node3D
## ВОДА — два РАЗНЫХ вещества, а не одна «вода».
##
## Разделение, до которого дошли числами:
##   ПОЛОЖЕНИЕ — из настоящих данных (Overture, water.json): это измеренная
##     реальность, реки Парица и Колпанка там, где они есть на самом деле.
##     ИЗМЕРЕНО, почему не из расчёта: наш DEM даёт русла лишь вдвое лучше
##     случайного (11% против 5.4%) — долины (1.24 м) мельче ошибки данных
##     (5-10 м), река (5-15 м) уже одной ячейки (32 м). Точное положение из
##     такого рельефа вычислить НЕЛЬЗЯ в принципе.
##   ПОВЕДЕНИЕ — из физики: течение по flow_map (из настоящего уклона),
##     глубина из впадин, дно из подводных почв, оптика по измеренным
##     коэффициентам поглощения.
##
## ОЗЕРО и РЕКА отличаются ВЕЩЕСТВОМ (испытано в soil_profile/water_physics):
##   озеро — стоячее, цветёт планктоном (зелёная муть), дно САПРОПЕЛЬ (ил,
##     180 кг/м3, нога проваливается);
##   река — проточная 0.36 м/с, прозрачнее, но несёт глину (бурый оттенок),
##     дно ПРОМЫТЫЙ ПЕСОК (1750 кг/м3, твёрдое).

const WATER_JSON := "res://data/real/water.json"
const FLOW_BIN := "res://assets/dem/flow_map.bin"
const LAKE_BIN := "res://assets/dem/lake_depth_cm.bin"
const GRID_N := 513
const STEP_M := 32.0
const HALF_M := (GRID_N - 1) * STEP_M * 0.5

var terrain: Terrain
var lakes_built := 0
var rivers_built := 0

var _flow_tex: ImageTexture

func build() -> void:
	_load_flow()
	var f := FileAccess.open(WATER_JSON, FileAccess.READ)
	if f == null:
		push_warning("[water] нет данных водоёмов (%s)" % WATER_JSON)
		return
	var data: Variant = JSON.parse_string(f.get_as_text())
	if not data is Array:
		push_warning("[water] данные водоёмов не читаются")
		return

	for item in data:
		var cls := str(item.get("class", ""))
		var subtype := str(item.get("subtype", ""))
		# РЕКА или ОЗЕРО — по типу из настоящих данных
		var is_river: bool = cls.contains("river") or cls.contains("stream") \
			or subtype.contains("river") or subtype.contains("stream") \
			or item.has("lines")
		if item.has("polys"):
			for poly in item["polys"]:
				if poly.size() > 0:
					_build_body(poly[0], is_river)
		elif item.has("lines"):
			for line in item["lines"]:
				_build_ribbon(line)

	print("[water] озёр %d, рек %d — положение из настоящих данных, поведение из физики"
		% [lakes_built, rivers_built])

func _load_flow() -> void:
	var f := FileAccess.open(FLOW_BIN, FileAccess.READ)
	if f == null:
		return
	var b := f.get_buffer(GRID_N * GRID_N * 3)
	if b.size() != GRID_N * GRID_N * 3:
		return
	var img := Image.create_from_data(GRID_N, GRID_N, false, Image.FORMAT_RGB8, b)
	_flow_tex = ImageTexture.create_from_image(img)

## ОЗЕРО: полигон из настоящих данных, уровень — по самой низкой точке берега
func _build_body(ring: Array, is_river: bool) -> void:
	if ring.size() < 3:
		return
	var pts := PackedVector2Array()
	var lowest := INF
	for p in ring:
		var x := float(p[0])
		var z := -float(p[1])                    # данные: север+, движок: z=-север
		if absf(x) > HALF_M or absf(z) > HALF_M:
			return                                # за краем территории не строим
		pts.append(Vector2(x, z))
		if terrain != null:
			lowest = minf(lowest, terrain.height(x, z))
	if pts.size() < 3 or lowest == INF:
		return
	# уровень воды — чуть ниже самой низкой точки контура (берег сухой)
	var level := lowest - 0.15
	var idx := Geometry2D.triangulate_polygon(pts)
	if idx.is_empty():
		return
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	for k in idx:
		st.set_normal(Vector3.UP)
		st.add_vertex(Vector3(pts[k].x, level, pts[k].y))
	st.generate_normals()
	var mi := MeshInstance3D.new()
	mi.mesh = st.commit()
	mi.material_override = _material(is_river)
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(mi)
	if is_river:
		rivers_built += 1
	else:
		lakes_built += 1

## РЕКА-линия: узкая лента по настоящей оси, течёт по flow map
func _build_ribbon(line: Array) -> void:
	if line.size() < 2:
		return
	var pts := PackedVector2Array()
	for p in line:
		var x := float(p[0])
		var z := -float(p[1])
		if absf(x) > HALF_M or absf(z) > HALF_M:
			continue
		pts.append(Vector2(x, z))
	if pts.size() < 2:
		return
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var half_w := 3.0                            # ширина рек Гатчины ~5-8 м
	var base := 0
	for i in range(pts.size()):
		var dir := (pts[mini(i + 1, pts.size() - 1)] - pts[maxi(i - 1, 0)]).normalized()
		var perp := Vector2(-dir.y, dir.x) * half_w
		var y := (terrain.height(pts[i].x, pts[i].y) if terrain != null else 0.0) - 0.10
		for side in [perp, -perp]:
			st.set_normal(Vector3.UP)
			st.add_vertex(Vector3(pts[i].x + side.x, y, pts[i].y + side.y))
	for i in range(pts.size() - 1):
		var a := base + i * 2
		st.add_index(a); st.add_index(a + 1); st.add_index(a + 2)
		st.add_index(a + 1); st.add_index(a + 3); st.add_index(a + 2)
	var mi := MeshInstance3D.new()
	mi.mesh = st.commit()
	mi.material_override = _material(true)
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(mi)
	rivers_built += 1

## ВЕЩЕСТВО водоёма: озеро и река — разные, по испытанным свойствам
func _material(is_river: bool) -> ShaderMaterial:
	var m := ShaderMaterial.new()
	m.shader = load("res://shaders/world/water_real.gdshader")
	if is_river:
		# РЕКА: проточная, прозрачнее, но несёт глину -> буроватый оттенок;
		# дно — промытый песок (из подводных почв, 1750 кг/м3)
		m.set_shader_parameter("turbidity", 0.28)
		m.set_shader_parameter("tint", Vector3(0.18, 0.20, 0.15))
		m.set_shader_parameter("flow_scale", 1.0)
		m.set_shader_parameter("wave_amp", 0.030)      # течение мельчит волну
		m.set_shader_parameter("wave_len", 1.1)
		m.set_shader_parameter("bottom_color", Vector3(0.31, 0.29, 0.25))
	else:
		# ОЗЕРО: стоячее, цветёт планктоном -> зелёная муть; дно — сапропель
		# (ил, 180 кг/м3, почти чёрный мокрый)
		m.set_shader_parameter("turbidity", 0.55)
		m.set_shader_parameter("tint", Vector3(0.10, 0.26, 0.21))
		m.set_shader_parameter("flow_scale", 0.0)
		# ИЗМЕРЕНО (SMB, разгон 700 м при 5 м/с): на нашем озере волна 9 см
		m.set_shader_parameter("wave_amp", 0.045)
		m.set_shader_parameter("wave_len", 1.8)
		m.set_shader_parameter("bottom_color", Vector3(0.09, 0.09, 0.07))
	m.set_shader_parameter("dem_half", HALF_M)
	if _flow_tex != null:
		m.set_shader_parameter("flow_tex", _flow_tex)
	return m
