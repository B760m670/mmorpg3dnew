class_name GroundDetailBuilder
extends RefCounted
## Детализация грунта под ногами — мелкие камешки/комья земли (кластер из 4 гальки)
## размноженные через MultiMesh у точки спавна. Переиспользуемый объект: один
## меш-кластер инстансируется десятками тысяч раз.

static func make_cluster() -> Mesh:
	var noise := FastNoiseLite.new(); noise.frequency = 3.0; noise.seed = 5
	var rng := RandomNumberGenerator.new(); rng.seed = 5
	var st := SurfaceTool.new(); st.begin(Mesh.PRIMITIVE_TRIANGLES)
	for _p in range(4):
		var ox := rng.randf_range(-0.14, 0.14); var oz := rng.randf_range(-0.14, 0.14)
		var rad := rng.randf_range(0.02, 0.06)
		var rings := 5; var sect := 6
		var pts := []
		for i in range(rings + 1):
			var row := []
			var phi := PI * float(i) / rings
			for j in range(sect + 1):
				var th := TAU * float(j) / sect
				var n := Vector3(sin(phi) * cos(th), cos(phi), sin(phi) * sin(th))
				var d: float = rad * (1.0 + noise.get_noise_3d(n.x * 5.0 + ox, n.y * 5.0, n.z * 5.0 + oz) * 0.5)
				var pp := n * d; pp.y = pp.y * 0.6
				row.append(Vector3(ox, 0, oz) + pp)
			pts.append(row)
		for i in range(rings):
			for j in range(sect):
				for v in [pts[i][j], pts[i][j + 1], pts[i + 1][j + 1], pts[i][j], pts[i + 1][j + 1], pts[i + 1][j]]:
					st.add_vertex(v)
	st.generate_normals()
	var m := st.commit()
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.22, 0.19, 0.15)
	mat.normal_enabled = true
	mat.normal_texture = load("res://world/textures/ground/dirt_path_normal.png")
	mat.uv1_triplanar = true; mat.uv1_scale = Vector3(3.0, 3.0, 3.0)
	mat.roughness = 0.95
	m.surface_set_material(0, mat)
	return m

static func build(world: Node3D, data: WorldData) -> void:
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.mesh = make_cluster()
	var rng := RandomNumberGenerator.new(); rng.seed = 4242
	var count := 90000
	var radius := 130.0
	var sp := data.spawn_xz()
	var cx := sp.x; var cz := sp.y
	mm.instance_count = count
	var placed := 0; var tries := 0
	while placed < count and tries < count * 4:
		tries += 1
		var a := rng.randf() * TAU
		var rr := pow(rng.randf(), 0.7) * radius
		var x := cx + cos(a) * rr; var z := cz + sin(a) * rr
		if data.in_lake(x, z) or data.near_building(x, z, 4.0):
			continue
		var y := data.height_at(x, z)
		if y < -1.0:
			continue
		var t := Transform3D()
		var s := rng.randf_range(0.6, 1.6)
		t = t.scaled(Vector3(s, s * rng.randf_range(0.6, 1.0), s))
		t = t.rotated(Vector3.UP, rng.randf() * TAU)
		t.origin = Vector3(x, y, z)
		mm.set_instance_transform(placed, t)
		placed += 1
	mm.instance_count = placed
	var mmi := MultiMeshInstance3D.new()
	mmi.multimesh = mm
	mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	world.add_child(mmi)
