#!/usr/bin/env python3
"""Verify source-derived M4 0x180x touch IPC handler assignments.

Optional --private-m4-bin checks the owner's original extracted M4 binary
locally. Without that flag, CI verifies lookup mechanics with fabricated
TEST DATA, never includes original proprietary code or ROM contents.
"""
import argparse
from pathlib import Path
import struct

BASE = 0x1FFD0000
GROUP_OFFSET = 0x3DC
EXPECTED = {
    0x1809: 0x1FFDC6CC,  # register-byte I2C handler
    0x180A: 0x1FFDC704,  # 14-byte packet I2C handler
    0x180B: 0x1FFDC730,
    0x180C: 0x1FFDC76A,  # FUN_1ffdc76a -> FUN_1ffdbc8c(arg)
    0x180E: 0x1FFDC794,
}


def original_handler(blob, command):
    if not 0x1800 <= command <= 0x1818:
        raise ValueError("Not an original M4 touch IPC command")
    offset = GROUP_OFFSET + (command - 0x1800) * 4
    if len(blob) < offset + 4:
        raise ValueError("M4 image truncated before dispatch pointer")
    thumb_pointer = struct.unpack_from("<I", blob, offset)[0]
    if not (thumb_pointer & 1):
        raise ValueError(f"M4 handler lacks Cortex-M Thumb bit: 0x{thumb_pointer:x}")
    return thumb_pointer & ~1


def validate(blob):
    for command, address in EXPECTED.items():
        found = original_handler(blob, command)
        if found != address:
            raise AssertionError(
                f"0x{command:04x}: handler 0x{found:08x}"
                f", expected 0x{address:08x}")
    print("PASS original touch dispatch: 1809=I2C read,"
          " 180A=14-byte packet, 180C=pen arm/disarm")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--private-m4-bin", type=Path,
                   help="Local owner's original M4 image; NEVER upload to GitHub")
    args = p.parse_args()
    if args.private_m4_bin:
        blob = args.private_m4_bin.read_bytes()
        if not (len(blob) >= 0x440 and
                struct.unpack_from("<I", blob, 0)[0] == 0x20001c00):
            raise ValueError("Not the owner-supplied original M4 vector image")
        print("Checking private original M4 dispatch table locally")
    else:
        blob = bytearray(0x450)
        for command, handler in EXPECTED.items():
            struct.pack_into("<I", blob, GROUP_OFFSET +
                             (command - 0x1800) * 4, handler | 1)
        # Deliberate corruption must be detected by the same decoder.
        bad = bytearray(blob)
        struct.pack_into("<I", bad, GROUP_OFFSET +
                         (0x180C - 0x1800) * 4, 0x1FFDC704 | 1)
        try:
            validate(bad)
        except AssertionError:
            pass
        else:
            raise AssertionError("Failed to reject wrong 0x180C M4 dispatcher")
    validate(blob)


if __name__ == "__main__":
    main()
