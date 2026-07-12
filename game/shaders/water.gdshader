shader_type spatial;
render_mode diffuse_burley, specular_schlick_ggx, cull_disabled;
// Вода озёр: анимированные волны по нормалям, полупрозрачность, зеркальность.

uniform vec3 shallow : source_color = vec3(0.16, 0.34, 0.40);
uniform vec3 deep : source_color = vec3(0.03, 0.11, 0.19);
uniform float wave_speed = 0.35;
uniform float wave_scale = 0.055;

float wave(vec2 p, float t) {
	return sin(p.x*0.7 + t)*0.5 + sin(p.y*0.9 - t*1.3)*0.3 + sin((p.x+p.y)*0.5 + t*0.7)*0.2;
}

void fragment() {
	vec2 p = (INV_VIEW_MATRIX * vec4(VERTEX, 1.0)).xz;
	float t = TIME * wave_speed;
	float h = wave(p*wave_scale, t);
	vec2 dxy = vec2(
		wave((p+vec2(0.5,0.0))*wave_scale, t) - h,
		wave((p+vec2(0.0,0.5))*wave_scale, t) - h);
	NORMAL_MAP = normalize(vec3(dxy*0.8, 1.0))*0.5+0.5;
	ALBEDO = mix(deep, shallow, clamp(h*0.22+0.5, 0.0, 1.0));
	ROUGHNESS = 0.08;
	METALLIC = 0.0;
	SPECULAR = 0.9;
	ALPHA = 0.82;
}
