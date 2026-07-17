shader_type spatial;
// Террейн-материал, шаг 2 генплана: поверхность красится по РЕАЛЬНЫМ зонам
// землепользования (zone_tex из data/real: луг/парк/лес/поля/город/вода).
// Вершинный COLOR несёт атрибуты рельефа: r=крутизна, g=низина(сырость), b=шум.
// Диффуз без зеркалки (нет белой каймы у горизонта). С расстоянием нормаль
// сглаживается к вертикали — дальний рельеф не мерцает гранями.
// Зоны пока тонируют базовый цвет; настоящие PBR-наборы текстур лягут поверх
// этой же карты зон следующим этапом.
render_mode diffuse_burley, specular_disabled, cull_back;

uniform sampler2D zone_tex : filter_nearest;
uniform float zone_size_m = 12288.0;
uniform float flatten_near = 120.0;
uniform float flatten_far = 900.0;

varying vec3 v_attr;
varying vec3 v_wnormal;
varying vec3 v_wpos;

void vertex() {
	v_attr = COLOR.rgb;
	v_wnormal = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
	v_wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

float hash12(vec2 p) {
	p = fract(p * vec2(0.1031, 0.1030));
	p += dot(p, p.yx + 33.33);
	return fract((p.x + p.y) * p.x);
}

vec3 zone_tint(int z) {
	if (z == 1) return vec3(0.150, 0.310, 0.095);   // парк: сочная зелень
	if (z == 2) return vec3(0.080, 0.185, 0.075);   // лес: тёмная хвоя
	if (z == 3) return vec3(0.400, 0.345, 0.135);   // поля: соломенный
	if (z == 4) return vec3(0.330, 0.290, 0.235);   // город: пыльный грунт
	if (z == 5) return vec3(0.100, 0.140, 0.120);   // берег/дно: тёмный сырой
	return vec3(0.225, 0.315, 0.120);               // луг
}

void fragment() {
	vec2 uv = (v_wpos.xz + vec2(zone_size_m * 0.5)) / zone_size_m;
	// стохастическое размытие границ зон (~±7 м), чтобы не было резких швов
	vec2 j = (vec2(hash12(v_wpos.xz * 0.37), hash12(v_wpos.xz * 0.53 + 7.0)) - 0.5)
		* (14.0 / zone_size_m);
	int z = int(texture(zone_tex, clamp(uv + j, 0.0, 1.0)).r * 255.0 + 0.5);
	vec3 col = zone_tint(z);
	col = mix(col, vec3(0.32, 0.25, 0.16), v_attr.r);          // склоны — грунт
	col = mix(col, vec3(0.15, 0.18, 0.15), v_attr.g * 0.8);    // низины — сырость
	col *= 1.0 - 0.18 * v_attr.b;                               // пятнистость
	ALBEDO = col;
	ROUGHNESS = 1.0;
	METALLIC = 0.0;
	SPECULAR = 0.0;
	float dist = length(VERTEX);
	float f = smoothstep(flatten_near, flatten_far, dist);
	vec3 wn = normalize(mix(v_wnormal, vec3(0.0, 1.0, 0.0), f));
	NORMAL = normalize((VIEW_MATRIX * vec4(wn, 0.0)).xyz);
}
