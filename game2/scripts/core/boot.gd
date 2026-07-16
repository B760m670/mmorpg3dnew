extends Node3D
## Ф0 boot. Платформа на iPhone подтверждена (Metal + оверлей-пост, краха нет).
## Слой 3 — MetalFX-апскейл (ради него и форкали движок: рендер во внутреннем
## разрешении → апскейл в разрешение панели). Проверка ИЗМЕРИМАЯ: HUD с реальными
## числами (внутренний рендер → вывод, режим, масштаб, FPS, GPU). Если MetalFX
## не задействован (нет enum в шаблоне), HUD честно покажет bilinear 1.0.

const ENABLE_POST := true       # кино-пост (canvas-оверлей)
const ENABLE_METALFX := true    # MetalFX-апскейл (слой 3)

var _post_mat: ShaderMaterial
var _hud: Label

func _ready() -> void:
	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	var sky := Sky.new()
	var sm := ProceduralSkyMaterial.new()
	sm.sky_top_color = Color(0.25, 0.42, 0.66)
	sm.ground_bottom_color = Color(0.18, 0.16, 0.13)
	sky.sky_material = sm
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.tonemap_mode = Environment.TONE_MAPPER_ACES
	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)

	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-40, 30, 0)
	sun.light_energy = 2.0
	add_child(sun)

	var ball := MeshInstance3D.new()
	var sph := SphereMesh.new(); sph.radius = 0.5; sph.height = 1.0
	ball.mesh = sph
	var m := StandardMaterial3D.new()
	m.albedo_color = Color(0.75, 0.72, 0.68); m.roughness = 0.35
	ball.material_override = m
	ball.position = Vector3(0, 1.0, 0)
	add_child(ball)

	var floor_mi := MeshInstance3D.new()
	var pm := PlaneMesh.new(); pm.size = Vector2(8, 8)
	floor_mi.mesh = pm
	var fm := StandardMaterial3D.new(); fm.albedo_color = Color(0.35, 0.34, 0.32)
	floor_mi.material_override = fm
	add_child(floor_mi)

	var cam := Camera3D.new()
	cam.position = Vector3(0, 1.4, 3.2)
	cam.rotation_degrees = Vector3(-8, 0, 0)
	add_child(cam); cam.current = true

	# --- кино-пост оверлеем ---
	if ENABLE_POST:
		var layer := CanvasLayer.new()
		layer.layer = 100
		add_child(layer)
		var rect := ColorRect.new()
		rect.anchor_right = 1.0; rect.anchor_bottom = 1.0
		rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
		_post_mat = ShaderMaterial.new()
		_post_mat.shader = load("res://shaders/post/cinema_overlay.gdshader")
		rect.material = _post_mat
		layer.add_child(rect)

	if ENABLE_METALFX:
		Core.apply_scaling(get_viewport())

	# HUD с ИЗМЕРИМЫМИ числами (поверх поста — отдельный слой)
	var ui := CanvasLayer.new(); ui.layer = 101
	add_child(ui)
	_hud = Label.new()
	_hud.add_theme_font_size_override("font_size", 34)
	_hud.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.85))
	_hud.add_theme_constant_override("shadow_offset_x", 2)
	_hud.add_theme_constant_override("shadow_offset_y", 2)
	_hud.position = Vector2(60, 70)
	ui.add_child(_hud)
	_update_hud()

	print("[boot] Ф0, post=", ENABLE_POST, " metalfx=", ENABLE_METALFX,
		" adapter=", RenderingServer.get_video_adapter_name())

	if "--boot-shot" in OS.get_cmdline_user_args():
		await get_tree().create_timer(1.0).timeout
		get_viewport().get_texture().get_image().save_png("/tmp/claude-0/-home-user-mmorpg3dnew/45dce9e0-e4bb-550f-b915-c58072470dda/scratchpad/boot_shot.png")
		print("[boot] shot saved")
		get_tree().quit()

func _scaling_mode_name(vp: Viewport) -> String:
	# читаем то, что движок РЕАЛЬНО принял, а не то, что мы просили
	match vp.scaling_3d_mode:
		Viewport.SCALING_3D_MODE_BILINEAR: return "bilinear"
		Viewport.SCALING_3D_MODE_FSR: return "FSR1"
		Viewport.SCALING_3D_MODE_FSR2: return "FSR2"
		_:
			if "SCALING_3D_MODE_METALFX_SPATIAL" in Viewport \
					and vp.scaling_3d_mode == Viewport.SCALING_3D_MODE_METALFX_SPATIAL:
				return "MetalFX spatial"
			if "SCALING_3D_MODE_METALFX_TEMPORAL" in Viewport \
					and vp.scaling_3d_mode == Viewport.SCALING_3D_MODE_METALFX_TEMPORAL:
				return "MetalFX temporal"
			return "mode#%d" % vp.scaling_3d_mode

func _update_hud() -> void:
	if _hud == null:
		return
	var vp := get_viewport()
	var out := vp.get_visible_rect().size            # вывод (панель/окно)
	var scale := vp.scaling_3d_scale
	var inr := Vector2i(int(round(out.x * scale)), int(round(out.y * scale)))
	var mode := _scaling_mode_name(vp)
	var metalfx_on := mode.begins_with("MetalFX")
	_hud.text = "game2 · Godot 4.5.2 (форк) · Metal\n" \
		+ "GPU: %s\n" % RenderingServer.get_video_adapter_name() \
		+ "кино-пост(оверлей): %s\n" % ("ВКЛ" if ENABLE_POST else "выкл") \
		+ "MetalFX: %s  (%s)\n" % ["ВКЛ" if metalfx_on else "не задействован", mode] \
		+ "3D-рендер: %d×%d  →  вывод: %d×%d  (масштаб %.2f)\n" % [
			inr.x, inr.y, int(out.x), int(out.y), scale] \
		+ "FPS: %d / лимит %d" % [Engine.get_frames_per_second(), Engine.max_fps]

func _process(_delta: float) -> void:
	if _post_mat != null:
		_post_mat.set_shader_parameter("t", float(Time.get_ticks_msec()) / 1000.0)
	_update_hud()
