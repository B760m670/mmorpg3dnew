class_name CityBuildings
extends Node3D
## ГОРОД ГАТЧИНЫ. Два слоя, оба уже поставлены на рельеф и триангулированы
## офлайн (проверено числами, Godot в песочнице нет):
##   · ФОН — 35 844 реальных следа зданий, массинг-коробки эпохи 1894
##     (tools/build_city.py → gatchina_city.bin). Дальний силуэт, не крупный план.
##   · HERO — Большой Гатчинский дворец, массинг ПО РЕАЛЬНОМУ 44-вершинному
##     следу с переменной высотой и башнями (tools/build_palace.py →
##     gatchina_palace.bin). Каменный материал (пудостский известняк).
## Здесь только сборка ArrayMesh из буферов и материалы; вся геометрия и
## привязка к DEM просчитаны в инструментах. Формат буфера — CITY (2 поверхности:
## 0 стены, 1 кровли), координаты мировые (X=восток, Z=−север, ноль=дворец).
##
## Высоты фона ВЫВЕДЕНЫ (данные их не несут) — плейсхолдер массинга: плоские
## кровли, без фасадных членений. Детализация hero-дворца (окна, карнизы,
## скатные кровли, купол) — следующие шаги по референсам (docs/slice1_palace.md).

const CITY_PATH := "res://assets/city/gatchina_city.bin"
const PALACE_PATH := "res://assets/city/gatchina_palace.bin"

var terrain: Terrain                 # геометрия уже привязана; поле для симметрии API
var tri_count := 0

func build() -> void:
	_add_layer(CITY_PATH, _wall_material(), _roof_material())
	_add_layer(PALACE_PATH, _stone_material(), _stone_roof_material())
	print("[city] Гатчина: фон+дворец, △=%d (реальные следы, эпоха 1894)" % tri_count)

## читает буфер CITY и вешает узел с двумя материалами (стены/кровли)
func _add_layer(path: String, mat_wall: Material, mat_roof: Material) -> void:
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		push_warning("[city] нет буфера (%s)" % path)
		return
	if f.get_buffer(4) != "CITY".to_ascii_buffer():
		push_warning("[city] неверная сигнатура: %s" % path)
		return
	var _version := f.get_32()
	var surfaces := f.get_32()

	var am := ArrayMesh.new()
	for si in range(surfaces):
		var vcount := f.get_32()
		var icount := f.get_32()
		var fl := f.get_buffer(vcount * 32).to_float32_array()   # 8 float32 на вершину
		var verts := PackedVector3Array(); verts.resize(vcount)
		var norms := PackedVector3Array(); norms.resize(vcount)
		var uvs := PackedVector2Array(); uvs.resize(vcount)
		for k in range(vcount):
			var o := k * 8
			verts[k] = Vector3(fl[o], fl[o + 1], fl[o + 2])
			norms[k] = Vector3(fl[o + 3], fl[o + 4], fl[o + 5])
			uvs[k] = Vector2(fl[o + 6], fl[o + 7])
		var idx := f.get_buffer(icount * 4).to_int32_array()
		var arr := []
		arr.resize(Mesh.ARRAY_MAX)
		arr[Mesh.ARRAY_VERTEX] = verts
		arr[Mesh.ARRAY_NORMAL] = norms
		arr[Mesh.ARRAY_TEX_UV] = uvs
		arr[Mesh.ARRAY_INDEX] = PackedInt32Array(idx)
		am.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
		tri_count += icount / 3

	am.surface_set_material(0, mat_wall)
	if surfaces > 1:
		am.surface_set_material(1, mat_roof)

	var mi := MeshInstance3D.new()
	mi.mesh = am
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	add_child(mi)

# --- фон: штукатурный фасад / выветренная кровля. cull_disabled — буфер не
# гарантирует намотку (нормали заданы явно, тела замкнуты), так надёжнее ---
func _wall_material() -> StandardMaterial3D:
	return _flat(Color(0.74, 0.70, 0.62), 0.88)

func _roof_material() -> StandardMaterial3D:
	return _flat(Color(0.28, 0.27, 0.29), 0.72)

# --- hero-дворец: пудостский известняк (тёплый серо-охристый), кровля-жесть ---
func _stone_material() -> StandardMaterial3D:
	return _flat(Color(0.80, 0.74, 0.62), 0.80)

func _stone_roof_material() -> StandardMaterial3D:
	return _flat(Color(0.24, 0.25, 0.27), 0.60)

func _flat(col: Color, rough: float) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = col
	m.roughness = rough
	m.metallic = 0.0
	m.cull_mode = BaseMaterial3D.CULL_DISABLED
	return m
