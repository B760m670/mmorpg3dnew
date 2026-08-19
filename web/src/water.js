// ВОДА: поверхность из ПОЛЯ и настоящее отражение берега.
//
// Три вещи, которых не было в версии на Godot и из-за которых озеро читалось
// плитой:
//
// 1. ТОЛЩА БЫЛА ЦВЕТОМ, А НЕ СВЕТОМ. Дно и муть задавались константами яркости,
//    которые ни на что не умножались. Замерено на кадре: у берега толща выходила
//    на линейной яркости 0.126, а освещённая солнцем трава рядом — на 0.056.
//    Дно озера было ВДВОЕ ЯРЧЕ травы и одинаковым по всей глади. Такая
//    поверхность и не может читаться иначе как крашеная плита.
//
// 2. ОТРАЖЕНИЕ ДАЛЬНЕГО БЕРЕГА. Там оно бралось трассировкой по экрану (SSR), а
//    она по устройству не может отразить то, чего в кадре нет: смотришь на воду
//    сверху — берега на экране уже нет, и отражать нечего. Здесь отражение
//    ПЛОСКОСТНОЕ: сцена рисуется второй раз зеркальной камерой.
//
// 3. КРОМКА. Берег — изолиния глубины, а не многоугольник, и у самой кромки
//    гладь уходит в прозрачность, отдавая место мокрому песку (он в terrain.js).
//
// Поверхность ставится по полю: вершина сетки — узел решателя, её высота это
// отметка, которую посчитала физика.
import * as THREE from 'three';

const VERT = /* glsl */`
precision highp float;
uniform sampler2D tField;      // R=отметка, G,B=уклон, A=глубина
uniform vec2 fieldOrigin;
uniform float fieldSize;
// МАТРИЦА ЗЕРКАЛА, а не экранная координата главной камеры.
//
// Сперва отражение бралось по собственному положению фрагмента на экране. Для
// плоского зеркала это почти верно — но зеркальная камера строится с
// перевёрнутым «верхом», а значит у неё перевёрнута и ось X. Буфер выходил
// отзеркаленным по горизонтали, и отражение Солнца ложилось не туда, где ему
// место: на кадре это было круглое белое пятно посреди травы. Теперь мировая
// точка проецируется ТОЙ ЖЕ матрицей, которой снят буфер.
uniform mat4 reflMat;
varying vec3 vWorld;
varying vec2 vSlope;
varying float vDepth;
varying vec4 vRefl;
void main() {
	vec2 uv = (position.xz - fieldOrigin) / fieldSize;
	vec4 f = texture2D(tField, uv);
	vDepth = f.a;
	vSlope = f.gb;
	vec3 p = vec3(position.x, f.r, position.z);
	vWorld = p;
	vRefl = reflMat * vec4(p, 1.0);
	gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
}`;

