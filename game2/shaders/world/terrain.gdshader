shader_type spatial;
// ЗЕМЛЯ — основа под ногами. Высоты в GPU-текстуре (реальный DEM), нормали
// считаются НА ПИКСЕЛЬ из неё: дальний рельеф освещается гладко по мип-уровням
// (мерцающие полосы на горизонте исчезают), ближний — рельефно до кочки.
// Вблизи добавляются микронормали грунта (сантиметровая неровность) и
// микровариация цвета. Зоны — реальное землепользование (zone_tex).
// Видимая поверхность согласована с коллизией (обе — из той же height()).
render_mode diffuse_burley, specular_disabled, cull_back;

uniform sampler2D height_tex : filter_linear_mipmap, repeat_disable;
uniform float dem_half = 8192.0;         // текстура высот покрывает ±dem_half
uniform sampler2D zone_tex : filter_nearest, repeat_disable;
uniform float zone_size_m = 12288.0;
uniform float wet_level = -30.0;         // мировая высота сырых низин, м

// клипмап: уровень кольца этого меша (0 — центр 2 м ... 6 — кольцо 128 м)
instance uniform float clip_level = 0.0;

varying vec3 v_wpos;

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
	return vec3(0.225, 0.315, 0.120);               // луг
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

	// --- микронормали грунта вблизи (сантиметровая неровность) ---
	float nearf = 1.0 - smoothstep(15.0, 90.0, dist);
	vec3 n = gn;
	if (nearf > 0.001) {
		float me = 0.35;
		float amp = 0.075 * nearf;
		float mL = vnoise((v_wpos.xz + vec2(-me, 0.0)) * 2.1) + 0.5 * vnoise((v_wpos.xz + vec2(-me, 0.0)) * 7.3);
		float mR = vnoise((v_wpos.xz + vec2(me, 0.0)) * 2.1) + 0.5 * vnoise((v_wpos.xz + vec2(me, 0.0)) * 7.3);
		float mN = vnoise((v_wpos.xz + vec2(0.0, -me)) * 2.1) + 0.5 * vnoise((v_wpos.xz + vec2(0.0, -me)) * 7.3);
		float mS = vnoise((v_wpos.xz + vec2(0.0, me)) * 2.1) + 0.5 * vnoise((v_wpos.xz + vec2(0.0, me)) * 7.3);
		vec3 mn = normalize(vec3((mL - mR) * amp, 2.0 * me, (mN - mS) * amp));
		n = normalize(vec3(gn.x + mn.x, gn.y * mn.y, gn.z + mn.z));
	}

	// --- зона (реальное землепользование), размытая граница ---
	vec2 zuv = (v_wpos.xz + vec2(zone_size_m * 0.5)) / zone_size_m;
	vec2 j = (vec2(hash12(v_wpos.xz * 0.37), hash12(v_wpos.xz * 0.53 + 7.0)) - 0.5)
		* (14.0 / zone_size_m);
	int z = int(texture(zone_tex, clamp(zuv + j, 0.0, 1.0)).r * 255.0 + 0.5);
	vec3 col = zone_tint(z);

	// склоны — грунт; низины — сырость; пятнистость двух масштабов
	float slope = clamp((1.0 - gn.y) * 3.5, 0.0, 1.0);
	col = mix(col, vec3(0.32, 0.25, 0.16), slope);
	float wet = clamp((wet_level - hC) / 6.0, 0.0, 1.0);
	col = mix(col, vec3(0.15, 0.18, 0.15), wet * 0.8);
	float broad = vnoise(v_wpos.xz * 0.045);
	float fine = vnoise(v_wpos.xz * 1.35);
	col *= 1.0 - 0.16 * broad - 0.12 * fine * nearf;

	ALBEDO = col;
	ROUGHNESS = 1.0;
	METALLIC = 0.0;
	SPECULAR = 0.0;
	NORMAL = normalize((VIEW_MATRIX * vec4(n, 0.0)).xyz);
}
