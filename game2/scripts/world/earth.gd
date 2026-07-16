extends Node3D
## Земля как ТЕЛО В КОСМОСЕ (content-free). Контейнер — космос (чёрное
## пространство + звёзды), не купол неба. Никаких мест контента в основании:
## система координат — ECEF (центр Земли), Земля стоит в начале, наблюдатель
## (камера) свободен в пространстве. Солнце — направление в ECEF (тело), ведёт
## освещение. Поверхность — WGS84 + РЕАЛЬНЫЕ высоты (DEM), цвет суша/океан.
## Плавающее начало у наблюдателя и наземная точность — следующий слой (E5).

const R := 6371000.0               # средний радиус Земли, м (для радиуса камеры)
const LON_SEG := 512
const LAT_SEG := 256
const START_DIST := R + 12000000.0 # старт: орбита ~12000 км

var _geo := Geo.new()
var _dem := Dem.new()
var _sun: DirectionalLight3D
var _clock: WorldClock
var _cam: FreeCamera
var _hud: Label

func _ready() -> void:
	var args := OS.get_cmdline_user_args()

	# научные самопроверки числами и выход (до постройки сцены)
	if "--geo-test" in args:
		Geo.new().run_self_test()
		get_tree().quit(); return
	if "--astro-test" in args:
		var wc := WorldClock.new(); add_child(wc)
		wc.run_self_test()
		get_tree().quit(); return

	_build_space()          # космос-контейнер
	_build_sun()
	_build_surface()        # Земля-тело
	_build_camera()
	_build_hud()
	if _ENABLE_METALFX:
		Core.apply_scaling(get_viewport())

	print("[earth] тело Земля в космосе; R=%.0f м; DEM=%s" % [R, _dem.loaded])

	if "--boot-shot" in args or "--inspect" in args:
		var out := _arg_val(args, "--out")
		if out == "":
			out = "/tmp/claude-0/-home-user-mmorpg3dnew/45dce9e0-e4bb-550f-b915-c58072470dda/scratchpad/earth.png"
		var dist := _arg_val(args, "--dist")
		if dist != "":
			var p := _cam.position.normalized() * float(dist)
			_cam.setup(p, Vector3.ZERO)
		await get_tree().create_timer(2.0).timeout
		get_viewport().get_texture().get_image().save_png(out)
		print("[earth] shot -> ", out)
		get_tree().quit()

const _ENABLE_METALFX := true

# --- космос: контейнер (чёрное пространство + звёзды) ---
func _build_space() -> void:
	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	var sky := Sky.new()
	var sm := ShaderMaterial.new()
	sm.shader = load("res://shaders/sky/cosmos.gdshader")
	sky.sky_material = sm
	sky.process_mode = Sky.PROCESS_MODE_REALTIME
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.015, 0.02, 0.03)   # едва-едва (звёздный свет)
	env.ambient_light_energy = 1.0
	env.tonemap_mode = Environment.TONE_MAPPER_ACES
	env.tonemap_white = 6.0
	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)

# --- Солнце: тело в пространстве, направление в ECEF ---
func _build_sun() -> void:
	_sun = DirectionalLight3D.new()
	_sun.light_angular_distance = 0.53          # реальный угловой размер
	_sun.light_energy = 3.6
	add_child(_sun)
	_clock = WorldClock.new()
	_clock.set_datetime_utc(2025, 6, 21, 12, 0, 0)   # полдень по Гринвичу
	add_child(_clock)
	_update_sun()

func _update_sun() -> void:
	var d := _clock.sun_ecef_direction(_clock.utc_unix)   # к Солнцу, в ECEF=рендер
	var up := Vector3.UP if absf(d.y) < 0.98 else Vector3(1, 0, 0)
	_sun.look_at_from_position(Vector3.ZERO, -d, up)      # свет летит ОТ Солнца

