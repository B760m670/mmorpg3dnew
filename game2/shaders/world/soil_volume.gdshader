shader_type spatial;
// ПОЧВА КАК ВЕЩЕСТВО — материал ОБЪЁМА, а не покрытие поверхности.
//
// Здесь нет «фото почвы, натянутого на плоскость». Цвет каждой точки берётся из
// того, КАКОЙ СЛОЙ ЗАЛЕГАЕТ НА ЭТОЙ ГЛУБИНЕ (UV.x — глубина в метрах, UV.y —
// номер горизонта, посчитанный в soil_volume.gd по настоящему профилю).
// Поэтому в стенке вырытой ямы сверху вниз идут НАСТОЯЩИЕ слои: тёмный гумус,
// белёсый подзол, бурый иллювий, морена — как в реальном почвенном разрезе.
//
// Структура вещества (комья, зерно, поры) — процедурная и ОБЪЁМНАЯ (шум от
// мировых координат, включая высоту), поэтому она не «наклеена», а продолжается
// внутрь массива: срез в любом месте выглядит как срез грунта, а не как обои.
render_mode diffuse_burley, specular_disabled;

uniform vec4 hz_col[7];        // настоящие цвета горизонтов (из профиля)
uniform float hz_rough[7];
uniform float wetness = 0.0;   // 0 сухо .. 1 мокро (мокрый грунт темнее)

varying vec3 v_world;
varying vec2 v_soil;           // x = глубина, м; y = номер горизонта

void vertex() {
	v_world = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	v_soil = UV;
}

float hash13(vec3 p) {
	p = fract(p * 0.3183099 + vec3(0.71, 0.113, 0.419));
	p += dot(p, p.yzx + 33.33);
	return fract((p.x + p.y) * p.z);
}

// ОБЪЁМНЫЙ шум: значение зависит от точки В ПРОСТРАНСТВЕ (в т.ч. по высоте),
// поэтому структура грунта продолжается внутрь, а не лежит плёнкой на грани
float vnoise3(vec3 p) {
	vec3 i = floor(p);
	vec3 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	float n000 = hash13(i);
	float n100 = hash13(i + vec3(1, 0, 0));
	float n010 = hash13(i + vec3(0, 1, 0));
	float n110 = hash13(i + vec3(1, 1, 0));
	float n001 = hash13(i + vec3(0, 0, 1));
	float n101 = hash13(i + vec3(1, 0, 1));
	float n011 = hash13(i + vec3(0, 1, 1));
	float n111 = hash13(i + vec3(1, 1, 1));
	return mix(mix(mix(n000, n100, f.x), mix(n010, n110, f.x), f.y),
		mix(mix(n001, n101, f.x), mix(n011, n111, f.x), f.y), f.z);
}

void fragment() {
	int hz = clamp(int(v_soil.y + 0.5), 0, 6);
	vec3 base = hz_col[hz].rgb;

	// СМЕШЕНИЕ НА ГРАНИЦЕ СЛОЁВ: в природе горизонты переходят друг в друга
	// языками и затёками, а не по линейке. Смещаем границу объёмным шумом.
	float border = vnoise3(v_world * 3.7) - 0.5;
	int hz2 = clamp(hz + (border > 0.0 ? 1 : -1), 0, 6);
	float t = clamp(abs(border) * 1.4 - 0.35, 0.0, 1.0);
	base = mix(base, hz_col[hz2].rgb, t * 0.35);

	// СТРУКТУРА ГРУНТА (объёмная): крупные комья + зерно + поры
	float clods = vnoise3(v_world * 12.0);
	float grain = vnoise3(v_world * 55.0);
	float pores = smoothstep(0.62, 0.95, vnoise3(v_world * 28.0));
	float structure = 0.80 + 0.30 * clods + 0.12 * grain;
	structure *= 1.0 - 0.35 * pores;              // поры/пустоты темнее

	// глубже — плотнее и темнее (уплотнение под весом вышележащего)
	float depth = v_soil.x;
	float compaction = 1.0 - clamp(depth / 6.0, 0.0, 1.0) * 0.18;

	vec3 col = base * structure * compaction;
	// мокрый грунт темнее (реальный эффект: вода заполняет поры)
	col *= mix(1.0, 0.55, wetness);

	ALBEDO = clamp(col, vec3(0.0), vec3(1.0));
	ROUGHNESS = clamp(hz_rough[hz] * (1.0 - 0.25 * wetness), 0.35, 1.0);
	METALLIC = 0.0;
	SPECULAR = 0.02;                              // грунт матовый, не камень
	// микрорельеф комьев в нормали — грани ямы «рваные», не полированные
	float e = 0.02;
	float nx = vnoise3((v_world + vec3(e, 0, 0)) * 12.0) - clods;
	float nz = vnoise3((v_world + vec3(0, 0, e)) * 12.0) - clods;
	NORMAL_MAP = normalize(vec3(-nx * 6.0, -nz * 6.0, 1.0)) * 0.5 + 0.5;
}
