class_name BuildingComposer
extends RefCounted
## Собирает дом ИЗ ПЕРЕИСПОЛЬЗУЕМЫХ ЭЛЕМЕНТОВ (ConstructionKit), но ЗАПЕКАЕТ их в
## ОДИН меш с поверхностью на каждый материал. Так дом = ~5 вызовов отрисовки
## вместо ~33 отдельных узлов — критично для 120 FPS. Геометрия та же: стены с
## тайловым материалом, окна/дверь общими мешами, карниз, кровля, угловые камни,
## труба. Ничего плоско-примитивного.

const BAY := 3.4          # шаг оконных осей
const FLOOR_H := 3.6      # высота этажа

var kit: ConstructionKit
var _st: Dictionary = {}   # имя материала -> SurfaceTool (поверхность-накопитель)
var _order: Array[String] = []

func _init(shared_kit: ConstructionKit) -> void:
	kit = shared_kit

# wx,wz — габарит в плане; floors — этажность; wall/roof — имена материалов kit
func compose(wx: float, wz: float, floors: int, wall: String, roof: String, seed: int) -> Node3D:
	_st.clear(); _order.clear()
	var rng := RandomNumberGenerator.new(); rng.seed = seed
	var h := floors * FLOOR_H

	# цоколь (камень) / стены (тайловый материал) / карниз (камень)
	_box("stone", Vector3(0, 0.5, 0), Vector3(wx + 0.5, 1.0, wz + 0.5))
	_box(wall, Vector3(0, 1.0 + h * 0.5, 0), Vector3(wx, h, wz))
	_box("stone", Vector3(0, 1.0 + h + 0.25, 0), Vector3(wx + 0.6, 0.5, wz + 0.6))

	# окна по осям на передней и задней стене; дверь в центре первого этажа
	var nb := maxi(int(wx / BAY), 2)
	var win := kit.window_unit()
	var door := kit.door_unit()
	for f in range(floors):
		var wy := 1.0 + f * FLOOR_H + FLOOR_H * 0.55
		for b in range(nb):
			var bx := -wx * 0.5 + (b + 0.5) / nb * wx
			if f == 0 and b == nb / 2:
				_door(door, Vector3(bx, 1.0, wz * 0.5 + 0.08), 0.0)
				_door(door, Vector3(bx, 1.0, -wz * 0.5 - 0.08), PI)
				continue
			_window(win, Vector3(bx, wy, wz * 0.5 + 0.02), 0.0)
			_window(win, Vector3(bx, wy, -wz * 0.5 - 0.02), PI)
	# окна на торцах
	var nd := maxi(int(wz / BAY), 1)
	for f in range(floors):
		var wy := 1.0 + f * FLOOR_H + FLOOR_H * 0.55
		for b in range(nd):
			var bz := -wz * 0.5 + (b + 0.5) / nd * wz
			_window(win, Vector3(wx * 0.5 + 0.02, wy, bz), PI * 0.5)
			_window(win, Vector3(-wx * 0.5 - 0.02, wy, bz), -PI * 0.5)

	# угловые камни (руст) на всех четырёх углах
	var q := kit.quoin_unit(h)
	for sx in [-1.0, 1.0]:
		for sz in [-1.0, 1.0]:
			_append("stone", q, 0, _xform(Vector3(sx * wx * 0.5, 1.0, sz * wz * 0.5), 0.0))

	# двускатная кровля
	_add_roof(roof, wx, wz, 1.0 + h)

	# труба
	var cpos := Vector3(rng.randf_range(-wx * 0.25, wx * 0.25), 1.0 + h + wz * 0.28, rng.randf_range(-wz * 0.15, wz * 0.15))
	_append("brick", kit.chimney_unit(), 0, _xform(cpos, 0.0))

	# --- запечь накопленные поверхности в один меш ---
	var am := ArrayMesh.new()
	var i := 0
	for name in _order:
		var st: SurfaceTool = _st[name]
		am.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, st.commit_to_arrays())
		am.surface_set_material(i, kit.material(name)); i += 1
	var mi := MeshInstance3D.new()
	mi.mesh = am
	var root := Node3D.new()
	root.add_child(mi)
	return root

# --- накопление геометрии по материалам ---
func _bucket(name: String) -> SurfaceTool:
	if not _st.has(name):
		var st := SurfaceTool.new(); st.begin(Mesh.PRIMITIVE_TRIANGLES)
		_st[name] = st; _order.append(name)
	return _st[name]

func _append(name: String, mesh: Mesh, surf: int, xform: Transform3D) -> void:
	_bucket(name).append_from(mesh, surf, xform)

func _box(name: String, center: Vector3, size: Vector3) -> void:
	var bm := BoxMesh.new(); bm.size = size
	_bucket(name).append_from(bm, 0, Transform3D(Basis(), center))

func _window(win: Mesh, pos: Vector3, rot_y: float) -> void:
	var x := _xform(pos, rot_y)
	_append("glass", win, 0, x)
	_append("wood", win, 1, x)

func _door(door: Mesh, pos: Vector3, rot_y: float) -> void:
	var x := _xform(pos, rot_y)
	_append("wood", door, 0, x)
	_append("stone", door, 1, x)

func _xform(pos: Vector3, rot_y: float) -> Transform3D:
	return Transform3D(Basis(Vector3.UP, rot_y), pos)

# двускатная крыша: два ската + два фронтона, конёк вдоль X
func _add_roof(roof_mat: String, wx: float, wz: float, base_y: float) -> void:
	var oh := 0.5
	var rh := wz * 0.4
	var hx := wx * 0.5 + oh; var hz := wz * 0.5 + oh
	var ridge := base_y + rh
	var st := _bucket(roof_mat)
	var la := Vector3(-hx, base_y, -hz); var lb := Vector3(hx, base_y, -hz)
	var ra := Vector3(-hx, base_y, hz); var rb := Vector3(hx, base_y, hz)
	var rk0 := Vector3(-hx, ridge, 0); var rk1 := Vector3(hx, ridge, 0)
	_tri(st, la, lb, rk1); _tri(st, la, rk1, rk0)     # скат к -Z
	_tri(st, rb, ra, rk0); _tri(st, rb, rk0, rk1)     # скат к +Z
	_tri(st, la, rk0, ra); _tri(st, lb, rb, rk1)      # фронтоны

func _tri(st: SurfaceTool, a: Vector3, b: Vector3, c: Vector3) -> void:
	var nrm := (b - a).cross(c - a).normalized()
	st.set_normal(nrm); st.add_vertex(a)
	st.set_normal(nrm); st.add_vertex(b)
	st.set_normal(nrm); st.add_vertex(c)
