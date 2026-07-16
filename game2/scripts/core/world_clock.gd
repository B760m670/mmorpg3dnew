class_name WorldClock
extends Node
## Ф2.1 «Мировые часы» — сердце настоящего мира.
## Хранит реальные дату-время (UTC) и географию, вычисляет положение Солнца
## по астрономическому алгоритму (NOAA/Meeus) в ДВОЙНОЙ точности и ведёт им
## DirectionalLight + физическое небо. День/ночь/золотой час/длина дня/сезоны
## рождаются из реальности, а не подобраны вручную.
##
## Проверка — числами: полуденная высота Солнца в Гатчине должна совпасть с
## аналитикой (солнцестояния 53.9°/7.0°, равноденствие 30.4°). См. run_self_test().

@export var latitude_deg: float = 59.5648      # Гатчина
@export var longitude_deg: float = 30.1282     # восток — положительный
@export var tz_offset_hours: float = 3.0        # для отображения местного времени
@export var time_scale: float = 600.0           # 1 c реала = 600 c мира (сутки ≈ 2.4 мин)

var utc_unix: float = 0.0                        # мировое время (UTC), секунды
var sun: DirectionalLight3D                      # ведомый источник (назначается сценой)

# последний расчёт (для HUD)
var sun_elevation_deg: float = 0.0
var sun_azimuth_deg: float = 0.0
var sun_declination_deg: float = 0.0

const RAD := PI / 180.0
const DEG := 180.0 / PI

func set_datetime_utc(year: int, month: int, day: int, hour: int, minute: int, second: int) -> void:
	utc_unix = float(Time.get_unix_time_from_datetime_dict({
		"year": year, "month": month, "day": day,
		"hour": hour, "minute": minute, "second": second}))

func _process(delta: float) -> void:
	utc_unix += delta * time_scale
	_compute_and_apply()

# --- астрономия: положение Солнца из UTC-времени (Meeus, упрощ. NOAA) ---
func solar_position(unix_utc: float) -> Dictionary:
	# Юлианская дата
	var jd := unix_utc / 86400.0 + 2440587.5
	var t := (jd - 2451545.0) / 36525.0            # юлианские столетия от J2000

	var l0 := fposmod(280.46646 + t * (36000.76983 + t * 0.0003032), 360.0)
	var m := 357.52911 + t * (35999.05029 - 0.0001537 * t)
	var e := 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
	var mr := m * RAD
	var c := sin(mr) * (1.914602 - t * (0.004817 + 0.000014 * t)) \
		+ sin(2.0 * mr) * (0.019993 - 0.000101 * t) \
		+ sin(3.0 * mr) * 0.000289
	var true_long := l0 + c
	var omega := 125.04 - 1934.136 * t
	var lambda := true_long - 0.00569 - 0.00478 * sin(omega * RAD)   # видимая долгота

	var eps0 := 23.0 + (26.0 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60.0) / 60.0
	var eps := eps0 + 0.00256 * cos(omega * RAD)                      # наклон эклиптики

	var decl := asin(sin(eps * RAD) * sin(lambda * RAD)) * DEG        # склонение

	# уравнение времени (минуты)
	var y := tan(eps * RAD / 2.0)
	y = y * y
	var l0r := l0 * RAD
	var eot := 4.0 * DEG * (y * sin(2.0 * l0r) - 2.0 * e * sin(mr) \
		+ 4.0 * e * y * sin(mr) * cos(2.0 * l0r) \
		- 0.5 * y * y * sin(4.0 * l0r) - 1.25 * e * e * sin(2.0 * mr))

	# истинное солнечное время (минуты) на нашей долготе
	var minutes_utc := fposmod(unix_utc / 60.0, 1440.0)
	var tst := fposmod(minutes_utc + eot + 4.0 * longitude_deg, 1440.0)
	var ha := tst / 4.0 - 180.0                                        # часовой угол, град

	var lat := latitude_deg * RAD
	var dr := decl * RAD
	var har := ha * RAD
	var cos_zen := sin(lat) * sin(dr) + cos(lat) * cos(dr) * cos(har)
	cos_zen = clamp(cos_zen, -1.0, 1.0)
	var elev := (PI / 2.0 - acos(cos_zen)) * DEG                       # высота над горизонтом

	# азимут от севера по часовой
	var cos_az := (sin(dr) - sin(elev * RAD) * sin(lat)) / (cos(elev * RAD) * cos(lat))
	cos_az = clamp(cos_az, -1.0, 1.0)
	var az := acos(cos_az) * DEG
	if ha > 0.0:
		az = 360.0 - az

	return {"elevation": elev, "azimuth": az, "declination": decl}

