class_name GrassBuilder
extends RefCounted
## Настоящая трава — геометрия травинок (7-лезвийный кустик) размноженная через
## MultiMesh плотным ковром у игрока. Переиспользуемый объект: один меш кустика
## инстансируется тысячами раз (как и камни/детализация грунта).

static func _gv(st: SurfaceTool, p: Vector3, c: Color) -> void:
	st.set_normal(Vector3.UP)   # трава освещается «вверх» — ровная, без тёмных листьев
	st.set_color(c)
	st.add_vertex(p)

static func make_tuft() -> Mesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var rng := RandomNumberGenerator.new(); rng.seed = 99
	for _b in range(7):
		var ang := rng.randf() * TAU
		var off := rng.randf() * 0.05
		var bx := cos(ang) * off; var bz := sin(ang) * off
		var h := rng.randf_range(0.16, 0.30)
		var w := 0.009
		var ba := rng.randf() * TAU
		var bend := rng.randf_range(0.03, 0.12)
		var dx := cos(ba); var dz := sin(ba)
		var tint := rng.randf()
		# натуральная зелень с жёлто-зелёными и тёмными вариациями (не «неон»)
		var lo := Color(0.07, 0.16, 0.04).lerp(Color(0.11, 0.20, 0.05), tint)
		var hi := Color(0.22, 0.36, 0.10).lerp(Color(0.34, 0.40, 0.14), tint)
		var md := lo.lerp(hi, 0.5)
		var p0 := Vector3(bx - dz * w, 0, bz + dx * w)
		var p1 := Vector3(bx + dz * w, 0, bz - dx * w)
		var mc := Vector3(bx + dx * bend, h * 0.55, bz + dz * bend)
		var m0 := mc + Vector3(-dz * w * 0.6, 0, dx * w * 0.6)
		var m1 := mc + Vector3(dz * w * 0.6, 0, -dx * w * 0.6)
		var tip := Vector3(bx + dx * bend * 1.7, h, bz + dz * bend * 1.7)
		_gv(st, p0, lo); _gv(st, p1, lo); _gv(st, m1, md)
		_gv(st, p0, lo); _gv(st, m1, md); _gv(st, m0, md)
		_gv(st, m0, md); _gv(st, m1, md); _gv(st, tip, hi)
	var m := st.commit()
	var mat := ShaderMaterial.new()
	mat.shader = load("res://shaders/grass.gdshader")
	m.surface_set_material(0, mat)
	return m

static func build(world: Node3D, data: WorldData) -> void:
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.mesh = make_tuft()
	var rng := RandomNumberGenerator.new(); rng.seed = 2025
	# плотный ковёр рядом с игроком (как в эталоне) — под A18 Pro
	var count := 240000
	var radius := 110.0
	var sp := data.spawn_xz()
	var cx := sp.x; var cz := sp.y
	mm.instance_count = count
	var placed := 0; var tries := 0
	while placed < count and tries < count * 5:
		tries += 1
		var a := rng.randf() * TAU
		# больше плотности к центру (у игрока)
		var rr := pow(rng.randf(), 0.7) * radius
		var x := cx + cos(a) * rr; var z := cz + sin(a) * rr
		if data.ground_color(x, z).r < 0.55:   # только луг
			continue
		if data.in_lake(x, z) or data.near_building(x, z, 5.0):
			continue
		var y := data.height_at(x, z)
		if y < -1.0:
			continue
		var t := Transform3D()
		var s := rng.randf_range(0.75, 1.5)
		t = t.scaled(Vector3(s, rng.randf_range(0.9, 1.4) * s, s))
		t = t.rotated(Vector3.UP, rng.randf() * TAU)
		t.origin = Vector3(x, y, z)
		mm.set_instance_transform(placed, t)
		placed += 1
	mm.instance_count = placed
	var mmi := MultiMeshInstance3D.new()
	mmi.multimesh = mm
	mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	world.add_child(mmi)
