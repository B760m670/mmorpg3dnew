#[compute]
#version 450

// Кино-пост (Ф0), КАНОНИЧНЫЙ минимум для Metal: один проход, запись НА МЕСТЕ,
// без scratch-текстур и copy — только documented-путь CompositorEffect.
// Хроматика читает соседей из того же образа (read-only, без гонки на запись).

layout(local_size_x = 8, local_size_y = 8, local_size_z = 1) in;

layout(rgba16f, set = 0, binding = 0) uniform image2D color_image;

layout(push_constant, std430) uniform Params {
	vec2 raster_size;
	float time;
	float grain;
	float vignette;
	float ca;
	float pad0;
	float pad1;
} p;

float hash13(vec3 v) {
	v = fract(v * 0.1031);
	v += dot(v, v.zyx + 31.32);
	return fract((v.x + v.y) * v.z);
}

void main() {
	ivec2 uv = ivec2(gl_GlobalInvocationID.xy);
	ivec2 size = ivec2(p.raster_size);
	if (uv.x >= size.x || uv.y >= size.y) {
		return;
	}
	vec2 fuv = (vec2(uv) + 0.5) / p.raster_size;
	vec2 c = fuv - 0.5;
	float r2 = dot(c, c);

	vec4 base = imageLoad(color_image, uv);
	vec3 col = base.rgb;

	// лёгкая хроматика: соседние пиксели (чтение из того же образа — безопасно)
	if (p.ca > 0.0) {
		vec2 dir = (r2 > 1e-6) ? normalize(c) : vec2(0.0);
		ivec2 sh = ivec2(round(dir * (p.ca * r2 * 2.0)));
		float cr = imageLoad(color_image, clamp(uv + sh, ivec2(0), size - 1)).r;
		float cb = imageLoad(color_image, clamp(uv - sh, ivec2(0), size - 1)).b;
		col = vec3(cr, base.g, cb);
	}

	// виньетка
	col *= 1.0 - p.vignette * smoothstep(0.08, 0.5, r2);

	// плёночное зерно (сильнее в тенях)
	float g = hash13(vec3(vec2(uv), fract(p.time) * 977.0)) - 0.5;
	float lum = dot(col, vec3(0.299, 0.587, 0.114));
	col += g * p.grain * (1.0 - clamp(lum, 0.0, 1.0) * 0.6);

	imageStore(color_image, uv, vec4(max(col, vec3(0.0)), base.a));
}
