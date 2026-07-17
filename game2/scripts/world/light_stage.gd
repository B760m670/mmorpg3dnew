extends Node3D
## Ф1 «Свет» — первый кино-срез. Не игровой мир, а СТЕНД СВЕТА: золотой час,
## тёплое солнце с мягкой полутенью, физичное небо, реальная GI (SDFGI),
## контактные тени (SSAO), PBR-земля с микрорельефом, объекты для отскока и
## цветового бликования. Проверка — числами (гистограмма яркости, вклад GI),
## а не «на глаз». Кино-пост — тем же надёжным canvas-оверлеем. HUD измеримый.

const ENABLE_POST := true
const ENABLE_METALFX := true
const ENABLE_GI := true          # SDFGI (реальный отскок света)
const ENABLE_SSAO := true        # контактные тени
const ENABLE_GLOW := true        # мягкое свечение в бликах

var _post_mat: ShaderMaterial
var _hud: Label
var _env: Environment
var _sun: DirectionalLight3D
var _clock: WorldClock
var _terrain: Terrain
var _cam: FreeCamera

func _ready() -> void:
	# --- аргументы стенда (для оффлайн-аудита на CI) ---
	var args := OS.get_cmdline_user_args()
	var gi_off := "--gi-off" in args

	# самопроверки числами и выход
	if "--astro-test" in args:
		var wc := WorldClock.new()
		add_child(wc)
		wc.run_self_test()
		get_tree().quit()
		return
	if "--spectral-test" in args:
		var wc2 := WorldClock.new()
		add_child(wc2)
		wc2.run_spectral_test()
		get_tree().quit()
		return

	_env = _build_environment(ENABLE_GI and not gi_off)
	var we := WorldEnvironment.new()
	we.environment = _env
	add_child(we)

	_build_sun()
	_build_ground()
	_build_water()
	_build_props()
	_build_camera()

	if ENABLE_POST:
		_build_post_overlay()
	_build_hud(gi_off)

	if ENABLE_METALFX:
		Core.apply_scaling(get_viewport())

	# --- режим ИНСПЕКЦИИ (я «вхожу в мир»): задать время/камеру, выгрузить числа ---
	var inspect := "--inspect" in args
	var utc := _arg_val(args, "--utc")           # "HH:MM"
	if utc != "":
		var pp := utc.split(":")
		_clock.set_datetime_utc(2025, 6, 21, int(pp[0]), int(pp[1]) if pp.size() > 1 else 0, 0)
		_clock.time_scale = 0.0                   # фиксируем момент детерминированно
		_clock._compute_and_apply()
	var cp := _arg_val(args, "--campos")
	var cl := _arg_val(args, "--camlook")
	if cp != "" and cl != "":
		_cam.setup(_vec3(cp), _vec3(cl))

	print("[light] Ф1 свет, gi=", ENABLE_GI and not gi_off,
		" adapter=", RenderingServer.get_video_adapter_name())

	# офлайн-снимок / инспекция: ждём схождения и выгружаем состояние
	if "--boot-shot" in args or inspect:
		var out_path := _arg_val(args, "--out")
		if out_path == "":
			out_path = "/tmp/claude-0/-home-user-mmorpg3dnew/45dce9e0-e4bb-550f-b915-c58072470dda/scratchpad/light_shot.png"
		await get_tree().create_timer(2.5 if inspect else 3.5).timeout
		if inspect:
			_print_state()
		get_viewport().get_texture().get_image().save_png(out_path)
		print("[light] shot saved -> ", out_path)
		get_tree().quit()

func _arg_val(args: PackedStringArray, key: String) -> String:
	for a in args:
		if a.begins_with(key + "="):
			return a.substr(key.length() + 1)
	return ""

func _vec3(s: String) -> Vector3:
	var p := s.split(",")
	return Vector3(float(p[0]), float(p[1]), float(p[2]))

## выгрузка состояния мира числами (машинно-читаемо) — «взгляд изнутри»
func _print_state() -> void:
	var r := _terrain.report()
	var d := {
		"local": _clock.local_time_string(),
		"sun_el": snappedf(_clock.sun_elevation_deg, 0.1),
		"sun_az": snappedf(_clock.sun_azimuth_deg, 0.1),
		"daytime": _clock.is_daytime(),
		"sun_energy": snappedf(_sun.light_energy, 0.01),
		"sun_color": [snappedf(_sun.light_color.r, 0.01), snappedf(_sun.light_color.g, 0.01), snappedf(_sun.light_color.b, 0.01)],
		"sun_ct_k": int(_clock.sun_color_temp_k),
		"terrain_relief_m": snappedf(r["relief_m"], 0.1),
		"tris": r["tris"],
		"adapter": RenderingServer.get_video_adapter_name(),
	}
	print("STATE ", JSON.stringify(d))

