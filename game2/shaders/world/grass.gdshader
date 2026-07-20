shader_type spatial;
// ТРАВА — лезвия чистой геометрией. Техники по публичному методу Ghost of
// Tsushima (GDC), реализация своя; изучен открытый разбор 2Retr0/GodotGrass:
//  · КОГЕРЕНТНОЕ поле ветра — порывы БЕГУТ по миру (не пофазно на месте);
//    кончик трясётся сильнее и с задержкой по высоте (турбулентность);
//  · SSS-ПРОСВЕТ в light() — солнце светит сквозь лист к наблюдателю
//    (золотой час на просвет — то, ради чего трава «оживает»);
//  · градиент база→кончик + AO у корня + шероховатость кончика (блик росы).
// Нормаль — вертикаль (трава освещается как земля, иначе грани мерцают — урок
// GoT). View/дистанс-утолщение для дальнего покрова — следующий шаг (нужен
// model-space; сейчас world_vertex_coords).
render_mode diffuse_burley, specular_disabled, cull_disabled, world_vertex_coords;

uniform vec2 wind_dir = vec2(0.83, 0.55);   // базовое направление — мировое XZ
uniform float wind_amp = 0.14;              // размах кончика, м
uniform float fade_start = 70.0;
uniform float fade_end = 105.0;
uniform vec3 sss_color : source_color = vec3(1.0, 0.75, 0.30);  // тёплый просвет

varying float v_h;   // доля высоты лезвия (0 корень — 1 кончик)

void vertex() {
	v_h = UV.y;
	vec3 root = MODEL_MATRIX[3].xyz;
	float dist = distance(root, CAMERA_POSITION_WORLD);
	// растворение вдали: куст сжимается к корню — исчезает без щелчка
	float keep = 1.0 - smoothstep(fade_start, fade_end, dist);
	VERTEX = root + (VERTEX - root) * keep;

	// КОГЕРЕНТНЫЙ ветер: фаза порыва зависит от мировой позиции И бежит во
	// времени (dot(root.xz)−TIME) — волны катятся по полю в одну сторону.
	float gust_phase = dot(root.xz, vec2(0.060, 0.045)) - TIME * 1.1;
	float gust = 0.55 + 0.45 * sin(gust_phase);
	// направление слегка колышется вокруг базового — живой, не жёсткий вектор
	vec2 wdir = normalize(wind_dir + 0.5 * vec2(sin(gust_phase * 0.5),
		cos(gust_phase * 0.4)));
	// турбулентность кончика: сдвиг фазы ∝ высоте — верх дрожит, корень стоит
	float turb = 0.30 * sin(TIME * 5.0 + dot(root.xz, vec2(0.5, 0.7))
		+ v_h * v_h * 3.5);
	float bend = v_h * v_h * wind_amp * (gust + turb) * keep;
	VERTEX.xz += wdir * bend;

	NORMAL = vec3(0.0, 1.0, 0.0);
}

void fragment() {
	float h = v_h;
	ALBEDO = COLOR.rgb * mix(0.35, 1.10, h);       // корень темнее — глубина покрова
	ALBEDO *= mix(0.55, 1.0, h * h);               // доп. AO у основания
	ROUGHNESS = mix(1.0, 0.55, h);                 // кончик глаже (тонкий блик)
	METALLIC = 0.0;
	SPECULAR = 0.0;
}

// СВЕТ: диффуз с не-нулевым дном (амбиент-отскок) + подповерхностный просвет —
// солнце за лезвием светит сквозь него к камере (backlit translucency).
void light() {
	float ndl = max(dot(NORMAL, LIGHT), 0.0);
	float diff = mix(0.25, 1.0, ndl);                     // не падает в 0
	float back = max(-dot(VIEW, LIGHT), 0.0);             // свет за листом → к нам
	float sss = pow(back, 2.0) * 0.6 * v_h;               // сильнее к кончику
	DIFFUSE_LIGHT += (vec3(diff) + sss * sss_color) * ATTENUATION * LIGHT_COLOR;
}
