class_name WaterBuilder
extends RefCounted
## Вода озёр — плоскости с water-шейдером на уровне воды каждого озера из layout.

static func build(world: Node3D, data: WorldData) -> void:
	var wat := load("res://shaders/water.gdshader")
	for lk in data.LY.get("lakes", []):
		var c: Array = lk["center"]; var r: Array = lk["radius"]
		var mesh := PlaneMesh.new()
		mesh.size = Vector2(float(r[0]) * 2.2, float(r[1]) * 2.2)
		mesh.subdivide_width = 24; mesh.subdivide_depth = 24
		var mi := MeshInstance3D.new()
		mi.mesh = mesh
		var sm := ShaderMaterial.new(); sm.shader = wat
		mi.material_override = sm
		mi.position = Vector3(float(c[0]), float(lk["water_level"]), float(c[1]))
		world.add_child(mi)
