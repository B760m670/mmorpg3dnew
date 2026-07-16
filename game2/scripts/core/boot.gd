extends Node3D
## Ф0 boot — возвращаем фичи ПО ОДНОЙ (платформа на iPhone подтверждена).
## Слой 2: кино-пост (compute-компоситор) ВКЛ. MetalFX пока ВЫКЛ — отдельным шагом.

const ENABLE_POST := true      # кино-пост: зерно/виньетка/хроматика (compute)
const ENABLE_METALFX := false  # MetalFX-апскейл (следующий слой)

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
	if ENABLE_POST:
		var comp := Compositor.new()
		comp.compositor_effects = [CinemaPost.new()]
		we.compositor = comp
	add_child(we)

	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-40, 30, 0)
	sun.light_energy = 2.0
	add_child(sun)

	var ball := MeshInstance3D.new()
	var sph := SphereMesh.new(); sph.radius = 0.5; sph.height = 1.0
	ball.mesh = sph
	var m := StandardMaterial3D.new()
	m.albedo_color = Color(0.75, 0.72, 0.68)
	m.roughness = 0.35
	ball.material_override = m
	ball.position = Vector3(0, 1.0, 0)
	add_child(ball)

	var floor_mi := MeshInstance3D.new()
	var pm := PlaneMesh.new(); pm.size = Vector2(8, 8)
	floor_mi.mesh = pm
	var fm := StandardMaterial3D.new()
	fm.albedo_color = Color(0.35, 0.34, 0.32)
	floor_mi.material_override = fm
	add_child(floor_mi)

	var cam := Camera3D.new()
	cam.position = Vector3(0, 1.4, 3.2)
	cam.rotation_degrees = Vector3(-8, 0, 0)
	add_child(cam)
	cam.current = true

	# крупная надпись-подтверждение, что рендер жив
	var layer := CanvasLayer.new()
	add_child(layer)
	var lbl := Label.new()
	lbl.text = "game2 · Godot 4.5.2 (форк) · Metal\nкино-пост: %s   MetalFX: %s" % [
		"ВКЛ" if ENABLE_POST else "выкл", "ВКЛ" if ENABLE_METALFX else "выкл"]
	lbl.add_theme_font_size_override("font_size", 40)
	lbl.position = Vector2(60, 80)
	layer.add_child(lbl)

	if ENABLE_METALFX:
		Core.apply_scaling(get_viewport())
	print("[boot] Ф0, post=", ENABLE_POST, " metalfx=", ENABLE_METALFX,
		" adapter=", RenderingServer.get_video_adapter_name())

	if "--boot-shot" in OS.get_cmdline_user_args():
		await get_tree().create_timer(1.0).timeout
		get_viewport().get_texture().get_image().save_png("/tmp/claude-0/-home-user-mmorpg3dnew/45dce9e0-e4bb-550f-b915-c58072470dda/scratchpad/boot_shot.png")
		print("[boot] shot saved")
		get_tree().quit()
