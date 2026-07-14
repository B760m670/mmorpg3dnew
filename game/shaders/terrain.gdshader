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
uniform vec4 tiles = vec4(0.5, 0.55, 0.5, 0.6);      // повторов на метр для слоёв 0..3
uniform vec4 rough = vec4(0.92, 0.95, 0.9, 0.95);
uniform float macro_mix = 0.4;                        // доля крупномасштабной вариации
uniform float detail_str = 1.0;                       // сила микрорельефа (нормаль)

varying vec3 wpos;
varying vec4 wcol;

void vertex() {
	wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	wcol = COLOR;
}

// смешивание альбедо слоя в ДВУХ масштабах: мелкий (зерно) + крупный (пятна),
// чтобы вблизи была резкая детализация, а вдали не читалась плитка-повтор
vec3 layer_alb(sampler2D t, vec2 uv) {
	vec3 near = texture(t, uv).rgb;
	vec3 macro = texture(t, uv * 0.14).rgb;
	return mix(near, near * (0.6 + 0.8 * macro), macro_mix);
}

void fragment() {
	float s = wcol.r + wcol.g + wcol.b + wcol.a;
	vec4 w = s > 0.001 ? wcol / s : vec4(1.0, 0.0, 0.0, 0.0);
	vec2 u0 = wpos.xz * tiles.x; vec2 u1 = wpos.xz * tiles.y;
	vec2 u2 = wpos.xz * tiles.z; vec2 u3 = wpos.xz * tiles.w;
	ALBEDO = layer_alb(l0_alb, u0) * w.r + layer_alb(l1_alb, u1) * w.g
	       + layer_alb(l2_alb, u2) * w.b + layer_alb(l3_alb, u3) * w.a;
	vec3 n = texture(l0_nrm, u0).rgb * w.r + texture(l1_nrm, u1).rgb * w.g
	       + texture(l2_nrm, u2).rgb * w.b + texture(l3_nrm, u3).rgb * w.a;
	// два уровня микрорельефа: комья (средняя частота) + зерно (высокая)
	vec3 nb = normalize(n * 2.0 - 1.0);
	vec3 d1 = texture(l2_nrm, wpos.xz * 2.5).rgb * 2.0 - 1.0;
	vec3 d2 = texture(l0_nrm, wpos.xz * 7.0).rgb * 2.0 - 1.0;
	vec3 nrm = normalize(vec3(nb.xy + (d1.xy * 0.9 + d2.xy * 0.5) * detail_str, nb.z));
	NORMAL_MAP = nrm * 0.5 + 0.5;
	NORMAL_MAP_DEPTH = 1.35 * detail_str;
	ROUGHNESS = dot(w, rough);
	SPECULAR = 0.2;
	METALLIC = 0.0;
}
