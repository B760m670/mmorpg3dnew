extends Node3D
## Мир Гатчины 1894 (движок Godot 4).
## Рельеф, озёра, парки, дворец, город — из game/world (источник истины layout.json).
## Управление как в лаборатории: джойстик — ходьба, 1 палец — орбита камеры,
## 2 пальца — панорама/зум, кнопки — прыжок и карта.

const GRAVITY := PhysicsConfig.GRAVITY
const WALK_SPEED := PhysicsConfig.WALK_SPEED
const RUN_SPEED := PhysicsConfig.RUN_SPEED
const JUMP_VELOCITY := PhysicsConfig.JUMP_VELOCITY

var player: CharacterBody3D
var visual: Node3D
var uniform_inst: Node3D
var uniform_anim: AnimationPlayer
var char_yaw := PI

var cam_yaw_node: Node3D
var cam_pitch_node: Node3D
var camera: Camera3D
var cam_yaw := PI
var cam_pitch := -0.18
var boom := 4.5
var pan_offset := Vector3.ZERO
var want_jump := false

var joystick: Control
var status_label: Label
var map_layer: CanvasLayer
var map_marker: Control
var map_rect: TextureRect

var _touches := {}
var _pinch_dist := -1.0

# данные мира
var LY := {}                    # layout.json
var _h := PackedFloat32Array()  # высотная карта
var _hres := 0
var _hsize := 1800.0

func _ready() -> void:
	_load_data()
	_build_environment()
	_build_terrain()
	_build_grass()
	_build_rocks()
	_build_water()
	_build_buildings()
	_build_town()
	_build_forests()
	_build_player()
	_build_camera()
	_build_ui()

func _load_data() -> void:
	var f := FileAccess.open("res://world/gatchina/layout.json", FileAccess.READ)
	if f != null:
		LY = JSON.parse_string(f.get_as_text())
	var hf := FileAccess.open("res://world/gatchina/heights.json", FileAccess.READ)
	if hf != null:
		var d: Dictionary = JSON.parse_string(hf.get_as_text())
		_hres = int(d["res"]); _hsize = float(d["size"])
		for v in d["h"]:
			_h.append(float(v))

# билинейная выборка высоты рельефа в мировой точке (X — восток, Z — юг)
func height_at(x: float, z: float) -> float:
	if _hres == 0:
		return 0.0
	var half := _hsize * 0.5
	var fx: float = clampf((x + half) / _hsize, 0.0, 1.0) * (_hres - 1)
	var fz: float = clampf((z + half) / _hsize, 0.0, 1.0) * (_hres - 1)
	var i0 := int(fx); var j0 := int(fz)
	var i1: int = mini(i0 + 1, _hres - 1); var j1: int = mini(j0 + 1, _hres - 1)
	var tx := fx - i0; var tz := fz - j0
	var h00 := _h[j0 * _hres + i0]; var h10 := _h[j0 * _hres + i1]
	var h01 := _h[j1 * _hres + i0]; var h11 := _h[j1 * _hres + i1]
	return lerpf(lerpf(h00, h10, tx), lerpf(h01, h11, tx), tz)