const FRAG = /* glsl */`
precision highp float;
uniform sampler2D tReflect;
// skyLight — освещённость от неба на горизонтальную площадку, в тех же единицах,
// что sunColor. Та же величина, что у земли в terrain.js: если они разойдутся,
// вода и берег окажутся освещены разными солнцами.
uniform vec3 sunDir, sunColor, skyLight;
// projY = projectionMatrix[1][1], viewportH — высота кадра в пикселях.
// В three.js матрица проекции подставляется только в ВЕРШИННЫЙ шейдер; попытка
// прочитать её во фрагментном роняет сборку шейдера молча, и вода просто
// исчезает из кадра — ровно это и случилось.
uniform float drawDepth, windMs, time, viewportH, projY;
// РАЗБОР ПО СЛАГАЕМЫМ. Кадр показывает сумму, а спорить надо про слагаемое:
// «бледная вода» может быть и толщей, и отражением, и пеной, и по картинке их
// не различить. 1 толща · 2 отражение×Френель · 3 Френель · 4 пена · 5 глубина.
uniform int dbg;

varying vec3 vWorld;
varying vec2 vSlope;
varying float vDepth;
varying vec4 vRefl;

// ОПТИКА ОЗЁРНОЙ, А НЕ ДИСТИЛЛИРОВАННОЙ ВОДЫ.
//
// Поглощение чистой воды (Pope & Fry 1997, измерено в лаборатории), 1/м:
//   R 620 нм 0.3400 · G 550 нм 0.0638 · B 450 нм 0.0145
// Само по себе оно описывает воду, которой в природе нет. В озере к нему
// добавляется жёлтое вещество (CDOM, гумус из торфа) со спектром
//   a(λ) = a(440) · exp(-0.017 (λ-440)),  ПРЕДПОЛОЖЕНИЕ a(440) = 1.0 1/м
// — это умеренно гумусная вода; замера по Гатчине у меня нет, и число взято как
// середина между родниковым Серебряным озером и торфяным прудом. Отсюда
//   CDOM: R 0.047 · G 0.154 · B 0.844
// и обратное рассеяние взвесью b_b = 0.012 1/м (примерно спектрально ровное).
//
// ЗАЧЕМ ЭТО ВАЖНО: на чистой воде синий не гаснет вовсе (0.0145 1/м — это 70 м
// пути на порядок), и озеро выходит бирюзовой лагуной. Гумус гасит именно синий
// сильнее всего, и вода становится тёмно-оливковой. Это разница между бассейном
// и озером.
const vec3 KD = vec3(0.399, 0.230, 0.871);      // ослабление рассеянного света
const vec3 BB = vec3(0.012, 0.012, 0.012);      // обратное рассеяние
const vec3 BED_ALB = vec3(0.085, 0.072, 0.050); // сапропель — тёмный ил
const float IOR = 1.333;

// Точный Френель для неполяризованного света. Шлик дал бы ошибку до 0.06;
// точная формула стоит десяток операций и снимает вопрос.
float fresnel(float ci) {
	float s2 = (1.0 - ci * ci) / (IOR * IOR);
	if (s2 >= 1.0) return 1.0;
	float ct = sqrt(1.0 - s2);
	float rs = (ci - IOR * ct) / (ci + IOR * ct);
	float rp = (IOR * ci - ct) / (IOR * ci + ct);
	return clamp(0.5 * (rs * rs + rp * rp), 0.0, 1.0);
}

// Приближение Смита для распределения Бекмана (Walter et al. 2007).
float smithG1(float c, float m) {
	float t = sqrt(max(1.0 - c * c, 0.0)) / max(c, 1e-4);
	float a = 1.0 / (sqrt(max(m, 1e-6)) * max(t, 1e-4));
	if (a >= 1.6) return 1.0;
	return (3.535 * a + 2.181 * a * a) / (1.0 + 2.276 * a + 2.577 * a * a);
}

void main() {
	// БЕРЕГ — ИЗОЛИНИЯ. Тоньше порога гладь не рисуется вовсе: измерено, что
	// плёнка тоньше 2 см расползается по склону на площадь вдвое больше самой
	// воды, и рисовать её как гладь — это вернуть «воду на суше».
	if (vDepth < drawDepth) discard;

	// РЯБЬ КОРОЧЕ ЯЧЕЙКИ. Поле считает волны длиннее двух метров (сетка 1 м),
	// всё мельче добирается здесь. Средний квадрат уклона — Cox & Munk (1954),
	// измерен по бликам Солнца с самолёта.
	float mss = 0.003 + 0.00512 * windMs;
	float rms = sqrt(mss);
	vec2 sl = vSlope;
	// НАПРАВЛЕНИЯ РАЗБРОСАНЫ, А ДЛИНЫ НЕСОИЗМЕРИМЫ. Четыре волны с близкими
	// направлениями складывались в правильные диагональные полосы — на кадре это
	// было «гофрированное железо» по всей глади. Здесь шесть компонент, разброс
	// до ±1.2 рад, а отношение длин около 1/φ: золотое сечение хуже всего
	// приближается дробью, поэтому сумма не повторяется на видимых масштабах.
	const int NR = 6;
	float lam[6]; lam[0]=2.60; lam[1]=1.61; lam[2]=1.00; lam[3]=0.62; lam[4]=0.38; lam[5]=0.24;
	float dir[6]; dir[0]=0.07; dir[1]=-0.83; dir[2]=0.51; dir[3]=-0.29; dir[4]=1.14; dir[5]=-1.07;
	float wgt[6]; wgt[0]=0.20; wgt[1]=0.19; wgt[2]=0.18; wgt[3]=0.16; wgt[4]=0.14; wgt[5]=0.13;
	// СКОЛЬКО МЕТРОВ В ПИКСЕЛЕ на этой дальности: компоненту короче двух пикселей
	// экран не разрешает, и рисовать её уклон значит только искрить.
	float dist = max(length(cameraPosition - vWorld), 1.0);
	float px = 2.0 * dist / (projY * viewportH);
	for (int i = 0; i < NR; i++) {
		float vis = clamp(lam[i] / (2.0 * px) - 1.0, 0.0, 1.0);
		if (vis <= 0.001) continue;
		vec2 d = vec2(cos(dir[i]), sin(dir[i]));
		float k = 6.2831853 / lam[i];
		sl += d * rms * wgt[i] * vis * cos(k * dot(d, vWorld.xz) - sqrt(9.81 * k) * time);
	}
	vec3 n = normalize(vec3(-sl.x, 1.0, -sl.y));

	vec3 view = normalize(cameraPosition - vWorld);
	float ci = clamp(dot(view, n), 0.0, 1.0);

	// ОТРАЖЕНИЕ: точка, спроецированная матрицей зеркальной камеры, сдвинутая
	// уклоном. СДВИГ ПАДАЕТ С ДАЛЬНОСТЬЮ: постоянный сдвиг в долях экрана
	// означает, что рябь у горизонта таскает отражение на столько же пикселей,
	// что и рябь под ногами, — а там на пиксель приходятся уже десятки волн.
	vec2 suv = vRefl.xy / max(vRefl.w, 1e-4);
	suv += sl * 0.055 * clamp(12.0 / dist, 0.03, 1.0);
	vec3 refl = texture2D(tReflect, clamp(suv, 0.001, 0.999)).rgb;

	// ТОЛЩА — ЭТО СВЕТ, А НЕ ЦВЕТ. Считается путь: свет входит в воду,
	// преломляясь, идёт до дна, отражается по Ламберту и возвращается к глазу,
	// гаснув на обоих участках.
	float sunEl = max(sunDir.y, 0.02);
	float cosT = sqrt(max(1.0 - (1.0 - sunEl * sunEl) / (IOR * IOR), 0.04));
	// освещённость под поверхностью: прямое солнце минус то, что отразилось
	vec3 Ed = sunColor * sunEl * (1.0 - fresnel(sunEl)) + skyLight;
	float down = vDepth / cosT;
	float up = vDepth / max(abs(view.y), 0.12);
	vec3 bottom = BED_ALB * Ed * exp(-KD * (down + up));
	// свечение самой толщи: обратное рассеяние, накопленное вдоль пути
	vec3 vol = Ed * (BB / KD) * (1.0 - exp(-KD * (down + up)));
	vec3 under = bottom + vol;

	float F = fresnel(ci);
	vec3 col = mix(under, refl, F);

	// БЛИК СОЛНЦА ПО COX & MUNK, А НЕ ПО ПОКАЗАТЕЛЮ СТЕПЕНИ.
	// Было pow(dot(n,h), 900): при ветре 2.5 м/с это лепесток около 2°, тогда как
	// измеренный средний квадрат уклона mss = 0.0158 даёт полуугол около 7°.
	// Дорожки на воде поэтому не было вовсе. Здесь честное распределение уклонов
	//   D = exp(-tan²θ/mss) / (π mss cos⁴θ)
	// и микрогранная нормировка L = E · F · D · G / (4 cosθv). Солнце светит в
	// кадр, и это единственное, что делает гладь дорогой, а не заливкой.
	vec3 h = normalize(view + sunDir);
	float ch = max(dot(n, h), 1e-4);
	float t2 = (1.0 - ch * ch) / (ch * ch);
	float D = exp(-t2 / mss) / (3.14159265 * mss * ch * ch * ch * ch);
	float cv = max(dot(n, view), 1e-3);
	float cs = max(dot(n, sunDir), 0.0);
	// ЗАТЕНЕНИЕ ГРЕБНЯМИ ПО СМИТУ. Без него D/(4 cv) на скользящем взгляде уходит
	// в десятки: у самой кромки вспыхивало круглое белое пятно — не блик, а
	// деление на почти ноль. Чем положе взгляд, тем большую часть уклонов
	// закрывают соседние гребни.
	float vh = max(dot(view, h), 1e-4);
	float G = smithG1(cv, mss) * smithG1(cs, mss);
	col += sunColor * fresnel(vh) * D * G / (4.0 * cv);

	// ПЕНА У КРОМКИ — УЗКАЯ И РВАНАЯ. Первый заход брал 18 см глубины: на здешнем
	// пологом берегу (уклон около 1:30) это полоса в пять метров, и на кадре она
	// читалась сугробом. Теперь 5 см — меньше метра по берегу, и края разбиты
	// шумом: у стоячего пруда сплошной пенной каймы не бывает вовсе.
	float fw = 1.0 - smoothstep(drawDepth, drawDepth + 0.05, vDepth);
	float fn = 0.55 + 0.45 * sin(vWorld.x * 2.7 + vWorld.z * 1.9 + time * 0.7)
		* cos(vWorld.x * 1.3 - vWorld.z * 2.3);
	col = mix(col, vec3(0.62, 0.64, 0.63), fw * fn * 0.30);

	float a = smoothstep(drawDepth, drawDepth + 0.05, vDepth);
	if (dbg == 1) col = under;
	else if (dbg == 2) col = refl * F;
	else if (dbg == 3) col = vec3(F);
	else if (dbg == 4) col = vec3(fw * fn * 0.30);
	else if (dbg == 5) col = vec3(vDepth / 3.0);
	if (dbg > 0) { gl_FragColor = vec4(col, 1.0); return; }
	gl_FragColor = vec4(col, a);
}`;

