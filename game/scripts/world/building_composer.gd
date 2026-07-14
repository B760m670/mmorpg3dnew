class_name BuildingComposer
extends RefCounted
## Собирает дом ИЗ ПЕРЕИСПОЛЬЗУЕМЫХ ЭЛЕМЕНТОВ (ConstructionKit): стены с настоящим
## тайловым материалом (кирпич/штукатурка/камень), окна и дверь как общие меши,
## карниз, двускатная кровля, угловые камни, труба. Ничего примитивно-плоского —
## фасад читается как «сложенный из материалов». Один kit — общий склад деталей.

const BAY := 3.4          # шаг оконных осей
const FLOOR_H := 3.6      # высота этажа

var kit: ConstructionKit

func _init(shared_kit: ConstructionKit) -> void:
	kit = shared_kit

# wx,wz — габарит в плане; floors — этажность; wall/roof — имена материалов kit
func compose(wx: float, wz: float, floors: int, wall: String, roof: String, seed: int) -> Node3D:
	var rng := RandomNumberGenerator.new(); rng.seed = seed
	var root := Node3D.new()
	var h := floors * FLOOR_H

	# --- цоколь (каменный) ---
	_shell(root, Vector3(0, 0.5, 0), Vector3(wx + 0.5, 1.0, wz + 0.5), kit.material("stone"))
	# --- основной объём: стены с тайловым материалом ---
	_shell(root, Vector3(0, 1.0 + h * 0.5, 0), Vector3(wx, h, wz), kit.material(wall))
	# --- карниз под кровлей ---
	_shell(root, Vector3(0, 1.0 + h + 0.25, 0), Vector3(wx + 0.6, 0.5, wz + 0.6), kit.material("stone"))

	# --- окна по осям на передней и задней стене; дверь в центре первого этажа ---
	var nb := maxi(int(wx / BAY), 2)
	var win := kit.window_unit()
	for f in range(floors):
		var wy := 1.0 + f * FLOOR_H + FLOOR_H * 0.55
		for b in range(nb):
			var bx := -wx * 0.5 + (b + 0.5) / nb * wx
			if f == 0 and b == nb / 2:
				_place(root, kit.door_unit(), Vector3(bx, 1.0, wz * 0.5 + 0.08), 0.0)
				_place(root, kit.door_unit(), Vector3(bx, 1.0, -wz * 0.5 - 0.08), PI)
				continue
			_place(root, win, Vector3(bx, wy, wz * 0.5 + 0.02), 0.0)
			_place(root, win, Vector3(bx, wy, -wz * 0.5 - 0.02), PI)
	# окна на торцах
	var nd := maxi(int(wz / BAY), 1)
	for f in range(floors):
		var wy := 1.0 + f * FLOOR_H + FLOOR_H * 0.55
		for b in range(nd):
			var bz := -wz * 0.5 + (b + 0.5) / nd * wz
			_place(root, win, Vector3(wx * 0.5 + 0.02, wy, bz), PI * 0.5)
			_place(root, win, Vector3(-wx * 0.5 - 0.02, wy, bz), -PI * 0.5)

	# --- угловые камни (руст) на всех четырёх углах ---
	var q := kit.quoin_unit(h)
	for sx in [-1.0, 1.0]:
		for sz in [-1.0, 1.0]:
			_place(root, q, Vector3(sx * wx * 0.5, 1.0, sz * wz * 0.5), 0.0)

	# --- двускатная кровля ---
	_add_roof(root, wx, wz, 1.0 + h, kit.material(roof))

	# --- труба ---
	var cm := MeshInstance3D.new()
	cm.mesh = kit.chimney_unit()
	cm.position = Vector3(rng.randf_range(-wx * 0.25, wx * 0.25), 1.0 + h + wz * 0.28, rng.randf_range(-wz * 0.15, wz * 0.15))
	root.add_child(cm)
	return root

func _shell(root: Node3D, center: Vector3, size: Vector3, mat: Material) -> void:
	var mi := MeshInstance3D.new()
	var bm := BoxMesh.new(); bm.size = size
	mi.mesh = bm
	mi.position = center
	mi.material_override = mat
	root.add_child(mi)

func _place(root: Node3D, mesh: Mesh, pos: Vector3, rot_y: float) -> void:
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	mi.position = pos
	mi.rotation.y = rot_y
	root.add_child(mi)

# двускатная крыша: два ската + два фронтона, конёк вдоль X
func _add_roof(root: Node3D, wx: float, wz: float, base_y: float, mat: Material) -> void:
	var oh := 0.5                    # свес
	var rh := wz * 0.4               # высота конька над карнизом
	var hx := wx * 0.5 + oh; var hz := wz * 0.5 + oh
	var ridge := base_y + rh
	var st := SurfaceTool.new(); st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var la := Vector3(-hx, base_y, -hz); var lb := Vector3(hx, base_y, -hz)
	var ra := Vector3(-hx, base_y, hz); var rb := Vector3(hx, base_y, hz)
	var rk0 := Vector3(-hx, ridge, 0); var rk1 := Vector3(hx, ridge, 0)
	# скат к -Z
	for v in [la, lb, rk1, la, rk1, rk0]:
		st.add_vertex(v)
	# скат к +Z
	for v in [rb, ra, rk0, rb, rk0, rk1]:
		st.add_vertex(v)
	# фронтоны
	for v in [la, rk0, ra]:
		st.add_vertex(v)
	for v in [lb, rb, rk1]:
		st.add_vertex(v)
	st.generate_normals()
	var mi := MeshInstance3D.new()
	mi.mesh = st.commit()
	mi.material_override = mat
	root.add_child(mi)
