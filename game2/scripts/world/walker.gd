class_name Walker
extends CharacterBody3D
## ФИЗИЧЕСКИЙ пешеход — мир глазами жителя, телом, а не камерой.
## Капсула 1.75 м, настоящая гравитация 9.81, move_and_slide по коллизии
## рельефа: в горку медленнее, с обрыва — падение, сквозь землю — никогда.
## Управление: ЛЕВАЯ половина экрана — стик движения (дальше — быстрее, до
## бега), ПРАВАЯ — взгляд без инверсии. Двойной тап — вернуться в полёт.

signal toggle_requested

const GRAVITY := 9.81
const EYE := 1.62                 # уровень глаз от ног, м
@export var rot_sensitivity := 0.0026
@export var walk_speed := 1.6
@export var run_speed := 6.5

var cam: Camera3D
var _yaw := 0.0
var _pitch := 0.0
var _move_idx := -1
var _move_origin := Vector2.ZERO
var _move_vec := Vector2.ZERO
var _press_pos: Dictionary = {}
var _press_time: Dictionary = {}
var _last_tap_ms: int = -100000
var _last_tap_pos := Vector2.ZERO

func _ready() -> void:
	var col := CollisionShape3D.new()
	var cap := CapsuleShape3D.new()
	cap.radius = 0.35
	cap.height = 1.75
	col.shape = cap
	col.position = Vector3(0, 1.75 / 2.0, 0)      # ноги в origin тела
	add_child(col)
	cam = Camera3D.new()
	cam.fov = 66.0                                 # человеческое поле зрения
	cam.near = 0.05
	cam.far = 22000.0
	cam.position = Vector3(0, EYE, 0)
	add_child(cam)

func activate(world_pos: Vector3, yaw: float) -> void:
	global_position = world_pos
	_yaw = yaw
	_pitch = 0.0
	velocity = Vector3.ZERO
	_move_idx = -1
	_move_vec = Vector2.ZERO
	visible = true
	set_physics_process(true)
	set_process_input(true)
	cam.current = true
	_apply_look()

func deactivate() -> void:
	visible = false
	set_physics_process(false)
	set_process_input(false)

func _apply_look() -> void:
	_pitch = clampf(_pitch, deg_to_rad(-85.0), deg_to_rad(85.0))
	cam.transform.basis = Basis(Vector3.UP, 0.0)   # yaw несёт тело, pitch — камера
	rotation = Vector3(0, _yaw, 0)
	cam.rotation = Vector3(_pitch, 0, 0)

func _input(event: InputEvent) -> void:
	if event is InputEventScreenTouch:
		if event.pressed:
			_press_pos[event.index] = event.position
			_press_time[event.index] = Time.get_ticks_msec()
			if _move_idx == -1 \
					and event.position.x < get_viewport().get_visible_rect().size.x * 0.5:
				_move_idx = event.index
				_move_origin = event.position
				_move_vec = Vector2.ZERO
		else:
			_check_double_tap(event)
			_press_pos.erase(event.index)
			_press_time.erase(event.index)
			if event.index == _move_idx:
				_move_idx = -1
				_move_vec = Vector2.ZERO
	elif event is InputEventScreenDrag:
		if event.index == _move_idx:
			_move_vec = (event.position - _move_origin) / 130.0
			if _move_vec.length() > 1.0:
				_move_vec = _move_vec.normalized()
		else:
			_yaw += event.relative.x * rot_sensitivity
			_pitch += event.relative.y * rot_sensitivity
			_apply_look()

func _check_double_tap(event: InputEventScreenTouch) -> void:
	var now := Time.get_ticks_msec()
	var t0: int = _press_time.get(event.index, -1)
	var p0: Vector2 = _press_pos.get(event.index, event.position)
	if t0 < 0 or now - t0 > 260 or p0.distance_to(event.position) > 24.0:
		return
	if now - _last_tap_ms < 380 and _last_tap_pos.distance_to(event.position) < 90.0:
		_last_tap_ms = -100000
		toggle_requested.emit()
	else:
		_last_tap_ms = now
		_last_tap_pos = event.position

func _physics_process(delta: float) -> void:
	# горизонтальное намерение — от стика, относительно взгляда
	var fwd := Vector3(-sin(_yaw), 0.0, -cos(_yaw))
	var right := Vector3(cos(_yaw), 0.0, -sin(_yaw))
	var mag := _move_vec.length()
	var speed := lerpf(walk_speed, run_speed, clampf((mag - 0.35) / 0.65, 0.0, 1.0))
	var wish := (right * _move_vec.x + fwd * (-_move_vec.y))
	var horiz := wish.normalized() * speed * mag if wish.length_squared() > 0.001 else Vector3.ZERO
	velocity.x = horiz.x
	velocity.z = horiz.z
	# настоящая гравитация
	if is_on_floor():
		velocity.y = minf(velocity.y, 0.0)
	else:
		velocity.y -= GRAVITY * delta
	move_and_slide()
