#!/usr/bin/env bash
# ПОДНЯТЬ ИГРУ И ОСТАВИТЬ ЕЁ ЖИТЬ — она будет слушать команды на 127.0.0.1:8787.
#
# Раньше каждый взгляд на мир стоил полного запуска: рельеф, дороги, город,
# фон, звёзды, объёмные облака и SDFGI поднимались заново на ПРОГРАММНОМ
# растеризаторе. Здесь эта цена платится ОДИН раз, дальше — секунды на команду
# (tools/live.py): переставить камеру, обернуться, снять кадр, спросить что под
# ногами, сменить время суток, включить каркас.
#
# Разрешение по умолчанию скромное: узкое место — заливка пикселей, а не
# геометрия, и мелкий кадр отдаётся заметно быстрее.
#
#   bash tools/live_start.sh            # 960x540, полдень
#   bash tools/live_start.sh 1280x720   # крупнее, медленнее
set -u
RES="${1:-960x540}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SP="${SCRATCH:-/tmp/claude-live}"
mkdir -p "$SP"
GODOT="${GODOT:-$SP/godot}"
if [ ! -x "$GODOT" ]; then
    echo "нет движка: $GODOT (задай GODOT=путь)" >&2
    exit 1
fi
if python3 -c "import socket,sys; s=socket.socket(); sys.exit(0 if s.connect_ex(('127.0.0.1',8787))==0 else 1)"; then
    echo "игра уже живёт на 127.0.0.1:8787 — новый запуск не нужен"
    exit 0
fi
# ПЕРЕСБОРКА ИМПОРТА. Запущенная игра берёт не сам .glb, а СОБРАННЫЙ файл из
# .godot/imported — и файл этот пересобирает только редактор. Пока я этого не
# знал, я правил hero.glb, смотрел кадр и объяснял неизменившуюся картинку
# сначала «не работает перекраска», потом «Godot не читает цвет». Поймал
# проверкой в упор: спрятал пальто целиком — в кадре не изменилось НИЧЕГО.
# Импорт разностный: если ничего не менялось, он занимает секунды.
if [ "${NOIMPORT:-0}" != "1" ]; then
    LIBGL_ALWAYS_SOFTWARE=1 xvfb-run -a "$GODOT" --path "$ROOT/game2" \
        --headless --import > "$SP/import.log" 2>&1 \
        || echo "импорт ругнулся, смотри $SP/import.log" >&2
fi
nohup xvfb-run -a "$GODOT" --path "$ROOT/game2" \
    --rendering-driver vulkan --rendering-method forward_plus \
    --resolution "$RES" -- --live > "$SP/live.log" 2>&1 &
echo "поднимаю мир (лог: $SP/live.log)…"
for i in $(seq 1 240); do
    if grep -q "\[live\] канал открыт" "$SP/live.log" 2>/dev/null; then
        echo "готово за ${i} с — говори через: python3 tools/live.py \"state\""
        exit 0
    fi
    sleep 1
done
echo "канал не открылся за 240 с, смотри $SP/live.log" >&2
exit 1