# --- окружение: небо, тонемап, GI, SSAO, glow ---
func _build_environment(gi: bool) -> Environment:
	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	var sky := Sky.new()
	# ФИЗИЧЕСКОЕ небо: рэлеевское+ми рассеяние (не градиент). Золотой час
	# получается сам из низкого солнца — длинный путь через атмосферу краснит.
	var sm := PhysicalSkyMaterial.new()
	sm.rayleigh_coefficient = 2.6            # синева зенита
	sm.rayleigh_color = Color(0.26, 0.41, 0.58)
	sm.mie_coefficient = 0.005               # меньше мути
	sm.mie_eccentricity = 0.8
	sm.mie_color = Color(0.69, 0.71, 0.74)
	sm.turbidity = 3.2                        # чище воздух → голубой верх
	sm.sun_disk_scale = 1.6                   # почти реальный угловой размер (не «луна»)
	sm.ground_color = Color(0.20, 0.16, 0.12)
	sm.energy_multiplier = 1.1
	sm.use_debanding = true
	sky.sky_material = sm
	sky.process_mode = Sky.PROCESS_MODE_REALTIME   # без чёрного экрана до схождения
	sky.radiance_size = Sky.RADIANCE_SIZE_256       # realtime-небо требует 256
	env.sky = sky

	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_energy = 1.0
	env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY

	env.tonemap_mode = Environment.TONE_MAPPER_ACES
	env.tonemap_exposure = 1.0
	env.tonemap_white = 6.0

	if gi:
		env.sdfgi_enabled = true
		env.sdfgi_use_occlusion = true
		env.sdfgi_bounce_feedback = 0.85       # больше отскоков → заметнее цвет
		env.sdfgi_cascades = 4
		env.sdfgi_min_cell_size = 0.06
		env.sdfgi_energy = 1.6                  # усиленный вклад GI
		env.sdfgi_y_scale = Environment.SDFGI_Y_SCALE_75_PERCENT

	if ENABLE_SSAO:
		env.ssao_enabled = true
		env.ssao_radius = 0.5
		env.ssao_intensity = 1.5
		env.ssao_power = 1.5
		env.ssao_detail = 0.3

	if ENABLE_GLOW:
		env.glow_enabled = true
		env.glow_intensity = 0.5
		env.glow_bloom = 0.05
		env.glow_hdr_threshold = 1.1
		env.glow_blend_mode = Environment.GLOW_BLEND_MODE_SOFTLIGHT

	# воздушная перспектива: дальний рельеф растворяется в ЦВЕТЕ НЕБА (aerial=1),
	# контраст тёмная-земля/светлое-небо у горизонта падает → уходит алиасинг гряд
	env.fog_enabled = true
	env.fog_mode = Environment.FOG_MODE_DEPTH
	env.fog_light_color = Color(0.80, 0.84, 0.92)
	env.fog_density = 0.0016
	env.fog_sky_affect = 0.0
	env.fog_aerial_perspective = 1.0
	env.fog_depth_begin = 250.0
	env.fog_depth_end = 7000.0                    # территория 12.3 км — видим даль

	# ОБЪЁМНЫЙ туман: даёт световые шахты (god-rays) — тени в солнце режут
	# рассеяние, вперёд-рассеяние (anisotropy) тянет свет к солнцу.
	env.volumetric_fog_enabled = true
	env.volumetric_fog_density = 0.003
	env.volumetric_fog_albedo = Color(0.88, 0.80, 0.68)
	env.volumetric_fog_emission = Color(0, 0, 0)
	env.volumetric_fog_anisotropy = 0.72          # вперёд-рассеяние → лучи
	env.volumetric_fog_gi_inject = 1.0            # GI подсвечивает туман
	env.volumetric_fog_ambient_inject = 0.4
	env.volumetric_fog_length = 96.0
	env.volumetric_fog_detail_spread = 2.0
	return env

