#!/usr/bin/env python3
"""Synthetic ARM → GPIOA16 D/C → LCD DBI → RGB565 screenshot regression.

Uses fabricated 2-pixel red/green framebuffer, no Casio firmware.
"""
import argparse
import os
from pathlib import Path
import struct
import subprocess
import tempfile

BASE=0x60000000

def make_elf():
    ins, fixups=[],[]
    def emit(x): ins.append(x)
    def literal(reg,value):
        fixups.append((len(ins),reg,value))
        emit(0)
    def store(reg,base,offset):
        emit(0xe5800000 | base<<16 | reg<<12 | offset)
    def half(reg,base):
        emit(0xe1c000b0 | base<<16 | reg<<12)
    literal(4,0x400f0000)
    literal(5,0xb0000000)
    literal(6,0x10000)
    def cmd(x):
        store(6,4,8)
        literal(1,x)
        half(1,5)
        store(6,4,4)
    def val(x):
        literal(1,x)
        half(1,5)
    cmd(0x3a); val(0x55)
    cmd(0x35); val(0x00)
    cmd(0x2a)
    for x in (0,0,0,3): val(x)
    cmd(0x2b)
    for x in (0,0,0,0): val(x)
    cmd(0x2c);val(0xf800);val(0x07e0)
    literal(1,0xf800001f)  # 32-bit pixel pair: RGB565 blue, red
    store(1,5,0)
    emit(0xeafffffe)
    # Pool at end. Literal LDR immediate offset uses PC+8.
    pool_start=len(ins)
    for j,(pos,reg,value) in enumerate(fixups):
        off=(pool_start+j-pos)*4-8
        if off < 0 or off > 4095:
            raise ValueError("ARM literal pool out of range")
        ins[pos]=0xe59f0000 | reg<<12 | off
        ins.append(value)
    body=struct.pack("<%dI"%len(ins),*ins)
    ident=b"\x7fELF\x01\x01\x01"+bytes(9)
    hdr=struct.pack("<16sHHIIIIIHHHHHH",ident,2,40,1,BASE,52,0,0x05000000,
                    52,32,1,0,0,0)
    ph=struct.pack("<8I",1,0x100,BASE,BASE,len(body),len(body),5,0x100)
    return hdr+ph+bytes(0x100-len(hdr)-len(ph))+body

def run(qemu,profile):
    with tempfile.TemporaryDirectory() as tmp:
        tmp=Path(tmp)
        elf=tmp/"lcd-probe.elf"
        screenshot=tmp/"lcd-screenshot.ppm"
        memory=tmp/"probe.ini"
        elf.write_bytes(make_elf())
        memory.write_text(profile.read_text()+
            "\n[lcd-synthetic]\nkind=exesx-lcd\nbase=0xb0000000\nsize=0x1000\n")
        env=os.environ.copy()
        env["EXESX_MEMORY_PROFILE"]=str(memory)
        env["EXESX_EXPERIMENTAL_LCD"]="1"
        env["EXESX_LCD_SCREENSHOT"]=str(screenshot)
        env["LD_LIBRARY_PATH"]=str(qemu.resolve().parent/"lib")+os.pathsep+env.get("LD_LIBRARY_PATH","")
        cmd=[str(qemu.resolve()),"-machine","exesx","-m","64M",
             "-accel","tcg","-display","none","-serial","none",
             "-monitor","none","-no-reboot",
             "-device",f"loader,file={elf},cpu-num=0"]
        try:
            subprocess.run(cmd,env=env,stdout=subprocess.DEVNULL,
                           stderr=subprocess.PIPE,timeout=1.8,check=False)
        except subprocess.TimeoutExpired:
            pass
        if not screenshot.is_file():
            raise AssertionError("QEMU LCD device did not write screenshot")
        raw=screenshot.read_bytes()
        if not raw.startswith(b"P6\n864 480\n255\n"):
            raise AssertionError("Unexpected screenshot format/size")
        pixels=raw.split(b"\n",3)[3]
        if pixels[:12] != bytes([255,0,0,0,255,0,0,0,255,255,0,0]):
            raise AssertionError(f"LCD D/C, 16-bit/32-bit RAMWR or RGB565 wrong: {pixels[:12].hex()}")
        if pixels[12:18] != bytes(6):
            raise AssertionError("LCD wrote outside the four-pixel window")
    print("PASS synthetic ARM LCD writes two halfword + two word-packed RGB565 pixels through GPIOA16 and screenshot")

if __name__=="__main__":
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--qemu",type=Path,default=Path("build/qemu-system-arm"))
    ap.add_argument("--profile",type=Path,default=Path("profiles/imx7ulp-early-boot.ini"))
    args=ap.parse_args()
    run(args.qemu,args.profile)
