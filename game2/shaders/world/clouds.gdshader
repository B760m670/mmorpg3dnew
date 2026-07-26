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

// дизер шага марша (иначе на облаках видны кольца-ступени от конечного STEPS)
float hash12(vec2 p) {
	p = fract(p * vec2(0.1031, 0.1030));
	p += dot(p, p.yx + 33.33);
	return fract((p.x + p.y) * p.x);
}

// плотность облака в мировой точке p
float cloud_density(vec3 p) {
	// крупные КЛУБЫ (низкая частота — не мелкая «крупа»), сносятся ветром
	vec3 uv = p * 0.00016 + vec3(time_s * wind_x, 0.0, time_s * wind_z);
	float shape = textureLod(shape_tex, uv, 0.0).r;           // 0..1 fBm
	// высотный профиль: плотнее в середине слоя, тает у краёв
	float hh = clamp((p.y - cloud_h0) / (cloud_h1 - cloud_h0), 0.0, 1.0);
	float grad = pow(hh, 0.6) * pow(1.0 - hh, 0.9) * 3.2;
	float base = clamp((shape - (1.0 - coverage)) / 0.30, 0.0, 1.0) * grad;
	if (base <= 0.001) return 0.0;
	float det = textureLod(detail_tex, uv * 2.3, 0.0).r;      // Ворли-эрозия краёв
	return clamp(base - det * 0.30, 0.0, 1.0);
}

void fragment() {
	vec3 cam = CAMERA_POSITION_WORLD;
	vec3 rd = normalize(v_world - cam);

	// пересечение луча со слоем облаков [H0..H1] — РАБОТАЕТ на любой высоте:
	// снизу (смотрим вверх), внутри слоя, и СВЕРХУ (смотрим вниз на «палубу»
	// облаков — вид с высоты полёта). Без этого высокая камера видела пустое небо.
	// ВАЖНО: в Godot нельзя 'return' в fragment() — ранее это роняло компиляцию
	// шейдера, и облака НЕ рисовались вообще. Поэтому весь расчёт под флагом.
	float t0 = 0.0;
	float t1 = 0.0;
	bool valid = true;
	if (abs(rd.y) < 1e-4) {                       // почти горизонтально
		if (cam.y < cloud_h0 || cam.y > cloud_h1) { valid = false; }
		else { t0 = 0.0; t1 = 8000.0; }
	} else {
		float ta = (cloud_h0 - cam.y) / rd.y;
		float tb = (cloud_h1 - cam.y) / rd.y;
		t0 = max(min(ta, tb), 0.0);
		t1 = max(ta, tb);
	}
	float march_len = clamp(t1 - t0, 0.0, 6000.0);

	vec3 col = vec3(0.0);
	float trans = 1.0;
	if (valid && march_len > 1.0) {
		// ПОСТОЯННЫЙ шаг (не march_len/STEPS): у горизонта путь огромен, а при
		// фикс. числе шагов dt рос → «веер» ступеней. Constant dt = ровно, без вееров.
		const float DT = 160.0;           // м на шаг
		const int MAXSTEPS = 48;          // потолок (грациозные лучи), FPS-безопасно
		float ct = dot(rd, sun_dir);
		float phase = 0.65 * hg(ct, 0.6) + 0.35 * hg(ct, -0.15);
		// АНИМИРОВАННЫЙ джиттер: смещение шума во времени → MetalFX temporal
		// усредняет его в гладкое (статичный джиттер давал зернистость).
		float jitter = hash12(FRAGCOORD.xy + vec2(TIME * 41.0, TIME * 27.0));
		float traveled = jitter * DT;
		vec3 p = cam + rd * (t0 + traveled);
		vec3 dp = rd * DT;
		for (int i = 0; i < MAXSTEPS; i++) {
			if (traveled > march_len) { break; }
			float d = cloud_density(p);
			if (d > 0.001) {
				// свет к солнцу: короткий марш → самозатенение (Бир-Ламберт)
				float lt = 1.0;
				vec3 lp = p;
				for (int l = 0; l < 4; l++) {
					lp += sun_dir * 180.0;
					lt *= exp(-cloud_density(lp) * 180.0 * 0.02);
				}
				// облако ЯРКОЕ (пасмурно = облака светлее серого неба): прямой к
				// Солнцу (кромка) + купол-неба как основной, глубина затеняет мягко.
				float ltf = 0.4 + 0.6 * lt;
				vec3 lit = sun_color * (lt * phase * 2.5 + 0.2) + sky_ambient * 0.85 * ltf;
				float a = 1.0 - exp(-d * DT * 0.008);
				col += trans * a * lit;
				trans *= 1.0 - a;
				if (trans < 0.02) { break; }
			}
			p += dp;
			traveled += DT;
		}
	}
	// у горизонта (путь огромен, ступени грубее) — шире растворяем в дымку
	float horizon = smoothstep(0.0, 0.14, abs(rd.y));
	float alpha = (1.0 - trans) * horizon;
	ALBEDO = col;
	ALPHA = clamp(alpha, 0.0, 1.0);
}
