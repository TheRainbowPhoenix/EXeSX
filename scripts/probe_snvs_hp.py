#!/usr/bin/env python3
"""Firmware-free real ARM test of bounded i.MX7ULP SNVS HPCOMR / HPCR model.

The default test never invokes security violations. --diagnostic exercises
opt-in, explicitly *unimplemented* security-violation command pulses; it
DOES NOT emulate a trusted state or timekeeping.
"""
from pathlib import Path
import argparse
import os
import re
import struct
import subprocess
import time

BASE = 0x60000000
OUT = 0x6200A300
SNVS = 0x41070000


def make_elf(diagnostic=False):
    code = []
    literal_relocations = []

    def emit(word): code.append(word)
    def lit(reg, value):
        literal_relocations.append((len(code), reg, value))
        emit(0)
    def load(reg, base, offset=0):
        emit(0xE5900000 | base << 16 | reg << 12 | offset)
    def store(reg, base, offset=0):
        emit(0xE5800000 | base << 16 | reg << 12 | offset)

    lit(7, OUT)
    lit(0, SNVS)
    load(2, 0, 4); store(2, 7, 0)  # HPCOMR reset = 0
    lit(1, 0x10)
    store(1, 0, 4)                 # HPCOMR LP_SWR command pulse
    load(2, 0, 4); store(2, 7, 4)  # command self-clears
    lit(1, 1)
    store(1, 0, 8)                 # HPCR RTC_EN
    load(2, 0, 8); store(2, 7, 8)
    lit(1, 0x20)
    store(1, 0, 4)                 # HPCOMR LP_SWR_DIS sticky
    load(2, 0, 4); store(2, 7, 12)
    lit(1, 0x30)
    store(1, 0, 4)                 # LP_SWR pulse blocked by LP_SWR_DIS
    load(2, 0, 4); store(2, 7, 16)
    if diagnostic:
        lit(1, 0x500)
        store(1, 0, 4)             # security violations, NO state change
        load(2, 0, 4); store(2, 7, 20)  # pulsed flags never stick
        load(2, 0, 8); store(2, 7, 24)  # RTC control remains 1
    emit(0xEAFFFFFE)
    for index, reg, value in literal_relocations:
        offset = len(code) * 4 - (index * 4 + 8)
        if not 0 <= offset < 4096:
            raise ValueError("ARM literal outside 12-bit range")
        code[index] = 0xE59F0000 | (reg << 12) | offset
        code.append(value)
    program = struct.pack(f"<{len(code)}I", *code)
    ident = b"\x7fELF\x01\x01\x01" + bytes(9)
    elf = struct.pack("<16sHHIIIIIHHHHHH", ident, 2, 40, 1, BASE, 52, 0,
                      0x05000000, 52, 32, 1, 0, 0, 0)
    elf += struct.pack("<8I", 1, 0x100, BASE, BASE, len(program),
                       len(program), 5, 0x100)
    return elf + bytes(0x100 - len(elf)) + program


def run(qemu: Path, profile: Path, elf: Path, count: int, diagnostic: bool):
    env = os.environ.copy()
    env["EXESX_MEMORY_PROFILE"] = str(profile.resolve())
    env["EXESX_SNVS_DIAGNOSTIC_SECURITY_PULSES"] = "1" if diagnostic else "0"
    lib = qemu.resolve().parent / "lib"
    if lib.is_dir():
        env["LD_LIBRARY_PATH"] = str(lib) + ":" + env.get("LD_LIBRARY_PATH", "")
    cmd = [str(qemu.resolve()), "-machine", "exesx", "-m", "64M", "-accel", "tcg",
           "-display", "none", "-serial", "none", "-monitor", "stdio",
           "-no-reboot", "-device", f"loader,file={elf.resolve()},cpu-num=0"]
    guest = subprocess.Popen(cmd, env=env, stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True)
    try:
        time.sleep(0.45)
        commands = "".join(f"xp /1wx 0x{OUT+4*i:08x}\n" for i in range(count)) + "quit\n"
        log, _ = guest.communicate(commands, timeout=15)
    finally:
        if guest.poll() is None:
            guest.kill()
            guest.wait()
    results = []
    for i in range(count):
        match = re.search(r"(?im)^0*" + f"{OUT+4*i:08x}" +
                          r":\s+0x([0-9a-f]+)", log)
        if not match:
            raise AssertionError(f"Missing guest output word #{i}: {log[-1300:]}")
        results.append(int(match.group(1), 16))
    return results, log


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--qemu", type=Path, default=Path("build/qemu-system-arm"))
    p.add_argument("--profile", type=Path,
                   default=Path("profiles/imx7ulp-early-boot.ini"))
    p.add_argument("--elf", type=Path, default=Path("build/snvs-hp-probe.elf"))
    p.add_argument("--diagnostic", action="store_true")
    a = p.parse_args()
    a.elf.parent.mkdir(parents=True, exist_ok=True)
    a.elf.write_bytes(make_elf(a.diagnostic))
    count = 7 if a.diagnostic else 5
    actual, log = run(a.qemu, a.profile, a.elf, count, a.diagnostic)
    expected = [0, 0, 1, 0x20, 0x20] + ([0, 1] if a.diagnostic else [])
    if actual != expected:
        raise AssertionError(f"SNVS guest ARM: {list(map(hex,actual))} "
                             f"!= {list(map(hex,expected))}")
    if a.diagnostic and "DIAGNOSTIC security command pulse" not in log:
        raise AssertionError("Missing explicit diagnostic warning for security pulse")
    print("PASS SNVS guest ARM: HPCOMR pulse/reset/readback, RTC_EN, LP reset disable")
    if a.diagnostic:
        print("PASS diagnostic-only security command pulses; NO secure state emulated")


if __name__ == "__main__":
    main()
