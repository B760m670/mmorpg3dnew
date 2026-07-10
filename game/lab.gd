extends Node3D
## Лаборатория персонажей на движке Godot 4.
## Студия, скелетный Николай II (glTF из Blender), орбитальная камера,
## пинч-зум, ходьба джойстиком, переодевание Тело/Мундир.

var chars_root: Node3D
var uniform_inst: Node3D
var body_inst: Node3D
var uniform_anim: AnimationPlayer
var body_anim: AnimationPlayer
var show_uniform := true
var turntable := false
var char_yaw := PI

var cam_yaw_node: Node3D
var cam_pitch_node: Node3D
var camera: Camera3D
var cam_yaw := PI
var cam_pitch := -0.10
var boom := 2.6

var joystick: Control
var outfit_btn: Button
var status_label: Label

var _touches := {}
var _pinch_dist := -1.0

func _ready() -> void:
	_build_studio()
	_build_characters()
	_build_camera()
	_build_ui()

# ---------- студия ----------
func _build_studio() -> void:
	var sky_mat := ProceduralSkyMaterial.new()
	sky_mat.sky_top_color = Color(0.13, 0.15, 0.19)
	sky_mat.sky_horizon_color = Color(0.34, 0.36, 0.40)
	sky_mat.ground_bottom_color = Color(0.22, 0.22, 0.24)
	sky_mat.ground_horizon_color = Color(0.34, 0.36, 0.40)
	var sky := Sky.new()
	sky.sky_material = sky_mat
	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_energy = 0.7
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)

	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-48, -35, 0)
	sun.light_energy = 1.35
	sun.light_color = Color(1.0, 0.96, 0.90)
	sun.shadow_enabled = true
	add_child(sun)

	var fill := DirectionalLight3D.new()
	fill.rotation_degrees = Vector3(-25, 130, 0)
	fill.light_energy = 0.45
	fill.light_color = Color(0.82, 0.88, 1.0)
	add_child(fill)

	var floor_mesh := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(80, 80)
	var fmat := StandardMaterial3D.new()
	fmat.albedo_color = Color(0.40, 0.41, 0.43)
	fmat.roughness = 0.85
	plane.material = fmat
	floor_mesh.mesh = plane
	add_child(floor_mesh)

# ---------- персонаж ----------
func _instance_glb(path: String) -> Node3D:
	var packed: PackedScene = load(path)
	if packed == null:
		return null
	var inst: Node3D = packed.instantiate()
	return inst

func _find_anim(root: Node) -> AnimationPlayer:
	if root == null:
		return null
	var ap := root.find_child("AnimationPlayer", true, false)
	return ap as AnimationPlayer

func _setup_anim(ap: AnimationPlayer) -> void:
	if ap == null:
		return
	for anim_name in ["idle", "walk"]:
		if ap.has_animation(anim_name):
			var a := ap.get_animation(anim_name)
			a.loop_mode = Animation.LOOP_LINEAR
	if ap.has_animation("idle"):
		ap.play("idle")

func _build_characters() -> void:
	chars_root = Node3D.new()
	chars_root.rotation.y = char_yaw
	add_child(chars_root)

	uniform_inst = _instance_glb("res://nicholas_uniform.glb")
	if uniform_inst != null:
		chars_root.add_child(uniform_inst)
		uniform_anim = _find_anim(uniform_inst)
		_setup_anim(uniform_anim)

	body_inst = _instance_glb("res://nicholas_body.glb")
	if body_inst != null:
		body_inst.visible = false
		chars_root.add_child(body_inst)
		body_anim = _find_anim(body_inst)
		_setup_anim(body_anim)

# ---------- камера ----------
func _build_camera() -> void:
	cam_yaw_node = Node3D.new()
	cam_yaw_node.position = Vector3(0, 1.05, 0)
	add_child(cam_yaw_node)
	cam_pitch_node = Node3D.new()
	cam_yaw_node.add_child(cam_pitch_node)
	camera = Camera3D.new()
	camera.position = Vector3(0, 0, boom)
	camera.fov = 55
	cam_pitch_node.add_child(camera)
	cam_yaw_node.rotation.y = cam_yaw
	cam_pitch_node.rotation.x = cam_pitch
	camera.current = true

