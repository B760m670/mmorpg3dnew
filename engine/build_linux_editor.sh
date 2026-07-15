#!/usr/bin/env bash
# Линукс-редактор из форка — верификационный стенд в песочнице.
set -euo pipefail
DIR="${1:-$HOME/godot-fork}"
cd "$DIR"
scons platform=linuxbsd target=editor dev_build=no debug_symbols=no -j"$(nproc)"
echo "editor: $DIR/bin/"
