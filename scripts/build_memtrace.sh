#!/usr/bin/env bash
# Recompile ONLY the tracing plugin: no QEMU rebuild needed.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
QEMU_SOURCE="${QEMU_SOURCE:-$ROOT/vendor/qemu}"
OUT="${1:-$ROOT/build/exesx-memtrace.so}"
if [ ! -f "$QEMU_SOURCE/include/qemu/qemu-plugin.h" ]; then
  echo "QEMU 10.1.0 source/header required at $QEMU_SOURCE" >&2
  exit 1
fi
mkdir -p "$(dirname "$OUT")"
cc -O2 -g -std=gnu11 -fPIC -fvisibility=hidden -shared -Wall -Wextra \
  -I"$QEMU_SOURCE/include/qemu" $(pkg-config --cflags glib-2.0) \
  "$ROOT/plugins/memtrace.c" -o "$OUT" $(pkg-config --libs glib-2.0)
echo "Built plugin: $OUT"
