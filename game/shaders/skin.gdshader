shader_type spatial;
render_mode diffuse_burley, specular_schlick_ggx;
// Кожа с имитацией подповерхностного рассеивания (SSS) для мобильного рендера:
// свет «заворачивается» за терминатор (wrap lighting), а у самого терминатора
// добавляется тёплое просвечивание — как кровь под тонкой кожей.

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap;
uniform vec3 sss_tint : source_color = vec3(0.85, 0.42, 0.35);
uniform float sss_strength : hint_range(0.0, 1.0) = 0.45;
uniform float skin_roughness : hint_range(0.0, 1.0) = 0.52;
uniform float skin_specular : hint_range(0.0, 1.0) = 0.42;

void fragment() {
	ALBEDO = texture(albedo_tex, UV).rgb;
	ROUGHNESS = skin_roughness;
	SPECULAR = skin_specular;
	METALLIC = 0.0;
}

void light() {
	float ndl = dot(NORMAL, LIGHT);
	// wrap-освещение: смягчает терминатор, свет проникает «под кожу»
	float wrap = clamp((ndl + sss_strength) / (1.0 + sss_strength), 0.0, 1.0);
	vec3 diff = ALBEDO * LIGHT_COLOR * ATTENUATION * wrap;
	// тёплое просвечивание у края света (имитация рассеяния в тканях)
	float rim = clamp(1.0 - abs(ndl), 0.0, 1.0);
	vec3 sss = sss_tint * rim * sss_strength * ALBEDO * LIGHT_COLOR * ATTENUATION;
	DIFFUSE_LIGHT += diff + sss;
	// мягкий кожный блик (Blinn-Phong), иначе при своём light() specular пропадает
	vec3 half_v = normalize(VIEW + LIGHT);
	float ndh = max(dot(NORMAL, half_v), 0.0);
	float spec = pow(ndh, mix(8.0, 48.0, 1.0 - skin_roughness)) * skin_specular;
	SPECULAR_LIGHT += spec * LIGHT_COLOR * ATTENUATION * max(ndl, 0.0);
}
