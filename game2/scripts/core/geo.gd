class_name Geo
extends RefCounted
## Ф-Земля, этап E1 — ГЕОДЕЗИЧЕСКИЙ ФУНДАМЕНТ настоящей Земли.
## Форма Земли — эллипсоид WGS84 (тот же, что у GPS). Здесь: точные константы,
## переход геодезические↔ECEF (Earth-Centered Earth-Fixed) и настоящее
## геодезическое расстояние (Vincenty) — всё в ДВОЙНОЙ точности.
## Всё, что появится на Земле (Гатчина на 59.5648°N, 30.1282°E), сядет на этот
## каркас в реальных координатах. Проверяется научно (см. run_self_test).

# --- WGS84 (референсный эллипсоид Земли) ---
const A := 6378137.0                       # большая полуось (экватор), м
const F := 1.0 / 298.257223563             # сжатие
const B := A * (1.0 - F)                    # малая полуось (полюс) = 6356752.314245 м
const E2 := F * (2.0 - F)                   # квадрат эксцентриситета
const EP2 := E2 / (1.0 - E2)               # второй эксцентриситет²
const MEAN_R := 6371008.7714                # средний радиус, м
const RAD := PI / 180.0
const DEG := 180.0 / PI

# опорная точка контента (позже) — Гатчина, Дворец
const GATCHINA_LAT := 59.5648
const GATCHINA_LON := 30.1282

## геодезические (широта,долгота в °, высота в м) → ECEF (X,Y,Z, м)
func geodetic_to_ecef(lat_deg: float, lon_deg: float, h: float) -> Array:
	var lat := lat_deg * RAD
	var lon := lon_deg * RAD
	var sinlat := sin(lat)
	var coslat := cos(lat)
	var n := A / sqrt(1.0 - E2 * sinlat * sinlat)
	var x := (n + h) * coslat * cos(lon)
	var y := (n + h) * coslat * sin(lon)
	var z := (n * (1.0 - E2) + h) * sinlat
	return [x, y, z]

## ECEF (X,Y,Z, м) → геодезические (широта°, долгота°, высота м). Bowring.
func ecef_to_geodetic(x: float, y: float, z: float) -> Array:
	var lon := atan2(y, x)
	var p := sqrt(x * x + y * y)
	var theta := atan2(z * A, p * B)
	var st := sin(theta)
	var ct := cos(theta)
	var lat := atan2(z + EP2 * B * st * st * st, p - E2 * A * ct * ct * ct)
	var sinlat := sin(lat)
	var n := A / sqrt(1.0 - E2 * sinlat * sinlat)
	var h := p / cos(lat) - n
	return [lat * DEG, lon * DEG, h]

## настоящее геодезическое расстояние по эллипсоиду (Vincenty inverse), м
func vincenty_distance(lat1_deg: float, lon1_deg: float, lat2_deg: float, lon2_deg: float) -> float:
	var l := (lon2_deg - lon1_deg) * RAD
	var u1 := atan((1.0 - F) * tan(lat1_deg * RAD))
	var u2 := atan((1.0 - F) * tan(lat2_deg * RAD))
	var sinu1 := sin(u1); var cosu1 := cos(u1)
	var sinu2 := sin(u2); var cosu2 := cos(u2)
	var lam := l
	var sin_sigma := 0.0
	var cos_sigma := 0.0
	var sigma := 0.0
	var cos2_alpha := 0.0
	var cos2_sigma_m := 0.0
	for _i in range(200):
		var sin_lam := sin(lam)
		var cos_lam := cos(lam)
		sin_sigma = sqrt(pow(cosu2 * sin_lam, 2.0) \
			+ pow(cosu1 * sinu2 - sinu1 * cosu2 * cos_lam, 2.0))
		if sin_sigma == 0.0:
			return 0.0
		cos_sigma = sinu1 * sinu2 + cosu1 * cosu2 * cos_lam
		sigma = atan2(sin_sigma, cos_sigma)
		var sin_alpha := cosu1 * cosu2 * sin_lam / sin_sigma
		cos2_alpha = 1.0 - sin_alpha * sin_alpha
		cos2_sigma_m = 0.0 if cos2_alpha == 0.0 else cos_sigma - 2.0 * sinu1 * sinu2 / cos2_alpha
		var c := F / 16.0 * cos2_alpha * (4.0 + F * (4.0 - 3.0 * cos2_alpha))
		var lam_prev := lam
		lam = l + (1.0 - c) * F * sin_alpha * (sigma + c * sin_sigma \
			* (cos2_sigma_m + c * cos_sigma * (-1.0 + 2.0 * cos2_sigma_m * cos2_sigma_m)))
		if absf(lam - lam_prev) < 1e-12:
			break
	var u_sq := cos2_alpha * (A * A - B * B) / (B * B)
	var a_big := 1.0 + u_sq / 16384.0 * (4096.0 + u_sq * (-768.0 + u_sq * (320.0 - 175.0 * u_sq)))
	var b_big := u_sq / 1024.0 * (256.0 + u_sq * (-128.0 + u_sq * (74.0 - 47.0 * u_sq)))
	var d_sigma := b_big * sin_sigma * (cos2_sigma_m + b_big / 4.0 \
		* (cos_sigma * (-1.0 + 2.0 * cos2_sigma_m * cos2_sigma_m) \
		- b_big / 6.0 * cos2_sigma_m * (-3.0 + 4.0 * sin_sigma * sin_sigma) \
		* (-3.0 + 4.0 * cos2_sigma_m * cos2_sigma_m)))
	return B * a_big * (sigma - d_sigma)

