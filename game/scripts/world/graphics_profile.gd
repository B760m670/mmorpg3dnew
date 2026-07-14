class_name GraphicsProfile
extends RefCounted
## ЦЕНТРАЛЬНЫЙ профиль производительности. Одно место решает «сколько рисовать» —
## строители (трава, камни, участок земли, окружение) читают параметры отсюда,
## а не хардкодят. Профиль выводится из Settings.quality и держит цель до 120 FPS
## на A18 Pro (ProMotion): тяжёлый экранный пост-процесс — только на верхнем уровне.

# пост-обработка (GPU-дорогая)
var ssao := true
var ssil := true
var ssr := true
var volumetric_fog := true
var glow := true
var distant_fog := true

# плотность мира
var grass_count := 160000
var grass_radius := 100.0
var patch_radius := 46.0
var patch_step := 0.45
var rock_count := 400

# тени / кадр
var shadow_distance := 220.0
var msaa: int = Viewport.MSAA_2X
var render_scale := 1.0
var sky_realtime := true
var max_fps := 120

static func from_settings() -> GraphicsProfile:
	var p := GraphicsProfile.new()
	match Settings.quality:
		"high":
			# кинематографично: весь экранный пост, максимум плотности. До 120 FPS,
			# но в тяжёлых видах может проседать — для «красивых» кадров.
			p.ssao = true; p.ssil = true; p.ssr = true
			p.volumetric_fog = true; p.glow = true
			p.grass_count = 240000; p.grass_radius = 110.0
			p.patch_radius = 50.0; p.patch_step = 0.4
			p.rock_count = 500
			p.shadow_distance = 260.0; p.msaa = Viewport.MSAA_4X
			p.render_scale = 1.0; p.sky_realtime = true; p.max_fps = 120
		"performance":
			# цель — стабильные 120 FPS: без экранного пост-процесса и объёмного тумана.
			p.ssao = false; p.ssil = false; p.ssr = false
			p.volumetric_fog = false; p.glow = false; p.distant_fog = true
			p.grass_count = 90000; p.grass_radius = 80.0
			p.patch_radius = 38.0; p.patch_step = 0.5
			p.rock_count = 260
			p.shadow_distance = 150.0; p.msaa = Viewport.MSAA_2X
			p.render_scale = 0.9; p.sky_realtime = false; p.max_fps = 120
		_:  # "balanced" — 120 FPS с мягким затенением, без самых тяжёлых эффектов
			p.ssao = true; p.ssil = false; p.ssr = false
			p.volumetric_fog = false; p.glow = true; p.distant_fog = true
			p.grass_count = 150000; p.grass_radius = 95.0
			p.patch_radius = 44.0; p.patch_step = 0.45
			p.rock_count = 360
			p.shadow_distance = 190.0; p.msaa = Viewport.MSAA_2X
			p.render_scale = 1.0; p.sky_realtime = true; p.max_fps = 120
	return p

# применить общесистемные параметры (FPS, масштаб рендера, сглаживание)
func apply_to(world: Node) -> void:
	Engine.max_fps = max_fps
	var vp := world.get_viewport()
	vp.msaa_3d = msaa
	vp.scaling_3d_mode = Viewport.SCALING_3D_MODE_BILINEAR
	vp.scaling_3d_scale = render_scale
