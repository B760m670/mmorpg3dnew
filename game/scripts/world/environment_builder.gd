class_name EnvironmentBuilder
extends RefCounted
## Небо (физическая атмосфера), солнце, туман, пост-обработка и качество графики.
## Строится один раз при загрузке мира.

static func build(world: Node3D, gp: GraphicsProfile) -> void:
	var sky_mat := ShaderMaterial.new()
	sky_mat.shader = load("res://shaders/sky.gdshader")
	var sky := Sky.new()
	sky.sky_material = sky_mat
	sky.radiance_size = Sky.RADIANCE_SIZE_64
	# realtime только на верхних уровнях: пересчёт ambient каждый кадр дорог
	sky.process_mode = Sky.PROCESS_MODE_REALTIME if gp.sky_realtime else Sky.PROCESS_MODE_INCREMENTAL
	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_energy = 0.6
	env.tonemap_mode = Environment.TONE_MAPPER_ACES
	env.tonemap_exposure = 1.0

	# Затенение в складках/углах и экранное непрямое освещение (по профилю)
	env.ssao_enabled = gp.ssao
	env.ssao_radius = 3.0
	env.ssao_intensity = 3.2
	env.ssao_power = 2.0
	env.ssao_detail = 1.0
	env.ssil_enabled = gp.ssil
	env.ssil_radius = 4.0
	env.ssil_intensity = 1.0
	# Экранные отражения (вода, полированные поверхности)
	env.ssr_enabled = gp.ssr
	env.ssr_max_steps = 48
	env.ssr_fade_in = 0.15
	env.ssr_fade_out = 3.0
	# Объёмный туман — атмосфера, «воздух» между зданиями и над озёрами
	env.volumetric_fog_enabled = gp.volumetric_fog
	env.volumetric_fog_density = 0.0016
	env.volumetric_fog_albedo = Color(0.86, 0.89, 0.94)
	env.volumetric_fog_length = 180.0
	env.volumetric_fog_gi_inject = 0.6
	# Дальний туман для глубины
	env.fog_enabled = gp.distant_fog
	env.fog_light_color = Color(0.72, 0.78, 0.84)
	env.fog_density = 0.0009
	env.fog_sky_affect = 0.25
	env.fog_aerial_perspective = 0.5
	# Свечение ярких мест (солнце на золоте/воде)
	env.glow_enabled = gp.glow
	env.glow_intensity = 0.5
	env.glow_bloom = 0.1
	env.glow_blend_mode = Environment.GLOW_BLEND_MODE_SOFTLIGHT
	# Цветокоррекция — тёплый исторический тон
	env.adjustment_enabled = true
	env.adjustment_brightness = 1.02
	env.adjustment_contrast = 1.16
	env.adjustment_saturation = 1.18

	var we := WorldEnvironment.new(); we.environment = env
	world.add_child(we)

	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Settings.sun_rotation_deg()
	sun.light_energy = 0.5 if Settings.is_night() else 3.8
	sun.light_color = Color(1.0, 0.95, 0.86)
	sun.shadow_enabled = true
	sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
	sun.directional_shadow_max_distance = gp.shadow_distance
	sun.directional_shadow_split_1 = 0.08
	sun.directional_shadow_split_2 = 0.2
	sun.directional_shadow_split_3 = 0.5
	sun.directional_shadow_blend_splits = true
	world.add_child(sun)
