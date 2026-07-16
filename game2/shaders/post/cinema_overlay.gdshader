shader_type canvas_item;
// Кино-пост как ПОЛНОЭКРАННЫЙ оверлей (фрагмент-шейдер) — надёжен на любом
// бэкенде, включая Metal. Читает уже отрисованный кадр через screen-texture,
// накладывает хроматику, виньетку и плёночное зерно. Визуально неотличим от
// compute-варианта для этих эффектов.

uniform sampler2D screen_tex : hint_screen_texture, filter_linear;
uniform float grain = 0.022;
uniform float vignette = 0.28;
uniform float ca = 0.0016;   // хроматика в долях экрана
uniform float t = 0.0;       // время для анимации зерна

float hash(vec2 p) {
	p = fract(p * vec2(0.1031, 0.1030));
	p += dot(p, p.yx + 33.33);
	return fract((p.x + p.y) * p.x);
}

void fragment() {
	vec2 uv = SCREEN_UV;
	vec2 c = uv - 0.5;
	float r2 = dot(c, c);

	// хроматическая аберрация к краям
	vec2 dir = (r2 > 1e-6) ? normalize(c) : vec2(0.0);
	vec2 sh = dir * ca * r2 * 2.0;
	vec3 col;
	col.r = texture(screen_tex, uv + sh).r;
	col.g = texture(screen_tex, uv).g;
	col.b = texture(screen_tex, uv - sh).b;

	// виньетка
	col *= 1.0 - vignette * smoothstep(0.08, 0.5, r2);

	// плёночное зерно (сильнее в тенях)
	float g = hash(uv * vec2(1920.0, 1080.0) + fract(t) * 97.0) - 0.5;
	float lum = dot(col, vec3(0.299, 0.587, 0.114));
	col += g * grain * (1.0 - clamp(lum, 0.0, 1.0) * 0.6);

	COLOR = vec4(max(col, vec3(0.0)), 1.0);
}
