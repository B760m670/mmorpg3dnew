// ЗАГРУЗКА ИГРОВОГО СРЕЗА (tools/export_web_slice.py).
//
// Один файл на всё место: высоты рельефа и урез воды, снятые ТЕМИ ЖЕ функциями,
// что читает версия для телефона. Это принципиально: если браузерная версия
// возьмёт другую землю, она будет другой игрой, а не той же на другом экране.
//
// ИЗМЕРЕНО: срез 512x512 м с шагом 1 м весит 1028 КБ (два слоя по 16 бит).
// Для сравнения, в сборку телефона едет 68 МБ ассетов. Открытый мир в браузере
// делается потоковой подгрузкой таких плиток, а не одной загрузкой.

export const NO_WATER = -32768;

export async function loadSlice(url) {
	const buf = await (await fetch(url)).arrayBuffer();
	const dv = new DataView(buf);
	const magic = String.fromCharCode(dv.getUint8(0), dv.getUint8(1), dv.getUint8(2), dv.getUint8(3));
	if (magic !== 'GSL1') throw new Error('не тот формат среза: ' + magic);
	const n = dv.getUint32(4, true);
	const cell = dv.getFloat32(8, true);
	const ox = dv.getFloat32(12, true);
	const oz = dv.getFloat32(16, true);
	const hMin = dv.getFloat32(20, true);
	const hMax = dv.getFloat32(24, true);

	let p = 28;
	const hq = new Uint16Array(buf, p, n * n); p += n * n * 2;
	const lq = new Int16Array(buf, p, n * n);

	// РАСПАКОВКА В МЕТРЫ ОДИН РАЗ. Держать высоты упакованными и распаковывать
	// на каждом обращении — это тысячи делений в кадре ради 1 МБ памяти.
	const span = (hMax - hMin) / 65535;
	const bed = new Float32Array(n * n);
	const level = new Float32Array(n * n);
	let wet = 0;
	for (let k = 0; k < n * n; k++) {
		bed[k] = hMin + hq[k] * span;
		const l = lq[k];
		if (l === NO_WATER) {
			level[k] = NaN;
		} else {
			level[k] = hMin + l * 0.01;
			if (level[k] - bed[k] > 0.02) wet++;
		}
	}
	return {
		n, cell, ox, oz, hMin, hMax, bed, level, wet,
		size: (n - 1) * cell,
		bytes: buf.byteLength,
		// высота дна в мировой точке, билинейно
		bedAt(x, z) {
			let gx = (x - ox) / cell, gz = (z - oz) / cell;
			gx = Math.min(Math.max(gx, 0), n - 1.001);
			gz = Math.min(Math.max(gz, 0), n - 1.001);
			const i = gx | 0, j = gz | 0, ti = gx - i, tj = gz - j;
			const a = bed[j * n + i] * (1 - ti) + bed[j * n + i + 1] * ti;
			const b = bed[(j + 1) * n + i] * (1 - ti) + bed[(j + 1) * n + i + 1] * ti;
			return a * (1 - tj) + b * tj;
		},
	};
}
