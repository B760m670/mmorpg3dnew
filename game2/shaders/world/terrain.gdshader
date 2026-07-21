shader_type spatial;
// ЗЕМЛЯ — основа под ногами. Высоты в GPU-текстуре (реальный DEM), нормали
// считаются НА ПИКСЕЛЬ из неё: дальний рельеф освещается гладко по мип-уровням
// (мерцающие полосы на горизонте исчезают), ближний — рельефно до кочки.
// Вблизи добавляются микронормали грунта (сантиметровая неровность) и
// микровариация цвета. Зоны — реальное землепользование (zone_tex).
// Видимая поверхность согласована с коллизией (обе — из той же height()).
render_mode diffuse_burley, cull_back;   // спекуляр включён — для влажного блеска почвы

uniform sampler2D height_tex : filter_linear_mipmap, repeat_disable;
uniform float dem_half = 8192.0;         // текстура высот покрывает ±dem_half
uniform sampler2D zone_tex : filter_nearest, repeat_disable;
uniform float zone_size_m = 12288.0;
uniform float wet_level = -30.0;         // мировая высота сырых низин, м

// РЕАЛЬНЫЕ материалы поверхности (сканы ambientCG, CC0 — assets/materials/real).
// Цвет земли — это НАСТОЯЩИЙ альбедо скана (не палитра): трава и гравий,
// смешиваются по dirt_w. На всех дистанциях (мип усредняет даль сам).
uniform sampler2D grass_c : filter_linear_mipmap, repeat_enable;
uniform sampler2D grass_n : filter_linear_mipmap, repeat_enable;
uniform sampler2D grass_r : filter_linear_mipmap, repeat_enable;
uniform sampler2D gravel_c : filter_linear_mipmap, repeat_enable;
uniform sampler2D gravel_n : filter_linear_mipmap, repeat_enable;
uniform sampler2D gravel_r : filter_linear_mipmap, repeat_enable;
uniform float detail_tile_m = 2.0;

// ВЕРТИКАЛЬНЫЙ СРЕЗ (Дворцовый парк): детальная карта поверхностей 1 м/пкс.
// В её границах земля красится богатым набором (газон/роща/лес/аллея/плац/
// берег/мостовая) поверх грубой зоны — «земля везде разная».
uniform sampler2D slice_tex : filter_nearest, repeat_disable;
uniform vec2 slice_center = vec2(0.0, 400.0);   // данные: восток, север
uniform float slice_half = 0.0;                 // 0 → срез выключен

// клипмап: уровень кольца этого меша (0 — центр 2 м ... 6 — кольцо 128 м)
instance uniform float clip_level = 0.0;

// ДЕФОРМАЦИЯ почвы (следы/проседание под нагрузкой): imprint-буфер вокруг
// игрока, глубина ∝ деформируемости почвы (задаётся снаружи ground_deform.gd).
// Guarded: deform_half<=0 → выключено, террейн не трогается.
uniform sampler2D deform_tex : filter_linear, repeat_disable;
uniform vec2 deform_center = vec2(0.0);
uniform float deform_half = 0.0;
uniform float deform_depth = 0.12;

// ВЛАЖНОСТЬ почвы (реальное поле влаги build_soilfield): мокрая земля темнее и
// глянцевее (влажный блеск). Guarded: moisture_half<=0 → выключено.
uniform sampler2D moisture_tex : filter_linear, repeat_disable;
uniform vec2 moisture_center = vec2(0.0, 400.0);
uniform float moisture_half = 0.0;

// ДОЖДЬ (рантайм, из weather/rain.gd): дождь мочит поверхность ВЕЗДЕ (не только
// поле среза) — накопленная сырость rain_wet; при ливне на низинах-чашах стоит
// вода (лужи), по ней рябь ∝ rain_rate. Guarded: rain_wet=0 → сухо, ничего.
uniform float rain_wet = 0.0;     // 0 сухо .. 1 поверхность насыщена
uniform float rain_rate = 0.0;    // 0 нет дождя .. 1 ливень (сила ряби на лужах)

varying vec3 v_wpos;
varying float v_deform;

