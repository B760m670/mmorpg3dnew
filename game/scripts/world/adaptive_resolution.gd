class_name AdaptiveResolution
extends Node
## Адаптивное разрешение — «подгонка» под целевой FPS БЕЗ упрощения качества.
## Текстуры, геометрия, трава, эффекты остаются на месте — плавно меняется только
## внутреннее разрешение рендера (scaling_3d_scale). Если кадр не успевает — чуть
## снижаем, если запас есть — возвращаем к базовому. Так GPU не работает «на 100%»
## постоянно → телефон не перегревается и держит стабильный FPS.

var _target_fps := 60.0
var _base_scale := 1.0        # потолок (качество выбранного пресета)
var _min_scale := 0.65        # ниже не опускаемся
var _scale := 1.0
var _accum := 0.0
var _frames := 0
var _interval := 0.6          # как часто пересматриваем, сек

func setup(target_fps: int, base_scale: float) -> void:
	_target_fps = float(maxi(target_fps, 24))
	_base_scale = base_scale
	_scale = base_scale
	_min_scale = maxf(0.6, base_scale * 0.72)

func _process(delta: float) -> void:
	_accum += delta
	_frames += 1
	if _accum < _interval:
		return
	var fps := _frames / _accum
	_accum = 0.0; _frames = 0
	var changed := false
	# не успеваем держать цель — снижаем разрешение маленьким шагом
	if fps < _target_fps * 0.90 and _scale > _min_scale:
		_scale = maxf(_min_scale, _scale - 0.05); changed = true
	# есть уверенный запас — возвращаем к базовому качеству
	elif fps > _target_fps * 0.98 and _scale < _base_scale:
		_scale = minf(_base_scale, _scale + 0.03); changed = true
	if changed:
		get_viewport().scaling_3d_scale = _scale
