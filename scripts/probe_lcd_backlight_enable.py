#!/usr/bin/env python3
"""Real ARM test: original DY357 backlight EN2/EN3 GPIO set/clear and pin readback.
This does not establish PWM frequency, brightness or any analog-panel effect.
"""
import argparse
import os
import struct
import subprocess
import tempfile
import time
from pathlib import Path
from drive_factory_menu import QMP, choose_port, connect
from hmp_memory import memory_words

SCRATCH = 0x6200b400
ENTRY = 0x60000000

def elf_bytes():
    words, literals = [], []
    def op(x): words.append(x)
    def lit(r, value): literals.append((len(words), r, value)); op(0)
    def st(r, b, off): op(0xe5800000 | (b << 16) | (r << 12) | off)
    def ld(r, b, off): op(0xe5900000 | (b << 16) | (r << 12) | off)
    lit(7, SCRATCH)
    for base, bit, offset in ((0x400f00c0, 0x10, 0),
                               (0x4100f040, 0x800, 8)):
        lit(0, base)
        lit(1, bit)
        st(1, 0, 0x14)  # PDDR, output
        st(1, 0, 0x04)  # PSOR, high
        ld(2, 0, 0x10)  # PDIR
        st(2, 7, offset)
        st(1, 0, 0x08)  # PCOR, low
        ld(2, 0, 0x10)
        st(2, 7, offset + 4)
    op(0xeafffffe)
    pool = len(words)
    for idx, (pos, reg, val) in enumerate(literals):
        delta = (pool + idx - pos) * 4 - 8
        assert 0 <= delta < 4096
        words[pos] = 0xe59f0000 | (reg << 12) | delta
        words.append(val)
    body = struct.pack("<%dI" % len(words), *words)
    ident = b"\x7fELF\x01\x01\x01" + bytes(9)
    hdr = struct.pack("<16sHHIIIIIHHHHHH", ident, 2, 40, 1, ENTRY,
                      52, 0, 0x05000000, 52, 32, 1, 0, 0, 0)
    phdr = struct.pack("<8I", 1, 0x100, ENTRY, ENTRY, len(body),
                       len(body), 5, 0x100)
    return hdr + phdr + bytes(0x100 - len(hdr) - len(phdr)) + body

def run(qemu, profile):
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        elf = root / "backlight-en.elf"
        elf.write_bytes(elf_bytes())
        env = os.environ.copy()
        env["EXESX_MEMORY_PROFILE"] = str(profile.resolve())
        lib = qemu.resolve().parent / "lib"
        if lib.is_dir():
            env["LD_LIBRARY_PATH"] = str(lib) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
        port = choose_port()
        cmd = [str(qemu.resolve()), "-machine", "exesx", "-m", "64M",
               "-accel", "tcg,thread=single", "-display", "none",
               "-serial", "none", "-monitor", "none", "-no-reboot", "-S",
               "-qmp", "tcp:127.0.0.1:%d,server=on,wait=off" % port,
               "-device", "loader,file=%s,cpu-num=0" % elf.resolve()]
        with (root / "console.log").open("wb") as console:
            proc = subprocess.Popen(cmd, env=env, stdin=subprocess.DEVNULL,
                                    stdout=console, stderr=subprocess.STDOUT)
            try:
                with connect(port, proc) as sock:
                    qmp = QMP(sock)
                    qmp.execute("cont")
                    time.sleep(.25)
                    values = []
                    for i in range(4):
                        addr = SCRATCH + i * 4
                        values.append(memory_words(qmp.hmp("xp /1wx 0x%08x" % addr),
                                                   addr, 1)[0])
                    assert values == [0x10, 0, 0x800, 0], values
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
    print("PASS original ARM GPIOF bit4 and GPIOB bit11 EN high/low readback")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    args = parser.parse_args()
    run(args.qemu, args.profile)
