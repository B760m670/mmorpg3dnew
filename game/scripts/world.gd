extends Node3D
## Контроллер мира Гатчины 1894 (Godot 4). Тонкий оркестратор: делегирует ПОСТРОЙКУ
## отдельным модулям (scripts/world/*), а UI и карту — своим узлам (scripts/ui/*).
## Сам держит только рантайм игрока и камеры (ходьба, орбита, панорама, гироскоп).

const GRAVITY := PhysicsConfig.GRAVITY
const WALK_SPEED := PhysicsConfig.WALK_SPEED
const RUN_SPEED := PhysicsConfig.RUN_SPEED
const JUMP_VELOCITY := PhysicsConfig.JUMP_VELOCITY

var data: WorldData

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
var _running := false

var hud: GameHUD
var map: MapOverlay

var _touches := {}
var _pinch_dist := -1.0

func _ready() -> void:
	data = WorldData.new()
	data.load_all()
	EnvironmentBuilder.build(self)
	TerrainBuilder.build(self, data)
	GroundPatchBuilder.build(self, data)   # детальная земля с рельефом под игроком
	GrassBuilder.build(self, data)
	RockBuilder.build(self, data)
	WaterBuilder.build(self, data)
	BuildingPlacer.new(self, data).build_all()
	ForestBuilder.build(self, data)
	_build_player()
	_build_camera()
	_build_ui()

# ---------- персонаж ----------
func _build_player() -> void:
	player = CharacterBody3D.new()
	var sp := data.spawn_xz()
	player.position = Vector3(sp.x, data.height_at(sp.x, sp.y) + 2.0, sp.y)
	add_child(player)

	var col := CollisionShape3D.new()
	var capsule := CapsuleShape3D.new()
	capsule.radius = 0.3; capsule.height = 1.75
	col.shape = capsule
	col.position = Vector3(0, 0.9, 0)
	player.add_child(col)

	visual = Node3D.new()
	char_yaw = deg_to_rad(data.spawn_heading())
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
func _build_ui() -> void:
	hud = GameHUD.new()
	add_child(hud)
	hud.build()
	hud.menu_pressed.connect(func() -> void: get_tree().change_scene_to_file("res://scenes/menu.tscn"))
	hud.map_pressed.connect(func() -> void: map.toggle())
	hud.run_toggled.connect(func(on: bool) -> void: _running = on)
	hud.jump_pressed.connect(func() -> void: want_jump = true)

	map = MapOverlay.new()
	add_child(map)
	map.setup(player, data.size())

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
			var iy: float = -1.0 if Settings.invert_y else 1.0
			cam_yaw -= event.relative.x * 0.006 * sens
			cam_pitch = clampf(cam_pitch - event.relative.y * 0.004 * sens * iy, -1.2, 0.4)
			cam_yaw_node.rotation.y = cam_yaw
			cam_pitch_node.rotation.x = cam_pitch

# ---------- физика ----------
func _physics_process(delta: float) -> void:
	if player == null:
		return
	var v: Vector2 = hud.joystick.vector if hud != null and hud.joystick != null else Vector2.ZERO
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
	# гироскоп: наклон устройства вращает камеру (синхронизировано с настройками)
	if Settings.gyro_enabled:
		var gy := Input.get_gyroscope()
		var gs := Settings.gyro_sensitivity * 2.2
		var iy: float = -1.0 if Settings.invert_y else 1.0
		cam_yaw -= gy.y * delta * gs
		cam_pitch = clampf(cam_pitch + gy.x * delta * gs * iy, -1.2, 0.4)
		cam_yaw_node.rotation.y = cam_yaw
		cam_pitch_node.rotation.x = cam_pitch
	var target := player.global_position + Vector3(0, 1.2, 0) + pan_offset
	cam_yaw_node.position = cam_yaw_node.position.lerp(target, minf(1.0, delta * 9.0))
	if map != null and map.is_open():
		map.update_marker()
