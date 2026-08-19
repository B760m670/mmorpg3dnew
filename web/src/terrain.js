// РЕЛЬЕФ СРЕЗА. Меш из поля высот, снятого той же функцией, что в игре.
//
// МОКРАЯ ПОЛОСА У ВОДЫ ЖИВЁТ ЗДЕСЬ, А НЕ В ВОДЕ. Это была одна из трёх причин,
// по которым наше озеро читалось плитой: у него не было берега. Берег — не
// свойство воды, это свойство ЗЕМЛИ рядом с водой: мокрый песок темнее и
// глянцевее сухого, и полоса эта шириной в десятки сантиметров. Земля знает
// урез (он приехал в срезе), поэтому считает мокроту сама.
import * as THREE from 'three';

const VERT = /* glsl */`
varying vec3 vWorld;
varying float vWet;      // 0 сухо .. 1 под водой
varying float vDepth;    // на сколько метров земля ВЫШЕ уреза
attribute float wet;
attribute float depth;
void main() {
	vWorld = position;
	vWet = wet;
	vDepth = depth;
	gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`;

const FRAG = /* glsl */`
precision highp float;
varying vec3 vWorld;
varying float vWet;
varying float vDepth;
uniform vec3 sunDir;
uniform vec3 sunColor;
uniform vec3 skyColor;
// ОТСЕЧЕНИЕ ДЛЯ ЗЕРКАЛЬНОГО ПРОХОДА. Зеркальная камера стоит НИЖЕ плоскости
// воды, и дно озера загораживает ей весь дальний берег — отражение получалось
// пустым, одно небо. В зеркальном проходе всё, что ниже уреза, выбрасывается.
uniform float clipBelow;

// Целочисленный хеш: обычный fract(sin(dot())) на решётке коррелирует и кладёт
// на кадр диагональную рябь вместо шума.
float hash(vec2 p) {
	uvec2 q = uvec2(ivec2(p * 1024.0)) * uvec2(1597334673u, 3812015801u);
	uint n = (q.x ^ q.y) * 1597334673u;
	n = (n ^ (n >> 15u)) * 2246822519u;
	n = (n ^ (n >> 13u)) * 3266489917u;
	return float(n ^ (n >> 16u)) * (1.0 / 4294967295.0);
}
float vnoise(vec2 p) {
	vec2 i = floor(p), f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	float a = hash(i), b = hash(i + vec2(1, 0));
	float c = hash(i + vec2(0, 1)), d = hash(i + vec2(1, 1));
	return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

void main() {
	if (vWorld.y < clipBelow) discard;
	// нормаль из производных мировой точки — сетка сама её и задаёт
	vec3 n = normalize(cross(dFdx(vWorld), dFdy(vWorld)));
	if (n.y < 0.0) n = -n;
	float slope = 1.0 - n.y;

	// ПОКРОВ: трава на пологом, грунт на склоне. Две частоты шума, чтобы не
	// было заливки одним цветом; период 3.7 и 0.41 м — крупные пятна и зерно.
	float m1 = vnoise(vWorld.xz * 0.27);
	float m2 = vnoise(vWorld.xz * 2.4);
	vec3 grass = mix(vec3(0.115, 0.150, 0.062), vec3(0.180, 0.205, 0.088), m1);
	vec3 soil  = mix(vec3(0.150, 0.120, 0.082), vec3(0.195, 0.160, 0.110), m2);
	vec3 alb = mix(grass, soil, clamp(slope * 3.2 + m2 * 0.15, 0.0, 1.0));
	alb *= 0.88 + 0.24 * m2;

	// МОКРАЯ ПОЛОСА: у самой воды земля темнее и глянцевее.
	// vDepth ПОЛОЖИТЕЛЕН НАД ВОДОЙ (это bed - level). Первый заход брал
	// -min(vDepth, 0.0), что на всей суше даёт 0, а значит band = 1: мокрой
	// считалась ВСЯ земля, и берег темнел в 1.9 раза. Измерено: трава выходила
	// на линейной яркости 0.056 вместо 0.083.
	float wetness = clamp(vWet, 0.0, 1.0);
	float band = 1.0 - smoothstep(0.0, 0.25, max(vDepth, 0.0));
	wetness = max(wetness, band * 0.85);
	alb *= mix(1.0, 0.45, wetness);

	float ndl = max(dot(n, sunDir), 0.0);
	vec3 lit = alb * (sunColor * ndl + skyColor * (0.45 + 0.55 * n.y));

	// ВЛАЖНЫЙ ОТЛИВ. У мокрого грунта поверх зёрен стоит плёнка воды, поэтому у
	// него есть зеркальная составляющая, а у сухого нет.
	// Было pow(...,90) * 0.55: при низком солнце вектор h вставал почти
	// вертикально на всей полосе разом, и на берегу вспыхивало белое пятно
	// яркостью 0.47 при траве 0.08 — вшестеро. Теперь отражает не «блик», а
	// плёнка воды: доля отражённого берётся по Френелю (F0 = 0.02), и на
	// скользящем взгляде она честно растёт, а в лоб почти исчезает.
	if (wetness > 0.01) {
		vec3 v = normalize(cameraPosition - vWorld);
		vec3 hv = normalize(v + sunDir);
		float f0 = 0.02;
		float F = f0 + (1.0 - f0) * pow(1.0 - max(dot(v, hv), 0.0), 5.0);
		float sp = pow(max(dot(n, hv), 0.0), 220.0) * wetness * F;
		lit += sunColor * sp;
	}
	gl_FragColor = vec4(lit, 1.0);
}`;

