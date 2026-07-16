shader_type spatial;
// Террейн-материал (основа Ф3.3). Диффуз без зеркалки. Цвет из вершинного COLOR.
// Ключевое: с расстоянием СГЛАЖИВАЕМ нормаль к вертикали — дальний рельеф на
// скользящем угле перестаёт «мерцать» яркими гранями (нормаль-алиасинг),
// уходит белая кайма у горизонта. Дёшево, без геометрического LOD.
render_mode diffuse_burley, specular_disabled, cull_back;

uniform float flatten_near = 120.0;
uniform float flatten_far = 900.0;

varying vec3 v_col;
varying vec3 v_wnormal;

void vertex() {
	v_col = COLOR.rgb;
	v_wnormal = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
}

void fragment() {
	ALBEDO = v_col;
	ROUGHNESS = 1.0;
	METALLIC = 0.0;
	SPECULAR = 0.0;
	// расстояние до камеры (view-space глубина)
	float dist = length(VERTEX);
	float f = smoothstep(flatten_near, flatten_far, dist);
	vec3 wn = normalize(mix(v_wnormal, vec3(0.0, 1.0, 0.0), f));
	NORMAL = normalize((VIEW_MATRIX * vec4(wn, 0.0)).xyz);
}
