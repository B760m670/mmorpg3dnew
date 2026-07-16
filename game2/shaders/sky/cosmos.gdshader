shader_type sky;
// Космос — КОНТЕЙНЕР мира: чёрное пространство со звёздами. Земля стоит В нём.
// ВРЕМЕННО звёзды процедурные (по направлению взгляда); настоящий каталог звёзд
// (Hipparcos/Yale) на небесной сфере со звёздным временем — следующий слой.

uniform float density = 0.006;      // доля ячеек направления со звездой
uniform float brightness = 1.4;

float hash(vec3 p) {
	p = fract(p * vec3(443.897, 441.423, 437.195));
	p += dot(p, p.yzx + 19.19);
	return fract((p.x + p.y) * p.z);
}

void sky() {
	vec3 d = normalize(EYEDIR);
	vec3 cell = floor(d * 320.0);
	float h = hash(cell);
	float star = step(1.0 - density, h);
	float mag = hash(cell + 7.0);                 // разная яркость звёзд
	float b = star * mix(0.25, 1.0, mag) * brightness;
	COLOR = vec3(b);
}
