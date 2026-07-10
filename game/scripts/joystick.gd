extends Control
## Виртуальный джойстик: рисуется кодом, отдаёт нормализованный вектор.
## Вектор: x вправо, y вперёд (вверх по экрану = +y).

var vector := Vector2.ZERO
var _touch_id := -1
var _thumb := Vector2.ZERO

func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_STOP

func _radius() -> float:
	return min(size.x, size.y) * 0.5 - 12.0

func _center() -> Vector2:
	return size * 0.5

func _gui_input(event: InputEvent) -> void:
	if event is InputEventScreenTouch:
		if event.pressed and _touch_id == -1:
			_touch_id = event.index
			_update_thumb(event.position)
		elif not event.pressed and event.index == _touch_id:
			_touch_id = -1
			_thumb = Vector2.ZERO
			vector = Vector2.ZERO
			queue_redraw()
		accept_event()
	elif event is InputEventScreenDrag and event.index == _touch_id:
		_update_thumb(event.position)
		accept_event()

func _update_thumb(pos: Vector2) -> void:
	var d := pos - _center()
	var r := _radius()
	if d.length() > r:
		d = d.normalized() * r
	_thumb = d
	vector = Vector2(d.x / r, -d.y / r)
	queue_redraw()

func _draw() -> void:
	var c := _center()
	var r := _radius()
	draw_circle(c, r, Color(1, 1, 1, 0.08))
	draw_arc(c, r, 0.0, TAU, 48, Color(1, 1, 1, 0.38), 2.5)
	draw_circle(c + _thumb, r * 0.40, Color(1, 1, 1, 0.38))
