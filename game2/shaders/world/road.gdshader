shader_type spatial;
// ДОРОГА — лента на рельефе. Высота — из той же текстуры высот, что у
// клипмап-террейна, mip выбирается так же (по шахматному удалению от
// камеры): лента лежит на ВИДИМОЙ поверхности и вблизи, и на сглаженной
// дали. Эпоха 1894: грунт/макадам — колеи от колёс, тёмные обочины,
// никакой разметки. Цвет класса дороги — в вершинном цвете меша.
render_mode diffuse_burley, specular_disabled, cull_disabled;

uniform sampler2D height_tex : filter_linear_mipmap, repeat_disable;
uniform float dem_half = 8192.0;

// покрытия (синтез tools/make_materials.py): 0 грунт, 1 макадам, 2 булыжник
uniform sampler2D dirt_alb : filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D dirt_nr : filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D mac_alb : filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D mac_nr : filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D cob_alb : filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D cob_nr : filter_linear_mipmap_anisotropic, repeat_enable;
uniform float detail_tile_m = 2.0;

varying vec2 v_uv;
varying vec2 v_mat;    // x: id покрытия, y: ширина ленты, м

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
	v_mat = UV2;
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
	// покрытие эпохи: метраж поперёк — из ширины ленты (UV2.y)
	vec2 duv = vec2(x * v_mat.y, v_uv.y) / detail_tile_m;
	vec3 da; vec4 dn;
	if (v_mat.x > 1.5) { da = texture(cob_alb, duv).rgb; dn = texture(cob_nr, duv); }
	else if (v_mat.x > 0.5) { da = texture(mac_alb, duv).rgb; dn = texture(mac_nr, duv); }
	else { da = texture(dirt_alb, duv).rgb; dn = texture(dirt_nr, duv); }
	col *= da * 2.0;
	vec3 tn = vec3(dn.x * 2.0 - 1.0, 0.0, dn.y * 2.0 - 1.0);
	// на дали фактура гаснет (мип уводит нормаль в вертикаль сам)
	float detf = 1.0 - smoothstep(80.0, 300.0, length(VERTEX));
	vec3 n = normalize(vec3(tn.x * 0.8 * detf, 1.0, tn.z * 0.8 * detf));
	NORMAL = normalize((VIEW_MATRIX * vec4(n, 0.0)).xyz);
	// зерно грунта (не даёт ленте выглядеть пластиком)
	float g = hash12(floor(vec2(v_uv.y * 1.7, x * 7.0)) * 1.13);
	col *= 0.96 + 0.07 * g;
	ALBEDO = col;
	ROUGHNESS = dn.a;
	METALLIC = 0.0;
	SPECULAR = 0.0;
}
