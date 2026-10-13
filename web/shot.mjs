// Снимок браузерной версии: поднимаем страницу в Chromium и ждём, пока сцена
// соберётся. Смотреть на игру глазами — единственная надёжная проверка.
//
// Аргументы позиционные и легко съезжают: раньше вид читался из argv[5], а
// передавался четвёртым — и все снимки «near» на деле были «shore». Теперь всё
// после файла и задержки идёт в адрес как есть:
//   node shot.mjs out.png 6000 view=near dbg=refl
import { chromium } from 'playwright';
const out = process.argv[2] || '/tmp/web.png';
const waitMs = Number(process.argv[3] || 6000);
const qs = process.argv.slice(4).filter(Boolean).join('&');
const url = 'http://127.0.0.1:8099/' + (qs ? '?' + qs : '');
const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome', args: ['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader'] });
const p = await b.newPage({ viewport: { width: 1280, height: 720 } });
p.on('console', m => console.log('[browser]', m.text()));
p.on('pageerror', e => console.log('[ОШИБКА]', e.message));
console.log('адрес:', url);
await p.goto(url, { waitUntil: 'networkidle' });
await p.waitForTimeout(waitMs);
const hud = await p.evaluate(() => document.getElementById('hud')?.textContent || document.getElementById('boot')?.textContent || '');
console.log('--- HUD ---\n' + hud);
await p.screenshot({ path: out });
await b.close();
