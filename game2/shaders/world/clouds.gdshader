shader_type spatial;
// ОБЪЁМНЫЕ ОБЛАКА — не спрайт и не текстура, а RAYMARCH сквозь слой облаков.
// Рисуется на большом куполе-сфере вокруг камеры. Для каждого направления взгляда
// луч проходит слой и по шагам накапливает плотность и свет:
//   ПЛОТНОСТЬ: Перлин-Ворли (форма fBm-Перлина, эрозия краёв Ворли).
//   СВЕТ: короткий марш К СОЛНЦУ → пропускание по Бир-Ламберту (самозатенение);
//     фаза Хеньи-Гринштейна (вперёд-рассеяние = серебряная кромка у солнца).
//
// ============================================================================
// ЧТО БЫЛО СЛОМАНО И ПОЧЕМУ
// ============================================================================
// 1. НОЧЬЮ ОБЛАКА СВЕТИЛИСЬ БЕЛЫМ. Не «немного ярче» — ИЗМЕРЕНО, кадр в 22:00
//    выжигался в белое целиком. Свет облаков задавался КОНСТАНТАМИ
//    (sky_ambient 0.72, night_glow), а гасился отдельным множителем «дневности»
//    по высоте Солнца. Стоило экспозиции честно вырасти к ночи (×18), как эти
//    константы всплыли наружу. Это ровно та же болезнь, что была у земли:
//    свет, не связанный с люксами, живёт своей жизнью.
//    Теперь ОБА источника приходят из физики сцены: sun_energy — энергия луча
//    (у часов она из спектра и воздушной массы), sky_energy — рассеянный свет
//    неба (из таблицы освещённости). Ночью они падают сами, гасить нечем.
//
// 2. ВСЕ ОБЛАКА БЫЛИ ОДИНАКОВЫЕ. Один слой 1200..3200 м, один высотный профиль
//    на всё небо, одна частота шума. Отсюда «как будто копировали»: структура
//    везде та же, меняется только пятно. Теперь есть КАРТА ПОГОДЫ — медленное
//    2D-поле с периодом порядка 20 км, где у каждого места своё покрытие, своя
//    высота основания и СВОЙ ТИП: слоистые (плоская пелена) или кучевые (узкое
//    основание, раздутый рваный верх). Профиль высоты и сила эрозии берутся из
//    типа, поэтому в одном кадре бывают и пелена, и клубы.
//
// 3. ОБЛАКА БЫЛИ ТОЛЬКО НА ОДНОЙ ВЫСОТЕ. Основание теперь гуляет 700..2600 м
//    (нижний ярус), а выше добавлены ПЕРИСТЫЕ на 9 км. Перистые не маршируются:
//    ледяной слой в сотню метров для луча — плёнка, и считать его объёмом
//    значило бы платить за то, чего не видно. Одно пересечение с плоскостью.
render_mode blend_mix, cull_front, unshaded;

uniform sampler3D shape_tex : filter_linear, repeat_enable;   // fBm Перлин (форма)
uniform sampler3D detail_tex : filter_linear, repeat_enable;  // Ворли (эрозия)
uniform vec3 sun_dir = vec3(0.4, 0.6, -0.3);       // НА солнце (нормирован)
uniform vec3 sun_color = vec3(1.0, 0.97, 0.9);
uniform float sun_energy = 1.0;      // доля от полуденной (часы, спектр+воздушная масса)
uniform vec3 sky_tint = vec3(0.72, 0.78, 0.88);
uniform float sky_energy = 1.0;      // доля от полуденного рассеянного света неба
uniform float coverage = 0.5;        // 0 ясно .. 1 сплошь (погода, сдвигает карту)
uniform vec3 moon_dir = vec3(0.0, 1.0, 0.0);        // НА Луну (мир)
uniform vec3 moon_light = vec3(0.0);                // свет Луны (цвет×фаза×видимость)
uniform float wind_x = 0.006;
uniform float wind_z = 0.003;
uniform float cirrus = 0.55;         // сколько перистых наверху
uniform float time_s = 0.0;

// Нижний ярус: основание гуляет в этих пределах, толщина зависит от типа.
const float BASE_LO = 700.0;
const float BASE_HI = 2600.0;
const float THICK_STRAT = 500.0;     // пелена тонкая
const float THICK_CUM = 1200.0;      // кучевое разрастается вверх
const float SLAB_TOP = 3800.0;       // BASE_HI + THICK_CUM, потолок марша
const float CIRRUS_H = 9000.0;

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

// КАРТА ПОГОДЫ. Медленное 2D-поле (период около 20 км): x — местное покрытие,
// y — высота основания 0..1, z — тип 0 слоистые .. 1 кучевые. Берётся срезами
// того же 3D-шума на разных глубинах: отдельная текстура тут ничего не добавит,
// а память и время на генерацию возьмёт.
vec3 weather_at(vec2 p) {
	vec2 w = p * 0.00013 + vec2(time_s * wind_x, time_s * wind_z) * 0.35;
	float c = textureLod(shape_tex, vec3(w, 0.31), 0.0).r;
	float b = textureLod(shape_tex, vec3(w * 0.61 + 7.3, 0.77), 0.0).r;
	float t = textureLod(shape_tex, vec3(w * 0.43 + 3.1, 0.13), 0.0).r;
	return vec3(clamp(c * 1.4 - 0.28 + (coverage - 0.5) * 1.3, 0.0, 1.0), b, t);
}