# --- солнце золотого часа с мягкой полутенью ---
func _build_sun() -> void:
	# Солнце: параметры тени задаём тут, а НАПРАВЛЕНИЕ/ЦВЕТ/ЭНЕРГИЮ ведёт
	# WorldClock из настоящей астрономии.
	_sun = DirectionalLight3D.new()
	_sun.shadow_enabled = true
	_sun.light_angular_distance = 1.4                   # диаметр диска → полутень
	_sun.shadow_blur = 1.2
	_sun.directional_shadow_max_distance = 90.0
	_sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
	add_child(_sun)

	_clock = WorldClock.new()
	_clock.sun = _sun
	# старт: летнее утро над Гатчиной, ясный фронтальный свет (местное 09:00 → UTC 06:00)
	_clock.set_datetime_utc(2025, 6, 21, 6, 0, 0)
	add_child(_clock)

# --- НАСТОЯЩАЯ земля: рельеф Гатчины в реальном масштабе (метры) ---
func _build_ground() -> void:
	_terrain = Terrain.new()
	add_child(_terrain)
	_terrain.build()

# --- вода по реальным контурам (шаг 1 генплана) ---
var _water: WaterBodies

func _build_water() -> void:
	_water = WaterBodies.new()
	_water.terrain = _terrain
	add_child(_water)
	_water.build()

# --- объекты-эталоны масштаба: реальные размеры, стоят НА рельефе ---
func _build_props() -> void:
	# человекоростовой столб-эталон (1.8 м) — чувство масштаба земли
	var post := MeshInstance3D.new()
	var pb := BoxMesh.new(); pb.size = Vector3(0.4, 1.8, 0.4)
	post.mesh = pb
	post.position = _on_ground(2.0, 0.0, 0.9)
	post.mesh.surface_set_material(0, _lit_mat(Color(0.74, 0.10, 0.08), 0.6))
	add_child(post)

	# нейтральные кубы 1 м — эталон и мягкие тени, сидят на земле
	for p in [Vector2(6, -4), Vector2(-5, 5), Vector2(0, 8)]:
		var b := MeshInstance3D.new()
		var bm := BoxMesh.new(); bm.size = Vector3(1, 1, 1)
		b.mesh = bm
		b.position = _on_ground(p.x, p.y, 0.5)
		b.mesh.surface_set_material(0, _lit_mat(Color(0.68, 0.66, 0.62), 0.6))
		add_child(b)

	# сфера-эталон радиусом 0.5 м
	var ball := MeshInstance3D.new()
	var sph := SphereMesh.new(); sph.radius = 0.5; sph.height = 1.0
	ball.mesh = sph
	ball.position = _on_ground(0.0, 0.0, 0.5)
	ball.mesh.surface_set_material(0, _lit_mat(Color(0.80, 0.78, 0.74), 0.35))
	add_child(ball)

## позиция на поверхности рельефа + смещение вверх (полувысота объекта)
func _on_ground(x: float, z: float, y_off: float) -> Vector3:
	var h := _terrain.height(x, z) if _terrain != null else 0.0
	return Vector3(x, h + y_off, z)

func _build_camera() -> void:
	_cam = FreeCamera.new()
	_cam.fov = 50.0
	_cam.terrain = _terrain
	add_child(_cam)
	_cam.far = 22000.0                            # видеть всю территорию 12.3 км
	# старт: над землёй у объектов-эталонов, смотрим на них — сразу можно крутить/летать
	var eye := _on_ground(18.0, 22.0, 6.0)
	_cam.setup(eye, _on_ground(0.0, 0.0, 0.8))
	_cam.current = true

func _build_post_overlay() -> void:
	var layer := CanvasLayer.new(); layer.layer = 100
	add_child(layer)
	var rect := ColorRect.new()
	rect.anchor_right = 1.0; rect.anchor_bottom = 1.0
	rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_post_mat = ShaderMaterial.new()
	_post_mat.shader = load("res://shaders/post/cinema_overlay.gdshader")
	rect.material = _post_mat
	layer.add_child(rect)

func _build_hud(gi_off: bool) -> void:
	var ui := CanvasLayer.new(); ui.layer = 101
	add_child(ui)
	_hud = Label.new()
	_hud.add_theme_font_size_override("font_size", 32)
	_hud.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.85))
	_hud.add_theme_constant_override("shadow_offset_x", 2)
	_hud.add_theme_constant_override("shadow_offset_y", 2)
	_hud.position = Vector2(60, 64)
	_hud.set_meta("gi_off", gi_off)
	ui.add_child(_hud)
	_update_hud()