## расстояние до видимого горизонта с высоты h над сферой (геометрия), м
func horizon_distance(h: float) -> float:
	return sqrt(h * (2.0 * MEAN_R + h))

# --- НАУЧНАЯ САМОПРОВЕРКА (сверка с реальностью числами) ---
func run_self_test() -> void:
	print("=== E1 ГЕОДЕЗИЯ WGS84 — научная проверка ===")
	print("  a=%.3f м  b=%.6f м  f=1/%.9f" % [A, B, 1.0 / F])
	var ok := true

	# 1) точные аналитические точки эллипсоида
	var eq := geodetic_to_ecef(0.0, 0.0, 0.0)
	var po := geodetic_to_ecef(90.0, 0.0, 0.0)
	print("  экватор(0,0,0) ECEF X=%.3f (ожид %.1f)  " % [eq[0], A],
		"OK" if absf(eq[0] - A) < 1e-3 else "ПРОВАЛ")
	print("  полюс(90,0,0)  ECEF Z=%.3f (ожид b=%.3f)  " % [po[2], B],
		"OK" if absf(po[2] - B) < 1e-3 else "ПРОВАЛ")
	ok = ok and absf(eq[0] - A) < 1e-3 and absf(po[2] - B) < 1e-3

	# 2) круговой обход геодезические→ECEF→геодезические (Гатчина)
	var e := geodetic_to_ecef(GATCHINA_LAT, GATCHINA_LON, 137.0)
	var g := ecef_to_geodetic(e[0], e[1], e[2])
	var derr := maxf(absf(g[0] - GATCHINA_LAT), absf(g[1] - GATCHINA_LON))
	print("  Гатчина ECEF = (%.1f, %.1f, %.1f) м" % [e[0], e[1], e[2]])
	print("  обратно = (%.7f°, %.7f°, %.2f м)  ошибка=%.4f н°  %s" % [
		g[0], g[1], g[2], derr * 1e9, "OK" if derr < 1e-7 else "ПРОВАЛ"])
	ok = ok and derr < 1e-7

	# 3) Vincenty против published-эталона (Vincenty 1975: Flinders Peak→Buninyong)
	var vd := vincenty_distance(-37.95103342, 144.42486789, -37.65282114, 143.92649553)
	print("  Vincenty эталон = %.3f м (published 54972.271 м)  ошибка=%.2f мм  %s" % [
		vd, absf(vd - 54972.271) * 1000.0, "OK" if absf(vd - 54972.271) < 0.005 else "ПРОВАЛ"])
	ok = ok and absf(vd - 54972.271) < 0.005

	# 4) реальное расстояние Гатчина→Санкт-Петербург (Дворцовая пл. 59.9386,30.3159)
	var sp := vincenty_distance(GATCHINA_LAT, GATCHINA_LON, 59.9386, 30.3159)
	print("  Гатчина→Петербург = %.0f м (~42–45 км по факту)" % sp)

	# 5) длина экватора и горизонт
	print("  длина экватора 2πa = %.0f м (реальность 40075017 м)" % (TAU * A))
	print("  горизонт с 2 м = %.0f м, с 100 м = %.0f м, с 400 км(орбита) = %.0f км" % [
		horizon_distance(2.0), horizon_distance(100.0), horizon_distance(400000.0) / 1000.0])

	print("  ИТОГ: %s" % ("ФУНДАМЕНТ ВЕРЕН" if ok else "ЕСТЬ ПРОВАЛЫ"))
