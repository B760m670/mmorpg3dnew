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
const LEVEL_BIN := "res://assets/dem/water_level_cm.bin"
const GRID_N := 513
const STEP_M := 32.0
const HALF_M := (GRID_N - 1) * STEP_M * 0.5
const NO_WATER := -32768        # маркер растра уровня: здесь воды нет

var terrain: Terrain
var lakes_built := 0
var rivers_built := 0

var _flow_tex: ImageTexture
var _level: PackedByteArray     # растр уреза воды (int16, см), из carve_water_beds.py
var _biggest_w := 0.0
var _biggest := ""

func build() -> void:
	_load_flow()
	_load_level()
	_load_park_water()
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
	if _biggest != "":
		print(_biggest)

func _load_flow() -> void:
	var f := FileAccess.open(FLOW_BIN, FileAccess.READ)
	if f == null:
		return
	var b := f.get_buffer(GRID_N * GRID_N * 3)
	if b.size() != GRID_N * GRID_N * 3:
		return
	var img := Image.create_from_data(GRID_N, GRID_N, false, Image.FORMAT_RGB8, b)
	_flow_tex = ImageTexture.create_from_image(img)

func _load_level() -> void:
	var f := FileAccess.open(LEVEL_BIN, FileAccess.READ)
	if f == null:
		return
	var b := f.get_buffer(GRID_N * GRID_N * 2)
	if b.size() == GRID_N * GRID_N * 2:
		_level = b

# Урез в парке — из МЕТРОВОГО растра (tools/build_park_dem.py). Общая сетка
# 32 м не описывает пруд в 60-200 м: урез из неё выходил выше берега, и гладь
# висела плитой над землёй. В парке спрашиваем сначала метровую карту.
const PARK_WATER := "res://assets/dem/park_water_cm.bin"
var _park_w: PackedByteArray

func _load_park_water() -> void:
	if terrain == null or terrain.park_n == 0:
		return
	var f := FileAccess.open(PARK_WATER, FileAccess.READ)
	if f == null:
		return
	var b := f.get_buffer(terrain.park_n * terrain.park_n * 2)
	if b.size() == terrain.park_n * terrain.park_n * 2:
		_park_w = b

func _park_level_at(x: float, z: float) -> float:
	if _park_w.is_empty():
		return NAN
	var n: int = terrain.park_n
	var i := int(roundf(x - terrain.park_cx + terrain.park_half))
	var j := int(roundf(terrain.park_cy + terrain.park_half - (-z)))
	if i < 0 or j < 0 or i >= n or j >= n:
		return NAN
	var v := _park_w.decode_s16((j * n + i) * 2)
	if v == NO_WATER:
		return NAN
	return float(v) / 100.0 - terrain.h_ref

## Урез воды из растра (см → м). Возвращает NAN, если в этой клетке воды нет.
func level_at(x: float, z: float) -> float:
	# В ОКНЕ ПАРКА действует ТОЛЬКО метровый растр. Грубый (32 м) там нельзя
	# спрашивать даже как запасной: его уровни в парке заведомо неверны, и
	# именно они давали воду на 10 м ниже земли рядом с прудом.
	if terrain != null and terrain.park_weight(x, z) > 0.0:
		return _park_level_at(x, z)
	if _level.is_empty() or terrain == null:
		return NAN
	var i := int(roundf((x + HALF_M) / STEP_M))
	var j := int(roundf((z + HALF_M) / STEP_M))
	if i < 0 or j < 0 or i >= GRID_N or j >= GRID_N:
		return NAN
	var v := _level.decode_s16((j * GRID_N + i) * 2)
	if v == NO_WATER:
		return NAN
	# растр в АБСОЛЮТНЫХ метрах; мир отсчитывается от нуля-дворца
	return float(v) / 100.0 - terrain.h_ref

