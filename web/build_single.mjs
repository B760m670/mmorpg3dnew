// СБОРКА В ОДНУ СТРАНИЦУ.
//
// Обычная версия — это папка с модулями, срезом и WASM, и её надо чем-то
// раздавать. С телефона без компьютера так не запустишь: локального сервера
// там нет, а ES-модули и fetch с file:// браузер не пускает.
//
// Здесь всё складывается в один .html: three.js и наш код — сборкой esbuild,
// решатель воды — уже вшит в свой js (SINGLE_FILE), срез — как base64. Такую
// страницу можно открыть откуда угодно и чем угодно.
//
// ЦЕНА НАЗВАНА ЧЕСТНО: срез в base64 растёт на треть (1028 КБ -> 1371 КБ), и
// вся страница качается разом, без потоковой подгрузки. Для одного места это
// нормально; открытый мир так не делают.
import { build } from 'esbuild';
import { readFileSync, writeFileSync, mkdirSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

const here = dirname(fileURLToPath(import.meta.url));
const out = process.argv[2] || join(here, 'dist/gatchina.html');
mkdirSync(dirname(out), { recursive: true });

const r = await build({
	entryPoints: [join(here, 'src/main.js')],
	bundle: true, format: 'esm', write: false, minify: true, target: 'es2022',
	// 'three' указывает на копию в vendor — ту же, что раздаётся обычной версией
	alias: { three: join(here, 'vendor/three.module.js') },
	logLevel: 'warning',
});
const js = r.outputFiles[0].text;
const slice = readFileSync(join(here, 'data/slice.bin')).toString('base64');
const shell = readFileSync(join(here, 'index.html'), 'utf8');

// из обычной страницы берём только оформление: importmap и внешний скрипт здесь
// не нужны, а стиль и разметка должны совпадать один в один
let head = shell
	.replace(/<script type="importmap">[\s\S]*?<\/script>/, '')
	.replace(/<script type="module"[\s\S]*?<\/script>/, '')
	.trimEnd();

// РЕЖИМ ПУБЛИКАЦИИ (--artifact). Площадка сама оборачивает файл в <html><head>,
// поэтому свои doctype и meta оттуда надо убрать — иначе они попадут в тело
// документа и будут проигнорированы. А viewport при этом терять нельзя: без него
// Safari на телефоне рисует страницу как экран в 980 точек и кадр выходит
// вчетверо мельче. Поэтому он не удаляется, а ставится скриптом прямо в head.
const artifact = process.argv.includes('--artifact');
let fixups = '';
if (artifact) {
	head = head
		.replace(/<!doctype html>\s*/i, '')
		.replace(/<meta charset="utf-8">\s*/i, '')
		.replace(/<meta name="viewport"[^>]*>\s*/i, '');
	fixups = `<script>
(function(){
	var m = document.querySelector('meta[name=viewport]');
	if (!m) { m = document.createElement('meta'); m.name = 'viewport'; document.head.appendChild(m); }
	m.content = 'width=device-width,initial-scale=1,viewport-fit=cover,user-scalable=no';
	document.documentElement.style.height = document.body.style.height = '100%';
	document.body.style.margin = '0';
	document.body.style.background = '#0b0d10';
	document.body.style.overflow = 'hidden';
})();
</script>`;
}

writeFileSync(out, `${head}
${fixups}
<script>window.__SLICE_B64=${JSON.stringify(slice)};</script>
<script type="module">${js}</script>
`);

const kb = (n) => (n / 1024).toFixed(0) + ' КБ';
console.log('собрано', out);
console.log('  код (three.js + игра, минифицировано):', kb(js.length));
console.log('  срез в base64:', kb(slice.length), '(из', kb(readFileSync(join(here, 'data/slice.bin')).length) + ')');
console.log('  всего:', kb(readFileSync(out).length));
