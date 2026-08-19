# Браузерная версия

Тот же срез Гатчины, что и в версии для телефона: земля и урез воды сняты
`tools/export_web_slice.py` теми же функциями, что читает игра (`terrain.height`,
`water_real.level_at`), а физика воды — тот же
`engine/modules/gatchina_sim/water_field.h`, собранный в WASM. Своё здесь только
рисование.

## Запустить

Нужен любой статический сервер — из-за модулей ES и `fetch` открывать
`index.html` файлом с диска нельзя.

```sh
cd web
python3 -m http.server 8099
```

и открыть <http://127.0.0.1:8099/>.

Управление: `WASD` ходить, `Shift` быстрее, `Q`/`E` вниз-вверх, тянуть мышью —
смотреть, короткий клик — бросить камень в воду.

Ракурс можно задать адресом, не трогая код:

- `?view=shore` (по умолчанию) — у кромки, глаз человека
- `?view=near` — в двух шагах от воды, видно берег и толщу
- `?view=down` — с пригорка на всё озеро
- `?view=top` — сверху на весь срез
- `?eye=x,y,z&at=x,y,z` — произвольная точка и цель
- `?dbg=refl` — показать буфер отражения на весь экран
- `?dbg=1..5` — разбор шейдера воды по слагаемым:
  1 толща · 2 отражение×Френель · 3 Френель · 4 пена · 5 глубина

## Пересобрать данные и WASM

```sh
python3 tools/export_web_slice.py            # -> web/data/slice.bin (1028 КБ)
web/wasm/build.sh                            # нужен emscripten (em++)
npm install && cp node_modules/three/build/three.{module,core}.js vendor/
```

## Снять кадр без глаз

```sh
node shot.mjs /tmp/кадр.png 6000 view=near
```

Требует `npm install` (playwright) и Chromium.
