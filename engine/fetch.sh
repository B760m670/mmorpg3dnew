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
echo "engine ready: $DIR @ $GODOT_TAG (+$(ls "$HERE"/patches/*.patch 2>/dev/null | wc -l) patches)"
