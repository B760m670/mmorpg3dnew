shader_type spatial;
render_mode diffuse_burley;
// Грунт: смешивает до 4 типов почвы из библиотеки (world/textures/ground) по
// вершинному цвету (R,G,B,A — веса слоёв). Тайлинг по мировым координатам XZ.
// Слои назначаются из world.gd (луг / лесная подстилка / тропа / пашня и т.п.),
// поэтому один шейдер применим к любой области — меняются лишь текстуры и веса.

uniform sampler2D l0_alb : source_color, filter_linear_mipmap, repeat_enable;
uniform sampler2D l0_nrm : hint_normal, filter_linear_mipmap, repeat_enable;
uniform sampler2D l1_alb : source_color, filter_linear_mipmap, repeat_enable;
uniform sampler2D l1_nrm : hint_normal, filter_linear_mipmap, repeat_enable;
uniform sampler2D l2_alb : source_color, filter_linear_mipmap, repeat_enable;
uniform sampler2D l2_nrm : hint_normal, filter_linear_mipmap, repeat_enable;
uniform sampler2D l3_alb : source_color, filter_linear_mipmap, repeat_enable;
uniform sampler2D l3_nrm : hint_normal, filter_linear_mipmap, repeat_enable;
uniform vec4 tiles = vec4(0.14, 0.16, 0.16, 0.2);   // повторов на метр для слоёв 0..3
uniform vec4 rough = vec4(0.92, 0.95, 0.9, 0.95);

varying vec3 wpos;
varying vec4 wcol;

void vertex() {
	wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	wcol = COLOR;
}

void fragment() {
	float s = wcol.r + wcol.g + wcol.b + wcol.a;
	vec4 w = s > 0.001 ? wcol / s : vec4(1.0, 0.0, 0.0, 0.0);
	vec2 u0 = wpos.xz * tiles.x; vec2 u1 = wpos.xz * tiles.y;
	vec2 u2 = wpos.xz * tiles.z; vec2 u3 = wpos.xz * tiles.w;
	ALBEDO = texture(l0_alb, u0).rgb * w.r + texture(l1_alb, u1).rgb * w.g
	       + texture(l2_alb, u2).rgb * w.b + texture(l3_alb, u3).rgb * w.a;
	vec3 n = texture(l0_nrm, u0).rgb * w.r + texture(l1_nrm, u1).rgb * w.g
	       + texture(l2_nrm, u2).rgb * w.b + texture(l3_nrm, u3).rgb * w.a;
	// мелкая детализация вблизи: та же нормаль на высокой частоте (шероховатость грунта)
	vec3 nd = texture(l0_nrm, wpos.xz * 1.3).rgb;
	NORMAL_MAP = normalize(n + (nd - vec3(0.5)) * 0.7);
	NORMAL_MAP_DEPTH = 1.0;
	ROUGHNESS = dot(w, rough);
	SPECULAR = 0.2;
	METALLIC = 0.0;
}
