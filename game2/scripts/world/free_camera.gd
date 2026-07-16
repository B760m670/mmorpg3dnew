class_name FreeCamera
extends Camera3D
## Инструмент обзора (не «фича»): свободная камера по касаниям, без интерфейса.
##
## ОДИН палец (в любом месте) — поворот, без инверсии. Палец вниз → камера вниз,
##   вверх → вверх; палец вправо → камера налево, влево → камера направо. Поворот
##   следует за пальцем (скорость = скорость пальца). Yaw без предела (360°),
##   pitch ограничен ±89° (без переворота горизонта).
## ДВА пальца — зум + перенос. Разводишь пальцы → приближение, сводишь →
##   отдаление (доллирование вдоль взгляда, как в фото). Смещение двух пальцев →
##   перенос камеры за пальцами (без реверса).
## СКОРОСТЬ переноса/зума растёт с высотой над землёй: у земли — медленно и
##   точно, высоко — быстро. Так регулировка удобна на масштабах планеты без
##   меню. Потолок высоты — уровень облаков.

@export var rot_sensitivity: float = 0.0026        # рад/пиксель (поворот за пальцем)
@export var pan_gain: float = 0.0016               # перенос: доля от высоты на пиксель
@export var dolly_gain: float = 0.0022             # зум: доля от высоты на пиксель
@export var cloud_level: float = 2500.0            # потолок высоты (пока хватит)
@export var min_speed_alt: float = 3.0             # мин. «высота» для скорости у земли

var terrain: Terrain                               # для высоты земли (скорость/потолок)

var _yaw: float = 0.0
var _pitch: float = -0.15
var _touches: Dictionary = {}                      # индекс → позиция (пиксели)
var _two_active: bool = false
var _prev_centroid: Vector2 = Vector2.ZERO
var _prev_dist: float = 0.0

func setup(pos: Vector3, look_at_target: Vector3) -> void:
	position = pos
	var dir := (look_at_target - pos).normalized()
	_yaw = atan2(-dir.x, -dir.z)                    # −Z вперёд
	_pitch = asin(clampf(dir.y, -1.0, 1.0))
	_apply_orientation()

func _ready() -> void:
	far = 8000.0

func _apply_orientation() -> void:
	_pitch = clampf(_pitch, deg_to_rad(-89.0), deg_to_rad(89.0))
	transform.basis = Basis(Vector3.UP, _yaw) * Basis(Vector3.RIGHT, _pitch)

func _ground_y(x: float, z: float) -> float:
	return terrain.height(x, z) if terrain != null else 0.0

func _speed_scale() -> float:
	# скорость ∝ высоте над землёй (у земли медленно, высоко быстро)
	var alt := position.y - _ground_y(position.x, position.z)
	return maxf(alt, min_speed_alt)

func _input(event: InputEvent) -> void:
	if event is InputEventScreenTouch:
		if event.pressed:
			_touches[event.index] = event.position
		else:
			_touches.erase(event.index)
		_two_active = false                          # сброс базы жеста при смене числа пальцев
	elif event is InputEventScreenDrag:
		_touches[event.index] = event.position
		var n := _touches.size()
		if n == 1:
			_rotate_by(event.relative)
		elif n >= 2:
			_two_finger()

func _rotate_by(rel: Vector2) -> void:
	# палец вправо (rel.x>0) → поворот налево; палец вниз (rel.y>0) → камера ВНИЗ (без инверсии)
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
	var d_dist := dist - _prev_dist                  # >0 развёл (дальше), <0 свёл (ближе)
	var d_centroid := centroid - _prev_centroid
	_prev_dist = dist
	_prev_centroid = centroid

	var s := _speed_scale()
	var b := transform.basis
	# доллирование вдоль взгляда: развёл пальцы → ближе, свёл → дальше (как в фото)
	position += (-b.z) * d_dist * dolly_gain * s
	# перенос за пальцами: палец вправо → камера вправо; палец вверх → камера вверх
	position += b.x * d_centroid.x * pan_gain * s
	position += b.y * (-d_centroid.y) * pan_gain * s

func _process(_delta: float) -> void:
	var gy := _ground_y(position.x, position.z)
	position.y = clampf(position.y, gy + 1.5, cloud_level)