func _compute_and_apply() -> void:
	var s := solar_position(utc_unix)
	sun_elevation_deg = s["elevation"]
	sun_azimuth_deg = s["azimuth"]
	sun_declination_deg = s["declination"]
	if sun == null:
		return

	# направление НА Солнце (Y-вверх, -Z=север, +X=восток)
	var el := sun_elevation_deg * RAD
	var az := sun_azimuth_deg * RAD
	var horiz := cos(el)
	var to_sun := Vector3(horiz * sin(az), sin(el), -horiz * cos(az)).normalized()
	# свет летит ОТ Солнца вниз → направление эмиссии = -to_sun
	var up := Vector3.UP if absf(to_sun.y) < 0.98 else Vector3(0, 0, 1)
	sun.look_at_from_position(Vector3.ZERO, -to_sun, up)

	# цвет и энергия — ФИЗИЧЕСКИ: чернотельник 5778 K через атмосферу.
	if sun_elevation_deg <= -0.83:                 # Солнце за горизонтом (с рефракцией)
		sun.light_energy = 0.0
		sun.shadow_enabled = false
	else:
		sun.shadow_enabled = true
		var ce := _physical_sun(sun_elevation_deg)
		sun.light_color = ce[0]
		sun.light_energy = ce[1]
		sun_color_temp_k = ce[2]

# --- физический свет Солнца: экстинкция Рэлея по воздушной массе ---
# Спектр Солнца (5778 K) фильтруется атмосферой; путь через воздух (airmass)
# растёт к горизонту → синее рассеивается сильнее → закат краснеет и слабеет.
const BB_5778 := Vector3(1.0, 0.985, 0.955)   # чернотельник 5778 K в sRGB (норм.)
# зенитные оптические толщи Рэлея по каналам (R~615, G~535, B~465 нм)
const TAU_R := 0.061
const TAU_G := 0.113
const TAU_B := 0.209
const SUN_BASE_ENERGY := 4.3
var sun_color_temp_k: float = 5778.0

func _airmass(elev_deg: float) -> float:
	# Kasten–Young (1989): реальный путь через атмосферу, растёт к горизонту
	var h := maxf(elev_deg, -0.5)
	return 1.0 / (sin(h * RAD) + 0.50572 * pow(h + 6.07995, -1.6364))

func _physical_sun(elev_deg: float) -> Array:
	var am := _airmass(elev_deg)
	# прямой луч = спектр Солнца × пропускание атмосферы по каналам
	var beam := Vector3(
		BB_5778.x * exp(-TAU_R * am),
		BB_5778.y * exp(-TAU_G * am),
		BB_5778.z * exp(-TAU_B * am))
	# яркость луча относительно высокого солнца (airmass≈1.15 при ~60°)
	var lum := 0.2126 * beam.x + 0.7152 * beam.y + 0.0722 * beam.z
	var ref := 0.2126 * (BB_5778.x * exp(-TAU_R * 1.15)) \
		+ 0.7152 * (BB_5778.y * exp(-TAU_G * 1.15)) \
		+ 0.0722 * (BB_5778.z * exp(-TAU_B * 1.15))
	var energy := clampf(SUN_BASE_ENERGY * lum / ref, 0.0, SUN_BASE_ENERGY)
	# цвет = оттенок луча (яркость несёт энергия), ярчайший канал = 1
	var mx := maxf(beam.x, maxf(beam.y, beam.z))
	var col := Color(beam.x / mx, beam.y / mx, beam.z / mx)
	# оценка цветовой температуры (для отчёта): грубо по отношению B/R
	var ct := clampf(1800.0 + 4000.0 * (col.b / maxf(col.r, 0.001)), 1500.0, 6500.0)
	return [col, energy, ct]

func is_daytime() -> bool:
	return sun_elevation_deg > -0.83

func local_time_string() -> String:
	var loc := utc_unix + tz_offset_hours * 3600.0
	var d := Time.get_datetime_dict_from_unix_time(int(loc))
	return "%04d-%02d-%02d  %02d:%02d  (UTC+%s)" % [
		d["year"], d["month"], d["day"], d["hour"], d["minute"], str(tz_offset_hours)]

# --- самопроверка астрономии числами (без интернета) ---
func run_self_test() -> void:
	print("=== АСТРО-ТЕСТ: полуденная высота Солнца в Гатчине (%.4f°с.ш.) ===" % latitude_deg)
	var cases := [
		["солнцестояние лето", 2025, 6, 21, 53.88],
		["равноденствие весна", 2025, 3, 20, 30.44],
		["солнцестояние зима", 2025, 12, 21, 6.98],
	]
	var max_err := 0.0
	for c in cases:
		# сканируем сутки по минуте, ищем максимум высоты = локальный полдень
		var best := -90.0
		var base := float(Time.get_unix_time_from_datetime_dict({
			"year": c[1], "month": c[2], "day": c[3],
			"hour": 0, "minute": 0, "second": 0}))
		for mnt in range(0, 1440):
			var el: float = solar_position(base + mnt * 60.0)["elevation"]
			if el > best:
				best = el
		var expected: float = c[4]
		var err := absf(best - expected)
		max_err = maxf(max_err, err)
		print("  %-22s расчёт=%.2f°  аналитика=%.2f°  ошибка=%.2f°" % [c[0], best, expected, err])
	print("  МАКС. ОШИБКА = %.2f°  → %s" % [max_err, "ОК (модель верна)" if max_err < 0.5 else "ПРОВАЛ"])
