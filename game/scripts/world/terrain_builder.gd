class_name TerrainBuilder
extends RefCounted
## Рельеф из карты высот (heights.json) прямо в Godot — с явными нормалями «вверх»
## и мелким шумовым смещением (бугры/впадины сверх крупного рельефа). Грунт красится
## по вершинам (4 типа) и рендерится terrain-шейдером из библиотеки грунтов.

static func build(world: Node3D, data: WorldData) -> void:
	var hres := data.heights_res()
	if hres == 0:
		return
	var half := data.size() * 0.5
	var cell := data.size() / float(hres - 1)
	# мелкое шумовое смещение поверхности — бугры и неровности сверх крупного рельефа
	var dn := FastNoiseLite.new()
	dn.noise_type = FastNoiseLite.TYPE_SIMPLEX
	dn.frequency = 0.09
	dn.fractal_octaves = 4
	var damp := 0.7
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	# высота с учётом мелкого шума
	var hy := func(i: int, j: int) -> float:
		var x := -half + i * cell; var z := -half + j * cell
		return data.height_node(i, j) + dn.get_noise_2d(x, z) * damp
	# нормаль поля высот в узле (i,j) — всегда с доминантой +Y
	var norm := func(i: int, j: int) -> Vector3:
		var il := maxi(i - 1, 0); var ir := mini(i + 1, hres - 1)
		var jd := maxi(j - 1, 0); var ju := mini(j + 1, hres - 1)
		var hl: float = hy.call(il, j); var hr: float = hy.call(ir, j)
		var hd: float = hy.call(i, jd); var hu: float = hy.call(i, ju)
		return Vector3(hl - hr, 2.0 * cell, hd - hu).normalized()
	var vpos := func(i: int, j: int) -> Vector3:
		return Vector3(-half + i * cell, hy.call(i, j), -half + j * cell)
	for j in range(hres - 1):
		for i in range(hres - 1):
			var p00: Vector3 = vpos.call(i, j); var p10: Vector3 = vpos.call(i + 1, j)
			var p11: Vector3 = vpos.call(i + 1, j + 1); var p01: Vector3 = vpos.call(i, j + 1)
			var n00: Vector3 = norm.call(i, j); var n10: Vector3 = norm.call(i + 1, j)
			var n11: Vector3 = norm.call(i + 1, j + 1); var n01: Vector3 = norm.call(i, j + 1)
			var c00: Color = data.ground_color(p00.x, p00.z); var c10: Color = data.ground_color(p10.x, p10.z)
			var c11: Color = data.ground_color(p11.x, p11.z); var c01: Color = data.ground_color(p01.x, p01.z)
			# порядок вершин даёт лицевую сторону ВВЕРХ (видна сверху, не отсекается)
			for t in [[p00, n00, c00], [p10, n10, c10], [p11, n11, c11],
					[p00, n00, c00], [p11, n11, c11], [p01, n01, c01]]:
				st.set_normal(t[1])
				st.set_color(t[2])
				st.set_uv(Vector2(t[0].x, t[0].z) * 0.1)
				st.add_vertex(t[0])
	var mesh := st.commit()
	var mesh_inst := MeshInstance3D.new()
	mesh_inst.mesh = mesh
	# грунт из библиотеки: 4 слоя (луг / лесная подстилка / тропа / пашня-огород)
	var mat := ShaderMaterial.new()
	mat.shader = load("res://shaders/terrain.gdshader")
	var g := "res://world/textures/ground/"
	mat.set_shader_parameter("l0_alb", load(g + "meadow_albedo.png"))
	mat.set_shader_parameter("l0_nrm", load(g + "meadow_normal.png"))
	mat.set_shader_parameter("l1_alb", load(g + "forest_floor_albedo.png"))
	mat.set_shader_parameter("l1_nrm", load(g + "forest_floor_normal.png"))
	mat.set_shader_parameter("l2_alb", load(g + "dirt_path_albedo.png"))
	mat.set_shader_parameter("l2_nrm", load(g + "dirt_path_normal.png"))
	mat.set_shader_parameter("l3_alb", load(g + "field_albedo.png"))
	mat.set_shader_parameter("l3_nrm", load(g + "field_normal.png"))
	mesh_inst.material_override = mat
	world.add_child(mesh_inst)
	# коллизия рельефа
	var body := StaticBody3D.new()
	var col := CollisionShape3D.new()
	col.shape = mesh.create_trimesh_shape()
	body.add_child(col)
	world.add_child(body)
