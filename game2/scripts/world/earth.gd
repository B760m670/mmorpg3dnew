extends Node3D
## Земля E2 — настоящий эллипсоид WGS84 в РЕАЛЬНОМ масштабе.
## Якорь в Гатчине (ECEF, двойная точность). Рендер идёт в локальной системе
## ENU (восток/север/вверх) относительно якоря — плавающее начало координат,
## поэтому у камеры сохраняется точность несмотря на 6371 км Земли.
## Поверхность — участок эллипсоида; с высоты видна НАСТОЯЩАЯ кривизна горизонта.
## Топографии/океанов пока нет (это E3/E4) — поверхность гладкая, но настоящей
## формы и масштаба. Свет ведёт WorldClock (его горизонтные координаты = наш ENU).

const ANCHOR_LAT := Geo.GATCHINA_LAT
const ANCHOR_LON := Geo.GATCHINA_LON
const LON_SEG := 512               # разбиение планеты по долготе
const LAT_SEG := 256               # по широте
const START_ALT := 12000000.0      # старт камеры: 12000 км — видно всю Землю (шар)

var _geo := Geo.new()
var _dem := Dem.new()
var _anchor := Vector3.ZERO        # ECEF якоря (через double-массив ниже)
var _ax := 0.0
var _ay := 0.0
var _az := 0.0
var _east := Vector3.ZERO
var _north := Vector3.ZERO
var _up := Vector3.ZERO
var _sun: DirectionalLight3D
var _clock: WorldClock
var _cam: FreeCamera
var _hud: Label

func _ready() -> void:
	var args := OS.get_cmdline_user_args()
	_init_anchor()

	_build_environment()
	_build_sun()
	_build_surface()
	_build_camera()
	_build_hud()

	if ENABLE_METALFX():
		Core.apply_scaling(get_viewport())

	var horizon := _geo.horizon_distance(START_ALT)
	print("[earth] якорь Гатчина (%.4f,%.4f) ECEF=(%.1f,%.1f,%.1f)  горизонт с %.0f м = %.0f км" % [
		ANCHOR_LAT, ANCHOR_LON, _ax, _ay, _az, START_ALT, horizon / 1000.0])

	if "--boot-shot" in args or "--inspect" in args:
		var out := _arg_val(args, "--out")
		if out == "":
			out = "/tmp/claude-0/-home-user-mmorpg3dnew/45dce9e0-e4bb-550f-b915-c58072470dda/scratchpad/earth.png"
		var alt := _arg_val(args, "--alt")
		if alt != "":
			_cam.setup(Vector3(0, float(alt), 0), _ecef_to_render(0.0, 0.0, 0.0))
		await get_tree().create_timer(2.0).timeout
		get_viewport().get_texture().get_image().save_png(out)
		print("[earth] shot -> ", out)
		get_tree().quit()

func ENABLE_METALFX() -> bool:
	return true

# --- якорь и локальный базис ENU (в ECEF) ---
func _init_anchor() -> void:
	var e := _geo.geodetic_to_ecef(ANCHOR_LAT, ANCHOR_LON, 0.0)
	_ax = e[0]; _ay = e[1]; _az = e[2]
	var lat := ANCHOR_LAT * Geo.RAD
	var lon := ANCHOR_LON * Geo.RAD
	_east = Vector3(-sin(lon), cos(lon), 0.0)
	_north = Vector3(-sin(lat) * cos(lon), -sin(lat) * sin(lon), cos(lat))
	_up = Vector3(cos(lat) * cos(lon), cos(lat) * sin(lon), sin(lat))

## ECEF(double) → локальный рендер (Godot Y-вверх: X=восток, Y=вверх, Z=-север)
func _ecef_to_render(x: float, y: float, z: float) -> Vector3:
	var dx := x - _ax
	var dy := y - _ay
	var dz := z - _az
	var e := _east.x * dx + _east.y * dy + _east.z * dz
	var n := _north.x * dx + _north.y * dy + _north.z * dz
	var u := _up.x * dx + _up.y * dy + _up.z * dz
	return Vector3(e, u, -n)

func _geo_to_render(lat_deg: float, lon_deg: float, h: float) -> Vector3:
	var e := _geo.geodetic_to_ecef(lat_deg, lon_deg, h)
	return _ecef_to_render(e[0], e[1], e[2])

## нормаль поверхности эллипсоида (геодезическая вертикаль) в рендер-базисе
func _surface_normal(lat_deg: float, lon_deg: float) -> Vector3:
	var lat := lat_deg * Geo.RAD
	var lon := lon_deg * Geo.RAD
	var nx := cos(lat) * cos(lon)
	var ny := cos(lat) * sin(lon)
	var nz := sin(lat)
	var e := _east.x * nx + _east.y * ny + _east.z * nz
	var n := _north.x * nx + _north.y * ny + _north.z * nz
	var u := _up.x * nx + _up.y * ny + _up.z * nz
	return Vector3(e, u, -n).normalized()

