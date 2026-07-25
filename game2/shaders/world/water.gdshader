shader_type spatial;
// ВОДА — не плоская плита, а ЖИДКОСТЬ с чертами воды. Считается на GPU каждый
// кадр (так делают настоящую real-time воду — не запечённый ассет):
//   · ГЛУБИНА: дно берётся из ТОЙ ЖЕ текстуры высот, что у террейна (мы вырезали
//     реальные котловины) → цвет и прозрачность зависят от глубины: у берега
//     прозрачно (видно дно сквозь толщу), в глубине — плотная тёмная синь.
//   · ОТРАЖЕНИЕ НЕБА: низкая шероховатость → PBR-движок отражает небо (френель
//     из BRDF сам даёт «к горизонту зеркало, вниз — прозрачно»).
//   · ВОЛНЫ: анимированная нормаль из бегущего шума, амплитуда растёт с дождём.
//   · ПЕНА у берега на малой глубине.
// depth_draw_always: вода ПИШЕТ глубину → ближняя гладь перекрывает дальнюю,
// нет двойного смешения там, где река входит в озеро (были «слои поверх друг друга»).
render_mode blend_mix, cull_disabled, depth_draw_always, diffuse_burley;

uniform sampler2D height_tex : filter_linear_mipmap, repeat_disable;
uniform float dem_half = 8192.0;
uniform vec3 shallow_color : source_color = vec3(0.20, 0.42, 0.42);
uniform vec3 deep_color : source_color = vec3(0.02, 0.09, 0.14);
uniform float depth_full = 4.0;      // м: где цвет/плотность выходят на «глубоко»
uniform float rain_rate = 0.0;       // из weather → сила ряби от капель
uniform vec2 wind = vec2(1.0, 0.6);
uniform float flow_speed = 1.4;      // скорость сноса волн по течению рек

varying vec3 v_world;

void vertex() {
	v_world = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

float hash(vec2 p) {
	p = fract(p * vec2(0.1031, 0.1030));
	p += dot(p, p.yx + 33.33);
	return fract((p.x + p.y) * p.x);
}

float vnoise(vec2 p) {
	vec2 i = floor(p); vec2 f = fract(p); f = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash(i), hash(i + vec2(1, 0)), f.x),
		mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), f.x), f.y);
}

// сумма бегущих волн: две крупные (ветер) + мелкая рябь (усиливается дождём)
float wsum(vec2 p, float t) {
	vec2 d = wind * 0.5 * t;
	return vnoise((p + d) * 0.20) + 0.5 * vnoise((p - d * 1.3) * 0.45)
		+ (0.3 + 0.9 * rain_rate) * vnoise(p * 2.5 - vec2(t * 2.0));
}

void fragment() {
	// дно из текстуры высот (с вырезанными котловинами) → глубина воды
	vec2 huv = (v_world.xz + vec2(dem_half)) / (2.0 * dem_half);
	float bed = texture(height_tex, huv).r;
	float depth = max(v_world.y - bed, 0.0);
	float dn = clamp(depth / depth_full, 0.0, 1.0);

	// ТЕЧЕНИЕ: реки несут вершинный цвет (RG=направление, B=есть течение); озёра
	// стоят (COLOR=серый, B=0). Волны сносятся по течению вниз.
	vec2 fdir = COLOR.rg * 2.0 - 1.0;
	vec2 flow = fdir * COLOR.b * flow_speed;
	vec2 p = v_world.xz - flow * TIME;

	// нормаль волн из градиента шума
	float e = 0.5;
	float h0 = wsum(p, TIME);
	float hx = wsum(p + vec2(e, 0.0), TIME);
	float hy = wsum(p + vec2(0.0, e), TIME);
	// волна слабеет с далью — на грани у горизонта не даёт полосатых артефактов
	float amp = (0.22 + 0.9 * rain_rate) * (1.0 - smoothstep(60.0, 700.0, length(VERTEX)));
	vec3 wn = normalize(vec3((h0 - hx) * amp, 1.0, (h0 - hy) * amp));
	NORMAL = normalize((VIEW_MATRIX * vec4(wn, 0.0)).xyz);

	// пена у берега (малая глубина) с бегущей рябью
	float foam = smoothstep(0.7, 0.0, depth) * (0.4 + 0.6 * vnoise(v_world.xz * 0.9 - vec2(TIME * 0.5)));

	vec3 col = mix(shallow_color, deep_color, dn);
	ALBEDO = mix(col, vec3(0.90, 0.93, 0.95), clamp(foam, 0.0, 1.0) * 0.8);
	ROUGHNESS = mix(0.03, 0.10, dn);     // низкая → отражение неба (PBR/френель)
	METALLIC = 0.0;
	SPECULAR = 0.6;
	// плотнее, чем раньше: мелкая вода — вода, а не «песок сквозь плёнку».
	// Мелко чуть прозрачнее (виден урез дна), глубоко — плотная.
	ALPHA = clamp(0.62 + 0.35 * dn + foam, 0.0, 1.0);
}