// ДАЛЬНЯЯ ВОДА — ТА ЖЕ ПОВЕРХНОСТЬ, НО БЕЗ РЕШАТЕЛЯ.
//
// Поле решателя — 256 м с шагом 1 м, а озеро 322 м в поперечнике: дальняя треть
// оставалась вовсе без воды, и на кадре сквозь неё просвечивало голое дно. Гнать
// решатель на всё озеро — 147 тысяч ячеек вместо 65: втрое дороже ради воды, до
// которой не докинуть камнем.
//
// Поэтому волны считаются там, где стоит игрок, а остальное озеро рисуется тем же
// шейдером по НЕПОДВИЖНОМУ полю из среза. Материал один и тот же, значит и оптика
// одна: разницы в кадре нет, пока по глади не пойдёт волна — вот на границе окна
// она и оборвётся. Это известный шов, и он здесь назван, а не спрятан.
export function buildFarWater(slice, level, restLevel, hole, step) {
	const { n, cell, ox, oz, bed } = slice;
	const m = Math.floor((n - 1) / step) + 1;      // узлов в разреженной сетке
	const tex = new Float32Array(m * m * 4);
	let cells = 0;
	for (let j = 0; j < m; j++) {
		for (let i = 0; i < m; i++) {
			const si = Math.min(i * step, n - 1), sj = Math.min(j * step, n - 1);
			const x = ox + si * cell, z = oz + sj * cell;
			const lv = level[sj * n + si];
			let d = Number.isNaN(lv) ? 0 : lv - bed[sj * n + si];
			// ВЫРЕЗ ПОД ОКНО РЕШАТЕЛЯ: внутри него воду рисует поле, и две
			// поверхности в одной плоскости иначе дрались бы за глубину.
			// Вырез на клетку уже окна — чтобы между ними не осталось щели.
			if (x > hole.x0 + cell && x < hole.x1 - cell && z > hole.z0 + cell && z < hole.z1 - cell) d = 0;
			if (d > 0.02) cells++; else d = 0;
			const k = (j * m + i) * 4;
			tex[k] = restLevel; tex[k + 1] = 0; tex[k + 2] = 0; tex[k + 3] = d;
		}
	}
	const geo = new THREE.BufferGeometry();
	const pos = new Float32Array(m * m * 3);
	for (let j = 0; j < m; j++) {
		for (let i = 0; i < m; i++) {
			const k = j * m + i;
			pos[k * 3] = ox + Math.min(i * step, n - 1) * cell;
			pos[k * 3 + 1] = 0;
			pos[k * 3 + 2] = oz + Math.min(j * step, n - 1) * cell;
		}
	}
	const idx = new Uint32Array((m - 1) * (m - 1) * 6);
	let t = 0;
	for (let j = 0; j < m - 1; j++) {
		for (let i = 0; i < m - 1; i++) {
			const a = j * m + i, b = a + 1, c = a + m, d = c + 1;
			idx[t++] = a; idx[t++] = c; idx[t++] = b;
			idx[t++] = b; idx[t++] = c; idx[t++] = d;
		}
	}
	geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
	geo.setIndex(new THREE.BufferAttribute(idx, 1));
	const size = (n - 1) * cell;
	geo.boundingSphere = new THREE.Sphere(new THREE.Vector3(ox + size / 2, restLevel, oz + size / 2), size);
	const dt = new THREE.DataTexture(tex, m, m, THREE.RGBAFormat, THREE.FloatType);
	dt.magFilter = THREE.LinearFilter; dt.minFilter = THREE.LinearFilter;
	dt.needsUpdate = true;
	return { geo, tex: dt, origin: { x: ox, y: oz }, size, cells, tris: (m - 1) * (m - 1) * 2 };
}

