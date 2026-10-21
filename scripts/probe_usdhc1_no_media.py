#!/usr/bin/env python3
"""Real ARM test: USDHC1 empty eMMC slot yields CTOE, never a fake reply.

The backend has no card/image; response-requiring CMD1 times out under
virtual time. CMD0 no-response host completion is independently covered
by probe_a7_early_devices.py. No external media/interrupts are present.
"""
from pathlib import Path
import argparse
import os
import re
import struct
import subprocess
import time

ENTRY, OUT = 0x60000000, 0x6200BC00


def make_elf() -> bytes:
    code = []
    literals = []

    def emit(word):
        code.append(word)

    def lit(reg, value):
        literals.append((len(code), reg, value))
        emit(0)

    def ldr(dst, base, off=0):
        emit(0xe5900000 | base << 16 | dst << 12 | off)

    def strw(src, base, off=0):
        emit(0xe5800000 | base << 16 | src << 12 | off)

    lit(7, OUT)
    lit(0, 0x40380000)
    lit(1, 0x00010001)
    strw(1, 0, 0x34)         # Enable command timeout/status flags
    lit(1, 0x40ff8000)
    strw(1, 0, 0x08)         # Actual original ROM CMD1 OCR argument
    lit(1, 0x01020000)
    strw(1, 0, 0x0c)         # CMD1, short response needed, no media
    ldr(2, 0, 0x30)
    strw(2, 7, 0)           # Before timeout (no CC)
    lit(5, 5000000)
    emit(0xe2555001)        # subs r5,r5,#1
    emit(0x1afffffd)        # bne to SUBS
    ldr(2, 0, 0x30)
    strw(2, 7, 4)           # CTOE after virtual-time deadline
    ldr(2, 0, 0x10)
    strw(2, 7, 8)           # CMDRSP0 is zero, no fabricated OCR
    lit(1, 0x00010000)
    strw(1, 0, 0x30)        # W1C of CTOE
    ldr(2, 0, 0x30)
    strw(2, 7, 12)
    ldr(2, 0, 0x08)
    strw(2, 7, 16)          # Retained command argument
    ldr(2, 0, 0x0c)
    strw(2, 7, 20)          # Retained command index/response-type
    ldr(2, 0, 0x24)
    strw(2, 7, 24)          # SDSTB only; no card present
    emit(0xeafffffe)
    for pos, reg, value in literals:
        off = len(code) * 4 - (pos*4 + 8)
        if not 0 <= off <= 4095:
            raise ValueError("ARM literal too far from PC")
        code[pos] = 0xe59f0000 | reg << 12 | off
        code.append(value)
    program = struct.pack(f"<{len(code)}I", *code)
    ident = b"\x7fELF\x01\x01\x01" + bytes(9)
    ehdr = struct.pack("<16sHHIIIIIHHHHHH", ident, 2, 40, 1,
                       ENTRY, 52, 0, 0x05000000, 52, 32, 1, 0, 0, 0)
    phdr = struct.pack("<8I",1,0x100,ENTRY,ENTRY,
                       len(program),len(program),5,0x100)
    return ehdr + phdr + bytes(0x100-len(ehdr)-len(phdr)) + program


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--qemu",type=Path,default=Path("build/qemu-system-arm"))
    p.add_argument("--profile",type=Path,default=Path("profiles/imx7ulp-early-boot.ini"))
    p.add_argument("--elf",type=Path,default=Path("build/usdhc1-no-media.elf"))
    args=p.parse_args()
    args.elf.parent.mkdir(parents=True,exist_ok=True)
    args.elf.write_bytes(make_elf())
    env=os.environ.copy()
    env["EXESX_MEMORY_PROFILE"]=str(args.profile.resolve())
    lib=args.qemu.resolve().parent/"lib"
    if lib.is_dir():
        env["LD_LIBRARY_PATH"]=str(lib)+":"+env.get("LD_LIBRARY_PATH","")
    cmd=[str(args.qemu.resolve()),"-machine","exesx","-m","64M",
         "-accel","tcg","-display","none","-serial","none",
         "-monitor","stdio","-no-reboot",
         "-device",f"loader,file={args.elf.resolve()},cpu-num=0"]
    proc=subprocess.Popen(cmd,env=env,stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    try:
        time.sleep(0.8)
        cmds="".join(f"xp /1wx 0x{OUT+4*i:08x}\n" for i in range(7))+"quit\n"
        output,_=proc.communicate(cmds,timeout=15)
    finally:
        if proc.poll() is None:proc.kill();proc.wait()
    actual=[]
    for i in range(7):
        m=re.search(r"(?im)^0*"+f"{OUT+4*i:08x}"+r":\s+0x([0-9a-f]+)",output)
        if not m:raise AssertionError(f"Missing ARM guest result {i}: {output[-1200:]}")
        actual.append(int(m.group(1),16))
    expected=[0,0x10000,0,0,0x40ff8000,0x01020000,8]
    if actual!=expected:
        raise AssertionError(f"No-card USDHC status: {list(map(hex,actual))}"
                             f" != {list(map(hex,expected))}")
    print("PASS USDHC1 CMD1 response timeout W1C; no card, response or IRQ forged.")


if __name__=="__main__":
    main()
