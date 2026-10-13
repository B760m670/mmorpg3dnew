#!/usr/bin/env bash
# Клонирует пин апстрима и накладывает наши патчи (патч-очередь форка).
set -euo pipefail
DIR="${1:-$HOME/godot-fork}"
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/UPSTREAM"
if [ ! -d "$DIR/.git" ]; then
  git clone --depth 1 --branch "$GODOT_TAG" https://github.com/godotengine/godot.git "$DIR"
fi
cd "$DIR"
git checkout -q "$GODOT_TAG" 2>/dev/null || true
for p in "$HERE"/patches/*.patch; do
  [ -e "$p" ] || continue
  echo "applying $(basename "$p")"
  git apply --check "$p" && git apply "$p"
done
# НАШ КОД НА C++ — МОДУЛЯМИ ДВИЖКА. Не патчами: патч к чужому файлу ломается на
# каждом обновлении апстрима, а модуль лежит своей папкой и живёт сам. Всё, что
# мы пишем на C++ (симуляция воды, дальше разрушаемость и явления), кладётся
# сюда и попадает прямо в шаблон, который мы и так собираем сами.
mkdir -p "$DIR/modules"
for m in "$HERE"/modules/*/; do
  [ -d "$m" ] || continue
  name="$(basename "$m")"
  rm -rf "$DIR/modules/$name"
  cp -r "$m" "$DIR/modules/$name"
  echo "module: $name"
done
echo "engine ready: $DIR @ $GODOT_TAG (+$(ls "$HERE"/patches/*.patch 2>/dev/null | wc -l) patches, $(ls -d "$HERE"/modules/*/ 2>/dev/null | wc -l) modules)"
