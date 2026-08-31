shader_type spatial;
// НАСТОЯЩАЯ ЛУНА — сфера с РЕАЛЬНОЙ поверхностью (карта альбедо NASA/USGS),
// в НАСТОЯЩЕЙ ориентации и фазе. Не спрайт и не «шар без лица»:
//   ПОВЕРХНОСТЬ: селенографические координаты точки считаются из мировой нормали
//     и настоящего фрейма Луны (ось по позиционному углу P, направление на Землю),
//     ЛИБРАЦИЯ (l,b) сдвигает карту — за месяц открывается ~59% поверхности.
//   ФАЗА: сфера освещается НАСТОЯЩИМ направлением на Солнце (терминатор падает на
//     верные детали) + лимбовое затемнение к краю диска.
//   ТЁМНАЯ СТОРОНА: пепельный свет Земли — виден лишь когда небо реально тёмное
//     (днём прозрачна, нет чёрной точки в светлом небе).
// Данные ориентации/размера — из world_clock (Meeus 47+53, сверено verify_moon.py).
render_mode blend_mix, cull_back, depth_draw_never, unshaded;

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap;
uniform vec3 moon_axis = vec3(0.0, 1.0, 0.0);     // север Луны, мир
uniform vec3 moon_prime = vec3(0.0, 0.0, 1.0);    // селеногр. (0,0) → к Земле, мир
uniform vec3 moon_east = vec3(1.0, 0.0, 0.0);     // селеногр. восток, мир
uniform vec2 libration = vec2(0.0, 0.0);          // l,b в градусах
uniform vec3 sun_dir = vec3(0.0, 1.0, 0.0);       // к Солнцу, мир
uniform float night = 1.0;                         // приглушение днём
uniform vec3 moon_tint = vec3(1.02, 1.0, 0.96);    // чуть тёплый лунный тон

varying vec3 v_n;
varying vec3 v_wpos;

void vertex() {
	v_n = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
	v_wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	vec3 n = normalize(v_n);
	// селенографические долгота/широта из мировой нормали и фрейма Луны
	float lat = degrees(asin(clamp(dot(n, moon_axis), -1.0, 1.0)));
	float lon = degrees(atan(dot(n, moon_east), dot(n, moon_prime)));
	// либрация сдвигает карту (месячное покачивание)
	float u = fract(0.5 + (lon - libration.x) / 360.0);
	float v = clamp(0.5 - (lat - libration.y) / 180.0, 0.0, 1.0);
	vec3 alb = texture(albedo_tex, vec2(u, v)).rgb * moon_tint;

	// фаза: освещение настоящим Солнцем, мягкий терминатор
	float lam = dot(n, normalize(sun_dir));
	float lit = smoothstep(-0.05, 0.10, lam);
	// оппозиционный подъём у полнолуния (грубо) — Луна ярчает в фазе, близкой к полной
	float opp = 1.0 + 0.25 * smoothstep(0.7, 1.0, lam);
	vec3 daySide = alb * (0.05 + 1.15 * max(lam, 0.0)) * opp;
	vec3 earthshine = alb * vec3(0.05, 0.06, 0.085);   // пепельный свет Земли
	vec3 col = mix(earthshine, daySide, lit);

	// лимбовое затемнение и мягкий край диска (сглаживание)
	vec3 view = normalize(v_wpos - CAMERA_POSITION_WORLD);
	float facing = clamp(dot(n, -view), 0.0, 1.0);
	col *= pow(facing, 0.35);
	float edge = smoothstep(0.0, 0.06, facing);        // мягкая кромка диска

	ALBEDO = col;
	// тёмная сторона видна только в тёмном небе; днём прозрачна (нет чёрной точки)
	float earth_a = smoothstep(0.3, 0.8, night);
	ALPHA = clamp(max(lit, earth_a * 0.85), 0.0, 1.0) * edge;
}
