#!/usr/bin/env python3
"""Real ARM guest smoke test of A7 early USDHC0/DMA1/DMAMUX1/LPSPI2 MMIO.

No card, DMA engine or SPI device modeled. Only register initialization,
readback and mixed-width TCD/DMAMUX accesses are checked.
"""
from pathlib import Path
import argparse
import os
import re
import struct
import subprocess
import time

BASE, OUT = 0x60000000, 0x6200B200

def make_elf():
    words, literals = [], []
    def emit(w): words.append(w)
    def lit(reg, value):
        literals.append((len(words), reg, value))
        emit(0)
    def ldr(dest, base, off=0): emit(0xe5900000 | base << 16 | dest << 12 | off)
    def strw(src, base, off=0): emit(0xe5800000 | base << 16 | src << 12 | off)
    lit(7, OUT)
    lit(0, 0x40370000)
    ldr(2, 0, 0x24); strw(2, 7, 0)     # USDHC0 PRES_STATE, SDSTB not CINST
    lit(0, 0x40080000)
    lit(1, 0x90)
    strw(1, 0, 0)
    ldr(2, 0, 0); strw(2, 7, 4)        # DMA1 CR control readback
    ldr(2, 0, 4); strw(2, 7, 8)        # DMA1 ES idle
    lit(0, 0x40081040)
    lit(1, 0xaabbccdd)
    strw(1, 0, 0)                     # TCD channel2 SADDR
    ldr(2, 0, 0); strw(2, 7, 12)
    lit(1, 0x1234)
    emit(0xe1c010b4)                  # strh r1,[r0,#4] (SOFF)
    emit(0xe1d020b4)                  # ldrh r2,[r0,#4]
    strw(2, 7, 16)
    lit(0, 0x40210000)
    lit(1, 0x95)
    emit(0xe5c0100c)                  # strb r1,[r0,#12] DMAMUX1 CHCFG3 low byte
    emit(0xe5d0200c)                  # ldrb r2,[r0,#12]
    strw(2, 7, 20)       # CHCFG3.SOURCE bits0..6; bit7 reserved
    lit(1, 0xa1b2c3d4)
    strw(1, 0, 12)                     # One 32-bit CHCFG3; RAZ/WI reserved
    ldr(2, 0, 12); strw(2, 7, 28)   # CHCFG3 masked readback
    emit(0xe5d0200d)                   # ldrb r2,[r0,#13]
    strw(2, 7, 32)                  # High byte of CHCFG3 is reserved
    # Actual i.MX7ULP DMAMUX1 has 32 x uint32 CHCFG, not 32 bytes.
    lit(1, 0x8000001f)
    strw(1, 0, 0x20)                 # CHCFG8: enable source 31
    ldr(2, 0, 0x20); strw(2, 7, 116)
    # M4 DMAMUX0 is independently decoded at 0x41020000.
    # 32-bit CHCFG[0] is not a byte array; preserve ENBL/A_ON/SOURCE.
    lit(0, 0x41020000)
    lit(1, 0xa0000035)
    strw(1, 0, 0)
    ldr(2, 0, 0); strw(2, 7, 128)
    lit(1, 0xffffffff)
    strw(1, 0, 0x7c)                  # Last of 32 4-byte CHCFG registers
    ldr(2, 0, 0x7c); strw(2, 7, 132)
    lit(1, 0)
    strw(1, 0, 0)
    ldr(2, 0, 0); strw(2, 7, 136)    # Disable restores zero
    # M4 eDMA0 has the same 32-channel TCD layout and one-byte
    # SERQ/CERQ commands as eDMA1.  Registers should be writable,
    # but never report DONE without a real transfer.
    lit(0, 0x41009000)               # DMA0 + 0x1000 TCD ch0
    lit(1, 0x11223344)
    strw(1, 0, 0)
    ldr(2, 0, 0); strw(2, 7, 140)
    lit(0, 0x41008000)
    lit(1, 0)
    emit(0xe5c0101b)                 # STRB r1,[r0,#0x1b], SERQ ch0
    ldr(2, 0, 0x0c); strw(2, 7, 144)
    emit(0xe5c0101a)                 # CERQ ch0
    ldr(2, 0, 0x0c); strw(2, 7, 148)
    ldr(2, 0, 0x24); strw(2, 7, 152) # INT remains zero
    lit(0, 0x40080000)
    lit(1, 15)
    emit(0xe5c0101b)                 # STRB r1,[r0,#0x1b] DMA1.SERQ ch15
    ldr(2, 0, 0x0c); strw(2, 7, 120)  # ERQ bit15 enabled (no transfer)
    emit(0xe5c0101a)                 # STRB r1,[r0,#0x1a] DMA1.CERQ ch15
    ldr(2, 0, 0x0c); strw(2, 7, 124)  # ERQ bit15 cleared
    lit(0, 0x40290000)
    lit(1, 0x302)
    strw(1, 0, 0x10)                  # LPSPI2 CR early control
    ldr(2, 0, 0x10); strw(2, 7, 24)
    lit(0, 0x40380000)                   # USDHC1, separate host controller
    ldr(2, 0, 0xc0); strw(2, 7, 36)  # VEND_SPEC reset = 0
    lit(1, 0x100)
    strw(1, 0, 0xc0)                # Force SD CLK
    ldr(2, 0, 0xc0); strw(2, 7, 40)
    lit(1, 0)
    strw(1, 0, 0xc0)                # Release forced SD CLK
    ldr(2, 0, 0xc0); strw(2, 7, 44)
    lit(1, 0x01000000)
    strw(1, 0, 0x2c)                # SYS_CTRL.RSTA reset command
    ldr(2, 0, 0x2c); strw(2, 7, 48)  # resets self-clear
    ldr(2, 0, 0x24); strw(2, 7, 52)  # SDSTB stable, CINST unset
    lit(1, 0x00800000)
    strw(1, 0, 0x48)                # MIX_CTRL register storage; no transfer
    ldr(2, 0, 0x48); strw(2, 7, 56)
    lit(1, 0x0000000f)
    strw(1, 0, 0x2c)                # Actual A7 write includes reserved bits
    ldr(2, 0, 0x2c); strw(2, 7, 60)  # Reserved bits read as zero
    lit(1, 0x08200820)
    strw(1, 0, 0x44)                # Actual original-ROM WTMK_LVL write
    ldr(2, 0, 0x44); strw(2, 7, 64)  # Watermarks 32, burst lengths 8
    lit(1, 0xffffffff)
    strw(1, 0, 0x30)                # INT_STATUS W1C has no fabricated source
    ldr(2, 0, 0x30); strw(2, 7, 68)
    lit(1, 0x157f51ff)            # NXP-defined INT_STATUS bit mask
    strw(1, 0, 0x34)                # INT_STATUS_EN
    ldr(2, 0, 0x34); strw(2, 7, 72)
    strw(1, 0, 0x38)                # INT_SIGNAL_EN
    ldr(2, 0, 0x38); strw(2, 7, 76)
    ldr(2, 0, 0x30); strw(2, 7, 80)  # No CC/TC/card-insert signaled
    lit(1, 0x8820)
    strw(1, 0, 0x28)                # Real BIOS PROT_CTRL initial mode
    ldr(2, 0, 0x28); strw(2, 7, 112) # Only EMODE=0x20 defined; reserved ignored
    lit(1, 0)
    strw(1, 0, 0x08)                # CMD0 with argument 0
    strw(1, 0, 0x0c)                # CMD0 RSPTYP=0, no data
    ldr(2, 0, 0x30); strw(2, 7, 84)  # CC: host emitted no-reply CMD0
    ldr(2, 0, 0x08); strw(2, 7, 88)  # command argument stored
    ldr(2, 0, 0x0c); strw(2, 7, 92)  # command index/type stored
    lit(1, 1)
    strw(1, 0, 0x30)                # W1C host CC
    ldr(2, 0, 0x30); strw(2, 7, 96)
    lit(1, 0x1aa)
    strw(1, 0, 0x08)                # CMD8 requires real SD response
    lit(1, 0x08020000)
    strw(1, 0, 0x0c)                # CMD8 RSPTYP=2, no card
    ldr(2, 0, 0x08); strw(2, 7, 100)
    ldr(2, 0, 0x0c); strw(2, 7, 104)
    ldr(2, 0, 0x30); strw(2, 7, 108) # never forge CC/card response
    emit(0xeafffffe)
    for index, reg, value in literals:
        offset = len(words)*4 - (index*4+8)
        assert 0 <= offset < 4096
        words[index] = 0xe59f0000 | (reg<<12) | offset
        words.append(value)
    body = struct.pack(f"<{len(words)}I", *words)
    ident=b"\x7fELF\x01\x01\x01"+bytes(9)
    eh=struct.pack("<16sHHIIIIIHHHHHH",ident,2,40,1,BASE,52,0,0x05000000,52,32,1,0,0,0)
    ph=struct.pack("<8I",1,0x100,BASE,BASE,len(body),len(body),5,0x100)
    return eh+ph+bytes(0x100-len(eh)-len(ph))+body

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--qemu",type=Path,default=Path("build/qemu-system-arm"))
    ap.add_argument("--profile",type=Path,default=Path("profiles/imx7ulp-early-boot.ini"))
    ap.add_argument("--elf",type=Path,default=Path("build/a7-mmio-early.elf"))
    a=ap.parse_args()
    a.elf.parent.mkdir(parents=True,exist_ok=True)
    a.elf.write_bytes(make_elf())
    env=os.environ.copy()
    env["EXESX_MEMORY_PROFILE"]=str(a.profile.resolve())
    lib=a.qemu.resolve().parent/"lib"
    if lib.is_dir(): env["LD_LIBRARY_PATH"]=str(lib)+":"+env.get("LD_LIBRARY_PATH","")
    cmd=[str(a.qemu.resolve()),"-machine","exesx","-m","64M","-accel","tcg",
         "-display","none","-serial","none","-monitor","stdio","-no-reboot",
         "-device",f"loader,file={a.elf.resolve()},cpu-num=0"]
    guest=subprocess.Popen(cmd,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,text=True)
    try:
        time.sleep(0.5)
        script="".join(f"xp /1wx 0x{OUT+4*i:08x}\n" for i in range(39))+"quit\n"
        output,_=guest.communicate(script,timeout=15)
    finally:
        if guest.poll() is None: guest.kill();guest.wait()
    actual=[]
    for i in range(39):
        m=re.search(r"(?im)^0*"+f"{OUT+i*4:08x}"+r":\s+0x([0-9a-f]+)",output)
        if not m: raise AssertionError("Missing guest ARM output: "+output[-1600:])
        actual.append(int(m.group(1),16))
    expected=[8,0x90,0,0xaabbccdd,0x1234,0x15,0x302,0xa0000054,0,0,0x100,0,0,8,0x00800000,0,0x08200820,0,0x157f51ff,0x157f51ff,0,1,0,0,0,0x1aa,0x08020000,0,0x20,0x8000001f,0x8000,0,0xa0000035,0xe000007f,0,0x11223344,1,0,0]
    if actual != expected:
        raise AssertionError(f"Mixed-width A7 startup MMIO mismatch: {list(map(hex,actual))}")
    print("PASS A7 ARM USDHC0/1 host clocks with no card, DMA1/TCD, DMAMUX1 and LPSPI2 controls; DMAMUX1 32-bit CHCFG8 and byte SERQ/CERQ")
    print("PASS CMD0 host-only no-response complete; CMD8 retains argument but no card/response/IRQ.")

if __name__=="__main__": main()
