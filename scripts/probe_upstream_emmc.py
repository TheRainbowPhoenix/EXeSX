#!/usr/bin/env python3
"""Real ARM smoke test for opt-in upstream QEMU i.MX USDHC1 + eMMC.

Creates a *sparse* Samsung-size test image with separate boot0/boot1 and user area.
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
EMMC_BOOT_BYTES = 4 * 1024 * 1024
EMMC_IMAGE_BYTES = SAMSUNG_USER_BYTES + 2 * EMMC_BOOT_BYTES
MARKER = b"EXESX-EMMC-SYNTHETIC-SECTOR"

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
    # Exact original DY357 A7 reset + poll operations, apart from using
    # r6 for the same PRES_STATE base held by firmware r0 at 0x60017134.
    # Firmware 0x60017134/38/3c/40/44: LDR/ORR(RSTA)/STR/LDR/TST,
    # followed by BEQ backwards. Do not pre-enable the generic SDHCI
    # SYS_CTRL low nibble, which is reserved on i.MX7ULP.
    lit(6, 0x40380024)
    ldr(2, 6, 8)            # LDR r2,[r6,#8]   SYS_CTRL
    emit(0xe3822401)        # ORR r2,r2,#0x01000000   RSTA
    strw(2, 6, 8)           # STR r2,[r6,#8]
    poll_at = len(ins)
    ldr(2, 6, 0)            # LDR r2,[r6]     PRES_STATE
    emit(0xe3120008)        # TST r2,#8      SDSTB
    branch_at = len(ins)
    emit(0)                 # BEQ poll_at, filled as PC-relative ARM B
    ins[branch_at] = 0x0a000000 | ((poll_at - (branch_at+2)) & 0xffffff)
    strw(2, 7, 80)          # Reached only after clock stable following RSTA
    ldr(2,0,0x24); strw(2,7,0)
    lit(1,0x0000000f)
    strw(1,0,0x2c)          # Reserved i.MX7ULP nibble: RAZ/WI, not a clock
    ldr(2,0,0x2c); strw(2,7,84) # Readback: bits[3:0] must be zero
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
    # Identify through genuine QEMU eMMC CID/RCA/CSD/select operations.
    lit(1,0xffffffff); strw(1,0,0x30)
    lit(1,0); strw(1,0,0x08)
    lit(1,0x02010000); strw(1,0,0x0c)  # CMD2 (R2 CID)
    ldr(2,0,0x30); strw(2,7,20)
    ldr(2,0,0x10); strw(2,7,24)
    ldr(2,0,0x1c); strw(2,7,28)
    lit(1,0xffffffff); strw(1,0,0x30)
    lit(1,0x00020000); strw(1,0,0x08)
    lit(1,0x03020000); strw(1,0,0x0c)  # CMD3 (set RCA 2)
    ldr(2,0,0x30); strw(2,7,32)
    ldr(2,0,0x10); strw(2,7,36)
    lit(1,0xffffffff); strw(1,0,0x30)
    lit(1,0x00020000); strw(1,0,0x08)
    lit(1,0x09010000); strw(1,0,0x0c)  # CMD9 (R2 CSD)
    ldr(2,0,0x30); strw(2,7,40)
    ldr(2,0,0x1c); strw(2,7,44)
    lit(1,0xffffffff); strw(1,0,0x30)
    lit(1,0x00020000); strw(1,0,0x08)
    lit(1,0x07030000); strw(1,0,0x0c)  # CMD7 (select)
    ldr(2,0,0x30); strw(2,7,48)
    ldr(2,0,0x10); strw(2,7,52)
    # A genuine CMD17 PIO read must return a known byte pattern from
    # user sector zero, which starts after the two boot partitions.
    lit(1,0x00010200); strw(1,0,0x04)  # 1 × 512-byte block
    lit(1,0x10); strw(1,0,0x48)        # i.MX MIX_CTRL PIO read
    lit(1,0xffffffff); strw(1,0,0x30)
    lit(1,0); strw(1,0,0x08)
    lit(1,0x11220000); strw(1,0,0x0c)  # CMD17 SINGLE_BLOCK_READ
    ldr(2,0,0x30); strw(2,7,56)
    ldr(2,0,0x20); strw(2,7,60)       # first marker word
    ldr(2,0,0x20); strw(2,7,64)       # second marker word
    ldr(2,0,0x24); strw(2,7,68)
    # The full 512-byte FIFO transfer MUST complete before MMC CMD8.
    # Two data-port words were already checked; drain the remaining 126.
    for _ in range(126):
        ldr(2,0,0x20)
    # Now the host can receive the next real 512-byte EXT_CSD block.
    lit(1,0x00010200); strw(1,0,0x04)
    lit(1,0x10); strw(1,0,0x48)
    lit(1,0xffffffff); strw(1,0,0x30)
    lit(1,0); strw(1,0,0x08)
    lit(1,0x08220000); strw(1,0,0x0c)  # MMC SEND_EXT_CSD
    for word in range(54):
        ldr(2,0,0x20)
        if word == 48: strw(2,7,72)  # EXT_CSD_REV offset 192
        if word == 53: strw(2,7,76)  # SEC_COUNT offsets 212..215
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
    # Exclusive-create only: never truncate an existing user-supplied image.
    # QEMU's TYPE_EMMC exposes the first two 4 MiB as boot0/boot1,
    # followed by Samsung's 15,634,268,160-byte USER region.
    try:
        with args.image.open("xb") as backing:
            backing.truncate(EMMC_IMAGE_BYTES)  # sparse, no 16 GB allocation
            backing.seek(2 * EMMC_BOOT_BYTES)
            backing.write(MARKER)
    except FileExistsError:
        p.error(f"Refusing to overwrite existing image: {args.image}")
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
        commands="".join(f"xp /1wx 0x{OUT+4*i:08x}\n" for i in range(20))+"quit\n"
        output,_=qemu.communicate(commands,timeout=20)
    finally:
        if qemu.poll() is None:qemu.kill();qemu.wait()
    values=[]
    for i in range(22):
        m=re.search(r"(?im)^0*"+f"{OUT+4*i:08x}"+r":\s+0x([0-9a-f]+)",output)
        if not m:raise AssertionError(f"Missing guest result {i}. Output:\n{output[-3500:]}")
        values.append(int(m.group(1),16))
    if not values[20] & 0x8:
        raise AssertionError("Casio RSTA→PRES_STATE.SDSTB poll never completed")
    if values[21] & 0xf:
        raise AssertionError("i.MX7ULP reserved SYS_CTRL low nibble became "
                             f"generic SDHCI clocks: {values[21]:#x}")
    if not values[0]&0x10000 or not values[4]&0x10000:
        raise AssertionError(f"Attached upstream eMMC not visible: {[hex(x) for x in values]}")
    if not values[1]&1:
        raise AssertionError(f"No-response CMD0 host completion missing: {[hex(x) for x in values]}")
    if not values[2]&1:
        raise AssertionError(f"Upstream eMMC CMD1 missing host completion: {[hex(x) for x in values]}")
    if not values[3]&0x80000000:
        raise AssertionError(f"Upstream eMMC did not report OCR ready: {[hex(x) for x in values]}")
    for index,cmd in [(5,2),(8,3),(10,9),(12,7)]:
        if not values[index]&1:
            raise AssertionError(f"Real eMMC CMD{cmd} failed: {list(map(hex,values))}")
    if not values[6] or not values[11]:
        raise AssertionError("Missing actual CID or CSD response from QEMU card")
    if values[14]&0x21 != 0x21:
        raise AssertionError(f"eMMC CMD17 missing CC+buffer-ready: {values[14]:#x}")
    expected_words=(int.from_bytes(MARKER[:4],"little"),
                    int.from_bytes(MARKER[4:8],"little"))
    if tuple(values[15:17])!=expected_words:
        raise AssertionError("CMD17 did not read real user sector zero: "
                             +repr([hex(x) for x in values[15:17]]))
    if values[19] != SAMSUNG_USER_BYTES // 512:
        raise AssertionError(f"Wrong EXT_CSD.SEC_COUNT {values[19]:#x}, "
                             f"expected {(SAMSUNG_USER_BYTES//512):#x}; "
                             "boot partitions must not count as user sectors")
    print("PASS native QEMU i.MX USDHC1+eMMC CMD0/1/2/3/9/7/17/8, "
          "attached card and real user-sector data:", [hex(x) for x in values])
    print(f"QEMU eMMC EXT_CSD_REV={values[18]&255} "
          "(not guaranteed Samsung eMMC 5.1=8); "
          f"user SEC_COUNT=0x{values[19]:08x}")
    print("SYNTHETIC MEDIA ONLY, no Casio contents/RPMB; "
          "default no-card regression remains independent.")

if __name__=="__main__":
    main()
