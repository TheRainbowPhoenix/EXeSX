#!/usr/bin/env python3
"""Firmware-free original-ARM LCD MADCTL/window geometry regression.

Execute genuine ARM MMIO writes through EXeSX QEMU with either orientation.
The chosen 0x60 window resembles a centered-landscape box when MV+MX is
honored, but this does not authenticate the still-unidentified LCD panel.
"""
import argparse
import os
from pathlib import Path
import struct
import subprocess
import tempfile

BASE = 0x60000000
W, H = 864, 480
COLORS = (0xf800, 0x07e0, 0x001f, 0xffe0, 0x07ff, 0xf81f)


def make_elf(madctl):
    words, pool = [], []

    def emit(word):
        words.append(word)

    def literal(reg, value):
        pool.append((len(words), reg, value))
        emit(0)

    def store(src, base, offset=0):
        emit(0xe5800000 | base << 16 | src << 12 | offset)

    def half(src, base):
        emit(0xe1c000b0 | base << 16 | src << 12)

    literal(4, 0x400f0000)   # GPIOA bit16 is command/data line
    literal(5, 0xb0000000)
    literal(6, 0x10000)

    def cmd(value):
        store(6, 4, 8)      # PCOR: command (D/C LOW)
        literal(1, value)
        half(1, 5)
        store(6, 4, 4)      # PSOR: data (D/C HIGH)

    def val(value):
        literal(1, value)
        half(1, 5)

    def address_window(opcode, first, last):
        cmd(opcode)
        for value in (first >> 8, first & 255, last >> 8, last & 255):
            val(value)

    cmd(0x3a); val(0x55)     # RGB565
    cmd(0x36); val(madctl)   # Portrait/landscape MADCTL

    if madctl == 0x60:
        x0, x1, y0, y1 = 200, 201, 390, 392
    else:
        x0, x1, y0, y1 = 400, 402, 210, 211

    address_window(0x2a, x0, x1)
    address_window(0x2b, y0, y1)
    cmd(0x2c)
    for c in COLORS:
        val(c)
    val(0xffff)             # Seventh pixel: must NOT leak outside 2x3/3x2 window

    # Invalid CASET range that falls beyond the model's visible width:
    # this must not clamp to x=863 and smear pixels onto the edge.
    address_window(0x2a, 900, 901)
    address_window(0x2b, 100, 100)
    cmd(0x2c)
    val(0xffff)

    emit(0xeafffffe)        # spin in guest until QEMU screenshot timer
    pool_start = len(words)
    for i, (pos, reg, value) in enumerate(pool):
        off = (pool_start + i - pos) * 4 - 8
        if not 0 <= off <= 4095:
            raise ValueError("ARM literal pool too distant")
        words[pos] = 0xe59f0000 | reg << 12 | off
        words.append(value)

    body = struct.pack("<%dI" % len(words), *words)
    ident = b"\x7fELF\x01\x01\x01" + bytes(9)
    hdr = struct.pack("<16sHHIIIIIHHHHHH", ident, 2, 40, 1,
                      BASE, 52, 0, 0x05000000, 52, 32, 1, 0, 0, 0)
    ph = struct.pack("<8I", 1, 0x100, BASE, BASE, len(body),
                     len(body), 5, 0x100)
    return hdr + ph + bytes(0x100 - len(hdr) - len(ph)) + body


def pixel(rgb565):
    return bytes((((rgb565 >> 11) & 31) * 255 // 31,
                  ((rgb565 >> 5) & 63) * 255 // 63,
                  (rgb565 & 31) * 255 // 31))


def expected(madctl):
    if madctl == 0x60:
        # MV swaps address axes; MX mirrors the output X coordinate.
        return {(W - 1 - (390 + i % 3), 200 + i // 3): pixel(c)
                for i, c in enumerate(COLORS)}
    return {(400 + i % 3, 210 + i // 3): pixel(c)
            for i, c in enumerate(COLORS)}


def run(qemu, profile, madctl):
    with tempfile.TemporaryDirectory() as td:
        temp = Path(td)
        elf = temp / "lcd-orientation.elf"
        ppm = temp / "lcd-madctl.ppm"
        ini = temp / "lcd-profile.ini"
        elf.write_bytes(make_elf(madctl))
        ini.write_text(profile.read_text() +
                       "\n[lcd-orientation-test]\nkind=exesx-lcd\n"
                       "base=0xb0000000\nsize=0x1000\n")
        env = os.environ.copy()
        env["EXESX_MEMORY_PROFILE"] = str(ini)
        env["EXESX_EXPERIMENTAL_LCD"] = "1"
        env["EXESX_LCD_SCREENSHOT"] = str(ppm)
        lib = qemu.resolve().parent / "lib"
        if lib.is_dir():
            env["LD_LIBRARY_PATH"] = str(lib) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
        cmd = [str(qemu.resolve()), "-machine", "exesx", "-m", "64M",
               "-accel", "tcg", "-display", "none", "-serial", "none",
               "-monitor", "none", "-no-reboot", "-device",
               f"loader,file={elf},cpu-num=0"]
        try:
            subprocess.run(cmd, env=env, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=2.0, check=False)
        except subprocess.TimeoutExpired:
            pass
        if not ppm.is_file():
            raise AssertionError("No original-ARM synthetic LCD screenshot")
        raw = ppm.read_bytes()
        header = f"P6\n{W} {H}\n255\n".encode()
        if not raw.startswith(header) or len(raw) != len(header) + W * H * 3:
            raise AssertionError("Invalid framebuffer size")
        pixels = raw[len(header):]
        colored = {}
        for y in range(H):
            for x in range(W):
                start = (y * W + x) * 3
                value = pixels[start:start+3]
                if value != b"\x00\x00\x00":
                    colored[(x, y)] = value
        if colored != expected(madctl):
            raise AssertionError(
                f"MADCTL={madctl:#x}: expected {expected(madctl)}, "
                f"got {len(colored)} pixels, sample {list(colored.items())[:12]}")
    print(f"PASS original ARM MADCTL={madctl:#04x} centered geometry, inclusive "
          "window wrap and off-panel clipping")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, default=Path("build/qemu-system-arm"))
    parser.add_argument("--profile", type=Path,
                        default=Path("profiles/imx7ulp-early-boot.ini"))
    args = parser.parse_args()
    for mode in (0x00, 0x60):
        run(args.qemu, args.profile, mode)


if __name__ == "__main__":
    main()
