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
    # Exact instruction words from original SHA-verified DY357 A7
    # 0x60017134, 38, 3c, 40, 44, 48. In this probe, r0 points to
    # PRES_STATE during the poll, then restores the host base for CMD0+.
    lit(4, 0x40380000)
    lit(0, 0x40380024)
    ldr(2, 0, 8)            # e5902008 LDR r2,[r0,#8]
    emit(0xe3822740)        # e3822740 ORR r2,r2,#0x01000000
    strw(2, 0, 8)           # e5802008 STR r2,[r0,#8]
    poll_at = len(ins)
    ldr(2, 0, 0)            # e5902000 LDR r2,[r0]
    emit(0xe3120008)        # e3120008 TST r2,#8
    branch_at = len(ins)
    emit(0)                 # 0afffffc BEQ to poll_at
    ins[branch_at] = 0x0a000000 | ((poll_at - (branch_at+2)) & 0xffffff)
    assert ins[branch_at] == 0x0afffffc
    strw(2, 7, 80)          # Only reached after root clock becomes stable
    emit(0xe1a00004)        # MOV r0,r4, subsequent real eMMC MMIO base
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
    # NXP i.MX7ULP USDHC FIFO: original DY357 uses RD_WML=32 words.
    lit(1,0x08200820); strw(1,0,0x44)
    ldr(2,0,0x44); strw(2,7,88)
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
    # A genuine 512-byte FIFO remains available in four 32-word tranches.
    # A W1C BRR acknowledgment after each 128-byte tranche must permit
    # another BRR, but only while real unread sector bytes remain.
    for batch in range(4):
        for _ in range(30 if batch == 0 else 32):
            ldr(2,0,0x20)
        lit(1,0x20); strw(1,0,0x30)  # W1C BRR at batch boundary
        ldr(2,0,0x30); strw(2,7,92 + batch*4)
    # Now the host can receive the next real 512-byte EXT_CSD block.
    lit(1,0x00010200); strw(1,0,0x04)
    lit(1,0x10); strw(1,0,0x48)
    lit(1,0xffffffff); strw(1,0,0x30)
    lit(1,0); strw(1,0,0x08)
    lit(1,0x08220000); strw(1,0,0x0c)  # MMC SEND_EXT_CSD
    for word in range(128):
        ldr(2,0,0x20)
        if word == 48: strw(2,7,72)  # EXT_CSD_REV offset 192
        if word == 53: strw(2,7,76)  # SEC_COUNT offsets 212..215
        if (word + 1) % 32 == 0:
            lit(1,0x20); strw(1,0,0x30)
            ldr(2,0,0x30); strw(2,7,108 + (word//32)*4)
    # Original DY357 after recognizing PVOS: CMD23(count32), CMD18(LBA64),
    # then CMD12 with CMDTYP NORMAL and R1b while data is still in flight.
    # Use *real* QEMU eMMC buffered sectors and actual CMD12 response.
    lit(1,0xffffffff); strw(1,0,0x30)
    lit(1,32); strw(1,0,0x08)
    lit(1,0x17020000); strw(1,0,0x0c)  # CMD23 SET_BLOCK_COUNT
    ldr(2,0,0x30); strw(2,7,124)      # index 31: CMD23 CC
    lit(1,0xffffffff); strw(1,0,0x30)
    lit(1,0x00200200); strw(1,0,0x04) # 32 x 512 B
    lit(1,0x32); strw(1,0,0x48)       # MIX_CTRL multi | blkcnt | read
    lit(1,64); strw(1,0,0x08)
    lit(1,0x12220000); strw(1,0,0x0c) # CMD18 READ_MULTIPLE_BLOCK
    ldr(2,0,0x30); strw(2,7,128)      # index 32: CMD18 CC + BRR
    ldr(2,0,0x24); strw(2,7,132)      # index 33: DATA_INHIBIT true
    # Four 32-word watermarks finish sector64, then W1C of the last
    # tranche must not swallow the BRR event for already-buffered sector65.
    # Use short real ARM loops; 160 unrolled loads overflow ARM literal pool.
    for batch in range(5):
        if batch == 4:
            ldr(2,0,0x20)             # first real word from sector 65
            strw(2,7,188)             # index47, never fabricate media
            lit(3,31)
        else:
            lit(3,32)
        start = len(ins)
        ldr(2,0,0x20)
        emit(0xe2533001)              # SUBS r3,r3,#1
        pos = len(ins); emit(0)
        ins[pos] = 0x1a000000 | ((start - (pos + 2)) & 0xffffff)
        lit(1,0x20); strw(1,0,0x30)
        ldr(2,0,0x30); strw(2,7,168 + batch*4)  # indexes42..46
    # Original BIOS explicitly tries to clear MIX_CTRL while CMD18 is
    # active, then issues CMD13 followed by CMD12. Before this fix QEMU
    # unconditionally rewrote cached trnmod=0, losing active MULTI.
    lit(1,0); strw(1,0,0x48)          # attempted MIX_CTRL clear during CDIHB
    ldr(2,0,0x48); strw(2,7,156)      # index 39: retain active transfer bits
    lit(1,0x00020000); strw(1,0,0x08)
    lit(1,0x0d020000); strw(1,0,0x0c) # CMD13 during CMD18 data
    ldr(2,0,0x30); strw(2,7,160)      # index 40: CMD13 actually replied
    lit(1,0); strw(1,0,0x48)          # BIOS clears MIX_CTRL again
    ldr(2,0,0x48); strw(2,7,164)      # index 41: still MULTI active
    lit(1,0xffffffff); strw(1,0,0x30) # W1C old CMD13/BRR statuses
    lit(1,0x0c030000); strw(1,0,0x0c) # NORMAL-type CMD12, R1b
    ldr(2,0,0x30); strw(2,7,136)      # index 34: CC + TC, real CMD12
    ldr(2,0,0x24); strw(2,7,140)      # index 35: DATA_INHIBIT cleared
    ldr(2,0,0x04); strw(2,7,144)      # index 36: remaining blockcount
    lit(1,0xffffffff); strw(1,0,0x30)
    lit(1,0x00020000); strw(1,0,0x08)
    lit(1,0x0d020000); strw(1,0,0x0c) # CMD13 SEND_STATUS after CMD12
    ldr(2,0,0x30); strw(2,7,148)      # index 37: next normal command CC
    ldr(2,0,0x10); strw(2,7,152)      # index 38: card status R1
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
            backing.seek(2 * EMMC_BOOT_BYTES + 64 * 512)
            backing.write(b"EXESX-CMD18-REAL-LBA64-TEST")
            backing.seek(2 * EMMC_BOOT_BYTES + 65 * 512)
            backing.write(b"EXESX-CMD18-REAL-LBA65-TEST")
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
        commands="".join(f"xp /1wx 0x{OUT+4*i:08x}\n" for i in range(48))+"quit\n"
        output,_=qemu.communicate(commands,timeout=20)
    finally:
        if qemu.poll() is None:qemu.kill();qemu.wait()
    values=[]
    for i in range(48):
        m=re.search(r"(?im)^0*"+f"{OUT+4*i:08x}"+r":\s+0x([0-9a-f]+)",output)
        if not m:raise AssertionError(f"Missing guest result {i}. Output:\n{output[-3500:]}")
        values.append(int(m.group(1),16))
    if values[22] != 0x08200820:
        raise AssertionError(f"WTMK_LVL register lost configured watermark: {values[22]:#x}")
    for i in (23, 24, 25, 27, 28, 29):
        if not (values[i] & 0x20):
            raise AssertionError(f"Missing repeated FIFO BRR at sample {i}: "
                                 +repr([hex(v) for v in values]))
    if values[26] & 0x20 or values[30] & 0x20:
        raise AssertionError("Spurious BRR after actual end of a 512-byte block")
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
    for index in range(42,47):
        if not values[index] & 0x20:
            raise AssertionError(f"No genuine FIFO BRR after batch {index-42}; "
                                 f"at block rollover: {values[index]:#x}")
    if values[47] != int.from_bytes(b"EXES","little"):
        raise AssertionError("Expected real sector65 contents after rollover, "
                             f"got {values[47]:#x}")
    for idx in (39, 41):
        if (values[idx] & 0x32) != 0x32:
            raise AssertionError(
                f"MIX_CTRL must preserve read + multi + count bits while "
                f"CDIHB=1 (sample {idx}): {values[idx]:#x}")
    if not (values[40] & 0x1):
        raise AssertionError("CMD13 must complete with read still active")
    if not (values[31] & 1):
        raise AssertionError("Genuine CMD23 set-block-count not acknowledged")
    if (values[32] & 0x21) != 0x21 or not (values[33] & 0x2):
        raise AssertionError("CMD18 must start real multi-block buffered read: "
                             + repr([hex(v) for v in values[31:34]]))
    if (values[34] & 0x3) != 0x3:
        raise AssertionError("Normal-type CMD12 must obtain real card CC and "
                             "terminate pending transfer (TC): "
                             + repr([hex(v) for v in values[34:37]]))
    if values[35] & 0x0a02:
        raise AssertionError("CMD12 did not clear inhibit/read/data-available "
                             f"bits: {values[35]:#x}")
    if not values[37] & 1:
        raise AssertionError("Card did not accept CMD13 after real CMD12 stop")
    print("PASS native QEMU i.MX USDHC1+eMMC CMD0/1/2/3/9/7/17/8/23/18/12/13, "
          "attached card and real user-sector data:", [hex(x) for x in values])
    print(f"QEMU eMMC EXT_CSD_REV={values[18]&255} "
          "(not guaranteed Samsung eMMC 5.1=8); "
          f"user SEC_COUNT=0x{values[19]:08x}")
    print("SYNTHETIC MEDIA ONLY, no Casio contents/RPMB; "
          "default no-card regression remains independent.")

if __name__=="__main__":
    main()
