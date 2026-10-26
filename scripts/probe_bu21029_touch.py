#!/usr/bin/env python3
"""Firmware-free ARM BU21029 controller + M4 PORTB3 pen IRQ regression."""
import argparse
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import time

from drive_factory_menu import QMP, choose_port, connect

BASE, OUT, I2C = 0x60000000, 0x62008300, 0x41035000


def synthetic_elf():
    ins, literals = [], []

    def emit(word):
        ins.append(word)

    def lit(reg, value):
        literals.append((len(ins), reg, value))
        emit(0)

    def load(reg, base, offset=0):
        emit(0xe5900000 | base << 16 | reg << 12 | offset)

    def store(reg, base, offset=0):
        emit(0xe5800000 | base << 16 | reg << 12 | offset)

    def output(slot):
        store(2, 7, 4 * slot)

    def command(value):
        lit(1, value)
        store(1, 0, 0x60)

    def start(addr):
        command(0x400 | addr)

    def read_reg(reg, slot):
        start(0x80)
        command(reg)
        command(0x200)
        start(0x81)
        command(0x100)
        load(2, 0, 0x70)
        output(slot)

    lit(7, OUT)
    lit(0, I2C)
    lit(1, 1)
    store(1, 0, 0x10)
    start(0x80)
    load(2, 0, 0x14)
    output(0)
    command(0x80)    # trigger original BU21029 continuous autoscan mode
    read_reg(0x68, 1)  # BU21029 STATUS register 0x0d
    read_reg(0x70, 2)  # ID high
    read_reg(0x78, 3)  # ID low
    start(0x80)
    command(0x84)
    command(0x200)
    start(0x81)
    command(0x10d)    # original M4 requests 14 bytes
    for i in range(14):
        load(2, 0, 0x70)
        output(4 + i)
    lit(0, 0x4100f040)
    load(2, 0, 0x10)
    output(18)         # GPIOB PDIR: PEN_INT is bit3, active-low
    lit(0, 0x41040000)
    lit(1, 0x80000)
    store(1, 0, 0x0c) # PORTB.PCR3 IRQC=8 (logic-zero)
    # Polling IRQ runs in M4 virtual time after CPU reaches a tight loop.
    emit(0xeafffffe)
    for pos, reg, value in literals:
        off = len(ins) * 4 - (pos * 4 + 8)
        assert 0 <= off < 4096
        ins[pos] = 0xe59f0000 | reg << 12 | off
        ins.append(value)
    body = struct.pack("<%dI" % len(ins), *ins)
    ident = b"\x7fELF\x01\x01\x01" + bytes(9)
    eh = struct.pack("<16sHHIIIIIHHHHHH", ident, 2, 40, 1,
                     BASE, 52, 0, 0x05000000, 52, 32, 1, 0, 0, 0)
    ph = struct.pack("<8I", 1, 0x100, BASE, BASE, len(body), len(body), 5, 0x100)
    return eh + ph + bytes(0x100 - len(eh) - len(ph)) + body


def run(qemu, profile, enabled=False, contact=None):
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        elf = root / "bu21029-arm.elf"
        elf.write_bytes(synthetic_elf())
        log = root / "qemu.log"
        env = os.environ.copy()
        for key in ("EXESX_BU21029_LPI2C_BUS", "EXESX_BU21029_TOUCH_FILE",
                    "EXESX_I2C40_REGISTER_MIRROR", "EXESX_I2C4B_REPLY_HEX",
                    "EXESX_I2C40_REGISTER_MIRROR", "EXESX_I2C4B_REGISTER_MIRROR"):
            env.pop(key, None)
        env["EXESX_MEMORY_PROFILE"] = str(profile)
        env["EXESX_GPIOB_INPUT_MASK"] = "0x88"
        env["EXESX_EXPERIMENTAL_M4_PORT_IRQ"] = "1"
        if enabled:
            env["EXESX_BU21029_LPI2C_BUS"] = "2"
        if contact is not None:
            inp = root / "contact.txt"
            inp.write_text(contact, encoding="ascii")
            env["EXESX_BU21029_TOUCH_FILE"] = str(inp)
        lib = qemu.parent / "lib"
        if lib.is_dir():
            env["LD_LIBRARY_PATH"] = str(lib) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
        port = choose_port()
        cmd = [str(qemu), "-machine", "exesx", "-m", "64M",
               "-accel", "tcg", "-display", "none", "-serial", "none",
               "-monitor", "none", "-no-reboot", "-S",
               "-d", "unimp,guest_errors", "-D", str(log),
               "-qmp", f"tcp:127.0.0.1:{port},server=on,wait=off",
               "-device", f"loader,file={elf},cpu-num=0"]
        with (root / "console.log").open("wb") as stdout:
            child = subprocess.Popen(cmd, env=env, stdin=subprocess.DEVNULL,
                                     stdout=stdout, stderr=subprocess.STDOUT)
            try:
                with connect(port, child) as sock:
                    qmp = QMP(sock)
                    qmp.execute("cont")
                    time.sleep(1.0)
                    def read_word(addr):
                        value = qmp.hmp(f"xp /1wx 0x{addr:x}")
                        m = re.search(r":\s+0x([0-9a-fA-F]+)", value)
                        assert m, value
                        return int(m.group(1), 16)
                    data = [read_word(OUT + 4 * i) for i in range(19)]
                    isfr = read_word(0x410400a0)
                    return data, isfr, log.read_text(encoding="utf-8", errors="replace")
            finally:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--qemu", type=Path, required=True)
    p.add_argument("--profile", type=Path, required=True)
    args = p.parse_args()
    qemu, profile = args.qemu.resolve(), args.profile.resolve()
    absent, none_irq, _ = run(qemu, profile, False, "1 291 2748")
    assert absent[0] == 0x401 and absent[1:18] == [0x4000] * 17, absent
    assert absent[18] & 8 and not (none_irq & 8), (absent, none_irq)
    released, released_irq, _ = run(qemu, profile, True, "0 291 2748")
    assert released[0] == 1 and released[1:4] == [0x48, 0x02, 0x29], released
    assert released[4:18] == [0] * 14, released
    assert released[18] & 8 and not (released_irq & 8), (released, released_irq)
    pressed, pressed_irq, logs = run(qemu, profile, True, "1 291 2748")
    assert pressed[0] == 1 and pressed[1:4] == [0x49, 0x02, 0x29], pressed
    assert pressed[4:8] == [0x12, 0x30, 0xab, 0xc0], pressed
    assert pressed[18] & 8 == 0 and pressed_irq & 8, (pressed, pressed_irq)
    assert "BU21029" in logs, logs[-1500:]
    print("PASS BU21029 real ARM: default NACK, ID/status, raw XY, GPIOB3 pen IRQ and release")


if __name__ == "__main__":
    main()
