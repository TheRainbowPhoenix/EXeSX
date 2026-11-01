#!/usr/bin/env python3
"""Genuine A7 ARM PIO word transactions; no proprietary Casio ROM required.

Verify packed 40-bit frames, terminal byte alignment, PCS1 -> PCS0,
RX FIFO ordering and the disconnected / synthetic-loopback controls.
"""
import argparse
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import time

from drive_factory_menu import QMP, choose_port, connect

ENTRY = 0x60000000
OUT = 0x62009000
BASE = 0x40290000


def original_word_guest():
    code, litrefs = [], []
    def emit(w): code.append(w)
    def lit(reg, val): litrefs.append((len(code),reg,val)); emit(0)
    def load(dst, base, off=0): emit(0xe5900000 | (base<<16) | (dst<<12) | off)
    def store(src, base, off=0): emit(0xe5800000 | (base<<16) | (src<<12) | off)
    lit(7, OUT)
    lit(0, BASE)
    lit(1, 3)
    store(1,0,0x24)                 # CFGR1.MASTER=1, original writes 3
    lit(1,1)
    store(1,0,0x10)                 # MEN
    lit(1, 0x01000027)             # 40 bits / PCS1
    store(1,0,0x60)
    lit(1,0x11223344)
    store(1,0,0x64)                 # high/low 32bits of MOSI word
    lit(1,0xa5000000)
    store(1,0,0x64)                 # final byte high aligned by ROM
    load(2,0,0x5c);store(2,7,0)
    load(2,0,0x74);store(2,7,4)
    load(2,0,0x74);store(2,7,8)
    load(2,0,0x5c);store(2,7,12)
    lit(1,31)                      # 32-bit frame, PCS0
    store(1,0,0x60)
    lit(1,0xdeadbeef)
    store(1,0,0x64)
    load(2,0,0x74);store(2,7,16)
    load(2,0,0x14);store(2,7,20)
    load(2,0,0x5c);store(2,7,24)
    emit(0xeafffffe)
    for index,reg,value in litrefs:
        disp=len(code)*4 - (index*4 + 8)
        if not 0 <= disp <= 4095: raise ValueError("ARM literal too far")
        code[index] = 0xe59f0000 | reg<<12 | disp
        code.append(value)
    payload=struct.pack("<{}I".format(len(code)),*code)
    elf=struct.pack("<16sHHIIIIIHHHHHH",
                    b"\x7fELF\x01\x01\x01"+bytes(9),
                    2,40,1,ENTRY,52,0,0x05000000,52,32,1,0,0,0)
    phdr=struct.pack("<8I",1,0x100,ENTRY,ENTRY,len(payload),len(payload),5,0x100)
    return elf+phdr+bytes(0x100-len(elf)-len(phdr))+payload


def run(qemu, profile, loopback):
    with tempfile.TemporaryDirectory() as d:
        root=Path(d)
        elf=root/"packed.elf";elf.write_bytes(original_word_guest())
        env=os.environ.copy()
        env["EXESX_MEMORY_PROFILE"]=str(profile.resolve())
        env["EXESX_EXPERIMENTAL_LPSPI2_FIFO"]="1"
        env["EXESX_TRACE_WLAN_SPI"]="1"
        env["EXESX_DIAGNOSTIC_LPSPI2_LOOPBACK"]="1" if loopback else "0"
        lib=qemu.resolve().parent/"lib"
        if lib.is_dir():
            env["LD_LIBRARY_PATH"]=str(lib)+os.pathsep+env.get("LD_LIBRARY_PATH","")
        port=choose_port()
        trace=root/"mmio.log"
        cmd=[str(qemu.resolve()),"-machine","exesx","-m","64M",
             "-accel","tcg,thread=single","-display","none",
             "-serial","none","-monitor","none","-no-reboot",
             "-d","unimp,guest_errors","-D",str(trace),
             "-S","-qmp",f"tcp:127.0.0.1:{port},server=on,wait=off",
             "-device",f"loader,file={elf.resolve()},cpu-num=0"]
        with (root/"console.log").open("wb") as log:
            proc=subprocess.Popen(cmd, env=env,stdin=subprocess.DEVNULL,
                                  stdout=log,stderr=subprocess.STDOUT)
            try:
                with connect(port,proc) as sock:
                    q=QMP(sock);q.execute("cont")
                    time.sleep(.8)
                    values=[]
                    for i in range(7):
                        response=q.hmp("xp /1wx 0x{:x}".format(OUT+4*i))
                        m=re.search(r":\s+0x([0-9a-fA-F]+)",response)
                        if not m:raise AssertionError(response)
                        values.append(int(m.group(1),16))
                    expect=[2<<16,
                            0x11223344 if loopback else 0xffffffff,
                            0xa5000000 if loopback else 0xff000000,
                            0,
                            0xdeadbeef if loopback else 0xffffffff]
                    assert values[:5] == expect,(list(map(hex,values)),list(map(hex,expect)))
                    assert values[5] & ((1<<10)|(1<<9)) == ((1<<10)|(1<<9))
                    assert values[6]==0, values
                    logs=trace.read_text(encoding="utf-8")
                    for phrase in ("PCS1 assert","PCS1 deassert",
                                   "PCS0 assert","PCS0 deassert",
                                   "shift 32 bits","shift 8 bits"):
                        assert phrase in logs, (phrase,logs[-1800:])
                    print("PASS native ARM 40-bit and 32-bit packed LPSPI2, "
                          "PCS and RX FIFO mode: "+("loopback" if loopback else "disconnected"),
                          flush=True)
            finally:
                proc.terminate()
                try:proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill();proc.wait()


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--qemu",type=Path,required=True)
    p.add_argument("--profile",type=Path,required=True)
    a=p.parse_args()
    for mode in (False, True):
        run(a.qemu,a.profile,mode)
    print("No WINC1510, SPI DMA or WLAN factory result is simulated.",flush=True)
