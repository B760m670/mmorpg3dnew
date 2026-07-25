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
@export var time_scale: float = 60.0            # 1 c реала = 60 c мира (сутки = 24 мин)

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
		# ПАСМУРНОСТЬ (облачность Гатчины): облака режут ПРЯМОЕ солнце и холодят/
		# обесцвечивают его (свет становится рассеянным серым). Положение Солнца —
		# по-прежнему настоящая астрономия; меняется только КАЧЕСТВО света.
		var col: Color = ce[0]
		col = col.lerp(Color(0.82, 0.85, 0.90), overcast * 0.75)
		sun.light_color = col
		sun.light_energy = float(ce[1]) * lerpf(1.0, 0.22, overcast)
		sun_color_temp_k = ce[2]

# --- ПОЛНАЯ СПЕКТРАЛЬНАЯ ФИЗИКА прямого солнечного луча ---
# Спектр: закон Планка при T=5778 K, 41 отсчёт 380..780 нм.
# Атмосфера, оптическая толща по каждой длине волны τ(λ):
#   Рэлей: 0.008569·λ⁻⁴(1+0.0113·λ⁻²+0.00013·λ⁻⁴), λ в мкм (τ550≈0.097 — как в лит.)
#   аэрозоль Ангстрёма: β·λ^−α (α=1.3, β=0.046 — ясный день)
#   озон, полоса Шаппюи: пик ~602 нм, столб 0.3 атм·см
# Пропускание T(λ)=exp(−m·τ(λ)), m — воздушная масса Kasten–Young (1989).
# Цвет: спектр → CIE XYZ (аналитические CMF Wyman–Sloan–Shirley 2013) →
#   линейный sRGB. Цвет. температура — McCamy (1992). Освещённость — из Y,
#   калибровка: внеатмосферная освещённость Солнца 133.3 клк.
# Проверка: run_spectral_test() — в вакууме конвейер обязан дать ≈5778 K.
const SUN_BASE_ENERGY := 4.3
const SUN_T_K := 5778.0
const EXO_ILLUM_KLX := 133.3        # освещённость вне атмосферы, клк
const SPEC_N := 41
const LAM0 := 380.0
const DLAM := 10.0

var sun_color_temp_k: float = 5778.0
var overcast: float = 0.0            # 0 ясно .. 1 сплошная облачность (Гатчина ~0.85)
var sun_direct_klx: float = 0.0      # освещённость прямым лучом (клк)

var _lut_ready := false
var _lut_col: Array[Color] = []
var _lut_energy: PackedFloat32Array = PackedFloat32Array()
var _lut_ct: PackedFloat32Array = PackedFloat32Array()
var _lut_klx: PackedFloat32Array = PackedFloat32Array()

func _airmass(elev_deg: float) -> float:
	# Kasten–Young (1989): реальный путь луча через атмосферу
	var h := maxf(elev_deg, 0.0)
	return 1.0 / (sin(h * RAD) + 0.50572 * pow(h + 6.07995, -1.6364))

func _planck(lam_nm: float) -> float:
	# спектральная плотность излучения (относительная), T = 5778 K
	var lam := lam_nm * 1e-9
	return 1.0 / (pow(lam, 5.0) * (exp(0.0143877688 / (lam * SUN_T_K)) - 1.0))

func _tau(lam_nm: float) -> float:
	var um := lam_nm / 1000.0
	var um2 := um * um
	var rayleigh := 0.008569 / (um2 * um2) * (1.0 + 0.0113 / um2 + 0.00013 / (um2 * um2))
	var aerosol := 0.046 * pow(um, -1.3)
	var ozone := 0.036 * exp(-0.5 * pow((lam_nm - 602.0) / 55.0, 2.0))
	return rayleigh + aerosol + ozone

func _cmf_lobe(l: float, mu: float, s1: float, s2: float) -> float:
	var s := s1 if l < mu else s2
	return exp(-0.5 * pow((l - mu) / s, 2.0))

func _cmf(l: float) -> Vector3:
	# CIE 1931 2° через аналитические гауссианы (Wyman–Sloan–Shirley 2013)
	var x := 1.056 * _cmf_lobe(l, 599.8, 37.9, 31.0) \
		+ 0.362 * _cmf_lobe(l, 442.0, 16.0, 26.7) \
		- 0.065 * _cmf_lobe(l, 501.1, 20.4, 26.2)
	var y := 0.821 * _cmf_lobe(l, 568.8, 46.9, 40.5) \
		+ 0.286 * _cmf_lobe(l, 530.9, 16.3, 31.1)
	var z := 1.217 * _cmf_lobe(l, 437.0, 11.8, 36.0) \
		+ 0.681 * _cmf_lobe(l, 459.0, 26.0, 13.8)
	return Vector3(x, y, z)

