#!/usr/bin/env bash
# Проверка решателя числами. Движок не нужен — только компилятор.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${TMPDIR:-/tmp}/sw_test"
g++ -O2 -std=c++17 -Wall -Wextra -o "$OUT" "$HERE/sw_test.cpp"
"$OUT"
