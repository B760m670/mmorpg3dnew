class_name TreeFactory
extends RefCounted
## Переиспользуемый меш дерева (ствол-цилиндр + двухъярусная крона-конусы),
## объединённый в один Mesh с vertex-color материалом. Используется лесом (MultiMesh).

static func make_mesh() -> Mesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var bark := Color(0.30, 0.22, 0.14)
	var leaf := Color(0.20, 0.36, 0.18)
	_add_cyl(st, Vector3(0, 1.4, 0), 0.22, 2.8, bark, 6)
	_add_cone(st, Vector3(0, 4.6, 0), 2.2, 3.2, leaf, 8)
	_add_cone(st, Vector3(0, 6.4, 0), 1.5, 2.6, leaf, 8)
	st.generate_normals()
	var m := st.commit()
	var mat := StandardMaterial3D.new()
	mat.vertex_color_use_as_albedo = true
	mat.roughness = 0.9
	m.surface_set_material(0, mat)
	return m

static func _add_cyl(st: SurfaceTool, base: Vector3, r: float, h: float, col: Color, seg: int) -> void:
	for i in range(seg):
		var a0 := float(i) / seg * TAU; var a1 := float(i + 1) / seg * TAU
		var p0 := base + Vector3(cos(a0) * r, -h * 0.5, sin(a0) * r)
		var p1 := base + Vector3(cos(a1) * r, -h * 0.5, sin(a1) * r)
		var p2 := p1 + Vector3(0, h, 0); var p3 := p0 + Vector3(0, h, 0)
		for p in [p0, p1, p2, p0, p2, p3]:
			st.set_color(col); st.add_vertex(p)

static func _add_cone(st: SurfaceTool, base: Vector3, r: float, h: float, col: Color, seg: int) -> void:
	var apex := base + Vector3(0, h, 0)
	for i in range(seg):
		var a0 := float(i) / seg * TAU; var a1 := float(i + 1) / seg * TAU
		var p0 := base + Vector3(cos(a0) * r, 0, sin(a0) * r)
		var p1 := base + Vector3(cos(a1) * r, 0, sin(a1) * r)
		for p in [p0, p1, apex]:
			st.set_color(col); st.add_vertex(p)
