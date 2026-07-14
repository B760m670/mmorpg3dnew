class_name MapOverlay
extends CanvasLayer
## Карта мира как отдельный узел: постройка, анимация открытия/закрытия (карта
## «прогружается» — плавное появление с масштабом) и маркер игрока. Контроллер
## мира только зовёт toggle().

var _root: Control
var _rect: TextureRect
var _marker: Control
var _tween: Tween
var _open := false
var _player: Node3D
var _world_size := 1800.0

func setup(player: Node3D, world_size: float) -> void:
	_player = player
	_world_size = world_size
	layer = 5
	visible = false
	_root = Control.new()
	_root.anchor_right = 1.0; _root.anchor_bottom = 1.0
	add_child(_root)
	var bg := ColorRect.new()
	bg.color = Color(0, 0, 0, 0.6)
	bg.anchor_right = 1.0; bg.anchor_bottom = 1.0
	_root.add_child(bg)
	_rect = TextureRect.new()
	_rect.texture = load("res://world/gatchina/map.png")
	_rect.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_rect.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	_rect.anchor_right = 1.0; _rect.anchor_bottom = 1.0
	_rect.offset_left = 40; _rect.offset_top = 40
	_rect.offset_right = -40; _rect.offset_bottom = -120
	_rect.pivot_offset = Vector2(556, 300)
	_root.add_child(_rect)
	_marker = Control.new()
	var dot := ColorRect.new()
	dot.color = Color(0.95, 0.15, 0.10)
	dot.size = Vector2(14, 14)
	dot.position = Vector2(-7, -7)
	_marker.add_child(dot)
	_rect.add_child(_marker)
	var close := UiKit.button("Закрыть", 24)
	close.anchor_left = 0.5; close.anchor_right = 0.5
	close.anchor_top = 1.0; close.anchor_bottom = 1.0
	close.offset_left = -95; close.offset_right = 95
	close.offset_top = -84; close.offset_bottom = -28
	close.pressed.connect(toggle)
	_root.add_child(close)

func toggle() -> void:
	if _open:
		close()
	else:
		open()

func open() -> void:
	_open = true
	visible = true
	if _tween != null and _tween.is_valid():
		_tween.kill()
	_root.modulate.a = 0.0
	_rect.scale = Vector2(0.9, 0.9)
	update_marker()
	_tween = create_tween().set_parallel(true).set_ease(Tween.EASE_OUT).set_trans(Tween.TRANS_CUBIC)
	_tween.tween_property(_root, "modulate:a", 1.0, 0.22)
	_tween.tween_property(_rect, "scale", Vector2.ONE, 0.28).set_trans(Tween.TRANS_BACK)

func close() -> void:
	_open = false
	if _tween != null and _tween.is_valid():
		_tween.kill()
	_tween = create_tween().set_parallel(true).set_ease(Tween.EASE_IN).set_trans(Tween.TRANS_CUBIC)
	_tween.tween_property(_root, "modulate:a", 0.0, 0.18)
	_tween.tween_property(_rect, "scale", Vector2(0.92, 0.92), 0.18)
	_tween.chain().tween_callback(func() -> void: visible = false)

func is_open() -> bool:
	return _open

func update_marker() -> void:
	if _rect == null or _rect.texture == null or _player == null:
		return
	var half := _world_size * 0.5
	var u: float = clampf((_player.global_position.x + half) / _world_size, 0.0, 1.0)
	var v: float = clampf((_player.global_position.z + half) / _world_size, 0.0, 1.0)
	var rs := _rect.size
	var ts := _rect.texture.get_size()
	var scale: float = minf(rs.x / ts.x, rs.y / ts.y)
	var draw := ts * scale
	var origin := (rs - draw) * 0.5
	_marker.position = origin + Vector2(u * draw.x, v * draw.y)
