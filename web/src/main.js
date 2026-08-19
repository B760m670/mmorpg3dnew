// БРАУЗЕРНАЯ ВЕРСИЯ — тот же срез Гатчины, что и в версии для телефона.
//
// Что общего с game2 (важно, чтобы это не разошлось):
//   ЗЕМЛЯ И УРЕЗ — из tools/export_web_slice.py, а он повторяет terrain.height и
//     water_real.level_at узел в узел;
//   ФИЗИКА ВОДЫ — тот же engine/modules/gatchina_sim/water_field.h, собранный
//     в WASM. Не порт, не «похожая реализация» — один файл на две платформы.
// Что здесь своё: отрисовка. И это единственное, ради чего затевался переезд.
import * as THREE from 'three';
import { loadSlice } from './slice.js';
import { buildTerrain } from './terrain.js';
import { buildWater, buildFarWater, Reflection } from './water.js';
import { Post } from './post.js';
import WaterFieldModule from './waterfield.js';

const FIELD_SIDE = 256;      // ячеек
const FIELD_CELL = 1.0;      // м
const LAKE = { x: -16, z: -640 };
// ЦЕНТР ПОЛЯ — НЕ ЦЕНТР ОЗЕРА. Озеро тянется на 161 м к северу от центра, а
// половина поля это 128 м: северный берег, на котором стоит игрок, оказывался
// ЗА полем, и у ног воды просто не было — на первом кадре это выглядело как
// широкая полоса травы до самой глади. Поле ставится туда, где ходят.
const FIELD_CENTER = { x: -16, z: -600 };

const hud = document.getElementById('hud');
const boot = document.getElementById('boot');

function say(s) { boot.textContent = s; }