// ВЫСОТНЫЙ ПРОФИЛЬ ПО ТИПУ — это и есть разница между «пеленой» и «клубами».
// Слоистые: плотность почти ровная по толщине, верх и низ плоские.
// Кучевые: узкое основание, раздутая середина, рваная вершина.
float height_profile(float hh, float ty) {
	float strat = smoothstep(0.0, 0.09, hh) * (1.0 - smoothstep(0.58, 1.0, hh));
	float cum = smoothstep(0.0, 0.24, hh) * (1.0 - smoothstep(0.60, 1.0, hh))
		* (0.42 + 0.58 * smoothstep(0.10, 0.48, hh));
	return mix(strat, cum, ty);
}

// плотность облака в мировой точке p
float cloud_density(vec3 p) {
	vec3 wm = weather_at(p.xz);
	if (wm.x <= 0.001) { return 0.0; }
	float base = mix(BASE_LO, BASE_HI, wm.y);
	float thick = mix(THICK_STRAT, THICK_CUM, wm.z);
	float hh = (p.y - base) / thick;
	if (hh < 0.0 || hh > 1.0) { return 0.0; }
	// МАСШТАБ КЛУБА — 800 м, а не 3 км. Прежние 0.00016 давали период шума
	// 6.2 км: в поле зрения (при взгляде вверх под 35° сектор неба это 0.6..2.7 км
	// по земле) помещалось ОДНО облако на весь кадр, и небо выходило пеленой.
	// Настоящее кучевое — 0.5..2 км поперёк.
	vec3 uv = p * 0.00055 + vec3(time_s * wind_x, 0.0, time_s * wind_z);
	float shape = textureLod(shape_tex, uv, 0.0).r;
	float d = clamp((shape - (1.0 - wm.x)) / 0.30, 0.0, 1.0)
		* height_profile(hh, wm.z) * 3.2;
	if (d <= 0.001) { return 0.0; }
	// ЭРОЗИЯ СИЛЬНЕЕ НАВЕРХУ и сильнее у кучевых: у настоящего кучевого низ
	// ровный (уровень конденсации — плоскость), а верх рваный.
	float det = textureLod(detail_tex, uv * 3.7, 0.0).r;
	d -= det * mix(0.10, 0.44, hh) * mix(0.45, 1.0, wm.z);
	return clamp(d, 0.0, 1.0);
}

// ПЕРИСТЫЕ на 9 км: лёд, тонкая плёнка, вытянутая ветром в полосы. Не объём —
// одно пересечение луча с плоскостью. Полосы делаются сжатием шума ПОПЕРЁК
// ветра, а не отдельной текстурой.
float cirrus_at(vec3 cam, vec3 rd) {
	if (rd.y <= 0.02 || cam.y > CIRRUS_H) { return 0.0; }
	float t = (CIRRUS_H - cam.y) / rd.y;
	vec2 q = (cam + rd * t).xz;
	vec2 uv = q * 0.00008 + vec2(time_s * wind_x, time_s * wind_z) * 0.6;
	uv.y *= 0.22;
	float f = textureLod(shape_tex, vec3(uv, 0.5), 0.0).r;
	float g = textureLod(detail_tex, vec3(uv * 3.1, 0.5), 0.0).r;
	return clamp((f - 0.50) * 3.2, 0.0, 1.0) * (0.5 + 0.5 * g) * cirrus;
}

