#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
QEMU_SOURCE="${QEMU_SOURCE:-$ROOT/vendor/qemu}"
if [ ! -f "$QEMU_SOURCE/configure" ]; then
  mkdir -p "$(dirname "$QEMU_SOURCE")"
  git clone --depth 1 --branch v10.1.0 https://gitlab.com/qemu-project/qemu.git "$QEMU_SOURCE"
fi
python3 "$ROOT/scripts/integrate_qemu.py" "$QEMU_SOURCE"
mkdir -p "$ROOT/build"
cd "$ROOT/build"
"$QEMU_SOURCE/configure" --target-list=arm-softmmu --disable-werror --disable-docs --disable-gtk --disable-sdl --disable-curses
ninja -j "${JOBS:-2}"
./qemu-system-arm -machine help | grep exesx
