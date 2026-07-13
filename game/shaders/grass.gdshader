shader_type spatial;
render_mode cull_disabled, diffuse_burley;
// Трава: настоящие травинки (геометрия) через MultiMesh. Ветер качает верхушки,
// свет просвечивает лист (BACKLIGHT), цвет — из вершинного цвета (тёмный низ →
// светлый кончик). Двусторонняя. Рассчитано на сильный мобильный GPU (A18 Pro).

uniform float wind_strength = 0.10;
uniform float wind_speed = 1.7;
uniform float blade_height = 0.34;
uniform vec3 backlight_tint : source_color = vec3(0.12, 0.22, 0.06);

void vertex() {
	float hfac = clamp(VERTEX.y / blade_height, 0.0, 1.0);   // 0 у корня, 1 у кончика
	vec3 wp = (MODEL_MATRIX * vec4(0.0, 0.0, 0.0, 1.0)).xyz; // позиция пучка в мире
	float phase = wp.x * 0.25 + wp.z * 0.25 + TIME * wind_speed;
	float gust = 0.6 + 0.4 * sin(TIME * 0.6 + wp.x * 0.05);
	VERTEX.x += sin(phase) * wind_strength * hfac * gust;
	VERTEX.z += cos(phase * 0.8) * wind_strength * hfac * 0.6 * gust;
}

void fragment() {
	ALBEDO = COLOR.rgb;
	ROUGHNESS = 0.6;
	SPECULAR = 0.2;
	BACKLIGHT = backlight_tint;    // свет сквозь лист (Forward+)
}
