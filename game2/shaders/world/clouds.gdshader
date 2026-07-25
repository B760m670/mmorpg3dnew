shader_type spatial;
// ОБЪЁМНЫЕ ОБЛАКА — не спрайт и не текстура, а RAYMARCH сквозь слой облаков (как
// в Horizon/RDR2). Рисуется на большом куполе-сфере вокруг камеры (аддитивно, не
// трогает базовое небо). Для каждого направления взгляда луч проходит слой
// облаков на высоте [H0..H1] и по шагам накапливает плотность и свет:
//   ПЛОТНОСТЬ: Перлин-Ворли (базовая форма fBm-Перлина, эрозия краёв Ворли) —
//     настоящая клубистая структура кучевых; покрытие = погода.
//   СВЕТ: короткий марш К СОЛНЦУ → пропускание по Бир-Ламберту (самозатенение);
//     фаза Хеньи-Гринштейна (вперёд-рассеяние = серебряная кромка у солнца).
//   ДВИЖЕНИЕ: шум сносится ветром по времени (на 5-мин сутках — ускоренно).
// cull_front — рисуем ИЗНУТРИ купола; тест глубины включён (рельеф/здания ближе
// купола перекрывают облака), но глубину не пишем (прозрачно поверх неба).
render_mode blend_mix, cull_front, unshaded;

uniform sampler3D shape_tex : filter_linear, repeat_enable;   // fBm Перлин (форма)
uniform sampler3D detail_tex : filter_linear, repeat_enable;  // Ворли (эрозия)
uniform vec3 sun_dir = vec3(0.4, 0.6, -0.3);       // НА солнце (нормирован)
uniform vec3 sun_color = vec3(1.0, 0.97, 0.9);
uniform vec3 sky_ambient = vec3(0.72, 0.78, 0.88);  // ЯРКИЙ пасмурный купол (не тёмный)
uniform float coverage = 0.5;                       // 0 ясно .. 1 сплошь (погода)
uniform float wind_x = 0.006;
uniform float wind_z = 0.003;
uniform float cloud_h0 = 1200.0;
uniform float cloud_h1 = 3200.0;
uniform float time_s = 0.0;

varying vec3 v_world;

void vertex() {
	v_world = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

float hg(float ct, float g) {
	float g2 = g * g;
	return (1.0 - g2) / (12.566 * pow(1.0 + g2 - 2.0 * g * ct, 1.5));
}

// плотность облака в мировой точке p
float cloud_density(vec3 p) {
	vec3 uv = p * 0.00035 + vec3(time_s * wind_x, 0.0, time_s * wind_z);
	float shape = textureLod(shape_tex, uv, 0.0).r;           // 0..1 fBm
	// высотный профиль: плотнее в середине слоя, тает у краёв
	float hh = clamp((p.y - cloud_h0) / (cloud_h1 - cloud_h0), 0.0, 1.0);
	float grad = pow(hh, 0.6) * pow(1.0 - hh, 0.9) * 3.2;
	float base = clamp((shape - (1.0 - coverage)) / 0.28, 0.0, 1.0) * grad;
	if (base <= 0.001) return 0.0;
	float det = textureLod(detail_tex, uv * 3.1, 0.0).r;      // Ворли-эрозия
	return clamp(base - det * 0.55, 0.0, 1.0);
}

void fragment() {
	vec3 cam = CAMERA_POSITION_WORLD;
	vec3 rd = normalize(v_world - cam);
	// смотрим только вверх (нижняя половина купола — прозрачна)
	if (rd.y < 0.02) { ALBEDO = vec3(0.0); ALPHA = 0.0; return; }

	// пересечение луча со слоем облаков [H0..H1]
	float t0 = (cloud_h0 - cam.y) / rd.y;
	float t1 = (cloud_h1 - cam.y) / rd.y;
	t0 = max(t0, 0.0);
	float march_len = clamp(t1 - t0, 0.0, 9000.0);
	if (march_len <= 1.0) { ALBEDO = vec3(0.0); ALPHA = 0.0; return; }

	const int STEPS = 24;                 // FPS-безопаснее (raymarch дорогой); поднимем, если тянет
	float dt = march_len / float(STEPS);
	float ct = dot(rd, sun_dir);
	float phase = 0.65 * hg(ct, 0.6) + 0.35 * hg(ct, -0.15);

	vec3 col = vec3(0.0);
	float trans = 1.0;
	vec3 p = cam + rd * t0;
	vec3 dp = rd * dt;
	for (int i = 0; i < STEPS; i++) {
		p += dp;
		float d = cloud_density(p);
		if (d > 0.001) {
			// свет к солнцу: короткий марш → самозатенение (Бир-Ламберт)
			float lt = 1.0;
			vec3 lp = p;
			for (int l = 0; l < 4; l++) {
				lp += sun_dir * 180.0;
				lt *= exp(-cloud_density(lp) * 180.0 * 0.02);  // мягкое самозатенение
			}
			// ОСВЕЩЕНИЕ облака ЯРКОЕ (пасмурно = облака светлее серого неба, не темнее):
			// прямой к солнцу (кромка) + купол-неба как основной, глубина затеняет мягко.
			float ltf = 0.4 + 0.6 * lt;
			vec3 lit = sun_color * (lt * phase * 4.0 + 0.5) + sky_ambient * 1.6 * ltf;
			float a = 1.0 - exp(-d * dt * 0.008);
			col += trans * a * lit;
			trans *= 1.0 - a;
			if (trans < 0.02) break;
		}
	}
	// у горизонта облака тают в дымку
	float horizon = smoothstep(0.02, 0.18, rd.y);
	float alpha = (1.0 - trans) * horizon;
	ALBEDO = col;
	ALPHA = clamp(alpha, 0.0, 1.0);
}
