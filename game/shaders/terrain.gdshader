shader_type spatial;
render_mode diffuse_burley, specular_schlick_ggx;
// Грунт Гатчины: смешивает три тайловых PBR-материала (трава/земля/брусчатка)
// по вершинному цвету (R=трава, G=земля, B=брусчатка). Тайлинг по мировым
// координатам XZ — без растяжения на больших поверхностях.

uniform sampler2D grass_alb : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D grass_nrm : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D dirt_alb : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D dirt_nrm : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D cobble_alb : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D cobble_nrm : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform float tile_grass = 0.18;   // повторов на метр
uniform float tile_dirt = 0.22;
uniform float tile_cobble = 0.6;

varying vec3 world_pos;
varying vec3 vcol;

void vertex() {
	world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	vcol = COLOR.rgb;
}

void fragment() {
	vec2 uvg = world_pos.xz * tile_grass;
	vec2 uvd = world_pos.xz * tile_dirt;
	vec2 uvc = world_pos.xz * tile_cobble;
	vec3 w = vcol / max(vcol.r + vcol.g + vcol.b, 0.001);
	vec3 alb = texture(grass_alb, uvg).rgb * w.r
	         + texture(dirt_alb, uvd).rgb * w.g
	         + texture(cobble_alb, uvc).rgb * w.b;
	vec3 nrm = texture(grass_nrm, uvg).rgb * w.r
	         + texture(dirt_nrm, uvd).rgb * w.g
	         + texture(cobble_nrm, uvc).rgb * w.b;
	ALBEDO = alb;
	NORMAL_MAP = nrm;
	NORMAL_MAP_DEPTH = 0.35;            // слабый рельеф — без муара тайлов на равнине
	ROUGHNESS = mix(0.95, 0.7, w.b);   // брусчатка чуть глаже травы
	SPECULAR = 0.25;
	METALLIC = 0.0;
}
