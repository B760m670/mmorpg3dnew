shader_type spatial;
// ВОДА, У КОТОРОЙ ПОВЕРХНОСТЬ МОЖЕТ ДВИГАТЬСЯ.
//
// ЧЕМ ЭТО ОТЛИЧАЕТСЯ ОТ water_real.gdshader (дальняя вода-задник). Там гладь —
// запечённые плиты по осям с одной вершиной на 33 м², и вершинный шейдер не
// делает НИЧЕГО: двигать нечего, поэтому решателю оставалось отдавать только
// наклон. Здесь меш — сетка с вершиной в КАЖДОМ узле поля, и вершина ставится
// НА ОТМЕТКУ ПОВЕРХНОСТИ, которую посчитал решатель (water_field.h).
//
// БЕРЕГ НЕ НАРИСОВАН И НЕ ЗАПЕЧЁН. Он там, где глубина падает ниже порога, то
// есть это изолиния поля: кривая, подвижная, с точностью до пикселя. Порог 2 см
// не выдуман — ИЗМЕРЕНО на проверке чаши (tests/wf_test.cpp): при пороге 1 мм
// мокрая площадь 2699 м² против 1315 м² при 2 см, то есть 1384 м² оказывается
// водой тоньше двух сантиметров, наползшей по склону. Рисовать её как гладь —
// значит вернуть ту самую «плёнку на суше»; ниже порога идёт МОКРЫЙ БЕРЕГ.
render_mode blend_mix, depth_draw_never, cull_disabled, specular_schlick_ggx;

uniform sampler2D screen_tex : hint_screen_texture, filter_linear_mipmap;
uniform sampler2D depth_tex : hint_depth_texture, filter_nearest;
// Поле: R = отметка поверхности (м), G и B = уклон, A = глубина (м).
uniform sampler2D field_tex : filter_linear, repeat_disable;
uniform vec2 field_origin = vec2(0.0);
uniform float field_size = 256.0;      // сторона окна поля, м
uniform float draw_depth = 0.02;       // ниже — не гладь, а мокрый берег
uniform float wind_ms = 3.0;
uniform float turbidity = 0.35;
uniform vec3 scatter_color = vec3(0.09, 0.16, 0.13);
uniform int ssr_steps = 16;
uniform vec3 sky_horizon = vec3(0.55, 0.60, 0.68);
uniform vec3 sky_zenith = vec3(0.35, 0.45, 0.65);
uniform float t_s = 0.0;

// измеренные коэффициенты поглощения чистой воды (Pope & Fry 1997), 1/м
const vec3 ABSORB = vec3(0.3400, 0.0638, 0.0145);
const float IOR = 1.333;

varying vec3 v_world;
varying float v_depth;
varying vec2 v_slope;

// РЯБЬ КОРОЧЕ ЯЧЕЙКИ. Поле считает волны длиннее двух метров (сетка 1 м), а
// всё, что короче, физике недоступно и добирается здесь. Длины несоизмеримы
// (отношение около 1/φ) — иначе сумма складывается в решётку и муарит вдаль.
const int NRIP = 5;
const float LAM[5] = { 1.90, 1.17, 0.72, 0.45, 0.28 };
const float DIR[5] = { 0.07, -0.83, 0.51, -0.29, 1.14 };
const float WGT[5] = { 0.24, 0.22, 0.20, 0.18, 0.16 };

void vertex() {
	// Узел стоит в начале мира, поэтому вершины несут МИРОВЫЕ x,z как есть —
	// это избавляет от обращения матрицы модели на каждую вершину.
	vec3 w = VERTEX;
	vec2 uv = (w.xz - field_origin) / field_size;
	vec4 f = textureLod(field_tex, clamp(uv, vec2(0.0), vec2(1.0)), 0.0);
	v_depth = f.a;
	v_slope = f.gb;
	w.y = f.r;                    // ВОТ РАДИ ЧЕГО ВСЁ: вершина на поверхности
	VERTEX = w;
	v_world = w;
	NORMAL = vec3(0.0, 1.0, 0.0);
}

float fresnel_exact(float cos_i) {
	float s2 = (1.0 - cos_i * cos_i) / (IOR * IOR);
	if (s2 >= 1.0) { return 1.0; }
	float cos_t = sqrt(1.0 - s2);
	float rs = (cos_i - IOR * cos_t) / (cos_i + IOR * cos_t);
	float rp = (IOR * cos_i - cos_t) / (IOR * cos_i + cos_t);
	return clamp(0.5 * (rs * rs + rp * rp), 0.0, 1.0);
}