void fragment() {
	vec3 cam = CAMERA_POSITION_WORLD;
	vec3 rd = normalize(v_world - cam);

	// пересечение луча со слоем [BASE_LO..SLAB_TOP] — РАБОТАЕТ на любой высоте:
	// снизу (смотрим вверх), внутри слоя, и СВЕРХУ (вид с высоты полёта).
	// ВАЖНО: в Godot нельзя 'return' в fragment() — ранее это роняло компиляцию
	// шейдера, и облака НЕ рисовались вообще. Поэтому весь расчёт под флагом.
	float t0 = 0.0;
	float t1 = 0.0;
	bool valid = true;
	if (abs(rd.y) < 1e-4) {                       // почти горизонтально
		if (cam.y < BASE_LO || cam.y > SLAB_TOP) { valid = false; }
		else { t0 = 0.0; t1 = 9000.0; }
	} else {
		float ta = (BASE_LO - cam.y) / rd.y;
		float tb = (SLAB_TOP - cam.y) / rd.y;
		t0 = max(min(ta, tb), 0.0);
		t1 = max(ta, tb);
	}
	float march_len = clamp(t1 - t0, 0.0, 9000.0);

	vec3 col = vec3(0.0);
	float trans = 1.0;
	if (valid && march_len > 1.0) {
		// ДВА ШАГА: крупный по пустоте, мелкий внутри облака.
		//
		// Постоянный шаг (не march_len/STEPS) — потому что у горизонта путь
		// огромен, и при фиксированном ЧИСЛЕ шагов dt рос, давая «веер»
		// ступеней. Но одного постоянного шага мало: когда клуб стал 800 м
		// вместо 3 км, 150 м на шаг — это пять отсчётов на облако, и края
		// пошли крапом (видно на кадре, не домысел). Внутри облака шагаем 55 м
		// (15 отсчётов), по пустоте 240 м. На переходе делаем шаг НАЗАД, иначе
		// крупный шаг перепрыгивает границу и она рвётся.
		const float DT_FINE = 55.0;
		const float DT_COARSE = 240.0;
		const int MAXSTEPS = 80;
		float ct = dot(rd, sun_dir);
		float phase = 0.65 * hg(ct, 0.6) + 0.35 * hg(ct, -0.15);
		float ct_m = dot(rd, moon_dir);
		float phase_m = 0.65 * hg(ct_m, 0.6) + 0.35 * hg(ct_m, -0.15);
		// АНИМИРОВАННЫЙ джиттер: смещение шума во времени → MetalFX temporal
		// усредняет его в гладкое (статичный джиттер давал зернистость).
		float jitter = hash12(FRAGCOORD.xy + vec2(TIME * 41.0, TIME * 27.0));
		float traveled = jitter * DT_FINE;
		vec3 p = cam + rd * (t0 + traveled);
		bool inside = false;      // идём ли сейчас мелким шагом
		int empty_run = 0;        // сколько подряд пустых мелких шагов
		for (int i = 0; i < MAXSTEPS; i++) {
			if (traveled > march_len) { break; }
			float d = cloud_density(p);
			float DT = inside ? DT_FINE : DT_COARSE;
			float step_len = DT;
			if (d > 0.001 && !inside) {
				// ГРАНИЦА: вернуться на крупный шаг назад и пойти мелко, иначе
				// вход в облако окажется там, куда случайно попал крупный шаг.
				inside = true;
				empty_run = 0;
				p -= rd * DT_COARSE;
				traveled -= DT_COARSE;
				continue;
			}
			if (d > 0.001) {
				// свет к солнцу: короткий марш → самозатенение (Бир-Ламберт)
				float lt = 1.0;
				vec3 lp = p;
				for (int l = 0; l < 4; l++) {
					lp += sun_dir * 180.0;
					lt *= exp(-cloud_density(lp) * 180.0 * 0.02);
				}
				float ltf = 0.4 + 0.6 * lt;
				// ВСЕ СЛАГАЕМЫЕ — ДОЛИ ОТ ПОЛУДЕННОГО СВЕТА, а не константы.
				// Ночью sun_energy и sky_energy падают сами, и гасить их
				// отдельным «множителем дневности» больше не нужно: именно он
				// раньше и не справлялся.
				vec3 sun_term = sun_color * (lt * phase * 2.5 + 0.15) * sun_energy;
				vec3 sky_term = sky_tint * 0.85 * ltf * sky_energy;
				vec3 moon_term = moon_light * (phase_m * 2.5 + 0.35) * ltf;
				float a = 1.0 - exp(-d * DT * 0.008);
				col += trans * a * (sun_term + sky_term + moon_term);
				trans *= 1.0 - a;
				empty_run = 0;
				if (trans < 0.02) { break; }
			} else if (inside) {
				// Вышли ли из клуба? Не по первой пустой пробе: край у облака
				// рваный, и одна пустота ещё не значит, что оно кончилось.
				// Возвращаемся к крупному шагу через шесть подряд.
				empty_run += 1;
				if (empty_run > 6) { inside = false; }
			}
			p += rd * step_len;
			traveled += step_len;
		}
	}

	// ПЕРИСТЫЕ поверх нижнего яруса. Свет у них проще: лёд почти не затеняет сам
	// себя, поэтому ни марша к солнцу, ни самозатенения тут нет.
	float ci = cirrus_at(cam, rd);
	if (ci > 0.001) {
		float ct2 = dot(rd, sun_dir);
		float ph2 = 0.7 * hg(ct2, 0.75) + 0.3;
		vec3 ci_lit = sun_color * (ph2 * 1.4 + 0.35) * sun_energy
			+ sky_tint * 0.9 * sky_energy + moon_light * 0.8;
		float a2 = ci * 0.55;
		col += trans * a2 * ci_lit;
		trans *= 1.0 - a2;
	}

	// у горизонта (путь огромен, ступени грубее) — шире растворяем в дымку
	float horizon = smoothstep(0.0, 0.14, abs(rd.y));
	float alpha = (1.0 - trans) * horizon;
	ALBEDO = col;
	ALPHA = clamp(alpha, 0.0, 1.0);
}
