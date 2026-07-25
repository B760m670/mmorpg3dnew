extends Node3D
## ЛЁГКИЙ СТЕНД НЕБА — только небо/облака/Луна/звёзды (без рельефа и города),
## чтобы РЕНДЕРИТЬ и ВИДЕТЬ их в софтовом GL за секунды (отладка неба на деле,
## а не вслепую). Не входит в игру — инструмент проверки.
## Аргументы: --out=путь --utc=HH:MM --date=YYYY-MM-DD --campos=x,y,z --camlook=x,y,z
##            --clear (ясное небо вместо пасмурного) --wait=сек

var _clock: WorldClock
var _sun: DirectionalLight3D
var _clouds: Clouds
var _night: NightSky

func _val(a: PackedStringArray, k: String, d: String) -> String:
	for s in a:
		if s.begins_with(k + "="):
			return s.substr(k.length() + 1)
	return d

func _v3(s: String) -> Vector3:
	var p := s.split(",")
	return Vector3(float(p[0]), float(p[1]), float(p[2]))

func _ready() -> void:
	var a := OS.get_cmdline_user_args()
	var clear := "--clear" in a

	# окружение: небо
	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	var sky := Sky.new()
	var sm := PhysicalSkyMaterial.new()
	if clear:
		sm.sun_disk_scale = 1.0
	else:
		sm.rayleigh_coefficient = 0.9
		sm.rayleigh_color = Color(0.55, 0.58, 0.62)
		sm.mie_coefficient = 0.09
		sm.mie_eccentricity = 0.55
		sm.mie_color = Color(0.86, 0.88, 0.90)
		sm.turbidity = 10.0
		sm.sun_disk_scale = 0.0
		sm.energy_multiplier = 1.5
	sky.sky_material = sm
	sky.process_mode = Sky.PROCESS_MODE_REALTIME
	sky.radiance_size = Sky.RADIANCE_SIZE_128
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_energy = 1.6
	env.tonemap_mode = Environment.TONE_MAPPER_ACES
	env.tonemap_exposure = 0.9
	var we := WorldEnvironment.new(); we.environment = env; add_child(we)

	# солнце + часы
	_sun = DirectionalLight3D.new(); add_child(_sun)
	_clock = WorldClock.new(); _clock.sun = _sun
	if not clear:
		_clock.overcast = 0.85
	var d := _val(a, "--date", "2025-06-21").split("-")
	var t := _val(a, "--utc", "12:00").split(":")
	_clock.set_datetime_utc(int(d[0]), int(d[1]), int(d[2]), int(t[0]), int(t[1]) if t.size() > 1 else 0, 0)
	_clock.time_scale = 0.0
	add_child(_clock)
	_clock._compute_and_apply()

	# облака + ночное небо (те же классы, что в игре)
	_clouds = Clouds.new(); _clouds.sun = _sun
	_clouds.coverage = float(_val(a, "--cov", "0.55"))
	_clouds.weather_enabled = not ("--fixcov" in a)   # стенд: фиксировать покрытие
	add_child(_clouds); _clouds.build()
	_night = NightSky.new(); _night.sun = _sun; _night.clock = _clock
	add_child(_night); _night.build()

	# камера
	var cam := Camera3D.new()
	cam.far = 22000.0
	cam.position = _v3(_val(a, "--campos", "0,150,0"))
	add_child(cam)                        # в дереве ДО look_at (иначе ошибка/без поворота)
	cam.look_at(_v3(_val(a, "--camlook", "200,300,-200")))
	cam.make_current()

	var out := _val(a, "--out", "/tmp/sky.png")
	var wait := float(_val(a, "--wait", "2.5"))
	await get_tree().create_timer(wait).timeout
	print("[skyprobe] Солнце %.1f° аз %.0f · погода %s · %s" % [
		_clock.sun_elevation_deg, _clock.sun_azimuth_deg,
		_clouds.weather_label(), "ясно" if clear else "пасмурно"])
	var img := get_viewport().get_texture().get_image()
	img.save_png(out)
	print("[skyprobe] shot -> ", out)
	get_tree().quit()