vec3 view_from_depth(vec2 uv, float d, mat4 inv_proj) {
	vec4 p = inv_proj * vec4(uv * 2.0 - 1.0, d, 1.0);
	return p.xyz / p.w;
}

vec3 sky_probe(float col_u, float ray_up) {
	for (int i = 0; i < 3; i++) {
		vec2 uv = vec2(col_u, 0.02 + float(i) * 0.07);
		if (textureLod(depth_tex, uv, 0.0).r <= 0.0001) {
			return textureLod(screen_tex, uv, 3.0).rgb;
		}
	}
	return mix(sky_horizon, sky_zenith, sqrt(clamp(ray_up, 0.0, 1.0)));
}

vec3 trace_reflection(vec3 ro, vec3 rd, mat4 proj, mat4 inv_proj,
		vec3 fallback, float lod) {
	int STEPS = clamp(ssr_steps, 4, 32);
	float t = 0.4;
	float step_len = 0.4;
	for (int i = 0; i < STEPS; i++) {
		vec3 p = ro + rd * t;
		if (p.z > -0.05) { break; }
		vec4 c = proj * vec4(p, 1.0);
		vec2 uv = (c.xy / c.w) * 0.5 + 0.5;
		if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) { break; }
		float d = textureLod(depth_tex, uv, 0.0).r;
		if (d > 0.0001 && d < 0.9999) {
			float sz = view_from_depth(uv, d, inv_proj).z;
			float behind = sz - p.z;
			// Потолок допуска 3 м — настоящая толщина стены или дерева. Без
			// него любой далёкий силуэт, мимо края которого прошёл луч,
			// засчитывался попаданием, и в воде появлялись искривлённые здания.
			if (behind > 0.0 && behind < min(step_len, 3.0) + 0.25) {
				float lo = t - step_len;
				float hi = t;
				vec2 last_uv = uv;
				for (int k = 0; k < 4; k++) {
					float mid = 0.5 * (lo + hi);
					vec3 pm = ro + rd * mid;
					vec4 cm = proj * vec4(pm, 1.0);
					vec2 um = (cm.xy / cm.w) * 0.5 + 0.5;
					float dm = textureLod(depth_tex, um, 0.0).r;
					float szm = view_from_depth(um, dm, inv_proj).z;
					if (szm - pm.z > 0.0) { hi = mid; } else { lo = mid; }
					last_uv = um;
				}
				vec2 e = smoothstep(vec2(0.0), vec2(0.12), last_uv)
					* (1.0 - smoothstep(vec2(0.88), vec2(1.0), last_uv));
				return mix(fallback, textureLod(screen_tex, last_uv, lod).rgb, e.x * e.y);
			}
		}
		step_len *= 1.35;
		t += step_len;
	}
	// Пересечения нет — луч ушёл в небо или за край кадра. Возвращать последний
	// пиксель на кромке нельзя: он размазывается вдоль края и едет при повороте.
	return fallback;
}