## ОЗЕРО: полигон из настоящих данных, урез — из растра (испечён вместе с чашей)
func _build_body(ring: Array, is_river: bool) -> void:
	if ring.size() < 3:
		return
	var pts := PackedVector2Array()
	var cen := Vector2.ZERO
	for p in ring:
		var x := float(p[0])
		var z := -float(p[1])                    # данные: север+, движок: z=-север
		if absf(x) > HALF_M or absf(z) > HALF_M:
			return                                # за краем территории не строим
		pts.append(Vector2(x, z))
		cen += Vector2(x, z)
	if pts.size() < 3:
		return
	cen /= float(pts.size())
	# УРЕЗ ВОДЫ берём из растра water_level_cm.bin — того самого, по которому
	# вырезана чаша (tools/carve_water_beds.py). Это принципиально:
	#   ИЗМЕРЕНО на озере «Тёплая»: SRTM пишет внутри озера ГЛАДЬ, а не дно —
	#   толща воды при уровне=медиана берега выходила -0.19 м, вода была НИЖЕ
	#   земли и ALPHA шейдера падала в 0. Воды не было видно вообще.
	#   Теперь чаша вырезана (толща 1.44..3.50 м), а урез испечён рядом с ней.
	#   Выводить урез заново из уже прорезанного DEM нельзя: он уползал бы вниз
	#   с каждым прогоном инструмента.
	var lv := level_at(cen.x, cen.y)
	if is_nan(lv):
		# вогнутый контур — центр мог попасть на сушу; ищем воду у вершин,
		# сдвинутых на 30% внутрь
		var found := PackedFloat32Array()
		for p2 in pts:
			var q := p2.lerp(cen, 0.3)
			var l2 := level_at(q.x, q.y)
			if not is_nan(l2):
				found.append(l2)
		if found.is_empty():
			return                                # водоём мельче клетки DEM — чаши нет
		found.sort()
		lv = found[found.size() / 2]
	var level: float = lv
	var idx := Geometry2D.triangulate_polygon(pts)
	if idx.is_empty():
		return
	# НАМОТКА. cull_back отсекает грань по обходу, а не по нормали: полигон,
	# свёрнутый «не в ту сторону», был бы невидим сверху и никакой шейдер бы не
	# помог. Данные приходят и по часовой, и против — поэтому обход задаём САМИ.
	# ИЗМЕРЕНО: в Godot (Y вверх, правая тройка) грань смотрит ВВЕРХ, когда
	# обход по (x,z) идёт ПО часовой стрелке (знаковая площадь < 0).
	var area2 := 0.0
	for i in range(pts.size()):
		var a := pts[i]
		var b := pts[(i + 1) % pts.size()]
		area2 += a.x * b.y - b.x * a.y
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	for t in range(0, idx.size(), 3):
		var tri := [idx[t], idx[t + 1], idx[t + 2]]
		if area2 > 0.0:
			tri.reverse()                         # контур был против часовой — разворачиваем
		for k in tri:
			st.set_normal(Vector3.UP)
			st.add_vertex(Vector3(pts[k].x, level, pts[k].y))
	# generate_normals() НЕ зовём: он выводит нормаль из обхода и на плоской
	# глади может дать её вниз — нормаль тут одна и известна, это UP.
	var mi := MeshInstance3D.new()
	mi.mesh = st.commit()
	mi.material_override = _material(is_river)
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(mi)
	if is_river:
		rivers_built += 1
	else:
		lakes_built += 1
	# --- КОНТРОЛЬ ЧИСЛАМИ по самому большому водоёму, а не «на глаз» ---
	var w := pts[0].distance_to(pts[pts.size() / 2])
	if w > _biggest_w:
		_biggest_w = w
		# ТОЛЩУ меряем не в центре ГАБАРИТА (у извилистого озера там суша и
		# замер врёт отрицательным числом), а по точкам, которые ТОЧНО в воде:
		# вершины, сдвинутые внутрь, и только там, где растр подтверждает воду.
		var th := PackedFloat32Array()
		for p3 in pts:
			var q3 := p3.lerp(cen, 0.35)
			if not is_nan(level_at(q3.x, q3.y)):
				th.append(level - terrain.height(q3.x, q3.y))
		var tmin := 0.0
		var tmax := 0.0
		if not th.is_empty():
			th.sort()
			tmin = th[0]
			tmax = th[th.size() - 1]
		_biggest = "[water] самый большой: центр (%.0f, %.0f), урез %.2f м, толща %.2f..%.2f м, △=%d, обход %s" \
			% [cen.x, cen.y, level, tmin, tmax, idx.size() / 3,
			"CCW→развёрнут" if area2 > 0.0 else "CW"]

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
	# ДНО БОЛЬШЕ НЕ ЗАДАЁТСЯ ЦВЕТОМ. Раньше тут стояли bottom_color и картинка
	# дна — то есть вода несла СВОЁ представление о том, что под ней. Теперь
	# сквозь воду видно НАСТОЯЩИЙ рельеф из кадра (преломление по экрану), и
	# цвет воды возникает из поглощения на измеренной толще. Остаётся задать
	# только ВЕЩЕСТВО: сколько в воде взвеси и какого она цвета.
	if is_river:
		# РЕКА: проточная, прозрачнее, но несёт глину -> буроватая взвесь
		m.set_shader_parameter("turbidity", 0.28)
		m.set_shader_parameter("scatter_color", Vector3(0.18, 0.20, 0.15))
		m.set_shader_parameter("flow_scale", 1.0)
		# над руслом ветер сбит берегами и деревьями
		m.set_shader_parameter("wind_ms", 2.0)
	else:
		# ОЗЕРО: стоячее, цветёт планктоном -> зелёная муть
		m.set_shader_parameter("turbidity", 0.55)
		m.set_shader_parameter("scatter_color", Vector3(0.10, 0.26, 0.21))
		m.set_shader_parameter("flow_scale", 0.0)
		# средний летний ветер Ленинградской области; отсюда по Cox & Munk
		# берётся уклон ряби в шейдере
		m.set_shader_parameter("wind_ms", 4.0)
	m.set_shader_parameter("dem_half", HALF_M)
	if _flow_tex != null:
		m.set_shader_parameter("flow_tex", _flow_tex)
	return m