async function main() {
	say('качаю срез…');
	const slice = await loadSlice('./data/slice.bin');

	say('поднимаю решатель воды (WASM)…');
	const wf = await WaterFieldModule();
	const org = { x: FIELD_CENTER.x - FIELD_SIDE * FIELD_CELL / 2, y: FIELD_CENTER.z - FIELD_SIDE * FIELD_CELL / 2 };
	wf._wf_setup(FIELD_SIDE, FIELD_CELL, org.x, org.y);
	wf._wf_set_manning(0.03);

	// ДНО В ПОЛЕ — из того же среза. Пишем прямо в память WASM: 65 536 вызовов
	// через границу JS/WASM стоили бы миллисекунды на пустом месте.
	const bedPtr = wf._wf_bed_ptr() >> 2;
	let restLevel = NaN, lvlN = 0, lvlSum = 0;
	for (let j = 0; j < FIELD_SIDE; j++) {
		for (let i = 0; i < FIELD_SIDE; i++) {
			const wx = org.x + i * FIELD_CELL, wz = org.y + j * FIELD_CELL;
			wf.HEAPF32[bedPtr + j * FIELD_SIDE + i] = slice.bedAt(wx, wz);
			// урез берём из среза, а не назначаем: иначе ближняя вода разойдётся
			// по высоте с той, что нарисована на телефоне
			const gi = Math.round((wx - slice.ox) / slice.cell);
			const gj = Math.round((wz - slice.oz) / slice.cell);
			if (gi >= 0 && gj >= 0 && gi < slice.n && gj < slice.n) {
				const lv = slice.level[gj * slice.n + gi];
				if (!Number.isNaN(lv)) { lvlSum += lv; lvlN++; }
			}
		}
	}
	if (!lvlN) { say('в срезе нет воды'); return; }
	restLevel = lvlSum / lvlN;
	wf._wf_fill_region(restLevel, restLevel);
	wf._wf_set_open(1, restLevel);

	// --- сцена ---
	const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
	renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
	renderer.setSize(innerWidth, innerHeight);
	renderer.setClearColor(0x0b0d10, 1);
	document.body.appendChild(renderer.domElement);

	const scene = new THREE.Scene();
	const camera = new THREE.PerspectiveCamera(58, innerWidth / innerHeight, 0.1, 6000);

	// НЕБО — купол с градиентом и диском Солнца. Настоящая модель (Рэлей, Ми,
	// астрономия Meeus) уже написана в game2/scripts/core/world_clock.gd и
	// переносится следующим шагом; пока здесь заглушка, и это видно.
	//
	// СОЛНЦЕ СТОИТ НАД ОЗЕРОМ, А НЕ СБОКУ. Азимут было 54° правее взгляда, то есть
	// за краем кадра (поле зрения 58°), и солнечной дорожки в кадре не было в
	// принципе. Дорожка — единственное, что на стоячей воде сразу читается как
	// вода: она показывает уклоны, которых иначе не видно. Высота 17°: низкое
	// солнце растягивает дорожку на всё озеро, высокое сжимает её в пятно.
	const sunDir = new THREE.Vector3(0.20, 0.30, -0.93).normalize();
	const skyGeo = new THREE.SphereGeometry(4000, 48, 24);
	const skyMat = new THREE.ShaderMaterial({
		side: THREE.BackSide, depthWrite: false,
		uniforms: { sunDir: { value: sunDir }, sunDisc: { value: 1.0 } },
		vertexShader: `varying vec3 vD; void main(){ vD = normalize(position); gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.0); }`,
		fragmentShader: `precision highp float; varying vec3 vD; uniform vec3 sunDir; uniform float sunDisc;
			void main(){
				float up = clamp(vD.y*0.5+0.5, 0.0, 1.0);
				// ЯРКОСТИ СОРАЗМЕРНЫ, а не «похожи на цвет неба». В линейных единицах,
				// где освещённая солнцем трава (альбедо 0.15) даёт около 0.15, небо у
				// горизонта это 0.30, а зенит вчетверо темнее: у настоящего неба зенит
				// около 6000 кд/м², горизонт 10000, трава 6400. Первый заход я взял
				// «цвета неба» прямо с экрана (0.62..0.74) и получил кадр в молоке.
				vec3 c = mix(vec3(0.30,0.31,0.33), vec3(0.075,0.115,0.215), pow(up,0.7));
				// ДИСК НАСТОЯЩЕГО РАЗМЕРА. Солнце с Земли — 0.53° в поперечнике,
				// то есть 0.0046 рад радиуса. Было pow(s,3000): половина яркости на
				// 1.5°, диск втрое шире настоящего — на кадре висел ватный шар.
				// Показатель считается из радиуса: cos(0.0046)^n = 0.5 при n = 65000.
				// ЯРКОСТЬ ТОЖЕ НЕ ВЫДУМАНА: диск занимает 6.8e-5 стерадиан, и при
				// освещённости 1.0 в наших единицах его яркость 1/6.8e-5. Такое число
				// обязано выйти за экран — за него отвечает ореол в post.js.
				float s = max(dot(normalize(vD), sunDir), 0.0);
				c += vec3(1.0,0.94,0.82) * pow(s, 65000.0) * 14700.0 * sunDisc;
				c += vec3(1.0,0.92,0.78) * pow(s, 900.0) * 0.55;   // околосолнечный ореол
				c += vec3(1.0,0.92,0.78) * pow(s, 8.0) * 0.07;     // дымка вокруг
				gl_FragColor = vec4(c, 1.0);
			}`,
	});
	scene.add(new THREE.Mesh(skyGeo, skyMat));

	const terr = buildTerrain(slice, slice.level);
	terr.mat.uniforms.sunDir.value.copy(sunDir);
	scene.add(terr.mesh);

	const water = buildWater(org, FIELD_SIDE, FIELD_CELL);
	water.mat.uniforms.sunDir.value.copy(sunDir);
	scene.add(water.mesh);

	// поле в текстуру: вершины сетки совпадают с узлами один в один
	const texPtr = wf._wf_tex_ptr() >> 2;
	const texData = wf.HEAPF32.subarray(texPtr, texPtr + FIELD_SIDE * FIELD_SIDE * 4);
	const fieldTex = new THREE.DataTexture(texData, FIELD_SIDE, FIELD_SIDE,
		THREE.RGBAFormat, THREE.FloatType);
	fieldTex.magFilter = THREE.LinearFilter;
	fieldTex.minFilter = THREE.LinearFilter;
	fieldTex.needsUpdate = true;
	water.mat.uniforms.tField.value = fieldTex;

	// остальное озеро — тем же материалом, по неподвижному полю из среза
	const far = buildFarWater(slice, slice.level, restLevel, {
		x0: org.x, x1: org.x + FIELD_SIDE * FIELD_CELL,
		z0: org.y, z1: org.y + FIELD_SIDE * FIELD_CELL,
	}, 2);
	const farMat = water.mat.clone();
	farMat.uniforms.tField.value = far.tex;
	farMat.uniforms.fieldOrigin.value = new THREE.Vector2(far.origin.x, far.origin.y);
	farMat.uniforms.fieldSize.value = far.size;
	const farMesh = new THREE.Mesh(far.geo, farMat);
	farMesh.frustumCulled = false;
	scene.add(farMesh);
	// уникформы, общие для обеих поверхностей: если обновлять только одну, дальняя
	// вода останется на нулевом времени и с чужой матрицей зеркала
	const waterMats = [water.mat, farMat];

	const post = new Post(renderer, innerWidth, innerHeight);
	const refl = new Reflection(renderer, innerWidth, innerHeight);
	for (const m of waterMats) m.uniforms.tReflect.value = refl.rt.texture;
	const reflOverrides = [
		{ u: terr.mat.uniforms.clipBelow, on: restLevel - 0.02, off: -1e9 },
		{ u: skyMat.uniforms.sunDisc, on: 0.0, off: 1.0 },
	];

	// --- КАМЕРА СТАВИТСЯ ПО ДАННЫМ, А НЕ НА ГЛАЗ ---
	// Идём от центра озера наружу, пока дно не поднимется выше уреза: это и есть
	// берег. Первый заход я поставил камеру «на 118 м южнее» и попал за холм —
	// в кадре не было ни капли воды.
	function findShore(dirX, dirZ) {
		for (let r = 0; r < 250; r += 0.5) {
			const x = LAKE.x + dirX * r, z = LAKE.z + dirZ * r;
			if (slice.bedAt(x, z) > restLevel + 0.05) return { x, z, r };
		}
		return { x: LAKE.x + dirX * 120, z: LAKE.z + dirZ * 120, r: 120 };
	}
	const sh = findShore(0, 1);
	// РАКУРС ЗАДАЁТСЯ АДРЕСОМ: ?eye=x,y,z&at=x,y,z или ?view=shore|near|down|top.
	// Это здешний аналог живого канала из game2: смотреть на игру надо часто и
	// с разных мест, а перезапуск ради ракурса — та самая цена, из-за которой
	// на телефоне мы смотрели редко.
	const q = new URLSearchParams(location.search);
	const V = {
		// у самой кромки, глаз человека, взгляд на дальний берег
		shore: [[LAKE.x, 0, sh.z + 3], [LAKE.x, restLevel, sh.z - 30], 1.65],
		// в двух шагах от воды, взгляд под ноги: тут видно берег и толщу
		near:  [[LAKE.x, 0, sh.z + 1.5], [LAKE.x, restLevel, sh.z - 8], 1.65],
		// с пригорка на всё озеро
		down:  [[LAKE.x, 0, sh.z + 55], [LAKE.x, restLevel, LAKE.z], 14],
		// сверху на срез
		top:   [[LAKE.x, 0, LAKE.z + 1], [LAKE.x, restLevel, LAKE.z], 190],
	};
	const preset = V[q.get('view') || 'shore'] || V.shore;
	let eye, at;
	if (q.get('eye')) {
		const e = q.get('eye').split(',').map(Number);
		const a = (q.get('at') || `${LAKE.x},${restLevel},${LAKE.z}`).split(',').map(Number);
		eye = new THREE.Vector3(e[0], e[1], e[2]);
		at = new THREE.Vector3(a[0], a[1], a[2]);
	} else {
		eye = new THREE.Vector3(preset[0][0], 0, preset[0][2]);
		eye.y = slice.bedAt(eye.x, eye.z) + preset[2];
		at = new THREE.Vector3(preset[1][0], preset[1][1], preset[1][2]);
	}
	camera.position.copy(eye);
	camera.lookAt(at);
	console.log('берег в', sh.r.toFixed(1), 'м от центра (z=' + sh.z.toFixed(1) + ');',
		'камера', eye.toArray().map(v => v.toFixed(1)).join(','),
		'смотрит на', at.toArray().map(v => v.toFixed(1)).join(','));

	// --- УПРАВЛЕНИЕ. Те же правила, что выверены на телефоне: без инверсий,
	// один палец — поворот, два — зум и перенос, скорость ∝ высоте над землёй.
	const look = { yaw: 0, pitch: 0 };
	{
		const d = at.clone().sub(eye).normalize();
		look.yaw = Math.atan2(-d.x, -d.z);
		look.pitch = Math.asin(THREE.MathUtils.clamp(d.y, -1, 1));
	}
	const keys = new Set();
	addEventListener('keydown', e => keys.add(e.code));
	addEventListener('keyup', e => keys.delete(e.code));
	let drag = null;
	renderer.domElement.addEventListener('pointerdown', e => {
		drag = { x: e.clientX, y: e.clientY, moved: 0 };
		renderer.domElement.setPointerCapture(e.pointerId);
	});
	renderer.domElement.addEventListener('pointermove', e => {
		if (!drag) return;
		const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
		drag.x = e.clientX; drag.y = e.clientY; drag.moved += Math.abs(dx) + Math.abs(dy);
		look.yaw -= dx * 0.0032;
		look.pitch = THREE.MathUtils.clamp(look.pitch - dy * 0.0032, -1.5, 1.5);
	});
	renderer.domElement.addEventListener('pointerup', e => {
		// короткое касание без протяжки — бросить камень: ОБЪЁМ, а не «высота волны»
		if (drag && drag.moved < 6) {
			const f = new THREE.Vector3(0, 0, -1).applyQuaternion(camera.quaternion);
			const t = (restLevel - camera.position.y) / (f.y < -1e-3 ? f.y : -1e-3);
			const p = camera.position.clone().addScaledVector(f, Math.min(Math.max(t, 2), 80));
			wf._wf_add_volume(p.x, p.z, 1.2, 2.0);
		}
		drag = null;
	});

	addEventListener('resize', () => {
		renderer.setSize(innerWidth, innerHeight);
		camera.aspect = innerWidth / innerHeight;
		camera.updateProjectionMatrix();
		refl.resize(innerWidth, innerHeight);
		post.resize(innerWidth, innerHeight);
	});

	// ОТЛАДКА ЗЕРКАЛА: ?dbg=refl показывает буфер отражения на весь экран.
	// Без этого «отражения не видно» — впечатление, а не факт: непонятно, пусто
	// в буфере или вода его не так читает.
	const dbg = q.get('dbg');
	if (dbg === 'refl') {
		const ds = new THREE.Scene();
		const dc = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
		ds.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2),
			new THREE.MeshBasicMaterial({ map: refl.rt.texture })));
		window.__dbgRefl = { ds, dc };
	} else if (dbg) {
		for (const m of waterMats) m.uniforms.dbg.value = Number(dbg) || 0;
	}
	boot.remove();
	let t = 0, last = performance.now(), acc = 0, frames = 0, fps = 0;
	let msSim = 0, msRefl = 0, msDraw = 0;

	function frame(now) {
		const dt = Math.min((now - last) / 1000, 0.05);
		last = now; t += dt;

		// ход камеры: скорость растёт с высотой над землёй, как в game2
		const gh = slice.bedAt(camera.position.x, camera.position.z);
		const sp = (1.8 + Math.max(0, camera.position.y - gh) * 1.4) * (keys.has('ShiftLeft') ? 4 : 1) * dt;
		const fwd = new THREE.Vector3(-Math.sin(look.yaw), 0, -Math.cos(look.yaw));
		const rgt = new THREE.Vector3(Math.cos(look.yaw), 0, -Math.sin(look.yaw));
		if (keys.has('KeyW')) camera.position.addScaledVector(fwd, sp);
		if (keys.has('KeyS')) camera.position.addScaledVector(fwd, -sp);
		if (keys.has('KeyD')) camera.position.addScaledVector(rgt, sp);
		if (keys.has('KeyA')) camera.position.addScaledVector(rgt, -sp);
		if (keys.has('KeyE')) camera.position.y += sp;
		if (keys.has('KeyQ')) camera.position.y -= sp;
		camera.quaternion.setFromEuler(new THREE.Euler(look.pitch, look.yaw, 0, 'YXZ'));

		let t0 = performance.now();
		wf._wf_step(dt);
		wf._wf_pack();
		fieldTex.needsUpdate = true;
		msSim = msSim * 0.9 + (performance.now() - t0) * 0.1;

		camera.updateMatrixWorld(true);
		for (const m of waterMats) {
			m.uniforms.time.value = t;
			m.uniforms.viewportH.value = renderer.domElement.height;
			m.uniforms.projY.value = camera.projectionMatrix.elements[5];
		}

		t0 = performance.now();
		refl.render(scene, camera, restLevel, [water.mesh, farMesh], reflOverrides);
		for (const m of waterMats) m.uniforms.reflMat.value.copy(refl.mat);
		msRefl = msRefl * 0.9 + (performance.now() - t0) * 0.1;

		t0 = performance.now();
		if (window.__dbgRefl) {
			renderer.setRenderTarget(null);
			renderer.render(window.__dbgRefl.ds, window.__dbgRefl.dc);
		} else {
			post.render(scene, camera, t);
		}
		msDraw = msDraw * 0.9 + (performance.now() - t0) * 0.1;

		frames++; acc += dt;
		if (acc >= 0.5) { fps = frames / acc; frames = 0; acc = 0; }
		else if (fps === 0) { fps = 1 / Math.max(dt, 1e-3); }

		hud.textContent =
			`Гатчина · срез ${slice.size} м · ${(slice.bytes / 1024).toFixed(0)} КБ данных\n` +
			`${fps.toFixed(0)} кадр/с   вода ${msSim.toFixed(1)} мс   отражение ${msRefl.toFixed(1)} мс   кадр ${msDraw.toFixed(1)} мс\n` +
			`поле ${FIELD_SIDE}x${FIELD_SIDE} по ${FIELD_CELL} м · подшагов ${wf._wf_substeps()}\n` +
			`решатель: ${wf._wf_volume().toFixed(0)} м³ на ${wf._wf_wet_area().toFixed(0)} м² · дальняя вода ${far.cells} узлов\n` +
			`урез ${restLevel.toFixed(2)} м · △ рельеф ${(terr.tris / 1000).toFixed(0)}k · вода ${((water.tris + far.tris) / 1000).toFixed(0)}k\n` +
			`WASD ходить · Shift быстрее · Q/E вниз-вверх · тянуть — смотреть · клик — бросить камень`;
		requestAnimationFrame(frame);
	}
	requestAnimationFrame(frame);

	// наружу — чтобы снимать кадры из скрипта
	window.__scene = { renderer, scene, camera, water, farMesh, farMat, terr, wf, slice, restLevel, waterMats };
}

main().catch(e => { say('не поднялось: ' + e.message); console.error(e); });