# ---------- окружение: небо, солнце, туман ----------
func _build_environment() -> void:
	# физическое небо: рассеяние Рэлея/Ми + солнце + облака (shaders/sky.gdshader)
	var sky_mat := ShaderMaterial.new()
	sky_mat.shader = load("res://shaders/sky.gdshader")
	var sky := Sky.new()
	sky.sky_material = sky_mat
	sky.radiance_size = Sky.RADIANCE_SIZE_64
	sky.process_mode = Sky.PROCESS_MODE_REALTIME      # небо анимировано — ambient каждый кадр
	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_energy = 0.6
	env.tonemap_mode = Environment.TONE_MAPPER_ACES
	env.tonemap_exposure = 1.0

	# --- Forward+ : «уровень движка» реализм ---
	# Для открытого мира глобальное освещение даёт само небо (AMBIENT_SOURCE_SKY):
	# физическая атмосфера освещает всё мягким небесным светом. SDFGI здесь не
	# нужен (тяжёл для мобильных и конфликтует с ярким HDR-небом).
	# Затенение в складках/углах и экранное непрямое освещение
	env.ssao_enabled = true
	env.ssao_radius = 2.0
	env.ssao_intensity = 2.0
	env.ssao_power = 1.5
	env.ssil_enabled = true
	env.ssil_radius = 4.0
	env.ssil_intensity = 1.0
	# Экранные отражения (вода, полированные поверхности)
	env.ssr_enabled = true
	env.ssr_max_steps = 48
	env.ssr_fade_in = 0.15
	env.ssr_fade_out = 3.0
	# Объёмный туман — атмосфера, «воздух» между зданиями и над озёрами
	env.volumetric_fog_enabled = true
	env.volumetric_fog_density = 0.0016
	env.volumetric_fog_albedo = Color(0.86, 0.89, 0.94)
	env.volumetric_fog_length = 180.0
	env.volumetric_fog_gi_inject = 0.6
	# Дальний туман для глубины
	env.fog_enabled = true
	env.fog_light_color = Color(0.72, 0.78, 0.84)
	env.fog_density = 0.0009
	env.fog_sky_affect = 0.25
	env.fog_aerial_perspective = 0.5
	# Свечение ярких мест (солнце на золоте/воде)
	env.glow_enabled = true
	env.glow_intensity = 0.5
	env.glow_bloom = 0.1
	env.glow_blend_mode = Environment.GLOW_BLEND_MODE_SOFTLIGHT
	# Цветокоррекция — тёплый исторический тон
	env.adjustment_enabled = true
	env.adjustment_brightness = 1.0
	env.adjustment_contrast = 1.06
	env.adjustment_saturation = 1.08

	_apply_quality(env)
	var we := WorldEnvironment.new(); we.environment = env
	add_child(we)

	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Settings.sun_rotation_deg()
	# физическое небо яркое (HDR) — солнце должно светить сильно, иначе земля чёрная
	sun.light_energy = 0.5 if Settings.is_night() else 3.8
	sun.light_color = Color(1.0, 0.95, 0.86)
	sun.shadow_enabled = true
	sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
	sun.directional_shadow_max_distance = 260.0
	sun.directional_shadow_split_1 = 0.08
	sun.directional_shadow_split_2 = 0.2
	sun.directional_shadow_split_3 = 0.5
	sun.directional_shadow_blend_splits = true
	add_child(sun)

# качество графики из настроек: отключаем тяжёлые эффекты на слабых устройствах
func _apply_quality(env: Environment) -> void:
	match Settings.quality:
		"balanced":
			env.ssil_enabled = false
			env.ssr_enabled = false
			env.volumetric_fog_density = 0.001
		"performance":
			env.ssao_enabled = false
			env.ssil_enabled = false
			env.ssr_enabled = false
			env.volumetric_fog_enabled = false
			get_viewport().msaa_3d = Viewport.MSAA_DISABLED

