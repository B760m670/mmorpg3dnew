#[compute]
#version 450

// Кино-пост (Ф0): хроматическая аберрация + виньетка + плёночное зерно.
// Работает ПОСЛЕ тонемапа (post-transparent), как объектив и плёнка камеры.

layout(local_size_x = 8, local_size_y = 8, local_size_z = 1) in;

layout(rgba16f, set = 0, binding = 0) uniform restrict image2D color_image;
layout(rgba16f, set = 0, binding = 1) uniform restrict image2D src_image;

layout(push_constant, std430) uniform Params {
	vec2 raster_size;   // ширина/высота кадра
	float time;         // секунды — анимация зерна
	float grain;        // сила зерна (0..~0.08)
	float vignette;     // сила виньетки (0..~0.45)
	float ca;           // хроматическая аберрация в пикселях у края (0..~2.5)
	float mode;        // 0 = проход-копия, 1 = эффект
	float pad1;
} p;

// хэш для зерна (без текстур)
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
	if (p.mode < 0.5) {                                // проход-копия
		imageStore(src_image, uv, imageLoad(color_image, uv));
		return;
	}
	vec2 fuv = (vec2(uv) + 0.5) / p.raster_size;      // 0..1
	vec2 c = fuv - 0.5;
	float r2 = dot(c, c);                              // 0 в центре, 0.5 в углу

	// --- хроматическая аберрация: R и B расходятся радиально к краям ---
	vec2 dir = (r2 > 1e-6) ? normalize(c) : vec2(0.0);
	float shift = p.ca * r2 * 2.0;                     // пиксели смещения
	// читаем ТОЛЬКО из копии кадра (src) — иначе in-place каскад в углах
	ivec2 uv_r = clamp(uv + ivec2(round(dir * shift)), ivec2(0), size - 1);
	ivec2 uv_b = clamp(uv - ivec2(round(dir * shift)), ivec2(0), size - 1);
	float cr = imageLoad(src_image, uv_r).r;
	vec4 base = imageLoad(src_image, uv);
	float cb = imageLoad(src_image, uv_b).b;
	vec3 col = vec3(cr, base.g, cb);

	// --- виньетка (мягкая, кино-объектив) ---
	col *= 1.0 - p.vignette * smoothstep(0.08, 0.5, r2);

	// --- плёночное зерно: яркостное, сильнее в тенях ---
	float g = hash13(vec3(vec2(uv), fract(p.time) * 977.0)) - 0.5;
	float lum = dot(col, vec3(0.299, 0.587, 0.114));
	col += g * p.grain * (1.0 - clamp(lum, 0.0, 1.0) * 0.6);

	imageStore(color_image, uv, vec4(max(col, vec3(0.0)), base.a));
}
