class_name ConstructionKit
extends RefCounted
## БИБЛИОТЕКА ПЕРЕИСПОЛЬЗУЕМЫХ ЭЛЕМЕНТОВ КОНСТРУКЦИИ.
## Как трава и камни — переиспользуемые объекты, так и здания собираются из общих
## элементов: настоящие PBR-материалы (кирпич/штукатурка/камень/дерево/кровля) и
## типовые детали (окно, дверь, труба, угловой камень). Каждый материал и каждый
## меш-элемент создаётся ОДИН раз и переиспользуется всеми зданиями (kit-of-parts).
##
## Экземпляр этого класса — общий «склад» деталей; BuildingComposer берёт отсюда
## материалы и меши и расставляет их, не создавая дубликатов.

const TEX := "res://world/textures/"

var _mats: Dictionary = {}     # имя материала -> StandardMaterial3D (кэш)
var _meshes: Dictionary = {}   # имя элемента  -> Mesh (кэш)

# --- материалы: настоящий PBR, тайлятся по поверхности (triplanar) ---
func material(name: String) -> StandardMaterial3D:
	if _mats.has(name):
		return _mats[name]
	var m := StandardMaterial3D.new()
	match name:
		"glass":
			m.albedo_color = Color(0.10, 0.14, 0.20)
			m.roughness = 0.08; m.metallic = 0.1
			m.metallic_specular = 0.6
		"gold":
			m.albedo_color = Color(0.80, 0.62, 0.18)
			m.roughness = 0.28; m.metallic = 1.0
		_:
			var tex := _tex_name(name)
			m.albedo_texture = _load(TEX + tex + "_albedo.png")
			m.normal_enabled = true
			m.normal_texture = _load(TEX + tex + "_normal.png")
			var rough := _load(TEX + tex + "_rough.png")
			if rough != null:
				m.roughness_texture = rough
			m.uv1_triplanar = true
			m.uv1_world_triplanar = true
			m.uv1_scale = _scale(name)
	_mats[name] = m
	return m

func _tex_name(name: String) -> String:
	# логическое имя элемента -> файл текстуры библиотеки
	match name:
		"brick": return "rustic"
		"plaster": return "plaster"
		"stone": return "stone"
		"wood": return "wood"
		"roof_tile": return "rooftile"
		"roof_metal": return "roofmetal"
	return "plaster"

func _scale(name: String) -> Vector3:
	match name:
		"brick": return Vector3(0.35, 0.35, 0.35)
		"stone": return Vector3(0.25, 0.25, 0.25)
		"roof_tile": return Vector3(0.5, 0.5, 0.5)
		"roof_metal": return Vector3(0.3, 0.3, 0.3)
		"wood": return Vector3(0.5, 0.5, 0.5)
	return Vector3(0.3, 0.3, 0.3)

func _load(path: String) -> Texture2D:
	if ResourceLoader.exists(path):
		return load(path)
	return null

# --- переиспользуемые меш-элементы (создаются один раз) ---

# окно: рама (дерево) + стекло + подоконник-наличник. Ширина ~1.2, высота ~1.8.
func window_unit() -> Mesh:
	if _meshes.has("window"):
		return _meshes["window"]
	var st := SurfaceTool.new(); st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var w := 1.2; var h := 1.8; var fr := 0.12; var dp := 0.14
	# стекло (surface 0) — отдельная поверхность со своим материалом
	_box(st, Vector3(0, h * 0.5, 0), Vector3(w - fr, h - fr, 0.04))
	st.generate_normals()
	# рама отдельным SurfaceTool -> отдельная поверхность, свой материал
	var fst := SurfaceTool.new(); fst.begin(Mesh.PRIMITIVE_TRIANGLES)
	_box(fst, Vector3(0, h, 0), Vector3(w + fr, fr, dp))            # перемычка сверху
	_box(fst, Vector3(0, 0, 0), Vector3(w + fr, fr * 1.4, dp * 1.2)) # подоконник
	_box(fst, Vector3(-w * 0.5, h * 0.5, 0), Vector3(fr, h, dp))    # левый косяк
	_box(fst, Vector3(w * 0.5, h * 0.5, 0), Vector3(fr, h, dp))     # правый косяк
	_box(fst, Vector3(0, h * 0.5, 0), Vector3(fr * 0.6, h, dp * 0.6)) # средник
	fst.generate_normals()
	# соберём составной меш: surface 0 = стекло, surface 1 = рама
	var am := ArrayMesh.new()
	am.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, st.commit_to_arrays())
	am.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, fst.commit_to_arrays())
	am.surface_set_material(0, material("glass"))
	am.surface_set_material(1, material("wood"))
	_meshes["window"] = am
	return am

