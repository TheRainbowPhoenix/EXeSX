#!/usr/bin/env python3
"""Real ARM smoke test for opt-in upstream QEMU i.MX USDHC1 + eMMC.

Creates a *sparse* synthetic 16GB Samsung-reference user area under build/.
The blank medium is NOT a Casio dump, its CID/EXT_CSD are QEMU's own.
Default no-media behavior is tested by existing probes, not overridden.
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import re
import struct
import subprocess
import time

BASE = 0x60000000
OUT = 0x6200BE00
SAMSUNG_USER_BYTES = 15_634_268_160

def make_elf():
    ins, literals = [], []
    def emit(w): ins.append(w)
    def lit(reg, val):
        literals.append((len(ins), reg, val)); emit(0)
    def ldr(dst, base, off=0):
        emit(0xE5900000 | (base << 16) | (dst << 12) | off)
    def strw(src, base, off=0):
        emit(0xE5800000 | (base << 16) | (src << 12) | off)
    lit(7, OUT)
    lit(0, 0x40380000)
    # Read present status after a bounded delay; QEMU models insertion.
    lit(5, 200000)
    emit(0xe2555001)
    emit(0x1afffffd)
    ldr(2,0,0x24); strw(2,7,0)
    lit(1,0x0000000f)
    strw(1,0,0x2c)          # SYS_CTRL host SDCLK bits (Casio setup)
    lit(1,0x157f51ff)
    strw(1,0,0x34)          # normal + error status enabled
    lit(1,0x8820)
    strw(1,0,0x28)          # PROT_CTRL little-endian
    lit(1,0)
    strw(1,0,0x08)          # CMD0 arg0
    strw(1,0,0x0c)          # GO_IDLE no response
    ldr(2,0,0x30); strw(2,7,4) # CMD0 host complete
    lit(1,0xffffffff)
    strw(1,0,0x30)          # W1C all old status
    lit(1,0x40ff8000)
    strw(1,0,0x08)          # CMD1 OCR requested
    lit(1,0x01020000)
    strw(1,0,0x0c)          # CMD1 SEND_OP_COND short response
    ldr(2,0,0x30); strw(2,7,8) # CMD1 host status
    ldr(2,0,0x10); strw(2,7,12)# QEMU emulated eMMC OCR response
    ldr(2,0,0x24); strw(2,7,16)# CINST/SDSTB
    emit(0xeafffffe)
    for pos,reg,value in literals:
        off=len(ins)*4-(pos*4+8)
        if off<0 or off>4095: raise ValueError("ARM literal offset overflow")
        ins[pos]=0xe59f0000|(reg<<12)|off
        ins.append(value)
    data=struct.pack(f"<{len(ins)}I",*ins)
    ident=b"\x7fELF\x01\x01\x01"+bytes(9)
    eh=struct.pack("<16sHHIIIIIHHHHHH",ident,2,40,1,BASE,52,0,0x05000000,52,32,1,0,0,0)
    ph=struct.pack("<8I",1,0x100,BASE,BASE,len(data),len(data),5,0x100)
    return eh+ph+bytes(0x100-len(eh)-len(ph))+data

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--qemu",type=Path,default=Path("build/qemu-system-arm"))
    p.add_argument("--profile",type=Path,default=Path("profiles/imx7ulp-early-boot.ini"))
    p.add_argument("--elf",type=Path,default=Path("build/emmc-upstream-guest.elf"))
    p.add_argument("--image",type=Path,default=Path("build/emmc-synthetic-16gb.raw"))
    args=p.parse_args()
    args.image.parent.mkdir(parents=True,exist_ok=True)
    args.elf.parent.mkdir(parents=True,exist_ok=True)
    with args.image.open("wb") as backing:
        backing.truncate(SAMSUNG_USER_BYTES)  # sparse: only file size, no 16GB write
    args.elf.write_bytes(make_elf())
    env=os.environ.copy()
    env["EXESX_MEMORY_PROFILE"]=str(args.profile.resolve())
    env["EXESX_USDHC1_EMMC"]="1"
    lib=args.qemu.resolve().parent/"lib"
    if lib.is_dir():env["LD_LIBRARY_PATH"]=str(lib)+":"+env.get("LD_LIBRARY_PATH","")
    cmd=[str(args.qemu.resolve()),"-machine","exesx","-m","64M",
         "-accel","tcg","-display","none","-serial","none",
         "-monitor","stdio","-no-reboot",
         "-drive",f"if=none,id=exesx-emmc,file={args.image.resolve()},format=raw,snapshot=on",
         "-device",f"loader,file={args.elf.resolve()},cpu-num=0"]
    qemu=subprocess.Popen(cmd,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT,text=True)
    try:
        time.sleep(1.0)
        commands="".join(f"xp /1wx 0x{OUT+4*i:08x}\n" for i in range(5))+"quit\n"
        output,_=qemu.communicate(commands,timeout=20)
    finally:
        if qemu.poll() is None:qemu.kill();qemu.wait()
    values=[]
    for i in range(5):
        m=re.search(r"(?im)^0*"+f"{OUT+4*i:08x}"+r":\s+0x([0-9a-f]+)",output)
        if not m:raise AssertionError(f"Missing guest result {i}. Output:\n{output[-3500:]}")
        values.append(int(m.group(1),16))
    if not values[0]&0x10000 or not values[4]&0x10000:
        raise AssertionError(f"Attached upstream eMMC not visible: {[hex(x) for x in values]}")
    if not values[1]&1:
        raise AssertionError(f"No-response CMD0 host completion missing: {[hex(x) for x in values]}")
    if not values[2]&1:
        raise AssertionError(f"Upstream eMMC CMD1 missing host completion: {[hex(x) for x in values]}")
    if not values[3]&0x80000000:
        raise AssertionError(f"Upstream eMMC did not report OCR ready: {[hex(x) for x in values]}")
    print("PASS genuine upstream QEMU eMMC inserted, CMD0/1, response OCR:",
          [hex(x) for x in values])
    print("Medium is synthetic sparse 16GB, NOT original Casio flash; no OS boot claimed.")

if __name__=="__main__":
    main()
