class_name FreeCamera
extends Camera3D
## Инструмент обзора и ПЕРВОЕ ПОГРУЖЕНИЕ. Два режима, переключение ДВОЙНЫМ ТАПОМ:
##
## ПОЛЁТ (стройка/инспекция):
##   один палец — поворот (без инверсии: вниз→вниз, вправо→налево);
##   два пальца — зум (развёл=ближе) + перенос «схвати мир»;
##   скорость ∝ высоте, потолок — облака.
## ПЕШЕХОД (мир глазами жителя, глаза 1.7 м):
##   ЛЕВАЯ половина экрана — виртуальный стик движения (куда потянул — туда
##   идёшь, дальше потянул — быстрее, до бега);
##   ПРАВАЯ половина — взгляд (те же правила, без инверсии);
##   ноги держит рельеф — вниз не провалишься, вверх не улетишь.
## Без кнопок и меню.

@export var rot_sensitivity: float = 0.0026        # рад/пиксель (поворот за пальцем)
@export var pan_gain: float = 0.0016               # перенос: доля от высоты на пиксель
@export var dolly_gain: float = 0.0022             # зум: доля от высоты на пиксель
@export var cloud_level: float = 2500.0            # потолок высоты (полёт)
@export var min_speed_alt: float = 3.0             # мин. «высота» для скорости у земли
@export var eye_height: float = 1.7                # рост глаз пешехода, м
@export var walk_speed: float = 1.6                # шаг, м/с
@export var run_speed: float = 6.5                 # бег (стик до упора), м/с

var terrain: Terrain                               # для высоты земли
var mode: String = "fly"                           # "fly" | "walk"

var _yaw: float = 0.0
var _pitch: float = -0.15
var _touches: Dictionary = {}                      # индекс → позиция (пиксели)
var _two_active: bool = false
var _prev_centroid: Vector2 = Vector2.ZERO
var _prev_dist: float = 0.0

# двойной тап
var _press_pos: Dictionary = {}                    # индекс → позиция нажатия
var _press_time: Dictionary = {}                   # индекс → время нажатия, мс
var _last_tap_ms: int = -100000
var _last_tap_pos: Vector2 = Vector2.ZERO

# пешеход: виртуальный стик
var _move_idx: int = -1
var _move_origin: Vector2 = Vector2.ZERO
var _move_vec: Vector2 = Vector2.ZERO              # -1..1

func setup(pos: Vector3, look_at_target: Vector3) -> void:
	position = pos
	var dir := (look_at_target - pos).normalized()
	_yaw = atan2(-dir.x, -dir.z)                    # −Z вперёд
	_pitch = asin(clampf(dir.y, -1.0, 1.0))
	_apply_orientation()

func _ready() -> void:
	if far < 8000.0:
		far = 8000.0

func _apply_orientation() -> void:
	_pitch = clampf(_pitch, deg_to_rad(-89.0), deg_to_rad(89.0))
	transform.basis = Basis(Vector3.UP, _yaw) * Basis(Vector3.RIGHT, _pitch)

func _ground_y(x: float, z: float) -> float:
	return terrain.height(x, z) if terrain != null else 0.0

func _speed_scale() -> float:
	var alt := position.y - _ground_y(position.x, position.z)
	return maxf(alt, min_speed_alt)

func _input(event: InputEvent) -> void:
	if event is InputEventScreenTouch:
		if event.pressed:
			_touches[event.index] = event.position
			_press_pos[event.index] = event.position
			_press_time[event.index] = Time.get_ticks_msec()
			if mode == "walk" and _move_idx == -1 \
					and event.position.x < get_viewport().get_visible_rect().size.x * 0.5:
				_move_idx = event.index
				_move_origin = event.position
				_move_vec = Vector2.ZERO
		else:
			_check_double_tap(event)
			_touches.erase(event.index)
			_press_pos.erase(event.index)
			_press_time.erase(event.index)
			if event.index == _move_idx:
				_move_idx = -1
				_move_vec = Vector2.ZERO
		_two_active = false
	elif event is InputEventScreenDrag:
		_touches[event.index] = event.position
		if mode == "walk":
			if event.index == _move_idx:
				_move_vec = (event.position - _move_origin) / 130.0
				if _move_vec.length() > 1.0:
					_move_vec = _move_vec.normalized()
			else:
				_rotate_by(event.relative)
			return
		var n := _touches.size()
		if n == 1:
			_rotate_by(event.relative)
		elif n >= 2:
			_two_finger()

func _check_double_tap(event: InputEventScreenTouch) -> void:
	# тап = короткое нажатие без движения; два тапа рядом подряд → смена режима
	var now := Time.get_ticks_msec()
	var t0: int = _press_time.get(event.index, -1)
	var p0: Vector2 = _press_pos.get(event.index, event.position)
	if t0 < 0 or now - t0 > 260 or p0.distance_to(event.position) > 24.0:
		return
	if now - _last_tap_ms < 380 and _last_tap_pos.distance_to(event.position) < 90.0:
		_last_tap_ms = -100000
		_toggle_mode()
	else:
		_last_tap_ms = now
		_last_tap_pos = event.position

func _toggle_mode() -> void:
	if mode == "fly":
		mode = "walk"
		_move_idx = -1
		_move_vec = Vector2.ZERO
	else:
		mode = "fly"
		# отойти от земли, чтобы полёт не начинался «в траве»
		position.y = maxf(position.y, _ground_y(position.x, position.z) + 25.0)

func _rotate_by(rel: Vector2) -> void:
	# палец вправо → поворот налево; палец вниз → камера ВНИЗ (без инверсии)
	_yaw += rel.x * rot_sensitivity
	_pitch += rel.y * rot_sensitivity
	_apply_orientation()

func _two_finger() -> void:
	var keys := _touches.keys()
	var p0: Vector2 = _touches[keys[0]]
	var p1: Vector2 = _touches[keys[1]]
	var centroid := (p0 + p1) * 0.5
	var dist := p0.distance_to(p1)
	if not _two_active:
		_two_active = true
		_prev_centroid = centroid
		_prev_dist = dist
		return
	var d_dist := dist - _prev_dist
	var d_centroid := centroid - _prev_centroid
	_prev_dist = dist
	_prev_centroid = centroid

	var s := _speed_scale()
	var b := transform.basis
	# зум: развёл пальцы → ближе, свёл → дальше (как в фото)
	position += (-b.z) * d_dist * dolly_gain * s
	# перенос «схвати мир»: сцена едет за пальцами
	position -= b.x * d_centroid.x * pan_gain * s
	position += b.y * d_centroid.y * pan_gain * s

func _process(delta: float) -> void:
	if mode == "walk":
		# движение по стику относительно взгляда (в плоскости земли)
		if _move_vec.length_squared() > 0.0004:
			var fwd := Vector3(-sin(_yaw), 0.0, -cos(_yaw))
			var right := Vector3(cos(_yaw), 0.0, -sin(_yaw))
			var mag := _move_vec.length()
			var speed := lerpf(walk_speed, run_speed, clampf((mag - 0.35) / 0.65, 0.0, 1.0))
			var dir := (right * _move_vec.x + fwd * (-_move_vec.y))
			if dir.length_squared() > 0.001:
				position += dir.normalized() * speed * mag * delta
		# ноги на рельефе, глаза 1.7 м (плавно по склонам)
		var target_y := _ground_y(position.x, position.z) + eye_height
		position.y = lerpf(position.y, target_y, minf(1.0, delta * 12.0))
		return
	var gy := _ground_y(position.x, position.z)
	position.y = clampf(position.y, gy + 1.5, cloud_level)