# --- Земля-тело: WGS84 + реальные высоты, центр в начале координат (ECEF) ---
func _build_surface() -> void:
	_dem.load_global()
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var row := LON_SEG + 1
	for j in range(LAT_SEG + 1):
		var lat := -89.0 + 178.0 * float(j) / float(LAT_SEG)
		for i in range(row):
			var lon := -180.0 + 360.0 * float(i) / float(LON_SEG)
			var h := _dem.elevation(lat, lon)
			st.set_color(_elev_color(h))
			st.set_normal(_ecef_normal(lat, lon))
			st.add_vertex(_ecef_vertex(lat, lon, h))
	for j in range(LAT_SEG):
		for i in range(LON_SEG):
			var a := j * row + i
			st.add_index(a); st.add_index(a + row); st.add_index(a + 1)
			st.add_index(a + 1); st.add_index(a + row); st.add_index(a + row + 1)
	var mi := MeshInstance3D.new()
	mi.mesh = st.commit()
	var m := StandardMaterial3D.new()
	m.vertex_color_use_as_albedo = true
	m.roughness = 1.0
	m.specular_mode = BaseMaterial3D.SPECULAR_DISABLED
	mi.material_override = m
	add_child(mi)

func _ecef_vertex(lat: float, lon: float, h: float) -> Vector3:
	var e := _geo.geodetic_to_ecef(lat, lon, h)
	return Vector3(e[0], e[1], e[2])

func _ecef_normal(lat: float, lon: float) -> Vector3:
	var la := lat * Geo.RAD
	var lo := lon * Geo.RAD
	return Vector3(cos(la) * cos(lo), cos(la) * sin(lo), sin(la)).normalized()

func _elev_color(h: float) -> Color:
	if h < 0.0:
		var d := clampf(-h / 6000.0, 0.0, 1.0)
		return Color(0.09, 0.22, 0.38).lerp(Color(0.01, 0.04, 0.13), d)
	var t := clampf(h / 2500.0, 0.0, 1.0)
	var c := Color(0.22, 0.36, 0.16).lerp(Color(0.42, 0.34, 0.22), t)
	if h > 3000.0:
		c = c.lerp(Color(0.92, 0.93, 0.95), clampf((h - 3000.0) / 2500.0, 0.0, 1.0))
	return c

func _build_camera() -> void:
	_cam = FreeCamera.new()
	_cam.fov = 55.0
	_cam.near = 100.0
	_cam.far = 6.0e7
	_cam.planet_radius = R
	_cam.cloud_level = 5.0e7          # предел удаления (радиальный режим)
	add_child(_cam)
	# старт: орбита над (30°,0°) — днём видна освещённая Африка/Европа
	var dir := _ecef_normal(30.0, 0.0)
	_cam.setup(dir * START_DIST, Vector3.ZERO)
	_cam.current = true

func _build_hud() -> void:
	var ui := CanvasLayer.new(); ui.layer = 101
	add_child(ui)
	_hud = Label.new()
	_hud.add_theme_font_size_override("font_size", 32)
	_hud.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.9))
	_hud.add_theme_constant_override("shadow_offset_x", 2)
	_hud.add_theme_constant_override("shadow_offset_y", 2)
	_hud.position = Vector2(60, 64)
	ui.add_child(_hud)

func _process(_delta: float) -> void:
	_update_sun()
	if _hud == null:
		return
	var altitude := _cam.position.length() - R
	_hud.text = "КОСМОС · Земля-тело · WGS84 + реальные высоты (DEM %s) · Metal\n" % (
			"да" if _dem.loaded else "НЕТ") \
		+ "система координат: ECEF (центр Земли), без привязки к месту\n" \
		+ "высота над поверхностью: %s км\n" % _fmt_km(altitude) \
		+ "%s · подсолнечная долгота движется (сутки)\n" % _clock.local_time_string() \
		+ "FPS: %d" % Engine.get_frames_per_second()

func _fmt_km(m: float) -> String:
	return "%.1f" % (m / 1000.0)

func _arg_val(args: PackedStringArray, key: String) -> String:
	for a in args:
		if a.begins_with(key + "="):
			return a.substr(key.length() + 1)
	return ""