# ---------- рельеф ----------
func _build_terrain() -> void:
	# Рельеф строим прямо в Godot из heights.json — с явными нормалями «вверх».
	# Так исключаем неоднозначность экспорта из Blender (из-за неё грунт был чёрным).
	if _hres == 0:
		return
	var half := _hsize * 0.5
	var cell := _hsize / float(_hres - 1)
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	# нормаль поля высот в узле (i,j) — всегда с доминантой +Y
	var norm := func(i: int, j: int) -> Vector3:
		var il := maxi(i - 1, 0); var ir := mini(i + 1, _hres - 1)
		var jd := maxi(j - 1, 0); var ju := mini(j + 1, _hres - 1)
		var hl := _h[j * _hres + il]; var hr := _h[j * _hres + ir]
		var hd := _h[jd * _hres + i]; var hu := _h[ju * _hres + i]
		return Vector3(hl - hr, 2.0 * cell, hd - hu).normalized()
	var vpos := func(i: int, j: int) -> Vector3:
		return Vector3(-half + i * cell, _h[j * _hres + i], -half + j * cell)
	for j in range(_hres - 1):
		for i in range(_hres - 1):
			var p00: Vector3 = vpos.call(i, j); var p10: Vector3 = vpos.call(i + 1, j)
			var p11: Vector3 = vpos.call(i + 1, j + 1); var p01: Vector3 = vpos.call(i, j + 1)
			var n00: Vector3 = norm.call(i, j); var n10: Vector3 = norm.call(i + 1, j)
			var n11: Vector3 = norm.call(i + 1, j + 1); var n01: Vector3 = norm.call(i, j + 1)
			var c00: Color = _ground_color(p00.x, p00.z); var c10: Color = _ground_color(p10.x, p10.z)
			var c11: Color = _ground_color(p11.x, p11.z); var c01: Color = _ground_color(p01.x, p01.z)
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
	add_child(mesh_inst)
	# коллизия рельефа
	var body := StaticBody3D.new()
	var col := CollisionShape3D.new()
	col.shape = mesh.create_trimesh_shape()
	body.add_child(col)
	add_child(body)

func _first_mesh(root: Node) -> MeshInstance3D:
	for m in root.find_children("*", "MeshInstance3D", true, false):
		return m as MeshInstance3D
	return null

# расстояние от точки до отрезка (для покраски дорог)
func _seg_dist(px: float, pz: float, ax: float, az: float, bx: float, bz: float) -> float:
	var vx := bx - ax; var vz := bz - az
	var wx := px - ax; var wz := pz - az
	var t: float = clampf((wx * vx + wz * vz) / (vx * vx + vz * vz + 1e-6), 0.0, 1.0)
	var dx := px - (ax + t * vx); var dz := pz - (az + t * vz)
	return sqrt(dx * dx + dz * dz)

# вес типов грунта в точке: R=луг, G=лесная подстилка, B=тропа, A=пашня/огород
func _ground_color(x: float, z: float) -> Color:
	var g := 0.0
	for fr in LY.get("forests", []):
		var c: Array = fr["center"]; var r: Array = fr["radius"]
		var d := sqrt(pow((x - float(c[0])) / float(r[0]), 2.0) + pow((z - float(c[1])) / float(r[1]), 2.0))
		if d < 1.05:
			g = maxf(g, clampf((1.05 - d) / 0.3, 0.0, 1.0))
	var b := 0.0
	for rd in LY.get("roads", []):
		var pts: Array = rd["points"]; var hw := float(rd["width"]) * 0.5 + 1.0
		var dm := 1e9
		for i in range(pts.size() - 1):
			dm = minf(dm, _seg_dist(x, z, float(pts[i][0]), float(pts[i][1]), float(pts[i + 1][0]), float(pts[i + 1][1])))
		if dm < hw + 3.0:
			b = maxf(b, clampf((hw + 3.0 - dm) / 4.0, 0.0, 1.0))
	var a := 0.0
	for zone in (LY.get("fields", []) + LY.get("gardens", [])):
		var c2: Array = zone["center"]; var s2: Array = zone["size"]
		var fx: float = 1.0 - clampf((absf(x - float(c2[0])) - float(s2[0]) * 0.35) / (float(s2[0]) * 0.15), 0.0, 1.0)
		var fz: float = 1.0 - clampf((absf(z - float(c2[1])) - float(s2[1]) * 0.35) / (float(s2[1]) * 0.15), 0.0, 1.0)
		a = maxf(a, fx * fz)
	var r: float = maxf(0.0, 1.0 - g - b - a)
	return Color(r, g, b, a)

# ---------- трава: настоящие травинки (геометрия) через MultiMesh ----------
func _gv(st: SurfaceTool, p: Vector3, c: Color) -> void:
	st.set_normal(Vector3.UP)   # трава освещается «вверх» — ровная, без тёмных листьев
	st.set_color(c)
	st.add_vertex(p)