# --- ВСЯ планета: реальные высоты (DEM), суша/океан по данным ---
func _build_surface() -> void:
	_dem.load_global()
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var row := LON_SEG + 1
	for j in range(LAT_SEG + 1):
		var lat := -89.0 + 178.0 * float(j) / float(LAT_SEG)
		for i in range(row):
			var lon := -180.0 + 360.0 * float(i) / float(LON_SEG)
			var h := _dem.elevation(lat, lon)          # НАСТОЯЩАЯ высота
			st.set_color(_elev_color(h))
			st.set_normal(_surface_normal(lat, lon))
			st.add_vertex(_geo_to_render(lat, lon, h))
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

## цвет поверхности по реальной высоте: океан (глубина) / суша / снег
func _elev_color(h: float) -> Color:
	if h < 0.0:
		var d := clampf(-h / 6000.0, 0.0, 1.0)
		return Color(0.09, 0.22, 0.38).lerp(Color(0.01, 0.04, 0.13), d)
	var t := clampf(h / 2500.0, 0.0, 1.0)
	var c := Color(0.22, 0.36, 0.16).lerp(Color(0.42, 0.34, 0.22), t)
	if h > 3000.0:
		c = c.lerp(Color(0.92, 0.93, 0.95), clampf((h - 3000.0) / 2500.0, 0.0, 1.0))
	return c

func _build_environment() -> void:
	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	var sky := Sky.new()
	var sm := PhysicalSkyMaterial.new()
	sm.rayleigh_coefficient = 2.6
	sm.mie_coefficient = 0.005
	sm.turbidity = 3.2
	sm.sun_disk_scale = 1.6
	sm.ground_color = Color(0.12, 0.14, 0.12)
	sm.energy_multiplier = 1.1
	sky.sky_material = sm
	sky.process_mode = Sky.PROCESS_MODE_REALTIME
	sky.radiance_size = Sky.RADIANCE_SIZE_256
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_energy = 1.0
	env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	env.tonemap_mode = Environment.TONE_MAPPER_ACES
	env.tonemap_white = 6.0
	env.fog_enabled = false            # вид из космоса — приземная дымка не нужна
	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)

func _build_sun() -> void:
	_sun = DirectionalLight3D.new()
	_sun.shadow_enabled = true
	_sun.light_angular_distance = 0.53      # реальный угловой размер Солнца
	_sun.directional_shadow_max_distance = 20000.0
	add_child(_sun)
	_clock = WorldClock.new()
	_clock.latitude_deg = ANCHOR_LAT
	_clock.longitude_deg = ANCHOR_LON
	_clock.sun = _sun
	_clock.set_datetime_utc(2025, 6, 21, 9, 0, 0)   # день, солнце высоко
	add_child(_clock)

func _build_camera() -> void:
	_cam = FreeCamera.new()
	_cam.fov = 60.0
	_cam.near = 50.0
	_cam.far = 5.0e7                        # планета простирается на миллионы метров
	_cam.cloud_level = 30000000.0          # можно отлететь и увидеть всю Землю
	add_child(_cam)
	# старт: высоко над Гатчиной, взгляд в ЦЕНТР Земли — виден весь шар
	_cam.setup(Vector3(0, START_ALT, 0), _ecef_to_render(0.0, 0.0, 0.0))
	_cam.current = true

func _build_hud() -> void:
	var ui := CanvasLayer.new(); ui.layer = 101
	add_child(ui)
	_hud = Label.new()
	_hud.add_theme_font_size_override("font_size", 32)
	_hud.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.85))
	_hud.add_theme_constant_override("shadow_offset_x", 2)
	_hud.add_theme_constant_override("shadow_offset_y", 2)
	_hud.position = Vector2(60, 64)
	ui.add_child(_hud)

func _process(_delta: float) -> void:
	if _hud == null:
		return
	var alt := _cam.position.y
	var horizon := _geo.horizon_distance(maxf(alt, 1.0))
	_hud.text = "Земля E3 · WGS84 · РЕАЛЬНЫЕ высоты (DEM %s) · Metal\n" % (
			"загружен" if _dem.loaded else "НЕТ") \
		+ "якорь: Гатчина %.4f°N %.4f°E (ECEF, double)\n" % [ANCHOR_LAT, ANCHOR_LON] \
		+ "высота камеры: %.1f км   горизонт: %.0f км\n" % [alt / 1000.0, horizon / 1000.0] \
		+ "%s · Солнце %.1f°/аз %.0f°\n" % [_clock.local_time_string(),
			_clock.sun_elevation_deg, _clock.sun_azimuth_deg] \
		+ "FPS: %d" % Engine.get_frames_per_second()

func _arg_val(args: PackedStringArray, key: String) -> String:
	for a in args:
		if a.begins_with(key + "="):
			return a.substr(key.length() + 1)
	return ""
