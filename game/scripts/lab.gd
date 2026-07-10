extends Node3D
## Лаборатория персонажей (движок Godot 4).
## Физика: гравитация, коллизии, прыжок (CharacterBody3D).
## Управление: джойстик — ходьба; один палец — орбита камеры;
## два пальца — панорама и зум; кнопка — прыжок.

const GRAVITY := 9.8
const WALK_SPEED := 1.7
const JUMP_VELOCITY := 4.6

var player: CharacterBody3D
var visual: Node3D
var uniform_inst: Node3D
var body_inst: Node3D
var uniform_anim: AnimationPlayer
var body_anim: AnimationPlayer
var show_uniform := true
var turntable := false
var char_yaw := PI
var want_jump := false

var cam_yaw_node: Node3D
var cam_pitch_node: Node3D
var camera: Camera3D
var cam_yaw := PI
var cam_pitch := -0.08
var boom := 2.8
var pan_offset := Vector3.ZERO

var joystick: Control
var outfit_btn: Button
var status_label: Label

var _touches := {}
var _pinch_dist := -1.0

func _ready() -> void:
	_build_studio()
	_build_player()
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

	# пол: физическое тело + видимая плоскость
	var floor_body := StaticBody3D.new()
	var floor_col := CollisionShape3D.new()
	var floor_shape := BoxShape3D.new()
	floor_shape.size = Vector3(80, 1, 80)
	floor_col.shape = floor_shape
	floor_col.position = Vector3(0, -0.5, 0)
	floor_body.add_child(floor_col)
	var floor_mesh := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(80, 80)
	var fmat := StandardMaterial3D.new()
	fmat.albedo_color = Color(0.40, 0.41, 0.43)
	fmat.roughness = 0.85
	plane.material = fmat
	floor_mesh.mesh = plane
	floor_body.add_child(floor_mesh)
	add_child(floor_body)

# ---------- персонаж (физическое тело + скелетные модели) ----------
func _instance_glb(path: String) -> Node3D:
	var packed: PackedScene = load(path)
	if packed == null:
		return null
	return packed.instantiate() as Node3D

func _find_anim(root: Node) -> AnimationPlayer:
	if root == null:
		return null
	return root.find_child("AnimationPlayer", true, false) as AnimationPlayer

func _setup_anim(ap: AnimationPlayer) -> void:
	if ap == null:
		return
	for anim_name in ["idle", "walk"]:
		if ap.has_animation(anim_name):
			ap.get_animation(anim_name).loop_mode = Animation.LOOP_LINEAR
	if ap.has_animation("jump"):
		ap.get_animation("jump").loop_mode = Animation.LOOP_NONE
	if ap.has_animation("idle"):
		ap.play("idle")

func _build_player() -> void:
	player = CharacterBody3D.new()
	player.position = Vector3(0, 0.1, 0)
	add_child(player)

	var col := CollisionShape3D.new()
	var capsule := CapsuleShape3D.new()
	capsule.radius = 0.3
	capsule.height = 1.75
	col.shape = capsule
	col.position = Vector3(0, 0.9, 0)
	player.add_child(col)

	visual = Node3D.new()
	visual.rotation.y = char_yaw
	player.add_child(visual)

	uniform_inst = _instance_glb("res://characters/nicholas/uniform.glb")
	if uniform_inst != null:
		visual.add_child(uniform_inst)
		uniform_anim = _find_anim(uniform_inst)
		_setup_anim(uniform_anim)

	body_inst = _instance_glb("res://characters/nicholas/body.glb")
	if body_inst != null:
		body_inst.visible = false
		visual.add_child(body_inst)
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
	title.text = "ЛАБОРАТОРІЯ ПЕРСОНАЖЕЙ"
	title.add_theme_font_size_override("font_size", 26)
	title.position = Vector2(28, 16)
	layer.add_child(title)

	status_label = Label.new()
	status_label.text = "Николай II • Godot 4 • физика включена"
	status_label.add_theme_font_size_override("font_size", 15)
	status_label.position = Vector2(28, 50)
	layer.add_child(status_label)
	if uniform_inst == null and body_inst == null:
		status_label.text = "ОШИБКА: модель не загрузилась"

	# правая колонка кнопок
	var vbox := VBoxContainer.new()
	vbox.anchor_left = 1.0
	vbox.anchor_right = 1.0
	vbox.offset_left = -220
	vbox.offset_right = -24
	vbox.offset_top = 16
	vbox.add_theme_constant_override("separation", 12)
	layer.add_child(vbox)

	outfit_btn = _mk_button("Тѣло")
	outfit_btn.pressed.connect(_toggle_outfit)
	vbox.add_child(outfit_btn)

	var turn_btn := _mk_button("⟳ Поворотъ")
	turn_btn.pressed.connect(func() -> void: turntable = not turntable)
	vbox.add_child(turn_btn)

	var reset_btn := _mk_button("⌖ Камера")
	reset_btn.pressed.connect(_reset_camera)
	vbox.add_child(reset_btn)

	# джойстик: слева снизу, с отступами от края
	joystick = load("res://scripts/joystick.gd").new()
	joystick.anchor_left = 0.0
	joystick.anchor_top = 1.0
	joystick.anchor_bottom = 1.0
	joystick.offset_left = 48
	joystick.offset_top = -320
	joystick.offset_right = 48 + 250
	joystick.offset_bottom = -70
	layer.add_child(joystick)

	# кнопка прыжка: справа снизу
	var jump_btn := _mk_button("Прыжокъ", 26)
	jump_btn.anchor_left = 1.0
	jump_btn.anchor_right = 1.0
	jump_btn.anchor_top = 1.0
	jump_btn.anchor_bottom = 1.0
	jump_btn.offset_left = -230
	jump_btn.offset_right = -48
	jump_btn.offset_top = -180
	jump_btn.offset_bottom = -84
	jump_btn.pressed.connect(func() -> void: want_jump = true)
	layer.add_child(jump_btn)

	var hint := Label.new()
	hint.text = "1 палецъ — орбита • 2 пальца — панорама и зумъ"
	hint.add_theme_font_size_override("font_size", 14)
	hint.anchor_left = 0.5
	hint.anchor_right = 0.5
	hint.anchor_top = 1.0
	hint.anchor_bottom = 1.0
	hint.offset_left = -220
	hint.offset_right = 220
	hint.offset_top = -36
	hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	layer.add_child(hint)

