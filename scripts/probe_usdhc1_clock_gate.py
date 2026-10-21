#!/usr/bin/env python3
"""Bounded real ARM negative control: USDHC1 RSTA cannot create a root clock.

Run only after probe_upstream_emmc.py creates a synthetic sparse eMMC image.
Identical upstream host/card, but EXESX_USDHC1_INPUT_CLOCK=0. There must
be no SDSTB response even if the eMMC card is inserted or FORCE is written.
No proprietary firmware is uploaded or executed in CI.
"""
from pathlib import Path
import argparse
import os
import re
import struct
import subprocess
import time

BASE = 0x60000000
RESULTS = 0x6200C000


def make_elf():
    code, literals = [], []
    def emit(word): code.append(word)
    def literal(reg, value):
        literals.append((len(code), reg, value))
        emit(0)
    def ldr(dest, src, off=0):
        emit(0xe5900000 | src << 16 | dest << 12 | off)
    def strw(src, dest, off=0):
        emit(0xe5800000 | dest << 16 | src << 12 | off)

    literal(7, RESULTS)
    literal(0, 0x40380024)   # Same r0 value as the original Casio loop
    ldr(2, 0, 8)             # 0x60017134: LDR r2,[r0,#8]
    emit(0xe3822401)        # 0x60017138: ORR r2,r2,#0x01000000
    strw(2, 0, 8)            # 0x6001713c: STR r2,[r0,#8]
    ldr(2, 0, 0)            # 0x60017140: LDR r2,[r0]
    strw(2, 7, 0)            # Preserve status instead of infinite loop
    ldr(2, 0, 8)
    strw(2, 7, 4)            # Reset self-cleared
    ldr(2, 0, 0x9c)
    strw(2, 7, 8)            # Vendor register after reset
    literal(1, 0x100)
    strw(1, 0, 0x9c)         # Force SDCLK output (not input source)
    ldr(2, 0, 0)
    strw(2, 7, 12)
    emit(0xeafffffe)
    for pos, reg, value in literals:
        delta = len(code) * 4 - (pos * 4 + 8)
        if not 0 <= delta <= 4095:
            raise ValueError("ARM literal offset overflow")
        code[pos] = 0xe59f0000 | reg << 12 | delta
        code.append(value)
    payload = struct.pack(f"<{len(code)}I", *code)
    eh = struct.pack("<16sHHIIIIIHHHHHH", b"\x7fELF\x01\x01\x01" + bytes(9),
                     2, 40, 1, BASE, 52, 0, 0x05000000, 52, 32, 1, 0, 0, 0)
    ph = struct.pack("<8I", 1, 0x100, BASE, BASE, len(payload),
                     len(payload), 5, 0x100)
    return eh + ph + bytes(0x100 - len(eh) - len(ph)) + payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, default=Path("build/qemu-system-arm"))
    parser.add_argument("--profile", type=Path, default=Path("profiles/imx7ulp-early-boot.ini"))
    parser.add_argument("--image", type=Path, default=Path("build/emmc-synthetic-16gb.raw"))
    parser.add_argument("--elf", type=Path, default=Path("build/emmc-clock-gated.elf"))
    args = parser.parse_args()
    if not args.image.is_file():
        parser.error("Run probe_upstream_emmc.py first to create the synthetic card")
    args.elf.parent.mkdir(parents=True, exist_ok=True)
    args.elf.write_bytes(make_elf())
    env = os.environ.copy()
    env["EXESX_MEMORY_PROFILE"] = str(args.profile.resolve())
    env["EXESX_USDHC1_EMMC"] = "1"
    env["EXESX_USDHC1_INPUT_CLOCK"] = "0"
    lib = args.qemu.resolve().parent / "lib"
    if lib.is_dir():
        env["LD_LIBRARY_PATH"] = str(lib) + ":" + env.get("LD_LIBRARY_PATH", "")
    cmd = [str(args.qemu.resolve()), "-machine", "exesx", "-m", "64M",
           "-accel", "tcg", "-display", "none", "-serial", "none",
           "-monitor", "stdio", "-no-reboot",
           "-drive", f"if=none,id=exesx-emmc,file={args.image.resolve()},format=raw,snapshot=on",
           "-device", f"loader,file={args.elf.resolve()},cpu-num=0"]
    proc = subprocess.Popen(cmd, env=env, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        time.sleep(0.8)
        commands = "".join(f"xp /1wx 0x{RESULTS + i*4:08x}\n" for i in range(4)) + "quit\n"
        output, _ = proc.communicate(commands, timeout=20)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    results = []
    for i in range(4):
        m = re.search(r"(?im)^0*" + f"{RESULTS + i*4:08x}" +
                      r":\s+0x([0-9a-f]+)", output)
        if not m:
            raise AssertionError(f"Missing negative control result {i}: {output[-1800:]}")
        results.append(int(m.group(1), 16))
    if (results[0] & 8) or (results[3] & 8):
        raise AssertionError(f"Missing input clock incorrectly reported SDSTB: {results}")
    if results[1] & 0x01000000:
        raise AssertionError(f"SYS_CTRL.RSTA must self-clear: {results[1]:#x}")
    print("PASS: Casio RSTA with disabled i.MX7ULP input clock cannot "
          "raise SDSTB, even after VEND_SPEC.FRC_SDCLK_ON; results:",
          list(map(hex, results)))


if __name__ == "__main__":
    main()
