class_name RoadNetwork
extends Node3D
## ДОРОГИ по реальной сети (Overture: шоссе, улицы, просёлки + железная
## дорога — Варшавская и Балтийская линии существовали к 1894). Каждая
## дорога — лента, облегающая рельеф: высоту лента берёт в ВЕРШИННОМ шейдере
## из ТОЙ ЖЕ текстуры высот, что клипмап-террейн, с тем же выбором mip по
## удалению — дорога лежит на видимой поверхности на любой дистанции
## (CPU-высота на дали разошлась бы со сглаженным LOD-рельефом).
## Эпоха 1894: макадам/грунт/булыжник, никакой разметки. Весь граф — один
## меш, один вызов отрисовки.

const ROADS_PATH := "res://data/real/roads.json"
const STEP_M := 8.0              # шаг вдоль оси — плавные повороты
const BOUND_M := 8100.0          # за краем DEM не строим

var terrain: Terrain
var count_built := 0
var length_km := 0.0
var tri_count := 0

## [ширина м, цвет, покрытие] по классу; 1894: шоссе — макадам (щебень),
## улицы — грунт, пешеходные/парадные — булыжник. Покрытие: 0 грунт,
## 1 макадам, 2 булыжник (текстуры tools/make_materials.py).
func _class_spec(cls: String) -> Array:
	match cls:
		"trunk": return [10.0, Color(0.44, 0.40, 0.33), 1.0]
		"primary": return [9.0, Color(0.42, 0.38, 0.31), 1.0]
		"secondary": return [7.5, Color(0.40, 0.36, 0.29), 1.0]
		"tertiary": return [6.5, Color(0.37, 0.32, 0.25), 0.0]
		"residential": return [5.5, Color(0.34, 0.29, 0.22), 0.0]
		"living_street": return [5.5, Color(0.38, 0.35, 0.30), 2.0]
		"pedestrian": return [2.5, Color(0.38, 0.35, 0.30), 2.0]
		"standard_gauge": return [3.2, Color(0.24, 0.22, 0.20), 1.0]  # ж/д насыпь
		_: return [5.0, Color(0.34, 0.29, 0.22), 0.0]

func build() -> void:
	var f := FileAccess.open(ROADS_PATH, FileAccess.READ)
	if f == null:
		push_warning("[roads] нет данных дорог (%s)" % ROADS_PATH)
		return
	var data: Variant = JSON.parse_string(f.get_as_text())
	if not data is Array:
		push_warning("[roads] данные дорог не читаются")
		return
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var vbase := 0
	for r in data:
		var spec := _class_spec(str(r.get("class", "unknown")))
		var found := false
		for line in r.get("lines", []):
			var nb := _ribbon(st, line, float(spec[0]) * 0.5, spec[1],
				float(spec[2]), vbase)
			found = found or nb != vbase
			vbase = nb
		if found:
			count_built += 1
	var mi := MeshInstance3D.new()
	mi.mesh = st.commit()
	var mat := ShaderMaterial.new()
	mat.shader = load("res://shaders/world/road.gdshader")
	mat.set_shader_parameter("height_tex", terrain.height_texture)
	mat.set_shader_parameter("dem_half", Terrain.DEM_HALF)
	for pair in [["dirt_alb", "dirt_alb"], ["dirt_nr", "dirt_nr"],
			["mac_alb", "macadam_alb"], ["mac_nr", "macadam_nr"],
			["cob_alb", "cobble_alb"], ["cob_nr", "cobble_nr"]]:
		mat.set_shader_parameter(pair[0],
			load("res://assets/materials/%s.png" % pair[1]))
	mi.material_override = mat
	# лента ездит по высоте в шейдере — граница отсечения широкая, как у колец
	mi.custom_aabb = AABB(Vector3(-Terrain.DEM_HALF, -200, -Terrain.DEM_HALF),
		Vector3(Terrain.DEM_HALF * 2, 600, Terrain.DEM_HALF * 2))
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(mi)
	print("[roads] сеть: %d дорог, %.1f км, △=%d (реальные оси, эпоха 1894)" % [
		count_built, length_km, tri_count])

## лента вдоль ломаной: данные (x=восток, y=север) → движок (x, z=-север);
## сегменты за краем DEM рвут ленту, длинные звенья дробятся шагом STEP_M
func _ribbon(st: SurfaceTool, line: Array, half: float, col: Color,
		mat_id: float, base: int) -> int:
	var pts: PackedVector2Array = []
	for k in range(line.size()):
		var p := Vector2(float(line[k][0]), -float(line[k][1]))
		if absf(p.x) > BOUND_M or absf(p.y) > BOUND_M:
			base = _emit(st, pts, half, col, mat_id, base)
			pts.clear()
			continue
		if pts.is_empty():
			pts.append(p)
			continue
		var a := pts[pts.size() - 1]
		var d := a.distance_to(p)
		if d < 0.01:
			continue
		var n := int(ceil(d / STEP_M))
		for s in range(1, n + 1):
			pts.append(a.lerp(p, float(s) / float(n)))
	return _emit(st, pts, half, col, mat_id, base)

func _emit(st: SurfaceTool, pts: PackedVector2Array, half: float,
		col: Color, mat_id: float, base: int) -> int:
	var n := pts.size()
	if n < 2:
		return base
	var s_along := 0.0
	var last_dir := Vector2.RIGHT
	for i in range(n):
		var dir := pts[mini(i + 1, n - 1)] - pts[maxi(i - 1, 0)]
		if dir.length_squared() < 1e-6:
			dir = last_dir
		else:
			dir = dir.normalized()
			last_dir = dir
		var perp := Vector2(-dir.y, dir.x) * half
		if i > 0:
			s_along += pts[i - 1].distance_to(pts[i])
		for side in [perp, -perp]:
			st.set_normal(Vector3.UP)
			st.set_color(col)
			st.set_uv(Vector2(0.0 if side == perp else 1.0, s_along))
			st.set_uv2(Vector2(mat_id, half * 2.0))   # покрытие + ширина, м
			st.add_vertex(Vector3(pts[i].x + side.x, 0.0, pts[i].y + side.y))
	for i in range(n - 1):
		var a := base + i * 2
		# обе стороны видимы (cull_disabled) — порядок не критичен
		st.add_index(a); st.add_index(a + 1); st.add_index(a + 2)
		st.add_index(a + 1); st.add_index(a + 3); st.add_index(a + 2)
	tri_count += (n - 1) * 2
	length_km += s_along / 1000.0
	return base + n * 2

func report() -> Dictionary:
	return {"built": count_built, "km": length_km, "tris": tri_count}
