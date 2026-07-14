class_name GraphicsProfile
extends RefCounted
## ЦЕНТРАЛЬНЫЙ профиль рендера. Собирается из ТРЁХ независимых осей (как в PUBG):
##   • Графика (graphics)   — ДЕТАЛИЗАЦИЯ: пост-процесс, плотность, тени, MSAA, масштаб.
##   • Частота кадров (fps) — цель FPS (энергосбережение … 120), главный рычаг нагрева.
##   • Стиль (style)        — ЦВЕТ/тон: тонемаппинг, насыщенность, контраст (без цены).
## Строители читают отсюда, ничего не хардкодя. Оси не смешиваются: можно «HD + 120 +
## киношный», можно «Плавно + эконом + классический».

# --- детализация (ось «Графика») ---
var ssao := true
var ssil := false
var ssr := false
var volumetric_fog := false
var glow := true
var distant_fog := true
var grass_count := 150000
var grass_radius := 95.0
var patch_radius := 44.0
var patch_step := 0.45
var rock_count := 360
var shadow_enabled := true
var shadow_distance := 190.0
var msaa: int = Viewport.MSAA_2X
var render_scale := 1.0
var sky_realtime := true

# --- частота кадров (ось «Частота кадров») ---
var max_fps := 60
var adaptive_res := true

# --- стиль (ось «Стиль») ---
var tonemap: int = Environment.TONE_MAPPER_ACES
var saturation := 1.12
var contrast := 1.16
var brightness := 1.02
var glow_by_style := true

static func from_settings() -> GraphicsProfile:
	var p := GraphicsProfile.new()
	p._detail(Settings.graphics)
	p.max_fps = Settings.frame_rate
	p.adaptive_res = Settings.adaptive_res
	p._style(Settings.style)
	if not p.glow_by_style:
		p.glow = false
	return p

# ось «Графика» — сколько геометрии/эффектов рисуем
func _detail(g: String) -> void:
	match g:
		"smooth":   # максимально лёгкий вид (анти-нагрев): без экранного пост-процесса
			ssao = false; ssil = false; ssr = false; volumetric_fog = false; distant_fog = true
			grass_count = 80000; grass_radius = 70.0
			patch_radius = 34.0; patch_step = 0.55; rock_count = 200
			shadow_enabled = true; shadow_distance = 120.0
			msaa = Viewport.MSAA_DISABLED; render_scale = 0.85; sky_realtime = false
		"hd":       # красивее: мягкое затенение + дальний туман, выше плотность
			ssao = true; ssil = false; ssr = false; volumetric_fog = false; distant_fog = true
			grass_count = 190000; grass_radius = 105.0
			patch_radius = 48.0; patch_step = 0.42; rock_count = 440
			shadow_enabled = true; shadow_distance = 220.0
			msaa = Viewport.MSAA_2X; render_scale = 1.0; sky_realtime = true
		"ultra":    # кинематографично: весь экранный пост, максимум плотности
			ssao = true; ssil = true; ssr = true; volumetric_fog = true; distant_fog = true
			grass_count = 240000; grass_radius = 115.0
			patch_radius = 52.0; patch_step = 0.38; rock_count = 520
			shadow_enabled = true; shadow_distance = 270.0
			msaa = Viewport.MSAA_4X; render_scale = 1.0; sky_realtime = true
		_:          # "balanced" — золотая середина
			ssao = true; ssil = false; ssr = false; volumetric_fog = false; distant_fog = true
			grass_count = 150000; grass_radius = 95.0
			patch_radius = 44.0; patch_step = 0.45; rock_count = 360
			shadow_enabled = true; shadow_distance = 190.0
			msaa = Viewport.MSAA_2X; render_scale = 1.0; sky_realtime = true

# ось «Стиль» — только цвет/тон, на производительность почти не влияет
func _style(s: String) -> void:
	match s:
		"colorful":   # яркий, насыщенный — объекты читаются контрастно
			tonemap = Environment.TONE_MAPPER_ACES
			saturation = 1.35; contrast = 1.22; brightness = 1.04; glow_by_style = true
		"realistic":  # естественный тон, спокойный цвет — «как в жизни»
			tonemap = Environment.TONE_MAPPER_FILMIC
			saturation = 1.0; contrast = 1.04; brightness = 1.0; glow_by_style = true
		"soft":       # мягкий, низкоконтрастный — меньше устают глаза
			tonemap = Environment.TONE_MAPPER_FILMIC
			saturation = 1.02; contrast = 0.94; brightness = 1.06; glow_by_style = true
		"movie":      # киношный: фильмик, тёплый, выше контраст, лёгкое свечение
			tonemap = Environment.TONE_MAPPER_FILMIC
			saturation = 1.14; contrast = 1.26; brightness = 1.0; glow_by_style = true
		_:            # "classic" — нейтральный сбалансированный тон
			tonemap = Environment.TONE_MAPPER_ACES
			saturation = 1.1; contrast = 1.16; brightness = 1.02; glow_by_style = true

# применить общесистемные параметры (FPS, масштаб рендера, сглаживание)
func apply_to(world: Node) -> void:
	Engine.max_fps = max_fps
	var vp := world.get_viewport()
	vp.msaa_3d = msaa
	vp.scaling_3d_mode = Viewport.SCALING_3D_MODE_BILINEAR
	vp.scaling_3d_scale = render_scale
