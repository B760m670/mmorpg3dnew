shader_type spatial;
// ЛУНА — настоящая сфера, а не спрайт неба. Положение — из настоящей орбиты
// (Meeus, night_sky.gd). ФАЗА рождается сама: сфера освещается НАСТОЯЩИМ
// направлением на Солнце (sun_dir) — терминатор проходит там, где и должен,
// для текущей геометрии Солнце-Земля-Луна. Тёмная сторона — пепельный свет
// (earthshine, отражённый Землёй). Диск чуть тёплый, к краю темнеет (лимб).
// прозрачно: днём тёмная сторона Луны НЕ должна быть чёрным диском в светлом
// небе — она исчезает (alpha→0), видна лишь освещённая часть бледным диском;
// ночью проявляется весь диск с пепельным светом.
render_mode blend_mix, cull_back, depth_draw_never, unshaded;

uniform vec3 sun_dir = vec3(0.0, 1.0, 0.0);        // к Солнцу, мир
uniform float night = 1.0;                          // приглушение днём
uniform vec3 moon_tint = vec3(0.95, 0.94, 0.88);

varying vec3 v_n;
varying vec3 v_wpos;

void vertex() {
	v_n = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
	v_wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	vec3 n = normalize(v_n);
	float lam = dot(n, normalize(sun_dir));         // освещённая сторона
	float lit = smoothstep(-0.06, 0.12, lam);       // мягкий терминатор
	// лимбовое затемнение к видимому краю (нормаль ⟂ лучу зрения)
	vec3 view = normalize(v_wpos - CAMERA_POSITION_WORLD);
	float limb = pow(clamp(dot(n, -view), 0.0, 1.0), 0.35);
	vec3 daySide = moon_tint * (0.06 + 1.05 * max(lam, 0.0)) * limb;
	vec3 earthshine = vec3(0.045, 0.052, 0.075);    // пепельный свет Земли
	vec3 c = mix(earthshine, daySide, lit);
	ALBEDO = c;
	// пепельный свет (тёмная сторона) виден только когда небо реально тёмное;
	// днём тёмная сторона прозрачна → нет чёрной точки, виден лишь бледный серп/диск
	float earth_a = smoothstep(0.3, 0.8, night);
	ALPHA = clamp(max(lit, earth_a * 0.85), 0.0, 1.0);
}
