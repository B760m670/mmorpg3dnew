class_name RainSystem
extends Node3D
## ДОЖДЬ — настоящая погода, не декор. Три связанных слоя:
##   1) ПАДАЮЩИЕ КАПЛИ (GPUParticles3D): столб дождя над камерой, капли летят с
##      физической скоростью (терминальная ~9 м/с), сносятся ветром. Локальные
##      координаты выключены — капли живут в мире, столб едет за камерой.
##   2) НАПИТЫВАНИЕ ПОЧВЫ (rain_wet): поверхность мокнет НЕ мгновенно (запаздывает
##      за началом дождя) и сохнет медленно после — как настоящая земля. Число
##      идёт в шейдер земли: мокрое темнее/глянцевее, в вогнутостях-низинах стоит
##      вода (лужи — сток вниз, реальная гидрология рельефа).
##   3) ПОГОДА (WeatherClock): интенсивность дождя мм/ч меняется плавно сама —
##      ясно → сгущается → ливень → расходится. Тестер на устройстве застаёт
##      разные фазы (сухо / морось / ливень с лужами).
##
## Времена напитывания/высыхания сжаты под геймплей (десятки секунд, не часы),
## но ПОВЕДЕНИЕ реальное: влага отстаёт от дождя и держится после. Проверка —
## числами (rain_state в HUD/inspect): rate мм/ч, rain_wet 0..1.

@export var terrain: Terrain                 # источник rain_wet-уравения и материал земли

const FALL_SPEED := 9.0                       # терминальная скорость капли, м/с
const COVER_HALF := 26.0                      # полуширина столба дождя вокруг камеры, м
const SPAWN_UP := 22.0                        # капли рождаются на этой высоте над камерой
const MAX_DROPS := 4200                       # капель при ливне (rate=1)

# напитывание/высыхание (игровые времена, поведение реальное)
const TAU_WET := 14.0                         # с: постоянная времени промокания
const TAU_DRY := 90.0                         # с: медленное высыхание после дождя

# погодный цикл (сумма синусов — плавная смена без резких скачков)
const RAIN_MAX_MMH := 12.0                    # мм/ч на пике ливня

var rate_mmh: float = 0.0                     # текущая интенсивность, мм/ч
var rain_wet: float = 0.0                     # 0 сухо .. 1 поверхность насыщена
var wind := Vector2(2.2, -1.4)                # снос капель (восток, север) м/с

var _drops: GPUParticles3D
var _clock_t: float = 0.0

func _ready() -> void:
	_build_drops()

func _build_drops() -> void:
	_drops = GPUParticles3D.new()
	_drops.amount = MAX_DROPS
	_drops.lifetime = (SPAWN_UP + 4.0) / FALL_SPEED   # успеть долететь до земли
	_drops.local_coords = false                        # капли в мире (столб едет за камерой)
	_drops.fixed_fps = 0
	_drops.visibility_aabb = AABB(Vector3(-COVER_HALF, -SPAWN_UP, -COVER_HALF),
		Vector3(COVER_HALF * 2.0, SPAWN_UP + 8.0, COVER_HALF * 2.0))

	var pm := ParticleProcessMaterial.new()
	pm.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_BOX
	pm.emission_box_extents = Vector3(COVER_HALF, 0.5, COVER_HALF)
	pm.direction = Vector3(0, -1, 0)
	pm.spread = 0.0
	pm.gravity = Vector3(0, -1.5, 0)                    # почти терминальная: почти не разгоняется
	pm.initial_velocity_min = FALL_SPEED
	pm.initial_velocity_max = FALL_SPEED
	# ветер сносит столб (задаём как постоянное ускорение по XZ)
	pm.linear_accel_min = 0.0
	pm.linear_accel_max = 0.0
	_drops.process_material = pm

	# капля-штрих: тонкий вытянутый квад, направлен по скорости (падение = вертикаль)
	var qm := QuadMesh.new()
	qm.size = Vector2(0.015, 0.55)                      # тонкая длинная чёрточка
	var dm := StandardMaterial3D.new()
	dm.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	dm.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	dm.albedo_color = Color(0.72, 0.78, 0.86, 0.5)      # холодная светлая вода
	dm.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
	dm.billboard_keep_scale = true
	dm.particles_anim_v_frames = 1
	dm.disable_receive_shadows = true
	qm.material = dm
	_drops.draw_pass_1 = qm
	_drops.emitting = false
	add_child(_drops)

func _process(delta: float) -> void:
	_clock_t += delta
	# --- ПОГОДА: плавная интенсивность из суммы медленных синусов (0..1) ---
	var t := _clock_t
	var w := 0.5 + 0.32 * sin(t * 0.021 - 1.2) + 0.18 * sin(t * 0.053 + 0.4)
	w = clampf(w - 0.30, 0.0, 1.0) / 0.70               # порог: часть времени ясно
	rate_mmh = w * RAIN_MAX_MMH

	# --- НАПИТЫВАНИЕ: влага отстаёт от дождя, сохнет медленно ---
	var target := clampf(rate_mmh / (RAIN_MAX_MMH * 0.55), 0.0, 1.0)  # 6+ мм/ч → насыщение
	if target > rain_wet:
		rain_wet += (target - rain_wet) * (1.0 - exp(-delta / TAU_WET))
	else:
		rain_wet += (target - rain_wet) * (1.0 - exp(-delta / TAU_DRY))
	rain_wet = clampf(rain_wet, 0.0, 1.0)

	# --- капли: столб едет за камерой, плотность и снос ∝ дождю ---
	var cam := get_viewport().get_camera_3d()
	if cam != null:
		_drops.global_position = Vector3(cam.global_position.x, cam.global_position.y + SPAWN_UP, cam.global_position.z)
	_drops.emitting = rate_mmh > 0.05
	_drops.amount_ratio = clampf(rate_mmh / RAIN_MAX_MMH, 0.02, 1.0)
	var pm := _drops.process_material as ParticleProcessMaterial
	if pm != null:
		# ветер как горизонтальная составляющая скорости (снос струй)
		pm.direction = Vector3(wind.x, -FALL_SPEED, wind.y).normalized()
		var v := Vector3(wind.x, -FALL_SPEED, wind.y).length()
		pm.initial_velocity_min = v
		pm.initial_velocity_max = v

	# --- отдать погоду шейдеру земли (мокро/лужи/рябь) ---
	if terrain != null and terrain.ground_mat != null:
		terrain.ground_mat.set_shader_parameter("rain_wet", rain_wet)
		terrain.ground_mat.set_shader_parameter("rain_rate", clampf(rate_mmh / RAIN_MAX_MMH, 0.0, 1.0))

## строка состояния погоды числами (для HUD / --inspect)
func state() -> Dictionary:
	return {"rate_mmh": snappedf(rate_mmh, 0.1), "rain_wet": snappedf(rain_wet, 0.01),
		"raining": rate_mmh > 0.05}
