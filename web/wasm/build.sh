#!/bin/sh
# Сборка поля воды в WASM. Собирается ТОТ ЖЕ заголовок, что идёт в модуль Godot
# для телефона — отдельной реализации для браузера нет и не должно быть.
#
# em++, а не emcc: в water_field.h есть шаблоны и std::vector, и сишный драйвер
# не соберёт их символы.
# -fno-exceptions: исключений в решателе нет, а таблицы раскрутки стоят 40% веса.
# -sMODULARIZE -sEXPORT_ES6: модуль подключается обычным import, без глобалей.
# -sSINGLE_FILE: двоичный код вшит в js как base64. Плюс 10 КБ к 30, зато нет
#   отдельной загрузки — и страницу можно собрать в один файл, который
#   открывается с телефона без всякого сервера.
set -e
cd "$(dirname "$0")"
OUT=../src/waterfield.js
em++ -O3 -msimd128 -fno-exceptions \
	-sMODULARIZE=1 -sEXPORT_ES6=1 -sENVIRONMENT=web -sSINGLE_FILE=1 \
	-sALLOW_MEMORY_GROWTH=1 -sEXPORTED_RUNTIME_METHODS='["HEAPF32","HEAPU8"]' \
	-sEXPORTED_FUNCTIONS='["_wf_setup","_wf_bed_ptr","_wf_h_ptr","_wf_tex_ptr","_wf_side","_wf_set_manning","_wf_set_open","_wf_fill_region","_wf_add_volume","_wf_step","_wf_depth_at","_wf_surface_at","_wf_volume","_wf_wet_area","_wf_substeps","_wf_pack","_malloc","_free"]' \
	wf_api.cpp -o "$OUT"
rm -f "${OUT%.js}.wasm"
ls -la "$OUT"
