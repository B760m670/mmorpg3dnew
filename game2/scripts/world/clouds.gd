class_name Clouds
extends Node3D
## ОБЛАКА — объёмный слой (raymarch в clouds.gdshader) на куполе-сфере вокруг
## камеры. Здесь: 3D-шумы (Перлин fBm — форма, Ворли — эрозия краёв), купол,
## связь с солнцем/погодой/временем. Аддитивно — базовое небо не трогается.
##
## Движение: шум сносится ветром по времени; на быстрых сутках (5 мин) — ускоренно.
## Погода: coverage (0 ясно .. 1 сплошь) — берётся из пасмурности сцены.

@export var sun: DirectionalLight3D
@export var coverage: float = 0.55
@export var day_time_scale: float = 288.0     # как у WorldClock (сутки=5 мин)
@export var weather_enabled: bool = true      # false → покрытие фиксировано (для стенда)

# купол невелик: полотно облаков — не «горизонт мира», а канва для raymarch;
# меньший радиус → слабее равномерная дымка depth-fog на нём (иначе облака
# сереют до невидимости и сливаются с небом). Слой облаков (1200..3200 м)
# считается аналитически по мировому лучу, от радиуса купола не зависит.
const DOME_R := 2500.0
var _mat: ShaderMaterial
var _t: float = 0.0

# --- НАСТОЯЩАЯ СМЕНА ПОГОДЫ: покрытие медленно дышит (фронты приходят/уходят) ---
# Не «вечное пасмурное»: coverage плавно гуляет вокруг среднего по времени
# (в масштабе часов; на 5-мин сутках заметно за десятки секунд). Ветер при этом
# сносит сами облака (движение). current_coverage — для HUD.
var _weather_t: float = 0.0
var current_coverage: float = 0.55

func _make_noise_3d(cellular: bool, freq: float, octaves: int) -> NoiseTexture3D:
	var n := FastNoiseLite.new()
	n.noise_type = FastNoiseLite.TYPE_CELLULAR if cellular else FastNoiseLite.TYPE_PERLIN
	n.frequency = freq
	n.fractal_type = FastNoiseLite.FRACTAL_FBM
	n.fractal_octaves = octaves
	if cellular:
		n.cellular_distance_function = FastNoiseLite.DISTANCE_EUCLIDEAN
		n.cellular_return_type = FastNoiseLite.RETURN_DISTANCE
	var t := NoiseTexture3D.new()
	t.width = 64; t.height = 64; t.depth = 64
	t.seamless = true
	t.normalize = true
	t.noise = n
	return t

func build() -> void:
	_mat = ShaderMaterial.new()
	_mat.shader = load("res://shaders/world/clouds.gdshader")
	# НИЗКАЯ частота — крупные связные клубы (высокая давала «крупу»/шум вдоль луча)
	_mat.set_shader_parameter("shape_tex", _make_noise_3d(false, 0.035, 3))  # форма
	_mat.set_shader_parameter("detail_tex", _make_noise_3d(true, 0.10, 2))   # эрозия краёв
	_mat.set_shader_parameter("coverage", coverage)
	_mat.set_shader_parameter("sky_ambient", Vector3(0.72, 0.78, 0.88))  # тон яркого пасмурного неба
	_mat.set_shader_parameter("wind_x", 0.004)
	_mat.set_shader_parameter("wind_z", 0.002)

	var sphere := SphereMesh.new()
	sphere.radius = DOME_R
	sphere.height = DOME_R * 2.0
	sphere.radial_segments = 32
	sphere.rings = 16
	var mi := MeshInstance3D.new()
	mi.mesh = sphere
	mi.material_override = _mat
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	mi.custom_aabb = AABB(Vector3(-DOME_R, -DOME_R, -DOME_R), Vector3(DOME_R * 2.0, DOME_R * 2.0, DOME_R * 2.0))
	add_child(mi)
	print("[clouds] объёмный слой: купол R=%.0f, покрытие %.2f (raymarch Перлин-Ворли)" % [DOME_R, coverage])

## текстовая сводка погоды для HUD
func weather_label() -> String:
	var c := current_coverage
	var name := "ясно"
	if c > 0.8: name = "сплошная облачность"
	elif c > 0.62: name = "пасмурно"
	elif c > 0.45: name = "облачно"
	elif c > 0.28: name = "переменная облачность"
	else: name = "малооблачно"
	return "%s (%.0f%%)" % [name, c * 100.0]

func _process(delta: float) -> void:
	if _mat == null:
		return
	_t += delta * day_time_scale * 0.04          # дрейф облаков (быстрее на быстрых сутках)
	_mat.set_shader_parameter("time_s", _t)

	# смена погоды: медленное «дыхание» покрытия (сумма разнопериодных волн —
	# натуральнее одиночной синусоиды: фронты то плотнее, то с просветами)
	if weather_enabled:
		_weather_t += delta * day_time_scale     # в сим-секундах (сутки=86400)
		var w := 0.60 * sin(TAU * _weather_t / 43200.0) \
			+ 0.30 * sin(TAU * _weather_t / 15300.0 + 1.7) \
			+ 0.10 * sin(TAU * _weather_t / 6100.0 + 0.5)
		current_coverage = clampf(coverage + 0.26 * w, 0.18, 0.92)
	else:
		current_coverage = coverage
	_mat.set_shader_parameter("coverage", current_coverage)
	# купол едет за камерой; солнце — из направления света
	var cam := get_viewport().get_camera_3d()
	if cam != null:
		global_position = cam.global_position
	if sun != null:
		# к солнцу = +Z оси света (look_at ставит -Z на -to_sun → +Z = to_sun)
		var to_sun := sun.global_transform.basis.z.normalized()
		_mat.set_shader_parameter("sun_dir", to_sun)
		_mat.set_shader_parameter("sun_color", Vector3(sun.light_color.r, sun.light_color.g, sun.light_color.b))