void vertex() {
	// кольцо — плоская сетка, ездит за камерой (в MODEL — снап-позиция);
	// высота берётся здесь, mip по уровню кольца: дальняя геометрия
	// сглаживается в самом источнике (чистый горизонт по построению)
	vec3 w = (MODEL_MATRIX * vec4(VERTEX.x, 0.0, VERTEX.z, 1.0)).xyz;
	vec2 huv = (w.xz + vec2(dem_half)) / (2.0 * dem_half);
	float lod = max(0.0, clip_level - 4.0);
	float h = textureLod(height_tex, huv, lod).r;
	float cell = 2.0 * exp2(clip_level);
	bool skirt = VERTEX.y < -500.0;      // маркер вершин-юбок
	VERTEX.y = h - (skirt ? cell * 2.0 + 2.0 : 0.0);
	v_wpos = vec3(w.x, h, w.z);

	// деформация — только на детальных кольцах у ног, вне юбок
	v_deform = 0.0;
	if (deform_half > 0.5 && clip_level < 2.5 && !skirt) {
		vec2 duv = (w.xz - deform_center) / (2.0 * deform_half) + 0.5;
		if (duv.x > 0.0 && duv.x < 1.0 && duv.y > 0.0 && duv.y < 1.0) {
			float d = texture(deform_tex, duv).r * deform_depth;
			VERTEX.y -= d;
			v_deform = d / max(deform_depth, 1e-4);
		}
	}
}

float hh(vec2 wxz) {
	vec2 uv = (wxz + vec2(dem_half)) / (2.0 * dem_half);
	return texture(height_tex, uv).r;
}

float hash12(vec2 p) {
	p = fract(p * vec2(0.1031, 0.1030));
	p += dot(p, p.yx + 33.33);
	return fract((p.x + p.y) * p.x);
}

// value-шум (билинейный) для микрорельефа/пятен
float vnoise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	float a = hash12(i);
	float b = hash12(i + vec2(1, 0));
	float c = hash12(i + vec2(0, 1));
	float d = hash12(i + vec2(1, 1));
	return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

vec3 zone_tint(int z) {
	if (z == 1) return vec3(0.150, 0.310, 0.095);   // парк
	if (z == 2) return vec3(0.080, 0.185, 0.075);   // лес
	if (z == 3) return vec3(0.340, 0.305, 0.130);   // поля
	if (z == 4) return vec3(0.330, 0.290, 0.235);   // город
	if (z == 5) return vec3(0.100, 0.140, 0.120);   // берег/дно
	if (z == 6) return vec3(0.180, 0.265, 0.110);   // кустарник
	if (z == 7) return vec3(0.140, 0.185, 0.115);   // болото
	if (z == 8) return vec3(0.295, 0.255, 0.190);   // дорога+обочина (утоптано)
	return vec3(0.225, 0.315, 0.120);               // луг
}

// поверхность среза: цвет, шероховатость, доля «голого грунта» (0 дернина
// … 1 песок/гравий) для примеси детальной текстуры
void slice_surface(int s, out vec3 c, out float rough, out float bare) {
	if (s == 1)      { c = vec3(0.140, 0.300, 0.090); rough = 0.95; bare = 0.05; } // газон стриженый
	else if (s == 2) { c = vec3(0.115, 0.155, 0.070); rough = 1.00; bare = 0.30; } // роща (подстилка)
	else if (s == 3) { c = vec3(0.070, 0.110, 0.058); rough = 1.00; bare = 0.20; } // лес плотный
	else if (s == 4) { c = vec3(0.355, 0.315, 0.230); rough = 0.90; bare = 1.00; } // аллея (гравий)
	else if (s == 5) { c = vec3(0.435, 0.400, 0.315); rough = 0.85; bare = 1.00; } // плац (песок)
	else if (s == 6) { c = vec3(0.085, 0.110, 0.105); rough = 0.55; bare = 1.00; } // дно/вода
	else if (s == 7) { c = vec3(0.220, 0.240, 0.140); rough = 1.00; bare = 0.55; } // берег/камыш
	else if (s == 8) { c = vec3(0.320, 0.295, 0.265); rough = 0.80; bare = 1.00; } // мостовая
	else             { c = vec3(0.205, 0.300, 0.110); rough = 1.00; bare = 0.00; } // луг
}

