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

const DOME_R := 8000.0
var _mat: ShaderMaterial
var _t: float = 0.0

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
	_mat.set_shader_parameter("shape_tex", _make_noise_3d(false, 0.9, 4))   # форма
	_mat.set_shader_parameter("detail_tex", _make_noise_3d(true, 1.6, 2))   # эрозия
	_mat.set_shader_parameter("coverage", coverage)
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

func _process(delta: float) -> void:
	if _mat == null:
		return
	_t += delta * day_time_scale * 0.04          # дрейф облаков (быстрее на быстрых сутках)
	_mat.set_shader_parameter("time_s", _t)
	# купол едет за камерой; солнце — из направления света
	var cam := get_viewport().get_camera_3d()
	if cam != null:
		global_position = cam.global_position
	if sun != null:
		# к солнцу = +Z оси света (look_at ставит -Z на -to_sun → +Z = to_sun)
		var to_sun := sun.global_transform.basis.z.normalized()
		_mat.set_shader_parameter("sun_dir", to_sun)
		_mat.set_shader_parameter("sun_color", Vector3(sun.light_color.r, sun.light_color.g, sun.light_color.b))
