#!/usr/bin/env python3
"""M4 LPIT0 IRQ49: real A7 ARM MMIO configuration, real M4 NVIC observation.

The guest's ARM program enables LPIT0 and programs original-style CH1
TVAL=12000 for 1ms at 12MHz, then idles. No IRQ/firmware/RTOS flag is
injected. The test reads M4's actual NVIC ISPR1 using QEMU's GDB view.
Negative controls: opt-in disabled, and LPIT0.MIER bit1 masked.
"""
import argparse
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import time
from drive_factory_menu import QMP, choose_port, connect
from probe_postdma_handoff import RSP

BASE, LPIT0 = 0x60000000, 0x4102D000
IRQ49 = 1 << 17


def synthetic_elf(mask):
    code, literals = [], []

    def lit(reg, word):
        literals.append((len(code), reg, word))
        code.append(0)

    def store(reg, base, off):
        code.append(0xe5800000 | base << 16 | reg << 12 | off)

    lit(0, LPIT0)
    lit(1, 1)
    store(1, 0, 8)        # MCR.M_CEN
    lit(1, 12000)
    store(1, 0, 0x30)     # LPIT0 channel 1, 1ms at 12MHz
    lit(1, 0x00840000)
    store(1, 0, 0x38)     # CH1 TCTRL original non-TEN fields
    lit(1, mask)
    store(1, 0, 0x10)     # LPIT0 MIER
    lit(1, 2)
    store(1, 0, 0x14)     # SETTEN CH1
    code.append(0xeafffffe)
    for offset, reg, word in literals:
        displacement = 4 * (len(code) - offset) - 8
        assert 0 <= displacement < 4096
        code[offset] = 0xe59f0000 | reg << 12 | displacement
        code.append(word)
    body = struct.pack(f"<{len(code)}I", *code)
    ident = b"\x7fELF\x01\x01\x01" + bytes(9)
    eh = struct.pack("<16sHHIIIIIHHHHHH", ident, 2, 40, 1,
                     BASE, 52, 0, 0x05000000, 52, 32, 1, 0, 0, 0)
    ph = struct.pack("<8I", 1, 0x100, BASE, BASE, len(body),
                     len(body), 5, 0x100)
    return eh + ph + bytes(0x100 - len(eh) - len(ph)) + body


def probe(qemu, profile, enabled, mask):
    with tempfile.TemporaryDirectory(prefix="exesx-lpit0-") as d:
        root = Path(d)
        elf = root / "lpit0.elf"
        elf.write_bytes(synthetic_elf(mask))
        env = os.environ.copy()
        env["EXESX_MEMORY_PROFILE"] = str(profile.resolve())
        if enabled:
            env["EXESX_EXPERIMENTAL_M4_LPIT0_IRQ"] = "1"
        else:
            env.pop("EXESX_EXPERIMENTAL_M4_LPIT0_IRQ", None)
        lib = qemu.resolve().parent / "lib"
        if lib.is_dir():
            env["LD_LIBRARY_PATH"] = str(lib) + os.pathsep + env.get(
                "LD_LIBRARY_PATH", "")
        qmp_port = choose_port()
        gdb_port = choose_port()
        while gdb_port == qmp_port:
            gdb_port = choose_port()
        cmd = [str(qemu.resolve()), "-machine", "exesx", "-m", "64M",
               "-accel", "tcg,thread=single", "-display", "none",
               "-serial", "none", "-monitor", "none", "-no-reboot", "-S",
               "-qmp", f"tcp:127.0.0.1:{qmp_port},server=on,wait=off",
               "-gdb", f"tcp:127.0.0.1:{gdb_port}",
               "-device", f"loader,file={elf},cpu-num=0"]
        with (root / "console.log").open("wb") as output:
            guest = subprocess.Popen(cmd, env=env, stdin=subprocess.DEVNULL,
                                     stdout=output, stderr=subprocess.STDOUT)
            try:
                with connect(qmp_port, guest) as qsocket:
                    qmp = QMP(qsocket)
                    qmp.execute("cont")
                    time.sleep(0.5)
                    qmp.execute("stop")
                    with socket.create_connection(("127.0.0.1", gdb_port), 4) as gs:
                        rsp = RSP(gs)
                        rsp.command("?")
                        if rsp.command("Hg2") != "OK":
                            raise RuntimeError("M4 GDB register view missing")
                        pending = rsp.memory(0xE000E204, 4)
                    if pending is None:
                        raise RuntimeError("M4 NVIC pending register unreadable")
                    import re
                    raw = qmp.hmp("xp /1wx 0x4102d00c")
                    match = re.search(r":\s+0x([0-9a-fA-F]+)", raw)
                    if not match:
                        raise RuntimeError(f"LPIT0 MSR missing: {raw}")
                    msr = int(match.group(1), 16)
                    return msr, pending
            finally:
                guest.terminate()
                try:
                    guest.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    guest.kill()
                    guest.wait()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--qemu", type=Path, required=True)
    p.add_argument("--profile", type=Path, required=True)
    a = p.parse_args()
    cases = [(False, 2, False), (True, 0, False),
             (True, 2, True)]
    for enabled, mask, expected in cases:
        msr, pending = probe(a.qemu, a.profile, enabled, mask)
        assert msr & 2, (enabled, mask, "LPIT0 CH1 did not expire", msr)
        assert bool(pending & IRQ49) == expected, (
            enabled, mask, hex(pending), expected)
        print(f"PASS LPIT0 enabled={enabled}, MIER={mask}, "
              f"MSR={msr:#x}, M4 IRQ49 pending={bool(pending & IRQ49)}")
    print("PASS genuine LPIT0 timer->Cortex-M4 IRQ49; no synthetic IRQ or RTOS event")


if __name__ == "__main__":
    main()