void fragment() {
	float dist = length(VERTEX);

	// --- нормаль рельефа НА ПИКСЕЛЬ из текстуры высот ---
	float e = 12.0;
	float hL = hh(v_wpos.xz + vec2(-e, 0.0));
	float hR = hh(v_wpos.xz + vec2(e, 0.0));
	float hN = hh(v_wpos.xz + vec2(0.0, -e));
	float hS = hh(v_wpos.xz + vec2(0.0, e));
	float hC = hh(v_wpos.xz);
	vec3 gn = normalize(vec3(hL - hR, 2.0 * e, hN - hS));   // геометрическая
	// на дали мип-уровни размазывают склоны берегов → нормали вспыхивают к
	// солнцу лентами; прижимаем дальнюю нормаль к вертикали (рельеф дали — LOD)
	gn = normalize(mix(gn, vec3(0.0, 1.0, 0.0), smoothstep(700.0, 2200.0, dist)));

	// --- зона (реальное землепользование), размытая граница ---
	vec2 zuv = (v_wpos.xz + vec2(zone_size_m * 0.5)) / zone_size_m;
	vec2 j = (vec2(hash12(v_wpos.xz * 0.37), hash12(v_wpos.xz * 0.53 + 7.0)) - 0.5)
		* (14.0 / zone_size_m);
	int z = int(texture(zone_tex, clamp(zuv + j, 0.0, 1.0)).r * 255.0 + 0.5);
	vec3 col = zone_tint(z);

	// склоны — грунт; низины — сырость; крупная пятнистость
	float slope = clamp((1.0 - gn.y) * 3.5, 0.0, 1.0);
	col = mix(col, vec3(0.32, 0.25, 0.16), slope);
	float wet = clamp((wet_level - hC) / 6.0, 0.0, 1.0);
	col = mix(col, vec3(0.15, 0.18, 0.15), wet * 0.8);
	float broad = vnoise(v_wpos.xz * 0.045);
	col *= 1.0 - 0.16 * broad;

	// база примеси грунта (склон/город/сырость) — срез её переопределит
	float dirt_w = clamp(slope * 1.4 + ((z == 4 || z == 8) ? 0.85 : 0.0)
		+ wet * 0.4, 0.0, 1.0);
	float rough_target = 1.0;

	// --- ВЕРТИКАЛЬНЫЙ СРЕЗ: детальные поверхности Дворцового парка ---
	if (slice_half > 1.0) {
		vec2 dpos = vec2(v_wpos.x, -v_wpos.z);        // данные: восток, север
		vec2 suv = (dpos - slice_center) / (2.0 * slice_half) + 0.5;
		suv.y = 1.0 - suv.y;                           // строка 0 = север
		if (suv.x > 0.0 && suv.x < 1.0 && suv.y > 0.0 && suv.y < 1.0) {
			vec2 edge = min(suv, vec2(1.0) - suv);
			float sinf = smoothstep(0.0, 40.0 / (2.0 * slice_half), min(edge.x, edge.y));
			int s = int(texture(slice_tex, suv).r * 255.0 + 0.5);
			vec3 sc; float sr; float sb;
			slice_surface(s, sc, sr, sb);
			sc *= 1.0 - 0.14 * broad;                 // та же крупная пятнистость
			col = mix(col, sc, sinf);
			dirt_w = mix(dirt_w, sb, sinf);
			rough_target = mix(rough_target, sr, sinf);
		}
	}

	// --- РЕАЛЬНЫЙ материал земли: трава/гравий по dirt_w, ЦВЕТ = скан (не
	// палитра), на ВСЕХ дистанциях (мип усредняет даль). Две частоты тайла —
	// против явного повтора. ---
	vec2 duv = v_wpos.xz / detail_tile_m;
	vec2 duvb = v_wpos.xz / (detail_tile_m * 5.7);
	vec3 g_alb = mix(texture(grass_c, duv).rgb, texture(grass_c, duvb).rgb, 0.45);
	vec3 v_alb = mix(texture(gravel_c, duv).rgb, texture(gravel_c, duvb).rgb, 0.45);
	vec3 mat_alb = mix(g_alb, v_alb, dirt_w);
	float mat_rough = mix(texture(grass_r, duv).r, texture(gravel_r, duv).r, dirt_w);
	vec3 g_tn = texture(grass_n, duv).xyz * 2.0 - 1.0;
	vec3 v_tn = texture(gravel_n, duv).xyz * 2.0 - 1.0;
	vec3 tn = mix(g_tn, v_tn, dirt_w);

	// зона — лишь лёгкий оттенок (тон, среднее 1) для крупной вариации, не палитра
	vec3 zt = zone_tint(z);
	vec3 tint = zt / max(dot(zt, vec3(0.333)), 0.02);
	vec3 col2 = mat_alb * mix(vec3(1.0), tint, 0.30);
	col2 *= 1.0 - 0.12 * broad;
	col2 = mix(col2, col2 * vec3(0.72, 0.66, 0.60), wet * 0.5);   // сырость темнит

	// нормаль материала слабеет с далью (против алиасинга лент к солнцу)
	float nstr = 0.9 * (1.0 - smoothstep(60.0, 320.0, dist));
	vec3 n = normalize(vec3(gn.x + tn.x * nstr, gn.y, gn.z + tn.z * nstr));

	float rough = mix(rough_target, mat_rough, 0.85);
	float spec = 0.15;
	// ВЛАЖНОСТЬ: поле почвы (статичная сырость низин) ⊕ ДОЖДЬ (рантайм мочит
	// поверхность ВЕЗДЕ). Мокрая почва темнее, глаже, с влажным блеском.
	float wetv = clamp(rain_wet, 0.0, 1.0);
	if (moisture_half > 1.0) {
		vec2 dpos = vec2(v_wpos.x, -v_wpos.z);       // данные: восток, север
		vec2 muv = (dpos - moisture_center) / (2.0 * moisture_half) + 0.5;
		muv.y = 1.0 - muv.y;
		if (muv.x > 0.0 && muv.x < 1.0 && muv.y > 0.0 && muv.y < 1.0)
			wetv = max(wetv, smoothstep(0.35, 0.90, texture(moisture_tex, muv).r));
	}
	col2 *= mix(1.0, 0.55, wetv);                    // мокрая — темнее
	rough = mix(rough, 0.32, wetv);                  // и глаже
	spec = mix(spec, 0.55, wetv);                    // влажный блеск

	// спрессованная почва в следе темнее и глаже (просадка от нагрузки)
	col2 *= mix(1.0, 0.62, v_deform);
	rough *= mix(1.0, 0.7, v_deform);

	// --- ЛУЖИ: вода собирается в вогнутостях рельефа (реальный сток вниз),
	// только на ровном И когда дождь напитал грунт. Стоячая вода — тёмная,
	// плоская (нормаль к небу), зеркальная; рябь от капель ∝ силе дождя. ---
	float lap = (hL + hR + hN + hS - 4.0 * hC);      // >0 — чаша, вода стекает сюда
	float flatv = smoothstep(0.90, 0.99, gn.y);
	float pond = clamp(smoothstep(0.12, 0.50, lap), 0.0, 1.0) * flatv
		* smoothstep(0.30, 0.75, wetv);
	if (pond > 0.001) {
		float rip = sin(dot(v_wpos.xz, vec2(7.3, 6.1)) - TIME * 9.0)
			+ sin(dot(v_wpos.xz, vec2(-5.7, 8.4)) + TIME * 7.0);
		vec3 rn = normalize(vec3(rip * 0.05 * rain_rate, 1.0, rip * 0.05 * rain_rate));
		n = normalize(mix(n, rn, pond));             // плоско к небу + рябь
		col2 = mix(col2, vec3(0.015, 0.022, 0.028), pond * 0.92);
		rough = mix(rough, 0.03, pond);
		spec = mix(spec, 1.0, pond);
	}

	ALBEDO = col2;
	ROUGHNESS = clamp(rough, 0.02, 1.0);
	METALLIC = 0.0;
	SPECULAR = spec;
	NORMAL = normalize((VIEW_MATRIX * vec4(n, 0.0)).xyz);
}