export function buildWater(origin, side, cell) {
	const size = side * cell;
	const geo = new THREE.BufferGeometry();
	const pos = new Float32Array(side * side * 3);
	for (let j = 0; j < side; j++) {
		for (let i = 0; i < side; i++) {
			const k = j * side + i;
			pos[k * 3] = origin.x + i * cell;
			pos[k * 3 + 1] = 0;                 // высоту поставит шейдер из поля
			pos[k * 3 + 2] = origin.y + j * cell;
		}
	}
	const idx = new Uint32Array((side - 1) * (side - 1) * 6);
	let t = 0;
	for (let j = 0; j < side - 1; j++) {
		for (let i = 0; i < side - 1; i++) {
			const a = j * side + i, b = a + 1, c = a + side, d = c + 1;
			idx[t++] = a; idx[t++] = c; idx[t++] = b;
			idx[t++] = b; idx[t++] = c; idx[t++] = d;
		}
	}
	geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
	geo.setIndex(new THREE.BufferAttribute(idx, 1));
	// СВОЙ ЯЩИК: вершины лежат в плоскости y=0, а высоту им даёт шейдер. Без
	// этого отсечение по пирамиде выбросило бы воду, когда камера смотрит сбоку.
	geo.boundingSphere = new THREE.Sphere(
		new THREE.Vector3(origin.x + size / 2, 0, origin.y + size / 2), size);

	const mat = new THREE.ShaderMaterial({
		vertexShader: VERT,
		fragmentShader: FRAG,
		transparent: true,
		uniforms: {
			tField: { value: null },
			tReflect: { value: null },
			reflMat: { value: new THREE.Matrix4() },
			fieldOrigin: { value: new THREE.Vector2(origin.x, origin.y) },
			fieldSize: { value: size },
			drawDepth: { value: 0.02 },
			windMs: { value: 2.5 },
			time: { value: 0 },
			viewportH: { value: 720 },
			projY: { value: 1.7 },
			dbg: { value: 0 },
			sunDir: { value: new THREE.Vector3(0.4, 0.55, -0.3).normalize() },
			sunColor: { value: new THREE.Color(1.0, 0.94, 0.84) },
			skyLight: { value: new THREE.Color(0.105, 0.130, 0.165) },
		},
	});
	const mesh = new THREE.Mesh(geo, mat);
	mesh.frustumCulled = false;
	return { mesh, mat, tris: (side - 1) * (side - 1) * 2 };
}

