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

// ГОРИЗОНТЫ ПОЧВЫ: какой слой профиля обнажён здесь (tools/build_soil_horizons.py).
// Земля разная не от шума, а от настоящей педологии: катена (смыв/намыв) + покров.
// hz_dry/hz_wet — НАСТОЯЩИЕ цвета слоёв (сухой/мокрый), hz_rough — шероховатость.
uniform sampler2D soil_hz_tex : filter_nearest, repeat_disable;
uniform float soil_hz_on = 0.0;
uniform vec4 hz_dry[7];
uniform vec4 hz_wet[7];
uniform float hz_rough[7];

// ВЛАГА: поле дренажа (где вода застаивается — ложбины и водоупорная глина;
// где уходит — песок на бугре). Считано из настоящих k_sat слоёв и рельефа.
// soil_wetness ведёт погода: дождь копит, сушь убирает.
uniform sampler2D drain_tex : filter_linear, repeat_disable;
uniform float drain_on = 0.0;
uniform float soil_wetness = 0.25;   // 0 сушь .. 1 после ливня

// ВИДИМОСТЬ НЕБА (SVF): доля небесного купола, видимая из точки. Под пасмурным
// небом это главный множитель рассеянного света: в овраге неба видно меньше —
// там сумрачнее. Посчитано из настоящего рельефа заранее (Dozier & Frew).
uniform sampler2D skyview_tex : filter_linear, repeat_disable;
uniform float skyview_on = 0.0;

// ОСНОВА ЗЕМЛИ = РЕАЛЬНАЯ ПОЧВА из ФОТО местной почвы Гатчины, СТРУКТУРНО (набор
// по полю): база — влажный серо-бурый суглинок (soil_c=loam), в низинах —
// плодородный тёмный гумус (soil_wet_c=fertile), на сухих пятнах — растрескавшаяся
// светлая (soil_dry_c=gatchina). Рельеф (Normal/Rough/AO) — общий (loam). Повтор
// разбивается де-тайлингом (две повёрнутые копии) в шейдере.
// АНИЗОТРОПНАЯ фильтрация + мип-карты — грунт виден под пологим углом, где обычной
// мип-фильтрации мало; без этого на дали был сильный алиасинг («зерно»).
uniform sampler2D soil_c : filter_linear_mipmap_anisotropic, repeat_enable;      // база (суглинок)
uniform sampler2D soil_dry_c : filter_linear_mipmap_anisotropic, repeat_enable;  // сухая (трещины)
uniform sampler2D soil_wet_c : filter_linear_mipmap_anisotropic, repeat_enable;  // плодородная (гумус)
uniform sampler2D soil_n : filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D soil_r : filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D soil_ao : filter_linear_mipmap_anisotropic, repeat_enable;
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
	float cell = 2.0 * exp2(clip_level);
	float lod = max(0.0, clip_level - 4.0);
	// ГЕОМОРФИНГ колец: у ВНЕШНЕГО края кольца высота плавно переходит к более
	// грубой (следующий mip) → на стыке совпадает с соседним, более крупным
	// кольцом. Без этого граница колец видна сверху «вложенными квадратами».
	// Морф только во внешней ~четверти кольца (dloc/ext), у ног (центр) — не трогает.
	float ext = float(64.0) * cell;                  // внешний полу-размер кольца, м
	float dloc = max(abs(VERTEX.x), abs(VERTEX.z));   // расстояние от центра кольца (локально)
	float morph = smoothstep(0.72, 0.98, dloc / ext);
	float h_fine = textureLod(height_tex, huv, lod).r;
	float h_coarse = textureLod(height_tex, huv, lod + 1.0).r;
	float h = mix(h_fine, h_coarse, morph);
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

// СМЕШИВАНИЕ ПО ВЫСОТЕ: вместо линейного mix спорят рельефы материалов —
// выступы одного пробиваются сквозь другой, впадины заполняются. Ширина зоны
// перехода D: чем меньше, тем резче «зубчатая» граница (как у настоящего грунта).
vec3 hblend(vec3 ca, float ha, vec3 cb, float hb, float w) {
	const float D = 0.12;
	float a = ha + (1.0 - w);
	float b = hb + w;
	float m = max(a, b) - D;
	float wa = max(a - m, 0.0);
	float wb = max(b - m, 0.0);
	return (ca * wa + cb * wb) / max(wa + wb, 1e-5);
}

