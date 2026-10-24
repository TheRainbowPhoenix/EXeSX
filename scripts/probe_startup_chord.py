#!/usr/bin/env python3
"""Synthetic ARM MMIO test of the original A7 BIOS startup chord.

The unchanged original A7 decomp checks 0x80+0x95+0x92 before entering
its version-dialog path. These source-derived contacts are electrically
sampled by real guest ARM GPIO/IOMUX instructions, NOT firmware events.
"""
import argparse
import os
from pathlib import Path
import struct
import tempfile
from hmp_memory import qmp_memory_words

BASE, RESULT = 0x60000000, 0x6200B900
GPIO_A, GPIO_B, IOMUX = 0x4100F000, 0x4100F040, 0x4103D000


def make_elf():
    code, lits = [], []

    def lit(reg, value):
        lits.append((len(code), reg, value))
        code.append(0)

    def store(src, base, offset):
        code.append(0xe5800000 | base << 16 | src << 12 | offset)

    def load(dst, base, offset):
        code.append(0xe5900000 | base << 16 | dst << 12 | offset)

    lit(0, GPIO_A)
    lit(1, GPIO_B)
    lit(3, IOMUX)
    lit(4, 0x20100)
    lit(5, 0)
    lit(7, RESULT)

    # B2 row0 -> B6 column0, original key 0x80.
    lit(6, 1 << 2)
    store(6, 1, 0x14)
    store(6, 1, 0x04)
    store(4, 3, 0x88)
    store(6, 1, 0x08)
    load(2, 1, 0x10)
    store(2, 7, 0)
    store(5, 3, 0x88)
    store(6, 1, 0x04)

    # A16 row5 -> A23 column6, original key 0x95.
    # A20 row7 -> A31 column7, original key 0x92.
    lit(6, (1 << 16) | (1 << 20))
    store(6, 0, 0x14)
    store(6, 0, 0x04)
    lit(6, 1 << 16)
    store(4, 3, 0x40)
    store(6, 0, 0x08)
    load(2, 0, 0x10)
    store(2, 7, 4)
    store(5, 3, 0x40)
    store(6, 0, 0x04)

    lit(6, 1 << 20)
    store(4, 3, 0x50)
    store(6, 0, 0x08)
    load(2, 0, 0x10)
    store(2, 7, 8)
    store(5, 3, 0x50)
    code.append(0xeafffffe)

    pool = len(code)
    for n, (pos, reg, value) in enumerate(lits):
        displacement = 4 * (pool + n - pos) - 8
        assert 0 <= displacement < 4096
        code[pos] = 0xe59f0000 | (reg << 12) | displacement
        code.append(value)

    body = struct.pack(f"<{len(code)}I", *code)
    ident = b'\x7fELF\x01\x01\x01' + bytes(9)
    header = struct.pack("<16sHHIIIIIHHHHHH", ident, 2, 40, 1,
                         BASE, 52, 0, 0x05000000, 52, 32, 1, 0, 0, 0)
    program = struct.pack("<8I", 1, 0x100, BASE, BASE,
                          len(body), len(body), 5, 0x100)
    return header + program + bytes(0x100 - len(header) - len(program)) + body


def read(qemu, profile, code):
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        contact = directory / "physical-contact.txt"
        contact.write_text(code + "\n", encoding="ascii")
        elf = directory / "startup-chord.elf"
        elf.write_bytes(make_elf())
        env = os.environ.copy()
        env.update(EXESX_MEMORY_PROFILE=str(profile.resolve()),
                   EXESX_M4_KEY_MATRIX_FILE=str(contact.resolve()),
                   EXESX_GPIOA_INPUT_MASK="0x808c6008",
                   EXESX_GPIOB_INPUT_MASK="0xc8")
        library = qemu.resolve().parent / "lib"
        if library.is_dir():
            env["LD_LIBRARY_PATH"] = (
                str(library) + os.pathsep + env.get("LD_LIBRARY_PATH", ""))
        cmd = [str(qemu.resolve()), "-machine", "exesx", "-m", "64M",
               "-accel", "tcg", "-display", "none", "-serial", "none",
               "-monitor", "stdio", "-no-reboot",
               "-device", f"loader,file={elf.resolve()},cpu-num=0"]
        return qmp_memory_words(cmd, env, RESULT, 3, delay=0.6)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, default=Path("build/qemu-system-arm"))
    parser.add_argument("--profile", type=Path,
                        default=Path("profiles/imx7ulp-early-boot.ini"))
    args = parser.parse_args()

    tests = [
        ("no contact", "0", [False, False, False]),
        ("all original startup keys", "0x80,0x95,0x92", [True, True, True]),
        ("missing 0x92", "0x80,0x95", [True, True, False]),
        ("unknown code fail-safe", "0x80,0xbeef,0x92", [False, False, False]),
    ]
    for name, code, expected in tests:
        b0, a5, a7 = read(args.qemu, args.profile, code)
        actual = [not bool(b0 & (1 << 6)),
                  not bool(a5 & (1 << 23)),
                  not bool(a7 & (1 << 31))]
        assert actual == expected, (name, actual, expected)
        print(f"PASS {name}: genuine ARM row/column contact readings {actual}")

if __name__ == "__main__":
    main()
