#!/usr/bin/env python3
"""Firmware-free ARM test: NACK vs isolated 8-bit register-mirror diagnosis."""
import argparse
import os
from pathlib import Path
import re
import struct
import subprocess

BASE = 0x60000000
OUT = 0x62006000


def make_elf():
    insns = []
    literals = []
    def ins(x):
        insns.append(x)
    def lit(reg, val):
        literals.append((len(insns), reg, val))
        ins(0)
    def store(reg, base, off=0):
        ins(0xe5800000 | (base << 16) | (reg << 12) | off)
    def load(reg, base, off=0):
        ins(0xe5900000 | (base << 16) | (reg << 12) | off)
    lit(7, OUT)
    lit(0, 0x41035000)
    lit(1, 1)
    store(1, 0, 0x10)
    # Set register 0x14 to 0x62, STOP, address it, then read one byte.
    for word in (0x496, 0x14, 0x62, 0x200, 0x496, 0x14, 0x497, 0x100):
        lit(1, word)
        store(1, 0, 0x60)
    load(2, 0, 0x70)
    store(2, 7)
    ins(0xeafffffe)
    for index, reg, value in literals:
        pool = len(insns) * 4
        insns.append(value)
        displacement = pool - (index * 4 + 8)
        assert 0 <= displacement < 4096
        insns[index] = 0xe59f0000 | (reg << 12) | displacement
    payload = struct.pack(f"<{len(insns)}I", *insns)
    ident = b"\x7fELF\x01\x01\x01" + bytes(9)
    header = struct.pack("<16sHHIIIIIHHHHHH", ident, 2, 40, 1, BASE, 52, 0,
                         0x05000000, 52, 32, 1, 0, 0, 0)
    segment = struct.pack("<8I", 1, 0x100, BASE, BASE, len(payload),
                          len(payload), 5, 0x100)
    return header + segment + bytes(0x100 - len(header) - len(segment)) + payload


def run(qemu: Path, profile: Path, elf: Path, mirror: bool) -> int:
    env = os.environ.copy()
    env["EXESX_MEMORY_PROFILE"] = str(profile.resolve())
    env.pop("EXESX_I2C4B_REPLY_HEX", None)
    env.pop("EXESX_I2C4B_REGISTER_MIRROR", None)
    if mirror:
        env["EXESX_I2C4B_REGISTER_MIRROR"] = "1"
    lib = qemu.resolve().parent / "lib"
    if lib.is_dir():
        env["LD_LIBRARY_PATH"] = str(lib) + ":" + env.get("LD_LIBRARY_PATH", "")
    cmd = [str(qemu.resolve()), "-machine", "exesx", "-m", "64M",
           "-accel", "tcg", "-display", "none", "-serial", "none",
           "-monitor", "stdio", "-no-reboot",
           "-device", f"loader,file={elf.resolve()},cpu-num=0"]
    output = subprocess.run(cmd, input=f"xp /1wx 0x{OUT:08x}\nquit\n",
                            capture_output=True, text=True, env=env,
                            timeout=15, check=True).stdout
    match = re.search(rf"{OUT:08x}:\s+0x([0-9a-fA-F]+)", output)
    if not match:
        raise AssertionError("QEMU monitor result missing: " + output[-1500:])
    return int(match.group(1), 16)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, default=Path("build/qemu-system-arm"))
    parser.add_argument("--profile", type=Path,
                        default=Path("profiles/imx7ulp-early-boot.ini"))
    parser.add_argument("--elf", type=Path,
                        default=Path("build/i2c4b-register-mirror.elf"))
    args = parser.parse_args()
    args.elf.parent.mkdir(parents=True, exist_ok=True)
    args.elf.write_bytes(make_elf())
    actual = (run(args.qemu, args.profile, args.elf, False),
              run(args.qemu, args.profile, args.elf, True))
    if actual != (0x4000, 0x62):
        raise AssertionError(f"NACK/RX mirror mismatch: {tuple(map(hex, actual))}")
    print("PASS: default NACK/RXEMPTY, opt-in readback of actual 0x14=0x62")


if __name__ == "__main__":
    main()
