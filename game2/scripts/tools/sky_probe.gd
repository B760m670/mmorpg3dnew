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

	var cov := float(_val(a, "--cov", "0.55"))
	# пасмурность из покрытия (та же связка, что в игре) — НЕ фейковая крыша
	var oc: float = 0.0 if clear else WeatherSky.overcast_from_coverage(cov)

	# окружение: небо (когерентно погоде)
	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	var sky := Sky.new()
	var sm := PhysicalSkyMaterial.new()
	WeatherSky.apply_sky(sm, oc)
	sky.sky_material = sm
	sky.process_mode = Sky.PROCESS_MODE_REALTIME
	sky.radiance_size = Sky.RADIANCE_SIZE_128
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_energy = WeatherSky.ambient_energy(oc)
	env.tonemap_mode = Environment.TONE_MAPPER_ACES
	env.tonemap_exposure = WeatherSky.exposure(oc)
	var we := WorldEnvironment.new(); we.environment = env; add_child(we)

	# солнце + часы (пасмурность гасит/сереет прямой свет)
	_sun = DirectionalLight3D.new()
	_sun.light_angular_distance = 0.53          # реальный угловой размер (как в игре)
	add_child(_sun)
	_clock = WorldClock.new(); _clock.sun = _sun
	_clock.overcast = oc
	var d := _val(a, "--date", "2025-06-21").split("-")
	var t := _val(a, "--utc", "12:00").split(":")
	_clock.set_datetime_utc(int(d[0]), int(d[1]), int(d[2]), int(t[0]), int(t[1]) if t.size() > 1 else 0, 0)
	_clock.time_scale = 0.0
	add_child(_clock)
	_clock._compute_and_apply()

	# облака + ночное небо (те же классы, что в игре)
	_clouds = Clouds.new(); _clouds.sun = _sun
	_clouds.coverage = cov
	_clouds.weather_enabled = not ("--fixcov" in a)   # стенд: фиксировать покрытие
	add_child(_clouds); _clouds.build()
	_night = NightSky.new(); _night.sun = _sun; _night.clock = _clock
	add_child(_night); _night.build()

	# камера
	var cam := Camera3D.new()
	cam.far = 22000.0
	cam.fov = float(_val(a, "--fov", "75"))
	var cpos := _v3(_val(a, "--campos", "0,150,0"))
	cam.position = cpos
	add_child(cam)                        # в дереве ДО look_at (иначе ошибка/без поворота)
	var target := _v3(_val(a, "--camlook", "200,300,-200"))
	if "--lookmoon" in a:                 # навести камеру НА Луну (проверка перекрытия облаками)
		var mo2 := _clock.moon_state(_clock.utc_unix)
		var lst := _clock.local_sidereal_deg(_clock.utc_unix) * (PI / 180.0)
		var rar := float(mo2["ra_deg"]) * (PI / 180.0)
		var decr := float(mo2["dec_deg"]) * (PI / 180.0)
		var phi := _clock.latitude_deg * (PI / 180.0)
		var hh := lst - rar
		var alt := asin(clampf(sin(phi) * sin(decr) + cos(phi) * cos(decr) * cos(hh), -1.0, 1.0))
		var az := atan2(-cos(decr) * sin(hh), sin(decr) * cos(phi) - cos(decr) * sin(phi) * cos(hh))
		var mdir := Vector3(cos(alt) * sin(az), sin(alt), -cos(alt) * cos(az))
		target = cpos + mdir * 1000.0
		print("[skyprobe] навёл на Луну: alt %.1f° az %.1f°" % [rad_to_deg(alt), rad_to_deg(az)])
	cam.look_at(target)
	cam.make_current()

	var out := _val(a, "--out", "/tmp/sky.png")
	var wait := float(_val(a, "--wait", "2.5"))
	await get_tree().create_timer(wait).timeout
	var mo := _clock.moon_state(_clock.utc_unix)
	print("[skyprobe] Солнце %.1f° аз %.0f · погода %s · %s" % [
		_clock.sun_elevation_deg, _clock.sun_azimuth_deg,
		_clouds.weather_label(), "ясно" if clear else "пасмурно"])
	print("[skyprobe] Луна: RA %.1f° Dec %+.1f° освещ %.2f размер %.2f'" % [
		mo["ra_deg"], mo["dec_deg"], mo["illum"], mo["ang_diam_deg"] * 60.0])
	var img := get_viewport().get_texture().get_image()
	img.save_png(out)
	print("[skyprobe] shot -> ", out)
	get_tree().quit()