func _make_grass_tuft() -> Mesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var rng := RandomNumberGenerator.new(); rng.seed = 99
	for _b in range(7):
		var ang := rng.randf() * TAU
		var off := rng.randf() * 0.05
		var bx := cos(ang) * off; var bz := sin(ang) * off
		var h := rng.randf_range(0.22, 0.36)
		var w := 0.012
		var ba := rng.randf() * TAU
		var bend := rng.randf_range(0.03, 0.10)
		var dx := cos(ba); var dz := sin(ba)
		var tint := rng.randf()
		var lo := Color(0.10, 0.26, 0.05).lerp(Color(0.15, 0.31, 0.06), tint)
		var hi := Color(0.34, 0.52, 0.14).lerp(Color(0.42, 0.56, 0.18), tint)
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

func _build_grass() -> void:
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.mesh = _make_grass_tuft()
	var rng := RandomNumberGenerator.new(); rng.seed = 2025
	var count := 140000
	var radius := 400.0
	var sp: Array = LY.get("spawn", {}).get("position", [40, 90])
	var cx := float(sp[0]); var cz := float(sp[1])
	mm.instance_count = count
	var placed := 0; var tries := 0
	while placed < count and tries < count * 5:
		tries += 1
		var a := rng.randf() * TAU
		var rr := sqrt(rng.randf()) * radius
		var x := cx + cos(a) * rr; var z := cz + sin(a) * rr
		if _ground_color(x, z).r < 0.55:   # только луг
			continue
		if _in_lake(x, z) or _near_building(x, z, 5.0):
			continue
		var y := height_at(x, z)
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
	add_child(mmi)

# ---------- камни: детальные валуны (смещённая сфера) + каменный материал ----------
func _make_rock_mesh(seed: int) -> Mesh:
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

func _build_rocks() -> void:
	var rmat := StandardMaterial3D.new()
	rmat.albedo_color = Color(0.30, 0.29, 0.27)
	rmat.normal_enabled = true
	rmat.normal_texture = load("res://world/textures/ground/clay_normal.png")
	rmat.normal_scale = 1.0
	rmat.uv1_triplanar = true
	rmat.uv1_scale = Vector3(1.2, 1.2, 1.2)
	rmat.roughness = 0.92
	var meshes := []
	for k in range(4):
		var mm := _make_rock_mesh(k * 13 + 1)
		mm.surface_set_material(0, rmat)
		meshes.append(mm)
	var rng := RandomNumberGenerator.new(); rng.seed = 771
	var sp: Array = LY.get("spawn", {}).get("position", [40, 90])
	var cx := float(sp[0]); var cz := float(sp[1])
	for _i in range(500):
		var a := rng.randf() * TAU
		var rr := sqrt(rng.randf()) * 420.0
		var x := cx + cos(a) * rr; var z := cz + sin(a) * rr
		var gc := _ground_color(x, z)
		if gc.b > 0.4 or _in_lake(x, z) or _near_building(x, z, 8.0):
			continue
		var y := height_at(x, z)
		if y < -1.0:
			continue
		var inst := MeshInstance3D.new()
		inst.mesh = meshes[rng.randi() % meshes.size()]
		var s := rng.randf_range(0.3, 1.1)
		inst.scale = Vector3(s, s * rng.randf_range(0.7, 1.0), s)
		inst.rotation.y = rng.randf() * TAU
		inst.position = Vector3(x, y + 0.05, z)
		add_child(inst)

# ---------- вода озёр ----------
func _build_water() -> void:
	var wat := load("res://shaders/water.gdshader")
	for lk in LY.get("lakes", []):
		var c: Array = lk["center"]; var r: Array = lk["radius"]
		var mesh := PlaneMesh.new()
		mesh.size = Vector2(float(r[0]) * 2.2, float(r[1]) * 2.2)
		mesh.subdivide_width = 24; mesh.subdivide_depth = 24
		var mi := MeshInstance3D.new()
		mi.mesh = mesh
		var sm := ShaderMaterial.new(); sm.shader = wat
		mi.material_override = sm
		mi.position = Vector3(float(c[0]), float(lk["water_level"]), float(c[1]))
		add_child(mi)

