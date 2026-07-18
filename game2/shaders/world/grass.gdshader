shader_type spatial;
// ТРАВА — лезвия чистой геометрией (без альфа-текстур: ни сортировки,
// ни просветов на MSAA-свободном мобильном кадре). Ветер и растворение
// вдали — в вершинах. Нормаль — вертикаль: трава освещается как сама
// поверхность земли (иначе лезвия мерцают гранями на солнце — урок GoT).
// Корень темнее кончика — ложная глубина покрова (self-occlusion).
render_mode diffuse_burley, specular_disabled, cull_disabled, world_vertex_coords;

uniform vec2 wind_dir = vec2(0.83, 0.55);   // откуда дует — мировое XZ
uniform float wind_amp = 0.10;              // размах кончика, м
uniform float fade_start = 70.0;
uniform float fade_end = 105.0;

varying float v_h;   // доля высоты лезвия (0 корень — 1 кончик)

void vertex() {
	v_h = UV.y;
	vec3 root = MODEL_MATRIX[3].xyz;
	float dist = distance(root, CAMERA_POSITION_WORLD);
	// растворение вдали: куст сжимается к корню — исчезает без щелчка,
	// дальше цвет несёт сама земля (зонная краска совпадает по тону)
	float keep = 1.0 - smoothstep(fade_start, fade_end, dist);
	VERTEX = root + (VERTEX - root) * keep;
	// ветер: два наложенных колебания, фаза — от мировой позиции куста
	// (волны бегут по полю), гнётся верх ∝ h² (корень стоит)
	float ph = root.x * 0.53 + root.z * 0.71;
	float sway = sin(TIME * 1.9 + ph) + 0.45 * sin(TIME * 4.1 + ph * 1.7);
	float bend = v_h * v_h * wind_amp * (0.55 + 0.45 * sway) * keep;
	VERTEX.xz += wind_dir * bend;
	NORMAL = vec3(0.0, 1.0, 0.0);
}

void fragment() {
	// COLOR — цвет инстанса (зона × вариация куста)
	ALBEDO = COLOR.rgb * mix(0.45, 1.08, v_h);
	ROUGHNESS = 1.0;
	METALLIC = 0.0;
	SPECULAR = 0.0;
}