func _toggle_outfit() -> void:
	show_uniform = not show_uniform
	if uniform_inst != null:
		uniform_inst.visible = show_uniform
	if body_inst != null:
		body_inst.visible = not show_uniform
	outfit_btn.text = "Тѣло" if show_uniform else "Мундиръ"

func _reset_camera() -> void:
	pan_offset = Vector3.ZERO
	boom = 2.8
	cam_pitch = -0.08
	camera.position = Vector3(0, 0, boom)
	cam_pitch_node.rotation.x = cam_pitch

# ---------- ввод: орбита (1 палец), панорама+зум (2 пальца) ----------
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
			# панорама: средний сдвиг пальцев двигает точку обзора
			var cam_right := Vector3(cos(cam_yaw), 0, -sin(cam_yaw))
			var k := 0.0011 * boom * 0.5
			pan_offset += (-cam_right * event.relative.x + Vector3.UP * event.relative.y) * k
			pan_offset.x = clampf(pan_offset.x, -5.0, 5.0)
			pan_offset.y = clampf(pan_offset.y, -0.9, 1.6)
			pan_offset.z = clampf(pan_offset.z, -5.0, 5.0)
			# зум: изменение расстояния между пальцами
			var keys := _touches.keys()
			var d: float = (_touches[keys[0]] as Vector2).distance_to(_touches[keys[1]] as Vector2)
			if _pinch_dist > 0.0 and absf(d - _pinch_dist) > 1.0:
				boom = clampf(boom * (_pinch_dist / d), 0.45, 9.0)
				camera.position = Vector3(0, 0, boom)
			_pinch_dist = d
		else:
			cam_yaw -= event.relative.x * 0.006
			cam_pitch = clampf(cam_pitch - event.relative.y * 0.004, -1.15, 0.35)
			cam_yaw_node.rotation.y = cam_yaw
			cam_pitch_node.rotation.x = cam_pitch

# ---------- физика ----------
func _physics_process(delta: float) -> void:
	if player == null:
		return
	var v: Vector2 = joystick.vector if joystick != null else Vector2.ZERO
	var mag := minf(v.length(), 1.0)

	# базис движения от камеры: вперёд = взгляд камеры (без вертикали)
	var fwd := Vector3(-sin(cam_yaw), 0, -cos(cam_yaw))
	var right := Vector3(cos(cam_yaw), 0, -sin(cam_yaw))

	var dir := fwd * v.y + right * v.x
	var hspeed := 0.0
	if mag > 0.1 and dir.length() > 0.01:
		dir = dir.normalized()
		hspeed = WALK_SPEED * mag
		char_yaw = lerp_angle(char_yaw, atan2(dir.x, dir.z), delta * 9.0)
		visual.rotation.y = char_yaw
		player.velocity.x = dir.x * hspeed
		player.velocity.z = dir.z * hspeed
	else:
		player.velocity.x = move_toward(player.velocity.x, 0.0, delta * 8.0)
		player.velocity.z = move_toward(player.velocity.z, 0.0, delta * 8.0)

	if player.is_on_floor():
		if want_jump:
			player.velocity.y = JUMP_VELOCITY
			var ap := uniform_anim if show_uniform else body_anim
			if ap != null and ap.has_animation("jump"):
				ap.play("jump", 0.05)
	else:
		player.velocity.y -= GRAVITY * delta
	want_jump = false

	player.move_and_slide()

	# анимации
	var anim := uniform_anim if show_uniform else body_anim
	if anim != null:
		if not player.is_on_floor():
			if anim.current_animation != "jump" and anim.has_animation("jump"):
				anim.play("jump", 0.1)
		elif hspeed > 0.3:
			if anim.current_animation != "walk":
				anim.play("walk", 0.2)
		else:
			if anim.current_animation != "idle":
				anim.play("idle", 0.25)

func _process(delta: float) -> void:
	if turntable and player != null and player.velocity.length() < 0.1:
		char_yaw += delta * 0.5
		visual.rotation.y = char_yaw

	var target := player.global_position + Vector3(0, 1.05, 0) + pan_offset
	cam_yaw_node.position = cam_yaw_node.position.lerp(target, minf(1.0, delta * 9.0))