# ---------- здания ----------
func _place_on_ground(node: Node3D, x: float, z: float, rot_deg: float) -> void:
	node.position = Vector3(x, height_at(x, z), z)
	node.rotation.y = deg_to_rad(rot_deg)
	add_child(node)

func _add_box_collision(node: Node3D, fw: float, fd: float, h: float) -> void:
	var body := StaticBody3D.new()
	var col := CollisionShape3D.new()
	var shp := BoxShape3D.new()
	shp.size = Vector3(fw, h, fd)
	col.shape = shp
	col.position = Vector3(0, h * 0.5, 0)
	body.add_child(col)
	node.add_child(body)

func _build_buildings() -> void:
	for b in LY.get("buildings", []):
		var path := "res://world/buildings/" + str(b["file"])
		var packed: PackedScene = load(path)
		if packed == null:
			continue
		var inst := packed.instantiate() as Node3D
		var pos: Array = b["position"]
		_place_on_ground(inst, float(pos[0]), float(pos[1]), float(b.get("rotation", 0)))
		var fp: Array = b.get("footprint", [20, 20])
		_add_box_collision(inst, float(fp[0]), float(fp[1]), float(b.get("height", 12)))

# ---------- городская застройка ----------
func _build_town() -> void:
	var houses := ["house_a.glb", "house_b.glb", "house_c.glb"]
	var rng := RandomNumberGenerator.new(); rng.seed = 1894
	var idx := 0
	for blk in LY.get("town", {}).get("blocks", []):
		var c: Array = blk["center"]; var s: Array = blk["size"]
		var rows := int(blk.get("rows", 2))
		var n := int(blk.get("houses", 6))
		var per := int(ceil(float(n) / rows))
		var placed := 0
		for row in range(rows):
			var zc: float = float(c[1]) - float(s[1]) * 0.5 + (row + 0.5) / rows * float(s[1])
			for k in range(per):
				if placed >= n:
					break
				var xc: float = float(c[0]) - float(s[0]) * 0.5 + (k + 0.5) / per * float(s[0])
				var packed: PackedScene = load("res://world/buildings/" + houses[idx % houses.size()])
				idx += 1; placed += 1
				if packed == null:
					continue
				var inst := packed.instantiate() as Node3D
				var face := 0.0 if row == 0 else 180.0
				_place_on_ground(inst, xc, zc, face + rng.randf_range(-6, 6))
				_add_box_collision(inst, 15, 11, 8)

# ---------- парки: деревья через MultiMesh ----------
func _build_forests() -> void:
	var tree_mesh := _make_tree_mesh()
	for fr in LY.get("forests", []):
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
			if _in_lake(x, z) or _near_building(x, z, 18.0):
				continue
			var y := height_at(x, z)
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
		add_child(mmi)

func _in_lake(x: float, z: float) -> bool:
	for lk in LY.get("lakes", []):
		var c: Array = lk["center"]; var r: Array = lk["radius"]
		var d := pow((x - float(c[0])) / float(r[0]), 2.0) + pow((z - float(c[1])) / float(r[1]), 2.0)
		if d < 1.15:
			return true
	return false

func _near_building(x: float, z: float, margin: float) -> bool:
	for b in LY.get("buildings", []):
		var p: Array = b["position"]; var fp: Array = b.get("footprint", [20, 20])
		if absf(x - float(p[0])) < float(fp[0]) * 0.5 + margin and absf(z - float(p[1])) < float(fp[1]) * 0.5 + margin:
			return true
	return false

func _make_tree_mesh() -> Mesh:
	# ствол (цилиндр) + крона (два конуса), объединены в один Mesh
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