# дверь: полотно (дерево) + каменный портал. Ширина ~1.5, высота ~2.6.
func door_unit() -> Mesh:
	if _meshes.has("door"):
		return _meshes["door"]
	var wst := SurfaceTool.new(); wst.begin(Mesh.PRIMITIVE_TRIANGLES)
	_box(wst, Vector3(0, 1.25, 0), Vector3(1.4, 2.5, 0.12))
	wst.generate_normals()
	var pst := SurfaceTool.new(); pst.begin(Mesh.PRIMITIVE_TRIANGLES)
	_box(pst, Vector3(0, 2.65, 0), Vector3(1.9, 0.3, 0.4))          # перемычка
	_box(pst, Vector3(-0.85, 1.35, 0), Vector3(0.3, 2.7, 0.4))      # левый пилястр
	_box(pst, Vector3(0.85, 1.35, 0), Vector3(0.3, 2.7, 0.4))       # правый пилястр
	pst.generate_normals()
	var am := ArrayMesh.new()
	am.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, wst.commit_to_arrays())
	am.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, pst.commit_to_arrays())
	am.surface_set_material(0, material("wood"))
	am.surface_set_material(1, material("stone"))
	_meshes["door"] = am
	return am

# печная труба
func chimney_unit() -> Mesh:
	if _meshes.has("chimney"):
		return _meshes["chimney"]
	var st := SurfaceTool.new(); st.begin(Mesh.PRIMITIVE_TRIANGLES)
	_box(st, Vector3(0, 0.9, 0), Vector3(0.9, 1.8, 0.9))
	_box(st, Vector3(0, 1.85, 0), Vector3(1.1, 0.2, 1.1))   # оголовок
	st.generate_normals()
	var am := ArrayMesh.new()
	am.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, st.commit_to_arrays())
	am.surface_set_material(0, material("brick"))
	_meshes["chimney"] = am
	return am

# угловой камень (руст) — стопка блоков для укрепления углов фасада
func quoin_unit(height: float) -> Mesh:
	var key := "quoin_%d" % int(height)
	if _meshes.has(key):
		return _meshes[key]
	var st := SurfaceTool.new(); st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var n := maxi(int(height / 0.6), 2)
	for i in range(n):
		var w := 0.7 if i % 2 == 0 else 0.5
		_box(st, Vector3(0, i * 0.6 + 0.3, 0), Vector3(w, 0.5, w))
	st.generate_normals()
	var am := ArrayMesh.new()
	am.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, st.commit_to_arrays())
	am.surface_set_material(0, material("stone"))
	_meshes[key] = am
	return am

# --- низкоуровневый помощник: куб в SurfaceTool ---
func _box(st: SurfaceTool, center: Vector3, size: Vector3) -> void:
	var h := size * 0.5
	var v := [
		center + Vector3(-h.x, -h.y, -h.z), center + Vector3(h.x, -h.y, -h.z),
		center + Vector3(h.x, h.y, -h.z), center + Vector3(-h.x, h.y, -h.z),
		center + Vector3(-h.x, -h.y, h.z), center + Vector3(h.x, -h.y, h.z),
		center + Vector3(h.x, h.y, h.z), center + Vector3(-h.x, h.y, h.z)]
	var faces := [[0, 1, 2, 3], [5, 4, 7, 6], [4, 0, 3, 7], [1, 5, 6, 2], [3, 2, 6, 7], [4, 5, 1, 0]]
	for f in faces:
		for idx in [f[0], f[1], f[2], f[0], f[2], f[3]]:
			st.add_vertex(v[idx])