## интеграл спектра через атмосферу (m<0 → вакуум) → XYZ
func _beam_xyz(m: float) -> Vector3:
	var acc := Vector3.ZERO
	for k in range(SPEC_N):
		var lam := LAM0 + float(k) * DLAM
		var s := _planck(lam)
		if m >= 0.0:
			s *= exp(-m * _tau(lam))
		acc += _cmf(lam) * s
	return acc

func _xyz_to_linear_srgb(v: Vector3) -> Color:
	var r := 3.2406 * v.x - 1.5372 * v.y - 0.4986 * v.z
	var g := -0.9689 * v.x + 1.8758 * v.y + 0.0415 * v.z
	var b := 0.0557 * v.x - 0.2040 * v.y + 1.0570 * v.z
	r = maxf(r, 0.0); g = maxf(g, 0.0); b = maxf(b, 0.0)
	var mx := maxf(r, maxf(g, b))
	if mx <= 0.0:
		return Color.WHITE
	return Color(r / mx, g / mx, b / mx)

func _mccamy_cct(v: Vector3) -> float:
	var sum := v.x + v.y + v.z
	if sum <= 0.0:
		return 0.0
	var x := v.x / sum
	var y := v.y / sum
	var n := (x - 0.3320) / (0.1858 - y)
	return 449.0 * n * n * n + 3525.0 * n * n + 6823.3 * n + 5520.33

func _ensure_lut() -> void:
	if _lut_ready:
		return
	var y_vac := _beam_xyz(-1.0).y
	var y_ref := _beam_xyz(_airmass(60.0)).y      # опорная яркость (солнце высоко)
	_lut_col.resize(91)
	_lut_energy.resize(91)
	_lut_ct.resize(91)
	_lut_klx.resize(91)
	for e in range(91):
		var xyz := _beam_xyz(_airmass(float(e)))
		_lut_col[e] = _xyz_to_linear_srgb(xyz)
		_lut_energy[e] = clampf(SUN_BASE_ENERGY * xyz.y / y_ref, 0.0, SUN_BASE_ENERGY)
		_lut_ct[e] = _mccamy_cct(xyz)
		_lut_klx[e] = EXO_ILLUM_KLX * xyz.y / y_vac
	_lut_ready = true

func _physical_sun(elev_deg: float) -> Array:
	_ensure_lut()
	var e := clampf(elev_deg, 0.0, 90.0)
	var i := int(floor(e))
	var j := mini(i + 1, 90)
	var f := e - float(i)
	var col := _lut_col[i].lerp(_lut_col[j], f)
	var energy := lerpf(_lut_energy[i], _lut_energy[j], f)
	var ct := lerpf(_lut_ct[i], _lut_ct[j], f)
	sun_direct_klx = lerpf(_lut_klx[i], _lut_klx[j], f)
	return [col, energy, ct]

## научная самопроверка спектрального конвейера — числами
func run_spectral_test() -> void:
	print("=== СПЕКТР-ТЕСТ: Планк 5778K × атмосфера → CIE XYZ → sRGB ===")
	var vac := _beam_xyz(-1.0)
	var vac_ct := _mccamy_cct(vac)
	var ok_vac := absf(vac_ct - SUN_T_K) < 120.0
	print("  вакуум (без атмосферы): ЦТ=%.0fK (обязано ≈5778K)  %s" % [
		vac_ct, "OK — конвейер верен" if ok_vac else "ПРОВАЛ"])
	_ensure_lut()
	print("  высота☉ | возд.масса | ЦТ,K | клк | sRGB")
	var prev_ct := 1e9
	var mono := true
	for e in [90, 60, 30, 20, 10, 5, 2, 1, 0]:
		var m := _airmass(float(e))
		var c := _lut_col[e]
		print("  %6d° | %6.2f | %5.0f | %5.1f | (%.2f,%.2f,%.2f)" % [
			e, m, _lut_ct[e], _lut_klx[e], c.r, c.g, c.b])
		if _lut_ct[e] > prev_ct + 1.0:
			mono = false
		prev_ct = _lut_ct[e]
	print("  ЦТ монотонно падает к горизонту: %s" % ("да" if mono else "НЕТ — ПРОВАЛ"))
	print("  ИТОГ: %s" % ("СПЕКТР ВЕРЕН" if ok_vac and mono else "ЕСТЬ ПРОВАЛЫ"))

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
