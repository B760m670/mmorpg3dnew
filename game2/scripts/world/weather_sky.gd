class_name WeatherSky
extends RefCounted
## КОГЕРЕНТНАЯ ПОГОДА: одно число — покрытие облаков — управляет ВСЕМ небом.
## Не «крашеная серая крыша»: ясное физ-небо синее, а пасмурность рождается
## из ПЛОТНЫХ ОБЛАКОВ (coverage→высокое) и этим же гасится/сереет свет.
## Один источник правды для игры (light_stage) и стенда (sky_probe).

## пасмурность 0..1 из покрытия: ясно/переменка → 0 (солнечно),
## плотная облачность → 1 (ровный серый свет). Порог — реальный: свет сереет
## только когда небо реально затянуто, а не при редких кучевых.
static func overcast_from_coverage(cov: float) -> float:
	return smoothstep(0.45, 0.82, cov)

## небо: интерполяция ЯСНОЕ(синее) ↔ ПАСМУРНОЕ(ровный серый) по пасмурности oc
static func apply_sky(sm: PhysicalSkyMaterial, oc: float) -> void:
	sm.rayleigh_coefficient = lerpf(2.0, 0.9, oc)
	sm.rayleigh_color = Color(0.26, 0.41, 0.58).lerp(Color(0.55, 0.58, 0.62), oc)
	sm.mie_coefficient = lerpf(0.005, 0.09, oc)
	sm.mie_eccentricity = lerpf(0.80, 0.55, oc)
	sm.mie_color = Color(0.69, 0.80, 0.92).lerp(Color(0.86, 0.88, 0.90), oc)
	sm.turbidity = lerpf(2.5, 10.0, oc)
	sm.sun_disk_scale = lerpf(1.0, 0.0, oc)          # диск гаснет за облачностью
	sm.energy_multiplier = lerpf(1.0, 1.5, oc)
	sm.ground_color = Color(0.30, 0.30, 0.31)

## экспозиция и сила рассеянного света неба по пасмурности (для Environment)
static func exposure(oc: float) -> float:
	return lerpf(0.95, 0.82, oc)

static func ambient_energy(oc: float) -> float:
	return lerpf(1.25, 2.1, oc)