# --- материалы/текстуры ---
func _lit_mat(col: Color, rough: float) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = col
	m.roughness = rough
	return m

func _noise_tex(size: int, freq: float, as_normal: bool, bump: float) -> NoiseTexture2D:
	var n := FastNoiseLite.new()
	n.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	n.frequency = freq
	n.fractal_octaves = 4
	var t := NoiseTexture2D.new()
	t.width = size; t.height = size
	t.seamless = true
	t.noise = n
	if as_normal:
		t.as_normal_map = true
		t.bump_strength = bump
	return t

func _scaling_mode_name(vp: Viewport) -> String:
	match vp.scaling_3d_mode:
		Viewport.SCALING_3D_MODE_BILINEAR: return "bilinear"
		Viewport.SCALING_3D_MODE_FSR: return "FSR1"
		Viewport.SCALING_3D_MODE_FSR2: return "FSR2"
		_:
			if "SCALING_3D_MODE_METALFX_TEMPORAL" in Viewport \
					and vp.scaling_3d_mode == Viewport.SCALING_3D_MODE_METALFX_TEMPORAL:
				return "MetalFX temporal"
			if "SCALING_3D_MODE_METALFX_SPATIAL" in Viewport \
					and vp.scaling_3d_mode == Viewport.SCALING_3D_MODE_METALFX_SPATIAL:
				return "MetalFX spatial"
			return "mode#%d" % vp.scaling_3d_mode

func _update_hud() -> void:
	if _hud == null:
		return
	var vp := get_viewport()
	var out := vp.get_visible_rect().size
	var scale := vp.scaling_3d_scale
	var inr := Vector2i(int(round(out.x * scale)), int(round(out.y * scale)))
	var mode := _scaling_mode_name(vp)
	var mfx := "ВКЛ" if mode.begins_with("MetalFX") else "нет"
	var gi_on := ENABLE_GI and not bool(_hud.get_meta("gi_off", false)) and _env.sdfgi_enabled
	_hud.text = "Ф3 · ЗЕМЛЯ+СВЕТ · Godot 4.5.2 (форк) · Metal\n" \
		+ "GPU: %s\n" % RenderingServer.get_video_adapter_name() \
		+ _terrain_line() \
		+ "Небо: физ.атмосфера   Туман(объём/god-rays): %s\n" % (
			"ВКЛ" if _env.volumetric_fog_enabled else "выкл") \
		+ "GI(SDFGI): %s   SSAO: %s   Glow: %s   пост: %s\n" % [
			"ВКЛ" if gi_on else "выкл",
			"ВКЛ" if ENABLE_SSAO else "выкл",
			"ВКЛ" if ENABLE_GLOW else "выкл",
			"ВКЛ" if ENABLE_POST else "выкл"] \
		+ "MetalFX: %s (%s)  3D %d×%d → %d×%d\n" % [mfx, mode, inr.x, inr.y, int(out.x), int(out.y)] \
		+ _clock_line() \
		+ "FPS: %d / лимит %d" % [Engine.get_frames_per_second(), Engine.max_fps]

func _terrain_line() -> String:
	if _terrain == null:
		return ""
	var r := _terrain.report()
	if r["real"]:
		return "Земля: %.1f×%.1f км · рельеф РЕАЛЬНЫЙ (Гатчина, DEM) %.0f..%.0f м · △ %d · вода: %d\n" % [
			r["size_m"] / 1000.0, r["size_m"] / 1000.0, r["abs_min"], r["abs_max"], r["tris"],
			_water.count_built if _water != null else 0]
	return "Земля: %.0f×%.0f м · рельеф ПРОЦЕДУРНЫЙ (фолбэк!) %.1f м · △ %d\n" % [
		r["size_m"], r["size_m"], r["relief_m"], r["tris"]]

func _clock_line() -> String:
	if _clock == null:
		return ""
	return "Гатчина %s · %s · Солнце %.1f°/аз %.0f° · %dK/%dклк · ×%d\n" % [
		_clock.local_time_string(),
		"ДЕНЬ" if _clock.is_daytime() else "НОЧЬ",
		_clock.sun_elevation_deg, _clock.sun_azimuth_deg,
		int(_clock.sun_color_temp_k), int(_clock.sun_direct_klx),
		int(_clock.time_scale)]

func _process(_delta: float) -> void:
	if _post_mat != null:
		_post_mat.set_shader_parameter("t", float(Time.get_ticks_msec()) / 1000.0)
	_update_hud()
