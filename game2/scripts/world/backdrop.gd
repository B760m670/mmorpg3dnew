class_name Backdrop
extends Node3D
## ДАЛЬНИЙ ФОН — настоящий рельеф РЕГИОНА до горизонта (не фейк-шум, не плоская
## плита). Отдельный статичный слой ПОВЕРХ клипмапа: у мира есть край, но за
## детальной территорией (±8 км) земля продолжается реальными холмами региона
## (залив на СЗ, низины Петербурга на С, плато на Ю) и тонет в дымке у горизонта.
##
## Данные: gatchina_region_cm.bin (tools/build_regional_dem.py) — 257×257×512 м,
## тот же ENU и источник terrarium, что у основного DEM → стык на 8 км сходится
## по высоте (проверено числами: расхождение ~3 м).
##
## Аддитивно и НИЗКО-РИСКОВО: обычный меш с реальными высотами в вершинах (без
## вершинного шейдера), дыра в центре ±HOLE_M под детальный клипмап. Клипмап
## непрозрачен и рисуется поверх в перекрытии — фон виден только дальше 8 км.

const REGION_BIN := "res://assets/dem/gatchina_region_cm.bin"
const REGION_META := "res://assets/dem/meta_region.json"
# дыра под детальный клипмап: клипмап накрывает ±8192 м вокруг КАМЕРЫ, поэтому
# пока наблюдатель в игровой зоне (~±3 км от центра) дыра ±5 км всегда закрыта им
# без щели. В кольце перекрытия (5..8 км) фон чуть ниже — детальный клипмап
# выигрывает по глубине (без z-fight), а его юбка прячет стык.
const HOLE_M := 5000.0
const DROP_M := 3.0               # фон ниже детального рельефа в перекрытии

var terrain: Terrain             # для мировой нулевой высоты (дворец=0)
var tri_count := 0

func build() -> void:
	var fm := FileAccess.open(REGION_META, FileAccess.READ)
	var fb := FileAccess.open(REGION_BIN, FileAccess.READ)
	if fm == null or fb == null:
		push_warning("[backdrop] нет регионального DEM (%s) — фона нет" % REGION_BIN)
		return
	var meta: Dictionary = JSON.parse_string(fm.get_as_text())
	var n := int(meta["grid_n"])
	var step := float(meta["step_m"])
	var raw := fb.get_buffer(n * n * 2)
	if raw.size() != n * n * 2:
		push_warning("[backdrop] региональный DEM неполный — фона нет")
		return

	# высоты (м, абсолютные) → в мировую систему (дворец = 0), как у клипмапа
	var h := PackedFloat32Array(); h.resize(n * n)
	for k in range(n * n):
		h[k] = float(raw.decode_s16(k * 2)) / 100.0
	var ref: float = terrain._h_ref if terrain != null else h[(n / 2) * n + (n / 2)]

	var half := (n - 1) * step * 0.5
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)

	# вершины сеткой; движок: x=восток, z=−север, y=высота−ref
	var wpos := func(i: int, j: int) -> Vector3:
		var east := -half + float(i) * step
		var north := half - float(j) * step
		return Vector3(east, h[j * n + i] - ref - DROP_M, -north)

	var in_hole := func(i: int, j: int) -> bool:
		var east: float = absf(-half + float(i) * step)
		var north: float = absf(half - float(j) * step)
		return maxf(east, north) < HOLE_M

	for j in range(n - 1):
		for i in range(n - 1):
			# пропускаем ячейку, если ВСЯ она в дыре (все 4 угла) — центр под клипмап
			if in_hole.call(i, j) and in_hole.call(i + 1, j) \
					and in_hole.call(i, j + 1) and in_hole.call(i + 1, j + 1):
				continue
			var a: Vector3 = wpos.call(i, j)
			var b: Vector3 = wpos.call(i + 1, j)
			var c: Vector3 = wpos.call(i, j + 1)
			var d: Vector3 = wpos.call(i + 1, j + 1)
			# два треугольника, лицо вверх (нормали посчитает generate_normals)
			st.add_vertex(a); st.add_vertex(b); st.add_vertex(c)
			st.add_vertex(b); st.add_vertex(d); st.add_vertex(c)
			tri_count += 2

	st.generate_normals()
	var mesh := st.commit()

	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	mi.material_override = _material()
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	mi.custom_aabb = AABB(Vector3(-half, -200, -half), Vector3(half * 2, 600, half * 2))
	add_child(mi)
	print("[backdrop] дальний фон: регион %.0f км, △=%d, дыра ±%.0f км (реальный рельеф)" % [
		(n - 1) * step / 1000.0, tri_count, HOLE_M / 1000.0])

# дальний рельеф: приглушённая земля, матовая; настоящие нормали дают силуэт
# холмов под солнцем, а воздушная перспектива (fog окружения) топит даль в небо.
func _material() -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = Color(0.52, 0.48, 0.40)   # земля/лес усреднённо, под дымку
	m.roughness = 1.0
	m.metallic = 0.0
	m.cull_mode = BaseMaterial3D.CULL_BACK
	m.specular_mode = BaseMaterial3D.SPECULAR_DISABLED
	return m
