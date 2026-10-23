#!/usr/bin/env python3
"""Verify A7 LPIT1/GIC25 interrupt with real synthetic ARM, no Casio firmware.

Three negative/positive cases: disabled bridge, masked LPIT MIER, active IRQ.
Guest secure ARM reads GICD enable/pending registers into RAM so host
monitor does not accidentally read the nonsecure GIC view.
"""
import argparse
import os
from pathlib import Path
import re
import struct
import subprocess
import time
from hmp_memory import memory_words, qmp_memory_words

BASE = 0x60000000
OUT = 0x6200b200
LPIT = 0x40270000
GICD = 0x40021000
SPI25 = 1 << 25


def make_elf(mask):
    words, literals = [], []

    def emit(w):
        words.append(w)

    def lit(reg, value):
        literals.append((len(words), reg, value))
        emit(0)

    def store(src, base, off):
        emit(0xe5800000 | (base << 16) | (src << 12) | off)

    lit(3, GICD)
    lit(1, SPI25)
    store(1, 3, 0x104)            # GICD.ISENABLER1 for IRQ ID=57
    lit(1, 1)
    store(1, 3, 0)                # GICD.CTLR enable
    lit(7, OUT)
    emit(0xe5932104)             # LDR r2,[r3,#0x104], SECURE GIC read
    store(2, 7, 0)

    lit(0, LPIT)
    lit(1, 1)
    store(1, 0, 0x08)            # LPIT.MCR module enable
    lit(1, 10000)
    store(1, 0, 0x20)            # LPIT channel0 TVAL
    lit(1, 1)
    store(1, 0, 0x28)            # LPIT channel0 TCTRL enable
    lit(1, mask)
    store(1, 0, 0x10)            # LPIT.MIER

    loop = len(words)
    emit(0xe5932204)             # Secure GICD.ISPENDR1
    store(2, 7, 4)
    emit(0xe590200c)             # LPIT.MSR
    store(2, 7, 8)
    i = len(words)
    emit(0xea000000 | ((loop - i - 2) & 0xffffff))

    for pos, reg, val in literals:
        displacement = len(words) * 4 - (pos * 4 + 8)
        assert 0 <= displacement < 4096
        words[pos] = 0xe59f0000 | (reg << 12) | displacement
        words.append(val)
    body = struct.pack("<%dI" % len(words), *words)
    ident = b"\x7fELF\x01\x01\x01" + bytes(9)
    eh = struct.pack("<16sHHIIIIIHHHHHH", ident, 2, 40, 1,
                     BASE, 52, 0, 0x05000000, 52, 32, 1, 0, 0, 0)
    ph = struct.pack("<8I", 1, 0x100, BASE, BASE,
                     len(body), len(body), 5, 0x100)
    return eh + ph + bytes(0x100 - len(eh) - len(ph)) + body


def probe(qemu, profile, elf, enabled, mask):
    elf.write_bytes(make_elf(mask))
    env = os.environ.copy()
    env["EXESX_MEMORY_PROFILE"] = str(profile.resolve())
    lib = qemu.resolve().parent / "lib"
    if lib.is_dir():
        env["LD_LIBRARY_PATH"] = str(lib) + ":" + env.get("LD_LIBRARY_PATH", "")
    if enabled:
        env["EXESX_EXPERIMENTAL_LPIT1_IRQ"] = "1"
    else:
        env.pop("EXESX_EXPERIMENTAL_LPIT1_IRQ", None)
    cmd = [str(qemu.resolve()), "-machine", "exesx", "-m", "64M",
           "-accel", "tcg", "-display", "none", "-serial", "none",
           "-monitor", "stdio", "-no-reboot",
           "-device", f"loader,file={elf.resolve()},cpu-num=0"]
    if os.name == "nt":
        return qmp_memory_words(cmd, env, OUT, 3)
    guest = subprocess.Popen(cmd, env=env, stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True)
    try:
        time.sleep(2.0 if os.name == 'nt' else 0.5)
        script = f"stop\nxp /3wx 0x{OUT:08x}\nquit\n"
        output, _ = guest.communicate(script, timeout=12)
    finally:
        if guest.poll() is None:
            guest.kill()
            guest.wait()
    return memory_words(output, OUT, 3)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--qemu", type=Path, default=Path("build/qemu-system-arm"))
    ap.add_argument("--profile", type=Path,
                    default=Path("profiles/imx7ulp-early-boot.ini"))
    ap.add_argument("--elf", type=Path,
                    default=Path("build/a7-lpit1-irq-probe.elf"))
    a = ap.parse_args()
    a.elf.parent.mkdir(parents=True, exist_ok=True)
    for enabled, mask, expected_pending in (
            (False, 1, 0),
            (True, 0, 0),
            (True, 1, SPI25)):
        gic_enable, pending, timer_status = probe(
            a.qemu, a.profile, a.elf, enabled, mask)
        assert gic_enable & SPI25, "GIC SPI25 not enabled by guest ARM"
        assert timer_status & 1, "Actual LPIT timer did not reach MSR expiry"
        assert (pending & SPI25) == expected_pending, (
            f"LPIT1 IRQ mode={enabled} MIER={mask}, "
            f"GIC pending={pending:#x}, expected {expected_pending:#x}")
    print("PASS real ARM LPIT1 expiry without bridge does not raise GIC25")
    print("PASS real ARM LPIT1 MIER=0 masks IRQ despite true timer expiry")
    print("PASS real ARM LPIT1 MIER=1 + opt-in bridge raises actual GIC SPI25")


if __name__ == "__main__":
    main()
