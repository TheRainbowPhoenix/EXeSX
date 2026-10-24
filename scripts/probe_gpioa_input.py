#!/usr/bin/env python3
"""Synthetic ARM/QEMU M4 PTA pin-level voltage diagnostic (not actual wiring).

Reuses the firmware-free GPIOB ARM guest, changing only its peripheral base
literal from M4 PTB to M4 PTA; tests input voltage and output precedence.
"""
import argparse
import os
from pathlib import Path
import struct
import tempfile
from probe_gpiob_input import guest_elf
from hmp_memory import qmp_memory_words

M4_GPIOB = 0x4100F040
M4_GPIOA = 0x4100F000
RESULT = 0x6200B400
INPUT_BITS = 0x808C6008


def gpioa_elf():
    program = guest_elf()
    old = struct.pack("<I", M4_GPIOB)
    if program.count(old) != 1:
        raise AssertionError("Ambiguous synthetic GPIOB address literal")
    return program.replace(old, struct.pack("<I", M4_GPIOA), 1)


def probe(qemu, profile, mask, elf):
    env = os.environ.copy()
    env["EXESX_MEMORY_PROFILE"] = str(profile.resolve())
    env["EXESX_GPIOA_INPUT_MASK"] = hex(mask)
    library = qemu.resolve().parent / "lib"
    if library.is_dir():
        env["LD_LIBRARY_PATH"] = str(library) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    cmd = [str(qemu.resolve()), "-machine", "exesx", "-m", "64M", "-accel", "tcg",
           "-display", "none", "-serial", "none", "-monitor", "stdio",
           "-no-reboot", "-device", f"loader,file={elf.resolve()},cpu-num=0"]
    return qmp_memory_words(cmd, env, RESULT, 3, delay=.5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, default=Path("build/qemu-system-arm"))
    parser.add_argument("--profile", type=Path,
                        default=Path("profiles/imx7ulp-early-boot.ini"))
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as folder:
        elf = Path(folder) / "gpioa-synthetic.elf"
        elf.write_bytes(gpioa_elf())
        for mask, expected in (
                (0, [0, 0x80, 0]),
                (INPUT_BITS, [INPUT_BITS, INPUT_BITS | 0x80, INPUT_BITS]),
                (INPUT_BITS | 0x80, [INPUT_BITS | 0x80, INPUT_BITS | 0x80, INPUT_BITS])):
            values = probe(args.qemu, args.profile, mask, elf)
            if values != expected:
                raise AssertionError(f"GPIOA mask {mask:#x}: actual {values}, expected {expected}")
            print(f"PASS synthetic M4 GPIOA PDIR external input mask={mask:#x}; PDDR output overrides input voltage")
    print("External pin values are a research input hypothesis, not physical board wiring.")


if __name__ == "__main__":
    main()
