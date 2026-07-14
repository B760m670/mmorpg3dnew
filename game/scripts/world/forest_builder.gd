class_name ForestBuilder
extends RefCounted
## Парки/леса — деревья (TreeFactory) размноженные через MultiMesh по эллиптическим
## зонам «forests» из layout, с обходом озёр и зданий.

static func build(world: Node3D, data: WorldData) -> void:
	var tree_mesh := TreeFactory.make_mesh()
	for fr in data.LY.get("forests", []):
		var c: Array = fr["center"]; var r: Array = fr["radius"]
		var rx := float(r[0]); var rz := float(r[1])
		var density := float(fr.get("density", 0.5))
		var count := int(clampf(rx * rz * 0.0016 * density, 60, 420))
		var mm := MultiMesh.new()
		mm.transform_format = MultiMesh.TRANSFORM_3D
		mm.mesh = tree_mesh
		mm.instance_count = count
		var rng := RandomNumberGenerator.new(); rng.seed = int(c[0]) * 100 + int(c[1])
		var placed := 0
		var tries := 0
		while placed < count and tries < count * 6:
			tries += 1
			var a := rng.randf() * TAU
			var rr := sqrt(rng.randf())
			var x := float(c[0]) + cos(a) * rx * rr
			var z := float(c[1]) + sin(a) * rz * rr
			if data.in_lake(x, z) or data.near_building(x, z, 18.0):
				continue
			var y := data.height_at(x, z)
			if y < -2.5:
				continue
			var t := Transform3D()
			var sc := rng.randf_range(0.8, 1.4)
			t = t.scaled(Vector3(sc, rng.randf_range(0.9, 1.3) * sc, sc))
			t = t.rotated(Vector3.UP, rng.randf() * TAU)
			t.origin = Vector3(x, y, z)
			mm.set_instance_transform(placed, t)
			placed += 1
		mm.instance_count = placed
		var mmi := MultiMeshInstance3D.new()
		mmi.multimesh = mm
		world.add_child(mmi)