void fragment() {
	// БЕРЕГ — ИЗОЛИНИЯ ПОЛЯ. Всё, что тоньше порога, гладью не рисуется.
	if (v_depth < draw_depth) { discard; }

	// --- НАКЛОН: крупный из поля, мелкий из ветра ---
	// Средний квадрат уклона по Cox & Munk (1954): измерен по бликам Солнца на
	// воде с самолёта — связывает ветер и шероховатость воды напрямую.
	float mss = 0.003 + 0.00512 * wind_ms;
	float rms_slope = sqrt(mss);

	float dist = max(-VERTEX.z, 0.5);
	// сколько метров в одном пикселе на этом расстоянии
	float px = 2.0 * dist / (PROJECTION_MATRIX[1][1] * VIEWPORT_SIZE.y);

	vec2 sl = v_slope;
	float lost = 0.0;
	for (int i = 0; i < NRIP; i++) {
		float lam = LAM[i];
		// компонента короче двух пикселей не разрешается экраном: её уклон не
		// рисуем, а отдаём в шероховатость — иначе она искрит
		float vis = clamp(lam / (2.0 * px) - 1.0, 0.0, 1.0);
		float amp_slope = rms_slope * WGT[i];
		if (vis <= 0.001) { lost += amp_slope * amp_slope; continue; }
		vec2 dir = vec2(cos(DIR[i]), sin(DIR[i]));
		float k = 6.2831853 / lam;
		// дисперсия глубокой воды: ω = sqrt(g·k)
		float ph = k * dot(dir, v_world.xz) - sqrt(9.81 * k) * t_s;
		sl += dir * amp_slope * cos(ph) * vis;
		lost += amp_slope * amp_slope * (1.0 - vis * vis);
	}
	vec3 n_world = normalize(vec3(-sl.x, 1.0, -sl.y));

	vec3 vdir = normalize(v_world - CAMERA_POSITION_WORLD);
	float cos_i = clamp(dot(-vdir, n_world), 0.0, 1.0);

	// --- ПРЕЛОМЛЕНИЕ: сдвиг того, что видно сквозь воду ---
	// Снелль: при малом наклоне поверхности луч уходит вбок примерно на
	// толща·(1 − 1/n)·уклон. Сдвиг переводим в экранные доли через проекцию.
	float d_vert = v_depth;
	vec2 off_world = -sl * d_vert * (1.0 - 1.0 / IOR);
	vec2 off_uv = off_world * PROJECTION_MATRIX[1][1] / max(dist, 0.5) * 0.5;
	vec2 ruv = clamp(SCREEN_UV + off_uv, vec2(0.001), vec2(0.999));

	// длина пути луча в воде до дна: толща, делённая на косинус наклона взгляда
	float d_ray = d_vert / max(abs(vdir.y), 0.15);

	// МУТНОСТЬ РАЗМЫВАЕТ ДНО: взвесь рассеивает свет, и дно теряет резкость тем
	// сильнее, чем толще слой. Это рассеяние, а не «блюр для красоты».
	float lod = clamp(d_vert * turbidity * 0.7, 0.0, 4.0);
	vec3 seen = textureLod(screen_tex, ruv, lod).rgb;

	// --- ПОГЛОЩЕНИЕ (Бугер-Ламберт-Бер) ---
	vec3 trans = exp(-ABSORB * (d_vert + d_ray));
	float murk = 1.0 - exp(-turbidity * (d_vert + d_ray) * 0.45);

	float F = fresnel_exact(cos_i);

	// ОТРАЖЁННЫЙ ЛУЧ поднимаем до горизонта: при скользящем взгляде рябь
	// наклоняет нормаль сильнее самого угла зрения, и часть лучей уходит В ВОДУ.
	// Трассир ловил там дно и берег — на кадре это были крапины по всей глади.
	vec3 rw = reflect(vdir, n_world);
	if (rw.y < 0.03) { rw = normalize(vec3(rw.x, 0.03, rw.z)); }
	vec3 sky_est = sky_probe(SCREEN_UV.x, rw.y);

	// Шероховатость — ровно тот уклон ряби, который экран уже не разрешает.
	ROUGHNESS = clamp(sqrt(lost) + 0.02, 0.02, 0.4);
	float refl_lod = clamp(ROUGHNESS * 12.0, 0.0, 4.0);
	vec3 rdir = normalize((VIEW_MATRIX * vec4(rw, 0.0)).xyz);
	vec3 refl = trace_reflection(VERTEX, rdir, PROJECTION_MATRIX,
		INV_PROJECTION_MATRIX, sky_est, refl_lod);

	// --- СБОРКА ---
	// Обе доли — УЖЕ ОСВЕЩЁННЫЕ пиксели кадра, в ALBEDO их класть нельзя: свет
	// применился бы дважды. Идут в EMISSION как готовая яркость.
	vec3 under = seen * trans * (1.0 - murk) + scatter_color * murk * sky_est;
	EMISSION = under * (1.0 - F) + refl * F;
	ALBEDO = vec3(0.0);
	NORMAL = normalize((VIEW_MATRIX * vec4(n_world, 0.0)).xyz);
	METALLIC = 0.0;
	// f0 = 0.16·SPECULAR² (формула Godot) → 0.354 даёт ровно 0.02, измеренное
	// отражение воды по нормали. От движка нужен один вклад — прямой блик
	// Солнца: он единственный, что доходит до прозрачных поверхностей.
	SPECULAR = 0.354;
	// У САМОГО БЕРЕГА гладь становится прозрачной за несколько сантиметров:
	// иначе на изолинии виден рез, а у настоящей воды там мокрый песок.
	ALPHA = smoothstep(draw_depth, draw_depth + 0.06, v_depth);
}