func _add_cyl(st: SurfaceTool, base: Vector3, r: float, h: float, col: Color, seg: int) -> void:
	for i in range(seg):
		var a0 := float(i) / seg * TAU; var a1 := float(i + 1) / seg * TAU
		var p0 := base + Vector3(cos(a0) * r, -h * 0.5, sin(a0) * r)
		var p1 := base + Vector3(cos(a1) * r, -h * 0.5, sin(a1) * r)
		var p2 := p1 + Vector3(0, h, 0); var p3 := p0 + Vector3(0, h, 0)
		for p in [p0, p1, p2, p0, p2, p3]:
			st.set_color(col); st.add_vertex(p)

func _add_cone(st: SurfaceTool, base: Vector3, r: float, h: float, col: Color, seg: int) -> void:
	var apex := base + Vector3(0, h, 0)
	for i in range(seg):
		var a0 := float(i) / seg * TAU; var a1 := float(i + 1) / seg * TAU
		var p0 := base + Vector3(cos(a0) * r, 0, sin(a0) * r)
		var p1 := base + Vector3(cos(a1) * r, 0, sin(a1) * r)
		for p in [p0, p1, apex]:
			st.set_color(col); st.add_vertex(p)

# ---------- персонаж ----------
func _build_player() -> void:
	player = CharacterBody3D.new()
	var sp: Array = LY.get("spawn", {}).get("position", [40, 90])
	player.position = Vector3(float(sp[0]), height_at(float(sp[0]), float(sp[1])) + 2.0, float(sp[1]))
	add_child(player)

	var col := CollisionShape3D.new()
	var capsule := CapsuleShape3D.new()
	capsule.radius = 0.3; capsule.height = 1.75
	col.shape = capsule
	col.position = Vector3(0, 0.9, 0)
	player.add_child(col)

	visual = Node3D.new()
	char_yaw = deg_to_rad(float(LY.get("spawn", {}).get("heading", 200)))
	visual.rotation.y = char_yaw
	player.add_child(visual)

	uniform_inst = _instance_glb("res://characters/nicholas/uniform.glb")
	if uniform_inst != null:
		visual.add_child(uniform_inst)
		uniform_anim = uniform_inst.find_child("AnimationPlayer", true, false) as AnimationPlayer
		_setup_anim(uniform_anim)

func _instance_glb(path: String) -> Node3D:
	var packed: PackedScene = load(path)
	return packed.instantiate() as Node3D if packed != null else null

func _setup_anim(ap: AnimationPlayer) -> void:
	if ap == null:
		return
	for a in ["idle", "walk"]:
		if ap.has_animation(a):
			ap.get_animation(a).loop_mode = Animation.LOOP_LINEAR
	if ap.has_animation("idle"):
		ap.play("idle")

# ---------- камера ----------
func _build_camera() -> void:
	cam_yaw_node = Node3D.new()
	cam_yaw_node.position = Vector3(0, 1.2, 0)
	add_child(cam_yaw_node)
	cam_pitch_node = Node3D.new()
	cam_yaw_node.add_child(cam_pitch_node)
	camera = Camera3D.new()
	camera.position = Vector3(0, 0, boom)
	camera.fov = 60
	camera.far = 1200.0
	cam_pitch_node.add_child(camera)
	cam_yaw_node.rotation.y = cam_yaw
	cam_pitch_node.rotation.x = cam_pitch
	camera.current = true

# ---------- интерфейс ----------
func _mk_button(text: String, font_size: int = 24) -> Button:
	var b := Button.new()
	b.text = text
	b.add_theme_font_size_override("font_size", font_size)
	b.custom_minimum_size = Vector2(190, 56)
	return b