export function buildTerrain(slice, level) {
	const { n, cell, ox, oz, bed } = slice;
	const geo = new THREE.BufferGeometry();
	const pos = new Float32Array(n * n * 3);
	const wet = new Float32Array(n * n);
	const dep = new Float32Array(n * n);
	for (let j = 0; j < n; j++) {
		for (let i = 0; i < n; i++) {
			const k = j * n + i;
			pos[k * 3] = ox + i * cell;
			pos[k * 3 + 1] = bed[k];
			pos[k * 3 + 2] = oz + j * cell;
			const lv = level[k];
			// насколько земля выше уреза (отрицательное — земля под водой)
			dep[k] = Number.isNaN(lv) ? 1.0 : bed[k] - lv;
			wet[k] = (!Number.isNaN(lv) && lv - bed[k] > 0.0) ? 1.0 : 0.0;
		}
	}
	// ИНДЕКСЫ 32-БИТНЫЕ: 513² узлов это 263 169 вершин, в 16 бит не влезает,
	// и без явного Uint32 геометрия молча свернулась бы в кашу.
	const idx = new Uint32Array((n - 1) * (n - 1) * 6);
	let t = 0;
	for (let j = 0; j < n - 1; j++) {
		for (let i = 0; i < n - 1; i++) {
			const a = j * n + i, b = a + 1, c = a + n, d = c + 1;
			idx[t++] = a; idx[t++] = c; idx[t++] = b;
			idx[t++] = b; idx[t++] = c; idx[t++] = d;
		}
	}
	geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
	geo.setAttribute('wet', new THREE.BufferAttribute(wet, 1));
	geo.setAttribute('depth', new THREE.BufferAttribute(dep, 1));
	geo.setIndex(new THREE.BufferAttribute(idx, 1));
	geo.computeBoundingSphere();

	const mat = new THREE.ShaderMaterial({
		vertexShader: VERT,
		fragmentShader: FRAG,
		uniforms: {
			sunDir: { value: new THREE.Vector3(0.4, 0.55, -0.3).normalize() },
			sunColor: { value: new THREE.Color(1.0, 0.94, 0.84) },
			// рассеянный свет неба — та же шкала, что у купола (горизонт 0.30 линейных)
			skyColor: { value: new THREE.Color(0.105, 0.130, 0.165) },
			clipBelow: { value: -1e9 },
		},
	});
	const mesh = new THREE.Mesh(geo, mat);
	mesh.frustumCulled = true;
	return { mesh, mat, tris: (n - 1) * (n - 1) * 2 };
}