# ---------- UI ----------
func _build_ui() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)

	var title := Label.new()
	title.text = "ЛАБОРАТОРІЯ ПЕРСОНАЖЕЙ — движокъ Godot 4"
	title.position = Vector2(24, 14)
	title.add_theme_font_size_override("font_size", 26)
	layer.add_child(title)

	status_label = Label.new()
	status_label.text = "Николай II • скелетная модель (Blender → glTF)"
	status_label.position = Vector2(24, 48)
	status_label.add_theme_font_size_override("font_size", 16)
	layer.add_child(status_label)
	if uniform_inst == null and body_inst == null:
		status_label.text = "ОШИБКА: glb не загрузился"

	outfit_btn = Button.new()
	outfit_btn.text = "Тѣло"
	outfit_btn.position = Vector2(get_viewport().get_visible_rect().size.x - 170, 14)
	outfit_btn.size = Vector2(140, 46)
	outfit_btn.pressed.connect(_toggle_outfit)
	layer.add_child(outfit_btn)

	var turn_btn := Button.new()
	turn_btn.text = "⟳ Поворотъ"
	turn_btn.position = Vector2(get_viewport().get_visible_rect().size.x - 330, 14)
	turn_btn.size = Vector2(150, 46)
	turn_btn.pressed.connect(func(): turntable = not turntable)
	layer.add_child(turn_btn)

	joystick = load("res://joystick.gd").new()
	joystick.position = Vector2(30, get_viewport().get_visible_rect().size.y - 250)
	joystick.size = Vector2(220, 220)
	layer.add_child(joystick)

func _toggle_outfit() -> void:
	show_uniform = not show_uniform
	if uniform_inst != null:
		uniform_inst.visible = show_uniform
	if body_inst != null:
		body_inst.visible = not show_uniform
	outfit_btn.text = "Тѣло" if show_uniform else "Мундиръ"

# ---------- ввод: орбита и пинч ----------
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
			var keys := _touches.keys()
			var d: float = (_touches[keys[0]] as Vector2).distance_to(_touches[keys[1]] as Vector2)
			if _pinch_dist > 0.0:
				boom = clampf(boom * (_pinch_dist / d), 0.45, 9.0)
				camera.position = Vector3(0, 0, boom)
			_pinch_dist = d
		else:
			cam_yaw -= event.relative.x * 0.006
			cam_pitch = clampf(cam_pitch - event.relative.y * 0.004, -1.15, 0.15)
			cam_yaw_node.rotation.y = cam_yaw
			cam_pitch_node.rotation.x = cam_pitch

# ---------- цикл ----------
func _process(delta: float) -> void:
	var active_anim := uniform_anim if show_uniform else body_anim
	var v: Vector2 = joystick.vector if joystick != null else Vector2.ZERO
	var mag := minf(v.length(), 1.0)

	if mag > 0.1:
		var fwd := Vector3(sin(cam_yaw), 0, cos(cam_yaw))
		var right := Vector3(-cos(cam_yaw), 0, sin(cam_yaw))
		var dir := (fwd * v.y + right * v.x)
		if dir.length() > 0.01:
			dir = dir.normalized()
			var target_yaw := atan2(dir.x, dir.z)
			char_yaw = lerp_angle(char_yaw, target_yaw, delta * 8.0)
			chars_root.rotation.y = char_yaw
			var speed := 1.5 * mag
			chars_root.position.x = clampf(chars_root.position.x + dir.x * speed * delta, -30, 30)
			chars_root.position.z = clampf(chars_root.position.z + dir.z * speed * delta, -30, 30)
		if active_anim != null and active_anim.current_animation != "walk":
			active_anim.play("walk", 0.25)
	else:
		if turntable:
			char_yaw += delta * 0.5
			chars_root.rotation.y = char_yaw
		if active_anim != null and active_anim.current_animation != "idle":
			active_anim.play("idle", 0.25)

	# камера следует за персонажем
	var target := Vector3(chars_root.position.x, 1.05, chars_root.position.z)
	cam_yaw_node.position = cam_yaw_node.position.lerp(target, minf(1.0, delta * 8.0))
