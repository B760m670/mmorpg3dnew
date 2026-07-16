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

func _ready() -> void:
	# --- аргументы стенда (для оффлайн-аудита на CI) ---
	var args := OS.get_cmdline_user_args()
	var gi_off := "--gi-off" in args

	_env = _build_environment(ENABLE_GI and not gi_off)
	var we := WorldEnvironment.new()
	we.environment = _env
	add_child(we)

	_build_sun()
	_build_ground()
	_build_props()
	_build_camera()

	if ENABLE_POST:
		_build_post_overlay()
	_build_hud(gi_off)

	if ENABLE_METALFX:
		Core.apply_scaling(get_viewport())

	print("[light] Ф1 свет, gi=", ENABLE_GI and not gi_off,
		" adapter=", RenderingServer.get_video_adapter_name())

	# офлайн-снимок для аудита: ждём схождения SDFGI
	if "--boot-shot" in args:
		var out_path := "/tmp/claude-0/-home-user-mmorpg3dnew/45dce9e0-e4bb-550f-b915-c58072470dda/scratchpad/light_shot.png"
		for a in args:
			if a.begins_with("--out="):
				out_path = a.substr(6)
		await get_tree().create_timer(3.5).timeout
		get_viewport().get_texture().get_image().save_png(out_path)
		print("[light] shot saved -> ", out_path)
		get_tree().quit()

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
	sm.sun_disk_scale = 12.0
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

	# лёгкая воздушная перспектива (глубина)
	env.fog_enabled = true
	env.fog_light_color = Color(0.78, 0.70, 0.60)
	env.fog_density = 0.006
	env.fog_sky_affect = 0.0
	env.fog_aerial_perspective = 0.35

	# ОБЪЁМНЫЙ туман: даёт световые шахты (god-rays) — тени в солнце режут
	# рассеяние, вперёд-рассеяние (anisotropy) тянет свет к солнцу.
	env.volumetric_fog_enabled = true
	env.volumetric_fog_density = 0.012
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
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-18.0, -52.0, 0.0)   # низко над горизонтом
	sun.light_color = Color(1.0, 0.83, 0.62)            # тёплый ключ
	sun.light_energy = 3.6
	sun.shadow_enabled = true
	sun.light_angular_distance = 1.4                    # диаметр диска → полутень
	sun.shadow_blur = 1.2
	sun.directional_shadow_max_distance = 80.0
	sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
	add_child(sun)

# --- PBR-земля с микрорельефом (шум как альбедо/шероховатость/нормаль) ---
func _build_ground() -> void:
	var mi := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(48, 48)
	pm.subdivide_width = 64
	pm.subdivide_depth = 64
	mi.mesh = pm
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.42, 0.36, 0.28)          # земля/пыль
	mat.albedo_texture = _noise_tex(512, 0.02, false, 0.0)
	mat.uv1_scale = Vector3(8, 8, 1)
	mat.roughness = 0.95
	mat.roughness_texture = _noise_tex(512, 0.03, false, 0.0)
	mat.normal_enabled = true
	mat.normal_texture = _noise_tex(512, 0.05, true, 0.9)
	mat.normal_scale = 0.8
	mi.mesh.surface_set_material(0, mat)
	add_child(mi)

# --- объекты: показать отскок, цветовое бликование, контактные тени ---
func _build_props() -> void:
	# насыщенно-красная стена — источник цветного отскока на землю (доказ. GI)
	var wall := MeshInstance3D.new()
	var wb := BoxMesh.new(); wb.size = Vector3(0.4, 2.6, 5.2)
	wall.mesh = wb
	wall.position = Vector3(-3.8, 1.3, -0.6)
	wall.mesh.surface_set_material(0, _lit_mat(Color(0.74, 0.10, 0.08), 0.65))
	add_child(wall)

	# нейтральные блоки — мягкие тени и AO в стыках
	for spec in [
		[Vector3(2.2, 0.6, -1.5), Vector3(1.2, 1.2, 1.2), Color(0.70, 0.68, 0.64), 0.6],
		[Vector3(3.6, 0.4, 1.2), Vector3(0.8, 0.8, 0.8), Color(0.30, 0.32, 0.36), 0.4],
		[Vector3(0.4, 0.3, 2.4), Vector3(0.6, 0.6, 0.6), Color(0.55, 0.50, 0.40), 0.8],
	]:
		var b := MeshInstance3D.new()
		var bm := BoxMesh.new(); bm.size = spec[1]
		b.mesh = bm
		b.position = spec[0]
		b.mesh.surface_set_material(0, _lit_mat(spec[2], spec[3]))
		add_child(b)

	# фокус-сфера, диэлектрик, средняя шероховатость
	var ball := MeshInstance3D.new()
	var sph := SphereMesh.new(); sph.radius = 0.7; sph.height = 1.4
	ball.mesh = sph
	ball.position = Vector3(0.6, 0.7, 0.0)
	ball.mesh.surface_set_material(0, _lit_mat(Color(0.80, 0.78, 0.74), 0.35))
	add_child(ball)

func _build_camera() -> void:
	var cam := Camera3D.new()
	cam.fov = 46.0
	add_child(cam)
	cam.look_at_from_position(Vector3(5.4, 2.3, 6.2), Vector3(0.4, 0.9, 0.0), Vector3.UP)
	cam.current = true

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
	_hud.text = "Ф1 · СВЕТ · Godot 4.5.2 (форк) · Metal\n" \
		+ "GPU: %s\n" % RenderingServer.get_video_adapter_name() \
		+ "Небо: физ.атмосфера   Туман(объём/god-rays): %s\n" % (
			"ВКЛ" if _env.volumetric_fog_enabled else "выкл") \
		+ "GI(SDFGI): %s   SSAO: %s   Glow: %s   пост: %s\n" % [
			"ВКЛ" if gi_on else "выкл",
			"ВКЛ" if ENABLE_SSAO else "выкл",
			"ВКЛ" if ENABLE_GLOW else "выкл",
			"ВКЛ" if ENABLE_POST else "выкл"] \
		+ "MetalFX: %s (%s)  3D %d×%d → %d×%d\n" % [mfx, mode, inr.x, inr.y, int(out.x), int(out.y)] \
		+ "FPS: %d / лимит %d" % [Engine.get_frames_per_second(), Engine.max_fps]

func _process(_delta: float) -> void:
	if _post_mat != null:
		_post_mat.set_shader_parameter("t", float(Time.get_ticks_msec()) / 1000.0)
	_update_hud()
