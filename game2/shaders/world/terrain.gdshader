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

// ОСНОВА ЗЕМЛИ = РЕАЛЬНАЯ ПОЧВА из ФОТО местной почвы Гатчины, СТРУКТУРНО (набор
// по полю): база — влажный серо-бурый суглинок (soil_c=loam), в низинах —
// плодородный тёмный гумус (soil_wet_c=fertile), на сухих пятнах — растрескавшаяся
// светлая (soil_dry_c=gatchina). Рельеф (Normal/Rough/AO) — общий (loam). Повтор
// разбивается де-тайлингом (две повёрнутые копии) в шейдере.
uniform sampler2D soil_c : filter_linear_mipmap, repeat_enable;      // база (суглинок)
uniform sampler2D soil_dry_c : filter_linear_mipmap, repeat_enable;  // сухая (трещины)
uniform sampler2D soil_wet_c : filter_linear_mipmap, repeat_enable;  // плодородная (гумус)
uniform sampler2D soil_n : filter_linear_mipmap, repeat_enable;
uniform sampler2D soil_r : filter_linear_mipmap, repeat_enable;
uniform sampler2D soil_ao : filter_linear_mipmap, repeat_enable;
uniform sampler2D soil_h : filter_linear_mipmap, repeat_enable;
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

	// --- РЕАЛЬНАЯ ПОЧВА как основа земли ВЕЗДЕ, ЦВЕТ = скан (сведён к почве
	// Гатчины). Реальный AO почвы. Две частоты тайла + макро-девариация —
	// против «плоской заливки» на дали. На всех дистанциях. ---
	// ДЕ-ТАЙЛИНГ: две повёрнутые/сдвинутые копии тайла, мягко смешанные по низкой
	// частоте — разбивает узнаваемый повтор (камешки) без ячеек-швов.
	vec2 uv0 = v_wpos.xz / detail_tile_m;
	float ca = 0.878, sa = 0.479;                 // cos/sin(0.5)
	float cb = 0.622, sb = -0.783;                // cos/sin(-0.9)
	vec2 uvA = vec2(uv0.x * ca - uv0.y * sa, uv0.x * sa + uv0.y * ca) + vec2(13.2, 7.4);
	vec2 uvB = vec2(uv0.x * cb - uv0.y * sb, uv0.x * sb + uv0.y * cb) + vec2(51.7, 29.1);
	// крупные пятна одной копии + тонкий шов → без интерференц-зерна
	float kmix = smoothstep(0.46, 0.54, vnoise(v_wpos.xz * 0.02));
	vec3 c_base = mix(texture(soil_c, uvA).rgb, texture(soil_c, uvB).rgb, kmix);
	vec3 c_dry = mix(texture(soil_dry_c, uvA).rgb, texture(soil_dry_c, uvB).rgb, kmix);
	vec3 c_wet = mix(texture(soil_wet_c, uvA).rgb, texture(soil_wet_c, uvB).rgb, kmix);

	// СТРУКТУРНО ПО ПОЛЮ: низины (wet) → плодородный тёмный; сухие пятна (шум,
	// не в низине, не на склоне) → растрескавшаяся светлая; иначе — суглинок-база.
	float wetf = clamp(wet * 1.4, 0.0, 1.0);
	float dryf = clamp(smoothstep(0.58, 0.85, vnoise(v_wpos.xz * 0.03))
		* (1.0 - wetf) - slope * 0.5, 0.0, 1.0) * 0.45;
	vec3 s_alb = mix(c_base, c_wet, wetf);
	s_alb = mix(s_alb, c_dry, dryf);

	float mat_rough = texture(soil_r, uv0).r;
	vec3 tn = texture(soil_n, uv0).xyz * 2.0 - 1.0;
	float s_ao = texture(soil_ao, uv0).r;
	vec3 mat_alb = s_alb * mix(1.0, s_ao, 0.75);   // реальный AO почвы в западинах

	// макро-девариация ДВУХ низких частот (тональная) — против «плоской заливки»;
	// крутые склоны чуть темнее (грунт в тени комьев).
	vec3 col2 = mat_alb;
	float macro = vnoise(v_wpos.xz * 0.05) * 0.6 + vnoise(v_wpos.xz * 0.013) * 0.4;
	col2 *= 0.85 + 0.30 * macro;
	col2 = mix(col2, col2 * vec3(0.82, 0.78, 0.72), slope * 0.4);

	// нормаль материала умеренная и слабеет с далью (сильная = искристое зерно)
	float nstr = 0.55 * (1.0 - smoothstep(60.0, 320.0, dist));
	vec3 n = normalize(vec3(gn.x + tn.x * nstr, gn.y, gn.z + tn.z * nstr));

	float rough = mix(rough_target, mat_rough, 0.85);
	float spec = 0.04;   // почва МАТОВАЯ: диэлектрик с почти нулевым бликом
	// ВЛАЖНОСТЬ (реальное поле влаги низин): мокрая почва темнее и чуть менее
	// матовая — но НЕ зеркало (грунт не бликует как мокрый камень).
	float wetv = 0.0;
	if (moisture_half > 1.0) {
		vec2 dpos = vec2(v_wpos.x, -v_wpos.z);       // данные: восток, север
		vec2 muv = (dpos - moisture_center) / (2.0 * moisture_half) + 0.5;
		muv.y = 1.0 - muv.y;
		if (muv.x > 0.0 && muv.x < 1.0 && muv.y > 0.0 && muv.y < 1.0)
			wetv = max(wetv, smoothstep(0.35, 0.90, texture(moisture_tex, muv).r));
	}
	col2 *= mix(1.0, 0.6, wetv);                     // мокрая — темнее
	rough = mix(rough, 0.7, wetv);                   // мокрая чуть глаже, но матовая
	spec = mix(spec, 0.12, wetv);                    // слабый влажный отлив, не блик

	// спрессованная почва в следе темнее (просадка от нагрузки)
	col2 *= mix(1.0, 0.7, v_deform);

	ALBEDO = col2;
	// ЖЁСТКИЙ матовый пол шероховатости — грунт НИКОГДА не бликует как камень/стекло
	ROUGHNESS = clamp(rough, 0.72, 1.0);
	METALLIC = 0.0;
	SPECULAR = spec;
	NORMAL = normalize((VIEW_MATRIX * vec4(n, 0.0)).xyz);
}
