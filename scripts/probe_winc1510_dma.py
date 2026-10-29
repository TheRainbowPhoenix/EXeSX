#!/usr/bin/env python3
"""Native A7 full-duplex eDMA1 LPSPI2 -> external WINC Python test.

Real ARM writes guest RAM, DMA1 TCD descriptors, DMAMUX1 enable,
LPSPI2 TCR/DER, then observes DMA INT and readback. No guest injected
events/IRQ and no network stack: only the original controller path.
"""
import argparse
import os
from pathlib import Path
import re
import socket
import struct
import subprocess
import sys
import tempfile
import time
from drive_factory_menu import QMP, choose_port, connect

ENTRY=0x60000000
TX=0x6200b800
RX=0x6200b900
RESULT=0x6200ba00
SPI=0x40290000
DMA=0x40080000
MUX=0x40210000

def make_guest():
    code,lits=[],[]
    def emit(w):code.append(w)
    def li(r,v):lits.append((len(code),r,v));emit(0)
    def st(r,b,o=0):emit(0xe5800000|(b<<16)|(r<<12)|o)
    def ld(r,b,o=0):emit(0xe5900000|(b<<16)|(r<<12)|o)
    li(6,TX);li(7,RESULT)
    for i,v in enumerate((0x001000ca,0,0)):
        li(1,v);st(1,6,4*i)
    # Synthetic standalone TX eDMA channel 2.
    li(0,DMA+0x1040)
    for off,v in ((0,TX),(4,0x02020004),(8,12),
                  (12,0),(16,SPI+0x64),(20,0x00010000),
                  (24,0),(28,0x00010002)):
        li(1,v);st(1,0,off)
    # RX channel 3, same 12 real SPI bytes (interleaved with TX).
    li(0,DMA+0x1060)
    for off,v in ((0,SPI+0x74),(4,0x02020000),(8,12),
                  (12,0),(16,RX),(20,0x00010004),
                  (24,0),(28,0x00010002)):
        li(1,v);st(1,0,off)
    li(0,MUX)
    li(1,0x8000001a);st(1,0,8)  # original TX source26
    li(1,0x80000019);st(1,0,12) # original RX source25
    li(0,DMA)
    li(1,0xc);st(1,0,0xc)         # ERQ on channels 2 and 3
    li(0,SPI)
    li(1,3);st(1,0,0x24)         # MASTER
    li(1,1);st(1,0,0x10)         # MEN
    li(1,0x0240005f);st(1,0,0x60) # 96-bit/12 bytes, original PCS2
    li(1,3);st(1,0,0x1c)         # TDDE/RDDE: REAL eDMA trigger
    li(0,DMA)
    ld(2,0,0x24);st(2,7,0)       # actual INTMAJOR pending 0xC
    li(1,0xc);st(1,0,0x24)       # W1C DMA1.INT
    ld(2,0,0x24);st(2,7,4)       # now zero
    emit(0xeafffffe)
    for pos,reg,val in lits:
        delta=len(code)*4-(pos*4+8)
        if not 0<=delta<=4095:raise ValueError("ARM literal too distant")
        code[pos]=0xe59f0000|reg<<12|delta
        code.append(val)
    raw=struct.pack("<{}I".format(len(code)),*code)
    header=struct.pack("<16sHHIIIIIHHHHHH",
      b"\x7fELF\x01\x01\x01"+bytes(9),2,40,1,ENTRY,52,0,
      0x05000000,52,32,1,0,0,0)
    phdr=struct.pack("<8I",1,0x100,ENTRY,ENTRY,len(raw),len(raw),5,0x100)
    return header+phdr+bytes(0x100-len(header)-len(phdr))+raw

def word(q,a):
    v=q.hmp("xp /1wx 0x{:x}".format(a))
    m=re.search(r":\s+0x([0-9a-fA-F]+)",v)
    if not m:raise AssertionError(v)
    return int(m.group(1),16)

def run(qemu,profile):
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);image=root/"dma.elf";image.write_bytes(make_guest())
        port=choose_port()
        python=subprocess.Popen([sys.executable,
            str(Path(__file__).resolve().with_name("winc1510_spi_backend.py")),
            "--port",str(port)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        try:
            for attempt in range(60):
                try:
                    with socket.create_connection(("127.0.0.1",port),.1):
                        break
                except OSError:
                    if python.poll() is not None:raise AssertionError("Python WINC process died")
                    time.sleep(.05)
            else:
                raise TimeoutError("WINC socket never listened")
            env=os.environ.copy()
            env["EXESX_MEMORY_PROFILE"]=str(profile.resolve())
            env["EXESX_EXPERIMENTAL_LPSPI2_FIFO"]="1"
            env["EXESX_EXPERIMENTAL_LPSPI2_DMA"]="1"
            env["EXESX_WINC1510_TCP_PORT"]=str(port)
            lib=qemu.resolve().parent/"lib"
            if lib.is_dir():env["LD_LIBRARY_PATH"]=str(lib)+os.pathsep+env.get("LD_LIBRARY_PATH","")
            qport=choose_port()
            cmd=[str(qemu.resolve()),"-machine","exesx","-m","64M",
                 "-accel","tcg,thread=single","-display","none",
                 "-serial","none","-monitor","none","-no-reboot",
                 "-S","-qmp",f"tcp:127.0.0.1:{qport},server=on,wait=off",
                 "-device",f"loader,file={image.resolve()},cpu-num=0"]
            with (root/"qemu.log").open("wb") as log:
                proc=subprocess.Popen(cmd,env=env,stdin=subprocess.DEVNULL,
                                      stdout=log,stderr=subprocess.STDOUT)
                try:
                    with connect(qport,proc) as sock:
                        q=QMP(sock);q.execute("cont")
                        time.sleep(.9)
                        got=[word(q,RX+4*i) for i in range(3)]
                        wanted=[0xffffffff,0xb0f300ca,0xff001002]
                        assert got==wanted,(list(map(hex,got)),list(map(hex,wanted)))
                        assert word(q,RESULT)==0xc
                        assert word(q,RESULT+4)==0
                        assert word(q,DMA+0x105c)&0x80
                        assert word(q,DMA+0x107c)&0x80
                        assert word(q,DMA+0x1054)&0xffff0000 == 0
                        print("PASS real A7 ARM eDMA1 paired RX/TX 12 SPI bytes"
                              " PCS2 Python WINC chip-ID and actual DONE/INT W1C",
                              flush=True)
                finally:
                    proc.terminate()
                    try:proc.wait(timeout=4)
                    except subprocess.TimeoutExpired:proc.kill();proc.wait()
        finally:
            python.terminate()
            try:python.wait(timeout=4)
            except subprocess.TimeoutExpired:python.kill();python.wait()


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--qemu",type=Path,required=True)
    p.add_argument("--profile",type=Path,required=True)
    a=p.parse_args();run(a.qemu,a.profile)