func _build_ui() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)

	var title := Label.new()
	title.text = "ГАТЧИНА • 1894"
	title.add_theme_font_size_override("font_size", 26)
	title.position = Vector2(28, 16)
	layer.add_child(title)

	status_label = Label.new()
	status_label.text = "Открытый міръ • Godot 4"
	status_label.add_theme_font_size_override("font_size", 15)
	status_label.position = Vector2(28, 50)
	layer.add_child(status_label)

	var vbox := VBoxContainer.new()
	vbox.anchor_left = 1.0; vbox.anchor_right = 1.0
	vbox.offset_left = -220; vbox.offset_right = -24; vbox.offset_top = 16
	vbox.add_theme_constant_override("separation", 12)
	layer.add_child(vbox)

	var menu_btn := _mk_button("☰ Меню")
	menu_btn.pressed.connect(func() -> void: get_tree().change_scene_to_file("res://scenes/menu.tscn"))
	vbox.add_child(menu_btn)

	var map_btn := _mk_button("🗺 Карта")
	map_btn.pressed.connect(_toggle_map)
	vbox.add_child(map_btn)

	var run_btn := _mk_button("Бѣгъ")
	run_btn.toggle_mode = true
	run_btn.toggled.connect(func(on: bool) -> void: _running = on)
	vbox.add_child(run_btn)

	joystick = load("res://scripts/joystick.gd").new()
	joystick.anchor_top = 1.0; joystick.anchor_bottom = 1.0
	joystick.offset_left = 48; joystick.offset_top = -320
	joystick.offset_right = 48 + 250; joystick.offset_bottom = -70
	layer.add_child(joystick)

	var jump_btn := _mk_button("Прыжокъ", 26)
	jump_btn.anchor_left = 1.0; jump_btn.anchor_right = 1.0
	jump_btn.anchor_top = 1.0; jump_btn.anchor_bottom = 1.0
	jump_btn.offset_left = -230; jump_btn.offset_right = -48
	jump_btn.offset_top = -180; jump_btn.offset_bottom = -84
	jump_btn.pressed.connect(func() -> void: want_jump = true)
	layer.add_child(jump_btn)

	_build_map_overlay()

var _running := false

func _build_map_overlay() -> void:
	map_layer = CanvasLayer.new()
	map_layer.layer = 5
	map_layer.visible = false
	add_child(map_layer)
	var bg := ColorRect.new()
	bg.color = Color(0, 0, 0, 0.6)
	bg.anchor_right = 1.0; bg.anchor_bottom = 1.0
	map_layer.add_child(bg)
	map_rect = TextureRect.new()
	var tex: Texture2D = load("res://world/gatchina/map.png")
	map_rect.texture = tex
	map_rect.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	map_rect.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	map_rect.anchor_right = 1.0; map_rect.anchor_bottom = 1.0
	map_rect.offset_left = 40; map_rect.offset_top = 40
	map_rect.offset_right = -40; map_rect.offset_bottom = -120
	map_layer.add_child(map_rect)
	# маркер игрока
	map_marker = Control.new()
	var dot := ColorRect.new()
	dot.color = Color(0.95, 0.15, 0.10)
	dot.size = Vector2(14, 14)
	dot.position = Vector2(-7, -7)
	map_marker.add_child(dot)
	map_rect.add_child(map_marker)
	var close := _mk_button("Закрыть", 24)
	close.anchor_left = 0.5; close.anchor_right = 0.5
	close.anchor_top = 1.0; close.anchor_bottom = 1.0
	close.offset_left = -95; close.offset_right = 95
	close.offset_top = -84; close.offset_bottom = -28
	close.pressed.connect(_toggle_map)
	map_layer.add_child(close)

func _toggle_map() -> void:
	map_layer.visible = not map_layer.visible

func _update_marker() -> void:
	if map_rect == null or map_rect.texture == null:
		return
	var half := _hsize * 0.5
	var u: float = clampf((player.global_position.x + half) / _hsize, 0.0, 1.0)
	var v: float = clampf((player.global_position.z + half) / _hsize, 0.0, 1.0)
	# область, реально занятая текстурой при KEEP_ASPECT_CENTERED
	var rs := map_rect.size
	var ts := map_rect.texture.get_size()
	var scale: float = minf(rs.x / ts.x, rs.y / ts.y)
	var draw := ts * scale
	var origin := (rs - draw) * 0.5
	map_marker.position = origin + Vector2(u * draw.x, v * draw.y)

