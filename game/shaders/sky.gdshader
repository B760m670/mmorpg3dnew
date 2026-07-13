shader_type sky;
render_mode use_debanding;
// Физическое небо: одиночное рассеяние Рэлея (голубизна) и Ми (гало солнца,
// дымка) по реальной модели атмосферы Земли; диск солнца; процедурные облака
// (FBM), освещённые солнцем; ночное потемнение и звёзды. Солнце берётся из
// первого DirectionalLight3D (LIGHT0_DIRECTION) — небо и свет физически связаны.

// --- атмосфера ---
uniform float atmo_energy = 20.0;
uniform vec3 rayleigh_beta = vec3(5.5e-6, 13.0e-6, 22.4e-6); // синий рассеивается сильнее
uniform float mie_beta = 21e-6;
uniform float mie_g : hint_range(0.0, 0.999) = 0.76;         // вытянутость гало вперёд
uniform float rayleigh_scale = 8000.0;
uniform float mie_scale = 1200.0;
uniform float planet_radius = 6371000.0;
uniform float atmo_radius = 6471000.0;
uniform float sun_disk_size : hint_range(0.0, 0.2) = 0.006;

// --- облака ---
uniform float cloud_coverage : hint_range(0.0, 1.0) = 0.48;
uniform float cloud_height = 1800.0;
uniform float cloud_scale = 0.00035;
uniform vec2 cloud_wind = vec2(0.006, 0.002);
uniform float cloud_softness : hint_range(0.01, 0.5) = 0.22;
uniform vec3 cloud_bright : source_color = vec3(1.0, 0.98, 0.95);
uniform vec3 cloud_dark : source_color = vec3(0.55, 0.58, 0.66);

// --- ночь ---
uniform vec3 night_color : source_color = vec3(0.01, 0.015, 0.03);
uniform float star_density : hint_range(0.0, 1.0) = 0.5;

// пересечение луча со сферой (атмосферой)
vec2 ray_sphere(vec3 o, vec3 d, float r) {
	float b = dot(o, d);
	float c = dot(o, o) - r*r;
	float h = b*b - c;
	if (h < 0.0) return vec2(1e9, -1e9);
	h = sqrt(h);
	return vec2(-b - h, -b + h);
}

// рассеяние в атмосфере (одиночное, рэймарч)
vec3 atmosphere(vec3 dir, vec3 sun_dir) {
	const int STEPS = 12;
	const int LIGHT_STEPS = 6;
	vec3 origin = vec3(0.0, planet_radius + 1000.0, 0.0);
	vec2 t = ray_sphere(origin, dir, atmo_radius);
	if (t.y < 0.0) return vec3(0.0);
	float seg = (t.y - max(t.x, 0.0)) / float(STEPS);
	float tcur = max(t.x, 0.0);

	float mu = dot(dir, sun_dir);
	float phase_r = 3.0/(16.0*PI) * (1.0 + mu*mu);
	float g = mie_g;
	float phase_m = 3.0/(8.0*PI) * ((1.0-g*g)*(1.0+mu*mu)) /
		((2.0+g*g)*pow(1.0 + g*g - 2.0*g*mu, 1.5));

	vec3 sum_r = vec3(0.0);
	vec3 sum_m = vec3(0.0);
	float od_r = 0.0;
	float od_m = 0.0;

	for (int i = 0; i < STEPS; i++) {
		vec3 p = origin + dir * (tcur + seg*0.5);
		float h = length(p) - planet_radius;
		float hr = exp(-h/rayleigh_scale) * seg;
		float hm = exp(-h/mie_scale) * seg;
		od_r += hr; od_m += hm;
		// оптическая глубина к солнцу
		vec2 tl = ray_sphere(p, sun_dir, atmo_radius);
		float segl = tl.y / float(LIGHT_STEPS);
		float odl_r = 0.0; float odl_m = 0.0;
		float tl_cur = 0.0;
		for (int j = 0; j < LIGHT_STEPS; j++) {
			vec3 pl = p + sun_dir * (tl_cur + segl*0.5);
			float hl = length(pl) - planet_radius;
			odl_r += exp(-hl/rayleigh_scale) * segl;
			odl_m += exp(-hl/mie_scale) * segl;
			tl_cur += segl;
		}
		vec3 tau = rayleigh_beta*(od_r+odl_r) + mie_beta*1.1*(od_m+odl_m);
		vec3 att = exp(-tau);
		sum_r += att * hr;
		sum_m += att * hm;
		tcur += seg;
	}
	return atmo_energy * (phase_r * rayleigh_beta * sum_r + phase_m * mie_beta * sum_m);
}

