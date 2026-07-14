class_name RockBuilder
extends RefCounted
## Валуны — смещённые сферы (4 варианта меша) с каменным материалом. Переиспользуемые
## объекты: набор мешей разбросан по лугу вокруг игрока.

static func make_mesh(seed: int) -> Mesh:
	var noise := FastNoiseLite.new()
	noise.frequency = 0.9; noise.seed = seed
	noise.fractal_octaves = 4
	var rings := 12; var sectors := 16
	var pts := []
	for i in range(rings + 1):
		var row := []
		var phi := PI * float(i) / rings
		for j in range(sectors + 1):
			var theta := TAU * float(j) / sectors
			var n := Vector3(sin(phi) * cos(theta), cos(phi), sin(phi) * sin(theta))
			var d: float = 1.0 + noise.get_noise_3d(n.x * 2.2, n.y * 2.2, n.z * 2.2) * 0.4
			var p := n * d
			p.y = p.y * 0.75 - 0.1   # приплюснуть, «сесть» в землю
			row.append(p)
		pts.append(row)
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	for i in range(rings):
		for j in range(sectors):
			var a: Vector3 = pts[i][j]; var b: Vector3 = pts[i][j + 1]
			var c: Vector3 = pts[i + 1][j + 1]; var d2: Vector3 = pts[i + 1][j]
			for v in [a, b, c, a, c, d2]:
				st.add_vertex(v)
	st.generate_normals()
	return st.commit()

static func build(world: Node3D, data: WorldData, gp: GraphicsProfile) -> void:
	var rmat := StandardMaterial3D.new()
	rmat.albedo_color = Color(0.30, 0.29, 0.27)
	rmat.normal_enabled = true
	rmat.normal_texture = load("res://world/textures/ground/clay_normal.png")
	rmat.normal_scale = 1.0
	rmat.uv1_triplanar = true
	rmat.uv1_scale = Vector3(1.2, 1.2, 1.2)
	rmat.roughness = 0.92
	# 4 варианта валуна, каждый — свой MultiMesh (валуны инстансируются, не по одному)
	var variants := 4
	var meshes := []
	for k in range(variants):
		var mm := make_mesh(k * 13 + 1)
		mm.surface_set_material(0, rmat)
		meshes.append(mm)
	var xforms := []
	for _k in range(variants):
		xforms.append([] as Array[Transform3D])
	var rng := RandomNumberGenerator.new(); rng.seed = 771
	var sp := data.spawn_xz()
	var cx := sp.x; var cz := sp.y
	for _i in range(gp.rock_count):
		var a := rng.randf() * TAU
		var rr := sqrt(rng.randf()) * 420.0
		var x := cx + cos(a) * rr; var z := cz + sin(a) * rr
		var gc := data.ground_color(x, z)
		if gc.b > 0.4 or data.in_lake(x, z) or data.near_building(x, z, 8.0):
			continue
		var y := data.height_at(x, z)
		if y < -1.0:
			continue
		var t := Transform3D()
		var s := rng.randf_range(0.3, 1.1)
		t = t.scaled(Vector3(s, s * rng.randf_range(0.7, 1.0), s))
		t = t.rotated(Vector3.UP, rng.randf() * TAU)
		t.origin = Vector3(x, y + 0.05, z)
		(xforms[rng.randi() % variants] as Array).append(t)
	for k in range(variants):
		var list: Array = xforms[k]
		if list.is_empty():
			continue
		var mmesh := MultiMesh.new()
		mmesh.transform_format = MultiMesh.TRANSFORM_3D
		mmesh.mesh = meshes[k]
		mmesh.instance_count = list.size()
		for i in range(list.size()):
			mmesh.set_instance_transform(i, list[i])
		var mmi := MultiMeshInstance3D.new()
		mmi.multimesh = mmesh
		world.add_child(mmi)