# ---------- ввод ----------
func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventScreenTouch:
		if event.pressed:
			_touches[event.index] = event.position
		else:
			_touches.erase(event.index)
		_pinch_dist = -1.0
	elif event is InputEventScreenDrag:
		_touches[event.index] = event.position
		if _touches.size() >= 2:
			var cbasis := camera.global_transform.basis
			var k := 0.004 * boom
			pan_offset += (-cbasis.x * event.relative.x + cbasis.y * event.relative.y) * k
			pan_offset.x = clampf(pan_offset.x, -12.0, 12.0)
			pan_offset.y = clampf(pan_offset.y, -2.0, 6.0)
			pan_offset.z = clampf(pan_offset.z, -12.0, 12.0)
			var keys := _touches.keys()
			var d: float = (_touches[keys[0]] as Vector2).distance_to(_touches[keys[1]] as Vector2)
			if _pinch_dist > 0.0 and absf(d - _pinch_dist) > 1.0:
				boom = clampf(boom * (_pinch_dist / d), 1.2, 22.0)
				camera.position = Vector3(0, 0, boom)
			_pinch_dist = d
		else:
			var sens: float = Settings.sensitivity
			cam_yaw -= event.relative.x * 0.006 * sens
			cam_pitch = clampf(cam_pitch - event.relative.y * 0.004 * sens, -1.2, 0.4)
			cam_yaw_node.rotation.y = cam_yaw
			cam_pitch_node.rotation.x = cam_pitch

# ---------- физика ----------
func _physics_process(delta: float) -> void:
	if player == null:
		return
	var v: Vector2 = joystick.vector if joystick != null else Vector2.ZERO
	var mag := minf(v.length(), 1.0)
	var cb := camera.global_transform.basis
	var fwd := -cb.z; fwd.y = 0.0
	if fwd.length() > 0.001: fwd = fwd.normalized()
	var right := cb.x; right.y = 0.0
	if right.length() > 0.001: right = right.normalized()
	var dir := fwd * v.y + right * v.x
	var hspeed := 0.0
	var top := RUN_SPEED if _running else WALK_SPEED
	if mag > 0.1 and dir.length() > 0.01:
		dir = dir.normalized()
		hspeed = top * mag
		char_yaw = lerp_angle(char_yaw, atan2(dir.x, dir.z), delta * 9.0)
		visual.rotation.y = char_yaw
		player.velocity.x = dir.x * hspeed
		player.velocity.z = dir.z * hspeed
	else:
		player.velocity.x = move_toward(player.velocity.x, 0.0, delta * 10.0)
		player.velocity.z = move_toward(player.velocity.z, 0.0, delta * 10.0)

	if player.is_on_floor():
		if want_jump:
			player.velocity.y = JUMP_VELOCITY
	else:
		player.velocity.y -= GRAVITY * delta
	want_jump = false
	player.move_and_slide()

	if uniform_anim != null:
		if hspeed > 0.3:
			var target := "walk"
			if uniform_anim.current_animation != target:
				uniform_anim.play(target, 0.2)
			uniform_anim.speed_scale = clampf(hspeed / WALK_SPEED, 0.8, 2.1)
		else:
			if uniform_anim.current_animation != "idle":
				uniform_anim.play("idle", 0.25)
			uniform_anim.speed_scale = 1.0

func _process(delta: float) -> void:
	if player == null:
		return
	var target := player.global_position + Vector3(0, 1.2, 0) + pan_offset
	cam_yaw_node.position = cam_yaw_node.position.lerp(target, minf(1.0, delta * 9.0))
	if map_layer != null and map_layer.visible:
		_update_marker()