// --- шум для облаков ---
float hash(vec2 p) {
	p = fract(p * vec2(123.34, 456.21));
	p += dot(p, p + 45.32);
	return fract(p.x * p.y);
}
float vnoise(vec2 p) {
	vec2 i = floor(p); vec2 f = fract(p);
	f = f*f*(3.0-2.0*f);
	float a = hash(i), b = hash(i+vec2(1,0)), c = hash(i+vec2(0,1)), d = hash(i+vec2(1,1));
	return mix(mix(a,b,f.x), mix(c,d,f.x), f.y);
}
float fbm(vec2 p) {
	float v = 0.0, a = 0.5;
	for (int i = 0; i < 5; i++) { v += a*vnoise(p); p *= 2.03; a *= 0.5; }
	return v;
}

void sky() {
	vec3 dir = EYEDIR;
	vec3 sun_dir = LIGHT0_DIRECTION;          // в небесном шейдере уже направление НА солнце
	float sun_up = clamp(sun_dir.y*4.0 + 0.1, 0.0, 1.0);

	vec3 col = atmosphere(dir, sun_dir);

	// диск солнца
	float sd = dot(dir, sun_dir);
	float disk = smoothstep(1.0 - sun_disk_size, 1.0 - sun_disk_size*0.3, sd);
	col += disk * LIGHT0_COLOR.rgb * LIGHT0_ENERGY * 12.0;

	// ночь: если солнце под горизонтом — потемнение и звёзды
	col = mix(night_color, col, sun_up);
	if (sun_up < 0.35 && dir.y > 0.0) {
		vec2 sc = dir.xz / max(dir.y, 0.08) * 60.0;
		float st = step(1.0 - star_density*0.02, hash(floor(sc)));
		col += st * (0.35 - sun_up) * vec3(0.9, 0.95, 1.0);
	}

	// облака (верхняя полусфера)
	if (dir.y > 0.02) {
		float dist = cloud_height / dir.y;
		vec2 cp = dir.xz * dist * cloud_scale + cloud_wind * TIME;
		float base = fbm(cp * 0.7);
		float detail = fbm(cp * 2.6 + 3.7);
		float d = base*0.65 + detail*0.35;
		float cov = smoothstep(cloud_coverage, cloud_coverage + cloud_softness, d);
		// затухание облаков к горизонту
		cov *= smoothstep(0.02, 0.25, dir.y);
		if (cov > 0.001) {
			// самозатенение: проба плотности в сторону солнца
			vec2 cps = cp + sun_dir.xz * 0.04;
			float ds = smoothstep(cloud_coverage, cloud_coverage + cloud_softness, fbm(cps*0.7)*0.65 + fbm(cps*2.6+3.7)*0.35);
			float light = clamp(1.0 - (ds - cov)*2.5, 0.25, 1.0);
			vec3 ccol = mix(cloud_dark, cloud_bright, light) * sun_up;
			// серебристая кромка у солнца
			ccol += pow(max(sd, 0.0), 8.0) * light * 0.6 * LIGHT0_COLOR.rgb;
			col = mix(col, ccol, cov * clamp(sun_up*1.5, 0.15, 1.0));
		}
	}

	COLOR = col;
}
