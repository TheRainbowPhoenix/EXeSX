#!/usr/bin/env python3
"""Original M4 TPM0 timer hardware behavior under actual ARM guest instructions.

No Casio firmware or debugger-injected RTOS events. A synthetic Cortex-A7
program configures TPM0.MOD=0x5dc and TPM0.SC (CMOD/TOIE), as the actual
original M4 FUN_1FFDB7C2(0) does. Observe real TPM0.SC.TOF and NVIC IRQ38
after the guest virtual clock runs. Negative controls disable the bridge,
disable TOIE, or stop the hardware clock.
"""
import argparse
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import time

from drive_factory_menu import QMP, connect, choose_port
from probe_postdma_handoff import RSP
from hmp_memory import memory_words

TPM0 = 0x41030000
NVIC_ISPR1 = 0xe000e204
BIT38 = 1 << (38 - 32)
ENTRY = 0x60000000


def original_tpm0_setup_elf(sc):
    words = []
    literals = []

    def literal(reg, value):
        literals.append((len(words), reg, value))
        words.append(0)

    def store(reg, base, off):
        words.append(0xe5800000 | base << 16 | reg << 12 | off)

    literal(0, TPM0)
    literal(1, 0x5dc)  # original 1500-count TPM0 modulo
    store(1, 0, 0x18)
    literal(1, 0)
    store(1, 0, 0x14)  # reset count
    literal(1, sc)
    store(1, 0, 0x10)  # TPM0.SC: TOIE bit6, CMOD bit3
    words.append(0xeafffffe)
    pool = len(words)
    for index, (pos, reg, value) in enumerate(literals):
        offset = 4 * (pool + index - pos) - 8
        assert 0 <= offset < 4096
        words[pos] = 0xe59f0000 | reg << 12 | offset
        words.append(value)
    body = struct.pack("<%dI" % len(words), *words)
    ident = b"\x7fELF\x01\x01\x01" + bytes(9)
    head = struct.pack("<16sHHIIIIIHHHHHH", ident, 2, 40, 1,
                       ENTRY, 52, 0, 0x05000000, 52, 32, 1, 0, 0, 0)
    phdr = struct.pack("<8I", 1, 0x100, ENTRY, ENTRY,
                       len(body), len(body), 5, 0x100)
    return head + phdr + bytes(0x100 - len(head) - len(phdr)) + body


def run(qemu, profile, enable, sc):
    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        elf = folder / "tpm0-original-guest-program.elf"
        elf.write_bytes(original_tpm0_setup_elf(sc))
        env = os.environ.copy()
        env["EXESX_MEMORY_PROFILE"] = str(profile.resolve())
        env["EXESX_EXPERIMENTAL_M4_TPM0_IRQ"] = "1" if enable else "0"
        env["EXESX_EXPERIMENTAL_M4_TPM0_INPUT_MHZ"] = "1"
        lib = qemu.resolve().parent / "lib"
        if lib.is_dir():
            env["LD_LIBRARY_PATH"] = str(lib) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
        qmp_port = choose_port()
        gdb_port = choose_port()
        while gdb_port == qmp_port:
            gdb_port = choose_port()
        args = [str(qemu.resolve()), "-machine", "exesx", "-m", "64M",
                "-accel", "tcg", "-display", "none", "-serial", "none",
                "-monitor", "none", "-no-reboot",
                "-device", f"loader,file={elf.resolve()},cpu-num=0",
                "-qmp", f"tcp:127.0.0.1:{qmp_port},server=on,wait=off",
                "-gdb", f"tcp:127.0.0.1:{gdb_port}"]
        process = subprocess.Popen(args, env=env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            with connect(qmp_port, process) as socket:
                qmp = QMP(socket)
                # Allow the real synthetic ARM code to program TPM0 and
                # several QEMU virtual timer overflows to occur.
                time.sleep(0.3)
                qmp.execute("stop")
                tpm_sc = memory_words(qmp.hmp(f"xp /1wx {TPM0 + 0x10:#x}"),
                                      TPM0 + 0x10, 1)[0]
                modulo = memory_words(qmp.hmp(f"xp /1wx {TPM0 + 0x18:#x}"),
                                       TPM0 + 0x18, 1)[0]
                assert modulo == 1500, f"ARM guest did not set TPM0.MOD: {modulo:#x}"
                assert tpm_sc & 0x48 == sc & 0x48, \
                    f"ARM guest did not set TPM0.SC: {tpm_sc:#x}"
                # Connecting GDB at launch can stop QEMU TCG virtual
                # timers; only attach now, after QMP stopped the guest.
                with connect(gdb_port, process) as gdb_socket:
                    rsp = RSP(gdb_socket)
                    rsp.command("?")
                    assert rsp.command("Hg2") == "OK"
                    pending = rsp.memory(NVIC_ISPR1, 4)
                    if pending is None:
                        raise AssertionError("Cannot read actual M4 NVIC ISPR1")
                expect_tof = bool(enable and (sc & 0x08))
                expect_irq = expect_tof and bool(sc & 0x40)
                assert bool(tpm_sc & 0x80) == expect_tof, \
                    f"TOF mismatch: enabled={enable} SC={sc:#x} observed={tpm_sc:#x}"
                assert bool(pending & BIT38) == expect_irq, \
                    f"IRQ38 mismatch: enabled={enable} SC={sc:#x} pending={pending:#x}"
                print(f"PASS TPM0 enabled={enable} guest_SC={sc:#x}, "
                      f"read_SC={tpm_sc:#x}, M4_IRQ38_pending={bool(pending & BIT38)}")
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, default=Path("build/qemu-system-arm"))
    parser.add_argument("--profile", type=Path,
                        default=Path("profiles/imx7ulp-early-boot.ini"))
    args = parser.parse_args()
    for enabled, sc in ((False, 0x48), (True, 0x08),
                        (True, 0x40), (True, 0x48)):
        run(args.qemu, args.profile, enabled, sc)
    print("PASS original TPM0 MOD/SC -> hardware TOF -> M4 IRQ38, no synthetic key events")


if __name__ == "__main__":
    main()
