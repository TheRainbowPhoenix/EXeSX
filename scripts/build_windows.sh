#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
QEMU_SOURCE="${QEMU_SOURCE:-$ROOT/vendor/qemu}"
if [ "${MSYSTEM:-}" != MINGW64 ]; then
  echo 'Run this script in the MSYS2 MINGW64 environment.' >&2
  exit 1
fi
if [ ! -f "$QEMU_SOURCE/configure" ]; then
  mkdir -p "$(dirname "$QEMU_SOURCE")"
  git clone --depth 1 --branch v10.1.0 https://gitlab.com/qemu-project/qemu.git "$QEMU_SOURCE"
fi
python "$ROOT/scripts/integrate_qemu.py" "$QEMU_SOURCE"
mkdir -p "$ROOT/build"
cd "$ROOT/build"
# Headless native PE executable. TCG plugins are not supported by this target.
"$QEMU_SOURCE/configure" --target-list=arm-softmmu \
  --without-default-features --enable-tcg --enable-fdt --enable-pixman \
  --disable-werror --disable-docs --disable-plugins --disable-guest-agent
ninja -j "${JOBS:-2}" qemu-system-arm.exe
./qemu-system-arm.exe -machine help | grep exesx
