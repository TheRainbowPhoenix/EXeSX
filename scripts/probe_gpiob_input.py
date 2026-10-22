#!/usr/bin/env python3
"""Real ARM test for opt-in i.MX7ULP GPIOB input pin voltages.

The Casio M4 sees GPIOB.PDIR at 0x4100f050. By default EXeSX has
no external pins attached, so GPIOB bit7 reads zero. The optional
EXESX_GPIOB_INPUT_MASK=0x80 ONLY injects a board input level, not
an IRQ, GPIO wakeup, true board wiring, or firmware success.
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import re
import struct
import subprocess
import time

ENTRY = 0x60000000
RESULT = 0x6200B400


def guest_elf() -> bytes:
    words: list[int] = []
    literals: list[tuple[int, int, int]] = []

    def emit(word: int):
        words.append(word)

    def lit(reg: int, value: int):
        literals.append((len(words), reg, value))
        emit(0)

    def ld(reg: int, base: int, off: int = 0):
        emit(0xE5900000 | base << 16 | reg << 12 | off)

    def st(reg: int, base: int, off: int = 0):
        emit(0xE5800000 | base << 16 | reg << 12 | off)

    lit(7, RESULT)
    lit(0, 0x4100F040)  # GPIOB_BASE
    lit(1, 0)
    st(1, 0, 0x14)     # PDDR all pins inputs
    st(1, 0, 0x00)     # PDOR all low
    ld(2, 0, 0x10)     # PDIR actual pin levels
    st(2, 7, 0)
    lit(1, 0x80)
    st(1, 0, 0x00)     # output value bit7 high
    st(1, 0, 0x14)     # direction bit7 output
    ld(2, 0, 0x10)
    st(2, 7, 4)
    lit(1, 0)
    st(1, 0, 0x00)     # output value bit7 low
    ld(2, 0, 0x10)
    st(2, 7, 8)
    emit(0xEAFFFFFE)
    for index, reg, value in literals:
        off = len(words)*4 - (index*4 + 8)
        if not 0 <= off <= 4095:
            raise ValueError("ARM literal outside 12-bit immediate range")
        words[index] = 0xE59F0000 | reg << 12 | off
        words.append(value)
    code = struct.pack(f"<{len(words)}I", *words)
    ident = b"\x7fELF\x01\x01\x01" + bytes(9)
    elf = struct.pack("<16sHHIIIIIHHHHHH",ident,2,40,1,ENTRY,52,0,0x05000000,52,32,1,0,0,0)
    phdr = struct.pack("<8I",1,0x100,ENTRY,ENTRY,len(code),len(code),5,0x100)
    return elf + phdr + bytes(0x100-len(elf)-len(phdr)) + code


def exercise(qemu: Path, profile: Path, elf: Path, mask: str) -> list[int]:
    env = os.environ.copy()
    env["EXESX_GPIOB_INPUT_MASK"] = mask
    env["EXESX_MEMORY_PROFILE"] = str(profile.resolve())
    lib = qemu.resolve().parent / "lib"
    if lib.is_dir():
        env["LD_LIBRARY_PATH"] = str(lib) + ":" + env.get("LD_LIBRARY_PATH", "")
    cmd = [str(qemu.resolve()), "-machine","exesx", "-m","64M",
           "-accel","tcg", "-display","none", "-serial","none",
           "-monitor","stdio", "-no-reboot",
           "-device",f"loader,file={elf.resolve()},cpu-num=0"]
    p = subprocess.Popen(cmd, env=env, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    try:
        time.sleep(.4)
        command = "".join(f"xp /1wx 0x{RESULT+4*i:08x}\n" for i in range(3)) + "quit\n"
        out,_=p.communicate(command,timeout=15)
    finally:
        if p.poll() is None:
            p.kill()
            p.wait()
    result=[]
    for i in range(3):
        m=re.search(r"(?im)^0*"+f"{RESULT+4*i:08x}"+r":\s+0x([0-9a-f]+)",out)
        if not m:
            raise AssertionError("Guest GPIOB result missing: "+out[-1500:])
        result.append(int(m.group(1),16))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--qemu",type=Path,default=Path("build/qemu-system-arm"))
    p.add_argument("--profile",type=Path,default=Path("profiles/imx7ulp-early-boot.ini"))
    p.add_argument("--elf",type=Path,default=Path("build/gpiob-pdir-probe.elf"))
    a=p.parse_args()
    a.elf.parent.mkdir(parents=True,exist_ok=True)
    a.elf.write_bytes(guest_elf())
    for mask,expected in (("0",[0,0x80,0]),("0x80",[0x80,0x80,0]),\n                          ("0x88",[0x88,0x88,0x08])):
        actual=exercise(a.qemu,a.profile,a.elf,mask)
        if actual!=expected:
            raise AssertionError(f"GPIOB mask={mask} returned {actual}, expected {expected}")
        print(f"PASS GPIOB external mask {mask}: PDIR {list(map(hex,actual))}")
    print("No real board input, interrupt, wakeup or OS success is claimed.")


if __name__=="__main__":main()
