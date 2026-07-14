class_name GroundPatchBuilder
extends RefCounted
## Детальный участок ЗЕМЛИ под игроком — НАСТОЯЩАЯ геометрия с буграми и
## углублениями (не плоскость). Плотная сетка (~сантиметры) вокруг спавна,
## многооктавное смещение: комья, зерно, микрорельеф + редкие ямки. Сшивается с
## крупным рельефом по краю (плавное затухание смещения). Материал — тот же
## грунтовый шейдер, но с мелким тайлингом для резкой детализации вблизи.

static func build(world: Node3D, data: WorldData, gp: GraphicsProfile) -> void:
	var R: float = gp.patch_radius
	var STEP: float = gp.patch_step
	var sp := data.spawn_xz()
	var cx := sp.x; var cz := sp.y

	var clod := FastNoiseLite.new()
	clod.noise_type = FastNoiseLite.TYPE_SIMPLEX; clod.frequency = 0.7; clod.fractal_octaves = 3
	var grain := FastNoiseLite.new()
	grain.noise_type = FastNoiseLite.TYPE_SIMPLEX; grain.frequency = 3.0
	var micro := FastNoiseLite.new()
	micro.noise_type = FastNoiseLite.TYPE_SIMPLEX; micro.frequency = 11.0
	var hollow := FastNoiseLite.new()
	hollow.noise_type = FastNoiseLite.TYPE_SIMPLEX; hollow.frequency = 0.22; hollow.seed = 7

	var n := int(2.0 * R / STEP)
	var w1 := n + 1
	# координаты узлов
	var X := PackedFloat32Array(); X.resize(w1)
	var Z := PackedFloat32Array(); Z.resize(w1)
	for i in range(w1):
		X[i] = cx - R + i * STEP
		Z[i] = cz - R + i * STEP
	# высоты и цвета грунта по узлам (один раз на узел)
	var H := PackedFloat32Array(); H.resize(w1 * w1)
	var C := PackedColorArray(); C.resize(w1 * w1)
	for j in range(w1):
		var z := Z[j]
		for i in range(w1):
			var x := X[i]
			var c := clod.get_noise_2d(x, z)
			var g := grain.get_noise_2d(x, z)
			var m := micro.get_noise_2d(x, z)
			var hv: float = clampf(hollow.get_noise_2d(x, z) * 0.5 + 0.5, 0.0, 1.0)
			var pit := pow(hv, 3.0) * 0.22
			var d := c * 0.11 + g * 0.03 + m * 0.012 - pit + 0.16
			var dist := sqrt((x - cx) * (x - cx) + (z - cz) * (z - cz))
			var fade: float = clampf((R - dist) / (R * 0.35), 0.0, 1.0)
			var idx := j * w1 + i
			H[idx] = data.height_at(x, z) + d * fade
			C[idx] = data.ground_color(x, z)

	# нормали по сетке высот
	var N := PackedVector3Array(); N.resize(w1 * w1)
	for j in range(w1):
		for i in range(w1):
			var il := maxi(i - 1, 0); var ir := mini(i + 1, n)
			var jd := maxi(j - 1, 0); var ju := mini(j + 1, n)
			var hl := H[j * w1 + il]; var hr := H[j * w1 + ir]
			var hd := H[jd * w1 + i]; var hu := H[ju * w1 + i]
			N[j * w1 + i] = Vector3(hl - hr, 2.0 * STEP, hd - hu).normalized()

	var st := SurfaceTool.new(); st.begin(Mesh.PRIMITIVE_TRIANGLES)
	for j in range(n):
		for i in range(n):
			var a := j * w1 + i; var b := j * w1 + i + 1
			var c2 := (j + 1) * w1 + i + 1; var e := (j + 1) * w1 + i
			var pa := Vector3(X[i], H[a], Z[j]); var pb := Vector3(X[i + 1], H[b], Z[j])
			var pc := Vector3(X[i + 1], H[c2], Z[j + 1]); var pe := Vector3(X[i], H[e], Z[j + 1])
			_v(st, pa, N[a], C[a]); _v(st, pb, N[b], C[b]); _v(st, pc, N[c2], C[c2])
			_v(st, pa, N[a], C[a]); _v(st, pc, N[c2], C[c2]); _v(st, pe, N[e], C[e])
	var mesh := st.commit()
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	mi.material_override = _material()
	world.add_child(mi)

static func _v(st: SurfaceTool, p: Vector3, nrm: Vector3, col: Color) -> void:
	st.set_normal(nrm); st.set_color(col); st.add_vertex(p)

# грунтовый шейдер с МЕЛКИМ тайлингом — резкое зерно вблизи, а не размытое пятно
static func _material() -> ShaderMaterial:
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
	mat.set_shader_parameter("tiles", Vector4(0.7, 0.8, 0.75, 0.9))
	return mat