// ПЛОСКОСТНОЕ ОТРАЖЕНИЕ. Сцена рисуется зеркальной камерой относительно
// плоскости воды. Разрешение вдвое ниже экрана: отражение всё равно размывается
// уклоном, а проход стоит как второй кадр.
export class Reflection {
	constructor(renderer, w, h) {
		this.rt = new THREE.WebGLRenderTarget(Math.floor(w / 2), Math.floor(h / 2), {
			minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter,
			type: THREE.HalfFloatType, depthBuffer: true,
		});
		this.cam = new THREE.PerspectiveCamera();
		this.renderer = renderer;
		// матрица «мировая точка -> координата в этом буфере», как в three.js Reflector
		this.mat = new THREE.Matrix4();
		this._look = new THREE.Vector3();
	}
	resize(w, h) { this.rt.setSize(Math.floor(w / 2), Math.floor(h / 2)); }
	// overrides — уникформы, у которых в зеркальном проходе другое значение:
	//   clipBelow у земли (иначе дно озера закрывает зеркальной камере весь берег
	//     и отражать становится нечего — буфер выходит пустым небом);
	//   sunDisc у неба (диск Солнца из буфера убирается: солнечную дорожку считает
	//     сама вода по распределению уклонов, и отражённый диск был бы вторым
	//     солнцем поверх неё).
	render(scene, camera, planeY, hide, overrides) {
		const c = this.cam;
		c.copy(camera);
		// зеркалим положение и взгляд относительно плоскости y = planeY
		c.position.set(camera.position.x, 2 * planeY - camera.position.y, camera.position.z);
		this._look.set(0, 0, -1).applyQuaternion(camera.quaternion).add(camera.position);
		c.up.set(0, -1, 0);
		c.lookAt(this._look.x, 2 * planeY - this._look.y, this._look.z);
		c.updateMatrixWorld(true);
		c.updateProjectionMatrix();
		// clip [-1..1] -> текстура [0..1]
		this.mat.set(0.5, 0, 0, 0.5, 0, 0.5, 0, 0.5, 0, 0, 0.5, 0.5, 0, 0, 0, 1);
		this.mat.multiply(c.projectionMatrix).multiply(c.matrixWorldInverse);

		const hid = [];
		for (const o of hide) { hid.push(o.visible); o.visible = false; }
		for (const o of overrides || []) o.u.value = o.on;
		const old = this.renderer.getRenderTarget();
		this.renderer.setRenderTarget(this.rt);
		this.renderer.clear();
		this.renderer.render(scene, c);
		this.renderer.setRenderTarget(old);
		for (const o of overrides || []) o.u.value = o.off;
		hide.forEach((o, i) => { o.visible = hid[i]; });
	}
}
