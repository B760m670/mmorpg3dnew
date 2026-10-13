#!/usr/bin/env bash
# Проверка ПОЛЯ ВОДЫ числами. Движок не нужен — только компилятор.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${TMPDIR:-/tmp}/wf_test"
g++ -O2 -std=c++17 -Wall -Wextra -o "$OUT" "$HERE/wf_test.cpp"
"$OUT"
