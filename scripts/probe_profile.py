#!/usr/bin/env python3
"""Firmware-free ARMv7-A probe of experimental EXeSX RAM profile."""
import argparse
from pathlib import Path
import re
import struct
import subprocess
import os
import time

BASE=0x60000000
VALUES=[(0x61080000,0xa1108000),(0x67100000,0xa1710000),(0x62000000,0x52414d21)]

def image():
    # PC+8 literal addressing with ARM-state LDR immediate.
    words=[]
    for i in range(3):
        pc=i*12
        addr_literal=40+8*i
        val_literal=addr_literal+4
        words.extend([
            0xe59f1000 | (addr_literal - (pc+8)),
            0xe59f0000 | (val_literal - (pc+12)),
            0xe5810000,
        ])
    words.append(0xeafffffe)  # spin when all three stores completed
    for addr,val in VALUES:
        words.extend([addr,val])
    data=struct.pack(f"<{len(words)}I",*words)
    ident=b"\x7fELF\x01\x01\x01"+bytes(9)
    hdr=struct.pack("<16sHHIIIIIHHHHHH",ident,2,40,1,BASE,52,0,
                    0x05000000,52,32,1,0,0,0)
    phdr=struct.pack("<8I",1,0x100,BASE,BASE,len(data),len(data),5,0x100)
    return hdr+phdr+bytes(0x100-len(hdr)-len(phdr))+data

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--qemu",type=Path,default=Path("build/qemu-system-arm"))
    p.add_argument("--profile",type=Path,default=Path("profiles/boot-ram-experimental.ini"))
    p.add_argument("--plugin",type=Path)
    p.add_argument("--elf",type=Path,default=Path("build/exesx-ram-probe.elf"))
    args=p.parse_args()
    args.elf.parent.mkdir(parents=True,exist_ok=True)
    args.elf.write_bytes(image())
    env=os.environ.copy()
    env["EXESX_MEMORY_PROFILE"]=str(args.profile.resolve())
    command=[str(args.qemu.resolve()),"-machine","exesx","-m","64M",
             "-accel","tcg","-display","none","-serial","none",
             "-monitor","stdio","-no-reboot",
             "-device",f"loader,file={args.elf.resolve()},cpu-num=0"]
    if args.plugin:
        command+=["-plugin",f"file={args.plugin.resolve()},range=0x61080000:0x61080004,range=0x67100000:0x67100004,max=15"]
    p0=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,text=True,env=env)
    try:
        time.sleep(0.7)
        output,_=p0.communicate("xp /1wx 0x61080000\nxp /1wx 0x67100000\nxp /1wx 0x62000000\nquit\n",timeout=15)
        print(output)
        expected=[(0x61080000,0xa1108000),(0x67100000,0xa1710000),
                  (0x62000000,0x52414d21)]
        for addr,val in expected:
            # QEMU HMP reports physical addresses with 16 or 8 hex digits.
            matches=re.findall(r"(?m)^0*"+f"{addr:08x}"+r":\s+0x([0-9a-fA-F]+)",output)
            if not matches or int(matches[0],16)!=val:
                raise AssertionError(f"Guest write at {addr:#x} missing (expected {val:#x})")
        print("PASS: real ARM guest wrote/read both experimental target RAM regions")
    finally:
        if p0.poll() is None:
            p0.kill()
            p0.wait()

if __name__=="__main__":
    main()