// СТОХАСТИЧЕСКОЕ (ГЕКСАГОНАЛЬНОЕ) ТАЙЛИРОВАНИЕ — приём современных AAA против
// «обоев»: глаз ловит повтор текстуры по сетке. Мир режется на ШЕСТИУГОЛЬНИКИ,
// у каждого свой случайный сдвиг И ПОВОРОТ выборки; три ближайших смешиваются
// по весам. Регулярной решётки не остаётся — повтор исчезает, а материал тот же.
// Три выборки заменяют прежний двухчастотный расстрой (он повтор не убирал).
vec2 hex_center(vec2 p, out vec3 w, out vec2 c1, out vec2 c2) {
	// косые координаты гекс-сетки
	const vec2 s = vec2(1.0, 1.7320508);         // 1, sqrt(3)
	vec2 a = mod(p, s) - s * 0.5;
	vec2 b = mod(p - s * 0.5, s) - s * 0.5;
	vec2 gv = dot(a, a) < dot(b, b) ? a : b;
	vec2 c0 = p - gv;
	// два соседа для смешения (по знаку смещения внутри ячейки)
	c1 = c0 + vec2(sign(gv.x) * s.x * 0.5, sign(gv.y) * s.y * 0.5);
	c2 = c0 + vec2(-sign(gv.x) * s.x * 0.5, sign(gv.y) * s.y * 0.5);
	float d0 = length(gv);
	float d1 = length(p - c1);
	float d2 = length(p - c2);
	// веса: ближе центр — больше вклад (мягко, чтобы не было швов)
	w = 1.0 / pow(vec3(d0, d1, d2) + 0.001, vec3(6.0));
	w /= (w.x + w.y + w.z);
	return c0;
}

vec2 hex_uv(vec2 uv, vec2 cell) {
	// свой сдвиг и ПОВОРОТ на каждый шестиугольник — ломает регулярность
	float r = fract(sin(dot(cell, vec2(41.7, 289.1))) * 43758.5453);
	float ang = r * 6.2831853;
	float ca = cos(ang);
	float sa = sin(ang);
	vec2 off = vec2(r, fract(r * 7.13)) * 13.0;
	return mat2(vec2(ca, -sa), vec2(sa, ca)) * uv + off;
}

