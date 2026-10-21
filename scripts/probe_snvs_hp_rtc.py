#!/usr/bin/env python3
"""Real ARM verification of SNVS HP RTC 32.768kHz monotonic/freeze semantics.

No wall clock, secure RTC synchronization, alarms or calendar claims.
"""
from pathlib import Path
import argparse
import os
import re
import struct
import subprocess
import time

START, OUTPUT = 0x60000000, 0x6200B500

def elf():
    words=[]; lits=[]
    def emit(x): words.append(x)
    def lit(reg,val):
        lits.append((len(words),reg,val)); emit(0)
    def ldr(reg,base,off=0): emit(0xe5900000|(base<<16)|(reg<<12)|off)
    def strw(reg,base,off=0): emit(0xe5800000|(base<<16)|(reg<<12)|off)
    def delay():
        lit(5,500000)
        emit(0xe2555001)  # subs r5,r5,#1
        emit(0x1afffffd)  # bne to subs; PC-relative -12 bytes
    def capture(pos):
        ldr(2,0,0x24); strw(2,7,pos*4)
        ldr(2,0,0x28); strw(2,7,(pos+1)*4)
    lit(7,OUTPUT)
    lit(0,0x41070000)
    lit(1,1)
    strw(1,0,8)   # HPCR RTC_EN
    capture(0)
    delay()
    capture(2)
    lit(1,0)
    strw(1,0,8)   # freeze HP counter
    capture(4)
    delay()
    capture(6)    # frozen time must be unchanged
    emit(0xeafffffe)
    for at,reg,val in lits:
        disp=len(words)*4-(at*4+8)
        assert 0 <= disp < 4096
        words[at]=0xe59f0000|(reg<<12)|disp
        words.append(val)
    body=struct.pack(f"<{len(words)}I",*words)
    ident=b"\x7fELF\x01\x01\x01"+bytes(9)
    eh=struct.pack("<16sHHIIIIIHHHHHH",ident,2,40,1,START,52,0,0x05000000,52,32,1,0,0,0)
    ph=struct.pack("<8I",1,0x100,START,START,len(body),len(body),5,0x100)
    return eh+ph+bytes(0x100-len(eh)-len(ph))+body

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--qemu",type=Path,default=Path("build/qemu-system-arm"))
    p.add_argument("--profile",type=Path,default=Path("profiles/imx7ulp-early-boot.ini"))
    p.add_argument("--elf",type=Path,default=Path("build/snvs-hp-rtc.elf"))
    a=p.parse_args()
    a.elf.parent.mkdir(parents=True,exist_ok=True)
    a.elf.write_bytes(elf())
    env=os.environ.copy()
    env["EXESX_MEMORY_PROFILE"]=str(a.profile.resolve())
    lib=a.qemu.resolve().parent/"lib"
    if lib.is_dir():env["LD_LIBRARY_PATH"]=str(lib)+":"+env.get("LD_LIBRARY_PATH","")
    cmd=[str(a.qemu.resolve()),"-machine","exesx","-m","64M","-accel","tcg",
         "-display","none","-serial","none","-monitor","stdio","-no-reboot",
         "-device",f"loader,file={a.elf.resolve()},cpu-num=0"]
    proc=subprocess.Popen(cmd,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT,text=True)
    try:
        time.sleep(.75)
        commands="".join(f"xp /1wx 0x{OUTPUT+4*i:08x}\n" for i in range(8))+"quit\n"
        out,_=proc.communicate(commands,timeout=20)
    finally:
        if proc.poll() is None:proc.kill();proc.wait()
    words=[]
    for i in range(8):
        m=re.search(r"(?im)^0*"+f"{OUTPUT+i*4:08x}"+r":\s+0x([0-9a-f]+)",out)
        if not m:raise AssertionError("Guest RTC result missing "+str(i)+": "+out[-1200:])
        words.append(int(m.group(1),16))
    samples=[(words[i]<<32)|words[i+1] for i in (0,2,4,6)]
    if not (samples[0] <= samples[1] <= samples[2] == samples[3] and samples[1] > samples[0]):
        raise AssertionError(f"SNVS HP RTC monotonic/freeze violation: {samples}")
    print("PASS SNVS HP RTC 32768Hz counter increases while RTC_EN and freezes after stop")
    print("No calendar/host wallclock or secure SNVS state emulated")

if __name__=="__main__":main()
