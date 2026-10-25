#!/usr/bin/env python3
"""Windows/Linux QMP RGB565 framebuffer export (no guest timers, no injections).

Requires an EXeSX build with EXESX_LCD_FRAMEBUFFER_EXPORT=1. The guest LCD
appears as read-only diagnostic region 0xb1000000, 864*480*2 bytes.
QEMU's HMP pmemsave performs a synchronous bus read, not a QEMU screenshot
timer or an original firmware RAM write. Never use a real hardware drive.
"""
from pathlib import Path
import os
import sys

WIDTH, HEIGHT = 864, 480
PHYSICAL_ADDRESS = 0xb1000000
FRAME_BYTES = WIDTH * HEIGHT * 2

def rgb565_to_rgb888(raw):
    if len(raw) != FRAME_BYTES:
        raise ValueError("incomplete RGB565 frame: {} bytes".format(len(raw)))
    result = bytearray(WIDTH * HEIGHT * 3)
    for i in range(WIDTH * HEIGHT):
        p = raw[2*i] | raw[2*i+1] << 8
        j = i * 3
        result[j] = ((p >> 11) & 31) * 255 // 31
        result[j+1] = ((p >> 5) & 63) * 255 // 63
        result[j+2] = (p & 31) * 255 // 31
    return bytes(result)

def capture_frame(qmp, raw_path, ppm_path=None):
    raw_path = Path(raw_path).resolve()
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    # The monitor parses this path as an argument, not as a Windows command.
    # Forward slashes are understood by MinGW fopen and avoid HMP backslash
    # escaping. No double quote can be allowed inside monitor command.
    path = raw_path.as_posix()
    if '"' in path or "\n" in path:
        raise ValueError("unsupported monitor capture filename")
    raw_path.unlink(missing_ok=True)
    answer = qmp.hmp("pmemsave 0x{:x} {} \"{}\"".format(
        PHYSICAL_ADDRESS, FRAME_BYTES, path))
    if not raw_path.is_file():
        raise RuntimeError("QMP framebuffer export failed: {}".format(answer))
    frame = raw_path.read_bytes()
    if len(frame) != FRAME_BYTES:
        raise RuntimeError("incomplete synchronous framebuffer export")
    if ppm_path:
        ppm = Path(ppm_path)
        payload = b"P6\n864 480\n255\n" + rgb565_to_rgb888(frame)
        staging = ppm.with_suffix(ppm.suffix + ".new")
        staging.write_bytes(payload)
        os.replace(staging, ppm)
    return frame

def main():
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("raw", type=Path, help="Private file written by a running QEMU")
    a = p.parse_args()
    if len(a.raw.read_bytes()) != FRAME_BYTES:
        p.error("wrong framebuffer size")
    print("RGB565 frame verified:", a.raw)

if __name__ == "__main__":
    main()