// выборка цвета БЕЗ ПОВТОРА (3 гекс-выборки, смешение по весам)
vec3 tex_stoch(sampler2D t, vec2 uv) {
	vec3 w;
	vec2 c1;
	vec2 c2;
	vec2 c0 = hex_center(uv * 0.35, w, c1, c2);   // масштаб гекс-сетки
	return texture(t, hex_uv(uv, c0)).rgb * w.x
		+ texture(t, hex_uv(uv, c1)).rgb * w.y
		+ texture(t, hex_uv(uv, c2)).rgb * w.z;
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
	// выборка почвы на ДВУХ частотах тайла — против явного повтора. Зерно на дали
	// лечится мип-картами + АНИЗОТРОПИЕЙ (в объявлениях сэмплеров), а не шейдером.
	// ТРИПЛАН на склонах: плоская проекция XZ растягивает материал тем сильнее,
	// чем круче склон (в 1/cos(наклона) раз). Подмешиваем боковые проекции по
	// весу нормали — на обрывах и в стенках выемок фактура перестаёт «течь».
	vec2 uv0 = v_wpos.xz / detail_tile_m;
	vec2 uvb = v_wpos.xz / (detail_tile_m * 5.7);
	vec2 uv_x = v_wpos.zy / detail_tile_m;
	vec2 uv_z = v_wpos.xy / detail_tile_m;
	vec3 tw = abs(gn);
	tw = pow(tw, vec3(4.0));
	tw /= max(tw.x + tw.y + tw.z, 1e-4);
	float side = 1.0 - tw.y;                     // 0 на ровном, 1 на отвесном

	// БЛИЗКО — стохастическое тайлирование (нет повтора, но 3 выборки);
	// ДАЛЬШЕ 90 м переходим на обычную выборку: там повтор всё равно не читается,
	// а лишние выборки едят кадр. Так честно и по виду, и по цене.
	float near_w = 1.0 - smoothstep(60.0, 90.0, dist);
	vec3 c_base;
	if (near_w > 0.01) {
		c_base = mix(texture(soil_c, uv0).rgb, tex_stoch(soil_c, uv0), near_w);
	} else {
		c_base = mix(texture(soil_c, uv0).rgb, texture(soil_c, uvb).rgb, 0.35);
	}
	if (side > 0.01) {
		vec3 cs = texture(soil_c, uv_x).rgb * tw.x + texture(soil_c, uv_z).rgb * tw.z;
		c_base = mix(c_base, cs / max(tw.x + tw.z, 1e-4), side);
	}
	vec3 c_dry = mix(texture(soil_dry_c, uv0).rgb, texture(soil_dry_c, uvb).rgb, 0.35);
	vec3 c_wet = mix(texture(soil_wet_c, uv0).rgb, texture(soil_wet_c, uvb).rgb, 0.35);

	// СТРУКТУРНО ПО ПОЛЮ: низины (wet) → плодородный тёмный; сухие пятна (шум,
	// не в низине, не на склоне) → растрескавшаяся светлая; иначе — суглинок-база.
	// ВЛАЖНОСТЬ ЗЕМЛИ = погода x способность места держать воду. В ложбине и на
	// глине после дождя сыро долго, на песчаном бугре сохнет сразу — это не
	// «нарисованные пятна», а следствие рельефа и водопроницаемости слоёв.
	float drain_hold = 0.5;
	if (drain_on > 0.5) {
		vec2 duv2 = clamp((v_wpos.xz + vec2(dem_half)) / (2.0 * dem_half), 0.0, 1.0);
		drain_hold = texture(drain_tex, duv2).r;
	}
	float weather_wet = clamp(soil_wetness * (0.35 + 1.3 * drain_hold), 0.0, 1.0);
	float wetf = clamp(max(wet * 1.4, weather_wet), 0.0, 1.0);
	float dryf = clamp(smoothstep(0.58, 0.85, vnoise(v_wpos.xz * 0.03))
		* (1.0 - wetf) - slope * 0.5, 0.0, 1.0) * 0.45;

	// СМЕШИВАНИЕ ПО ВЫСОТЕ (height-blend) — главный приём AAA вместо линейного
	// перехода. При обычном mix два материала «растворяются» друг в друге серой
	// кашей. Здесь спорят их РЕЛЬЕФЫ: где комья базового грунта выше, они
	// торчат сквозь наносимый слой, а тот заполняет впадины между ними —
	// как в жизни. hb(): смещаем высоты на вес и берём верхний с узкой зоной.
	// --- МИКРОРЕЛЬЕФ (параллакс): земля перестаёт быть плоской ---
	// Комья и борозды получают ГЛУБИНУ: луч зрения смещается по карте высот,
	// поэтому выступы загораживают впадины, а при движении головы возникает
	// параллакс — плоская «наклейка» превращается в поверхность с объёмом.
	// Прошлый раз POM работал ВЕЗДЕ и уронил FPS до 10. Теперь строго вблизи
	// (до 4 м, гаснет к 10 м) и малым числом шагов — цена ограничена.
	float pom_w = 1.0 - smoothstep(4.0, 10.0, dist);
	vec2 uv_p = uv0;
	if (pom_w > 0.01) {
		vec3 vdir_w = normalize(v_wpos - CAMERA_POSITION_WORLD);
		// направление взгляда в плоскости земли; крутизна = насколько косой взгляд
		vec2 pdir = vdir_w.xz / max(abs(vdir_w.y), 0.35);
		const float AMP = 0.035;                 // глубина рельефа, м (комья ~3.5 см)
		const int PSTEP = 6;                     // мало шагов — дёшево
		float layer = 1.0 / float(PSTEP);
		vec2 duv = pdir * (AMP / detail_tile_m) * layer;
		float cur_h = 1.0;
		vec2 uvp = uv0;
		float hs = texture(soil_h, uvp).r;
		for (int pi = 0; pi < PSTEP; pi++) {
			if (hs >= cur_h) { break; }
			uvp += duv;
			cur_h -= layer;
			hs = texture(soil_h, uvp).r;
		}
		uv_p = mix(uv0, uvp, pom_w);
	}

	float h_base = texture(soil_h, uv_p).r;
	float h_wet = texture(soil_h, uv0 * 1.31 + vec2(0.37)).r;   // своя фаза — не копия
	float h_dry = texture(soil_h, uv0 * 0.83 + vec2(0.71)).r;
	vec3 s_alb = hblend(c_base, h_base, c_wet, h_wet, wetf);
	s_alb = hblend(s_alb, mix(h_base, h_wet, wetf), c_dry, h_dry, dryf);

	// --- ГОРИЗОНТ ПОЧВЫ: чем земля ЯВЛЯЕТСЯ здесь (не шум, а педология) ---
	// Индекс обнажённого слоя из карты; его настоящий цвет (сухой/мокрый)
	// ПЕРЕКРАШИВАЕТ фотоснимок почвы, сохраняя его структуру (комья/зерно).
	// Так под лесом сверху тёмная подстилка, в поле — гумус, на срезе склона
	// и в городе — бурый иллювий, на размывах — белёсый подзол.
	float hz_rough_v = 1.0;
	if (soil_hz_on > 0.5) {
		// Карта горизонтов хранит НОМЕРА слоёв — их нельзя фильтровать (между
		// 1 и 3 получится чужой слой 2), поэтому берём 4 соседние клетки, у
		// каждой свой НАСТОЯЩИЙ цвет, и смешиваем ЦВЕТА билинейно. Иначе на
		// границах клеток DEM земля выглядит шахматной доской 32 м.
		float texel = 1.0 / 513.0;
		vec2 hzuv = clamp((v_wpos.xz + vec2(dem_half)) / (2.0 * dem_half), 0.0, 1.0);
		vec2 tc = hzuv / texel - 0.5;
		vec2 base = (floor(tc) + 0.5) * texel;
		vec2 fr = fract(tc);
		vec3 hcol = vec3(0.0);
		float rsum = 0.0;
		for (int oy = 0; oy < 2; oy++) {
			for (int ox = 0; ox < 2; ox++) {
				vec2 uv = clamp(base + vec2(float(ox), float(oy)) * texel, 0.0, 1.0);
				int k = clamp(int(texture(soil_hz_tex, uv).r * 255.0 + 0.5), 0, 6);
				float w = (ox == 0 ? 1.0 - fr.x : fr.x) * (oy == 0 ? 1.0 - fr.y : fr.y);
				hcol += mix(hz_dry[k].rgb, hz_wet[k].rgb, wetf) * w;
				rsum += hz_rough[k] * w;
			}
		}
		hz_rough_v = rsum;
		// Берём от снимка почвы ТОЛЬКО СТРУКТУРУ (яркостные вариации: комья,
		// зерно, трещины), а ЦВЕТ — от горизонта. Структура обязана быть
		// БЕСЦВЕТНОЙ: если оставить её цветной, оттенок снимка перемножится с
		// оттенком горизонта и земля уйдёт в неестественный пересвеченный тон.
		float lum = dot(s_alb, vec3(0.299, 0.587, 0.114));
		float structure = clamp(lum / 0.34, 0.55, 1.6);   // 0.34 — средняя яркость снимка
		s_alb = clamp(hcol * structure, vec3(0.0), vec3(1.0));
	}

	float mat_rough = texture(soil_r, uv_p).r;
	vec3 tn = texture(soil_n, uv_p).xyz * 2.0 - 1.0;
	float s_ao = texture(soil_ao, uv_p).r;
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

	float rough = mix(rough_target, mat_rough, 0.85) * hz_rough_v;
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

	// SVF гасит рассеянный свет неба (не прямой солнечный) — как в природе
	if (skyview_on > 0.5) {
		vec2 svuv = clamp((v_wpos.xz + vec2(dem_half)) / (2.0 * dem_half), 0.0, 1.0);
		float svf = texture(skyview_tex, svuv).r;
		AO = mix(1.0, svf, 0.85);
		AO_LIGHT_AFFECT = 0.0;      // гасим только окружающий свет, не солнце
	}
	ALBEDO = col2;
	// ЖЁСТКИЙ матовый пол шероховатости — грунт НИКОГДА не бликует как камень/стекло
	ROUGHNESS = clamp(rough, 0.72, 1.0);
	METALLIC = 0.0;
	SPECULAR = spec;
	NORMAL = normalize((VIEW_MATRIX * vec4(n, 0.0)).xyz);
}
