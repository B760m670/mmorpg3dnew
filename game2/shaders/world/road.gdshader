shader_type spatial;
// ДОРОГА — лента на рельефе. Высота — из той же текстуры высот, что у
// клипмап-террейна, mip выбирается так же (по шахматному удалению от
// камеры): лента лежит на ВИДИМОЙ поверхности и вблизи, и на сглаженной
// дали. Эпоха 1894: грунт/макадам — колеи от колёс, тёмные обочины,
// никакой разметки. Цвет класса дороги — в вершинном цвете меша.
render_mode diffuse_burley, specular_disabled, cull_disabled;

uniform sampler2D height_tex : filter_linear_mipmap, repeat_disable;
uniform float dem_half = 8192.0;

varying vec2 v_uv;

void vertex() {
	vec2 wxz = VERTEX.xz;
	vec2 huv = (wxz + vec2(dem_half)) / (2.0 * dem_half);
	// уровень клипмапа, под которым лежит эта точка (как в terrain.gdshader)
	vec2 dxz = abs(wxz - CAMERA_POSITION_WORLD.xz);
	float cheb = max(max(dxz.x, dxz.y), 130.0);
	float lv = clamp(ceil(log2(cheb / 128.0)), 0.0, 6.0);
	float lod = max(0.0, lv - 4.0);
	float cell = 2.0 * exp2(lv);
	// подъём растёт с ячейкой уровня: страховка от прорезания сквозь
	// сглаженный дальний рельеф (вблизи 10 см — стык с землёй плотный)
	VERTEX.y = textureLod(height_tex, huv, lod).r + 0.10 + cell * 0.03;
	v_uv = UV;
}

float hash12(vec2 p) {
	p = fract(p * vec2(0.1031, 0.1030));
	p += dot(p, p.yx + 33.33);
	return fract((p.x + p.y) * p.x);
}

void fragment() {
	float x = v_uv.x;
	// две колеи от колёс (тележные оси ~1.5 м) + утоптанный центр,
	// края мягко темнеют к обочине
	float rut = exp(-pow((abs(x - 0.5) - 0.24) * 8.5, 2.0));
	float edge = smoothstep(0.0, 0.12, min(x, 1.0 - x));
	vec3 col = COLOR.rgb * (1.0 - 0.20 * rut) * mix(0.76, 1.0, edge);
	// зерно грунта (не даёт ленте выглядеть пластиком)
	float g = hash12(floor(vec2(v_uv.y * 1.7, x * 7.0)) * 1.13);
	col *= 0.93 + 0.12 * g;
	ALBEDO = col;
	ROUGHNESS = 1.0;
	METALLIC = 0.0;
	SPECULAR = 0.0;
}
