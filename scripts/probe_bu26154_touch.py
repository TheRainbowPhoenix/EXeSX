#!/usr/bin/env python3
"""Firmware-free real-ARM BU26154 touch/I2C proof (opt-in; no ROM).
Assert absent chip NACK, opt-in I2C 0x1a and correct no-contact / 12-bit
X/Y ADC byte splitting. No virtual pen IRQ or unverified bus mapping.
"""
import argparse
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import time

from drive_factory_menu import QMP, choose_port, connect

PC, OUT, BUS = 0x60000000, 0x62008000, 0x41035000


def make_elf():
    ins, literals = [], []

    def emit(value):
        ins.append(value)

    def lit(reg, value):
        literals.append((len(ins), reg, value))
        emit(0)

    def store(src, base, off=0):
        emit(0xe5800000 | base << 16 | src << 12 | off)

    def load(dest, base, off=0):
        emit(0xe5900000 | base << 16 | dest << 12 | off)

    def mtdr(word):
        lit(1, word)
        store(1, 0, 0x60)

    def start(address_byte):
        mtdr(0x400 | address_byte)

    def select(reg):
        start(0x34)
        mtdr(reg)

    def read_reg(reg, slot):
        select(reg)
        start(0x35)
        mtdr(0x100)
        load(2, 0, 0x70)
        store(2, 7, slot * 4)

    def write_ctrl(value):
        select(0x61)
        mtdr(value)
        mtdr(0x200)

    lit(7, OUT)
    lit(0, BUS)
    lit(1, 1)
    store(1, 0, 0x10)
    start(0x34)
    load(2, 0, 0x14)
    store(2, 7, 0)
    read_reg(0x60, 1)              # reset control, 0x78 if attached
    read_reg(0x62, 2)              # TCHEN disabled => ADC zero
    write_ctrl(0xc8)              # TCHEN / X conversion
    read_reg(0x62, 3)              # upper 8 of X 0x123 = 0x12
    read_reg(0x64, 4)              # lower 4 of X = 0x03
    write_ctrl(0xd8)              # Y conversion
    read_reg(0x62, 5)              # Y 0xabc high = 0xab
    read_reg(0x64, 6)              # Y low = 0x0c
    write_ctrl(0x48)              # disable ADC, retain X mode
    read_reg(0x62, 7)              # zero again
    start(0x96)                   # separate unknown 0x4b must NACK
    load(2, 0, 0x14)
    store(2, 7, 8 * 4)
    emit(0xeafffffe)
    for pos, reg, value in literals:
        offset = len(ins) * 4 - pos * 4 - 8
        assert 0 <= offset < 4096
        ins[pos] = 0xe59f0000 | reg << 12 | offset
        ins.append(value)
    code = struct.pack("<%dI" % len(ins), *ins)
    ident = b"\x7fELF\x01\x01\x01" + bytes(9)
    header = struct.pack("<16sHHIIIIIHHHHHH", ident, 2, 40, 1,
                         PC, 52, 0, 0x05000000, 52, 32, 1, 0, 0, 0)
    phdr = struct.pack("<8I", 1, 0x100, PC, PC, len(code), len(code), 5, 0x100)
    return header + phdr + bytes(0x100 - len(header) - len(phdr)) + code


def run(qemu, profile, opt_in, touch):
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        elf = root / "bu26154-probe.elf"
        elf.write_bytes(make_elf())
        env = os.environ.copy()
        for key in ("EXESX_BU26154_LPI2C_BUS", "EXESX_BU26154_TOUCH_FILE",
                    "EXESX_I2C4B_REPLY_HEX", "EXESX_I2C4B_REGISTER_MIRROR",
                    "EXESX_I2C40_REGISTER_MIRROR"):
            env.pop(key, None)
        env["EXESX_MEMORY_PROFILE"] = str(profile)
        if opt_in:
            env["EXESX_BU26154_LPI2C_BUS"] = "2"
        if touch is not None:
            contact = root / "touch.txt"
            contact.write_text(touch, encoding="ascii")
            env["EXESX_BU26154_TOUCH_FILE"] = str(contact)
        lib = qemu.parent / "lib"
        if lib.is_dir():
            env["LD_LIBRARY_PATH"] = str(lib) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
        port = choose_port()
        log = root / "log.txt"
        cmd = [str(qemu), "-machine", "exesx", "-m", "64M", "-accel", "tcg",
               "-display", "none", "-serial", "none", "-monitor", "none",
               "-no-reboot", "-S", "-d", "unimp,guest_errors", "-D", str(log),
               "-qmp", f"tcp:127.0.0.1:{port},server=on,wait=off",
               "-device", f"loader,file={elf},cpu-num=0"]
        with (root / "console.txt").open("wb") as console:
            proc = subprocess.Popen(cmd, env=env, stdin=subprocess.DEVNULL,
                                    stdout=console, stderr=subprocess.STDOUT)
            try:
                with connect(port, proc) as sock:
                    qmp = QMP(sock)
                    qmp.execute("cont")
                    time.sleep(0.8)
                    values = []
                    for i in range(9):
                        reply = qmp.hmp(f"xp /1wx 0x{OUT + i * 4:x}")
                        match = re.search(r":\s+0x([0-9a-fA-F]+)", reply)
                        assert match, reply
                        values.append(int(match.group(1), 16))
                    return values, log.read_text(encoding="utf-8", errors="replace")
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--qemu", type=Path, required=True)
    p.add_argument("--profile", type=Path, required=True)
    args = p.parse_args()
    qemu, profile = args.qemu.resolve(), args.profile.resolve()
    absent, _ = run(qemu, profile, False, "1 291 2748")
    assert absent[0] == 0x401 and absent[1:8] == [0x4000] * 7, absent
    disconnected, _ = run(qemu, profile, True, None)
    assert disconnected == [1, 0x78, 0, 0, 0, 0, 0, 0, 0x401], disconnected
    released, _ = run(qemu, profile, True, "0 291 2748")
    assert released == disconnected, released
    touched, diagnostics = run(qemu, profile, True, "1 291 2748")
    assert touched == [1, 0x78, 0, 0x12, 0x3, 0xab, 0xc, 0, 0x401], touched
    assert "BU26154 touch control" in diagnostics, diagnostics[-2000:]
    print("PASS BU26154: absent NACK / disconnected / release / X,Y / disable / other-slave NACK")


if __name__ == "__main__":
    main()
