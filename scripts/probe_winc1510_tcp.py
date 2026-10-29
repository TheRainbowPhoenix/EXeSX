#!/usr/bin/env python3
"""One real ARM LPSPI2 transaction with an external Python WINC SPI process.

No Casio OS, no WLAN OK spoofing. The A7 ARM guest clocks the actual
ATWINC1510-style command CA001000 (read chip ID at 0x1000) through
the QEMU controller, TCP localhost and Python protocol parser.
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
OUT=0x6200a100
BASE=0x40290000

def elf():
    code,lits=[],[]
    def emit(w):code.append(w)
    def lit(reg,n):lits.append((len(code),reg,n));emit(0)
    def st(r,b,off):emit(0xe5800000 | b<<16 | r<<12 | off)
    def ld(r,b,off):emit(0xe5900000 | b<<16 | r<<12 | off)
    lit(7,OUT);lit(0,BASE)
    lit(1,3);st(1,0,0x24)               # MASTER mode
    lit(1,1);st(1,0,0x10)               # enabled
    lit(1,0x02000057);st(1,0,0x60)    # 11 bytes, original WLAN PCS2
    lit(1,0xca001000);st(1,0,0x64)     # WINC SINGLE_READ at 0x1000
    lit(1,0);st(1,0,0x64)              # 4 dummy clocks
    st(1,0,0x64)                       # 3 more clocks (last 24 bits)
    ld(2,0,0x74);st(2,7,0)
    ld(2,0,0x74);st(2,7,4)
    ld(2,0,0x74);st(2,7,8)
    ld(2,0,0x5c);st(2,7,12)
    emit(0xeafffffe)
    for pos,reg,val in lits:
        off=len(code)*4-pos*4-8
        if not 0<=off<=4095:raise ValueError("literal distance")
        code[pos]=0xe59f0000 | (reg<<12) | off
        code.append(val)
    raw=struct.pack("<{}I".format(len(code)),*code)
    ident=b"\x7fELF\x01\x01\x01"+bytes(9)
    header=struct.pack("<16sHHIIIIIHHHHHH",ident,2,40,1,ENTRY,52,0,
                       0x05000000,52,32,1,0,0,0)
    phdr=struct.pack("<8I",1,0x100,ENTRY,ENTRY,len(raw),len(raw),5,0x100)
    return header+phdr+bytes(0x100-len(header)-len(phdr))+raw

def result_word(q,addr):
    response=q.hmp("xp /1wx 0x{:x}".format(addr))
    m=re.search(r":\s+0x([0-9a-fA-F]+)",response)
    if not m:raise AssertionError(response)
    return int(m.group(1),16)


def run(qemu,profile):
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);image=root/"probe.elf";image.write_bytes(elf())
        port=choose_port()
        service=subprocess.Popen([sys.executable,
            str(Path(__file__).resolve().with_name("winc1510_spi_backend.py")),
            "--port",str(port)],stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,text=True)
        try:
            for _ in range(50):
                try:
                    with socket.create_connection(("127.0.0.1",port),.1):
                        break
                except OSError:
                    if service.poll() is not None:
                        raise AssertionError("WINC Python backend failed to start")
                    time.sleep(.05)
            env=os.environ.copy()
            env["EXESX_MEMORY_PROFILE"]=str(profile.resolve())
            env["EXESX_EXPERIMENTAL_LPSPI2_FIFO"]="1"
            env["EXESX_WINC1510_TCP_PORT"]=str(port)
            lib=qemu.resolve().parent/"lib"
            if lib.is_dir():
                env["LD_LIBRARY_PATH"]=str(lib)+os.pathsep+env.get("LD_LIBRARY_PATH","")
            qmp_port=choose_port()
            cmd=[str(qemu.resolve()),"-machine","exesx","-m","64M",
                 "-accel","tcg,thread=single","-display","none",
                 "-serial","none","-monitor","none","-no-reboot",
                 "-S","-qmp",f"tcp:127.0.0.1:{qmp_port},server=on,wait=off",
                 "-device",f"loader,file={image.resolve()},cpu-num=0"]
            with (root/"qemu.log").open("wb") as log:
                guest=subprocess.Popen(cmd,env=env,stdin=subprocess.DEVNULL,
                                       stdout=log,stderr=subprocess.STDOUT)
                try:
                    with connect(qmp_port,guest) as sock:
                        q=QMP(sock);q.execute("cont")
                        time.sleep(.7)
                        words=[result_word(q,OUT+i*4) for i in range(4)]
                        expected=[0xffffffff,0xca00f300,0x1002b000,0]
                        assert words==expected, (list(map(hex,words)),
                                                 list(map(hex,expected)))
                        print("PASS genuine ARM WINC1510 SPI register read "
                              "via external Python TCP backend and original PCS2",
                              flush=True)
                finally:
                    guest.terminate()
                    try:guest.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        guest.kill();guest.wait()
        finally:
            service.terminate()
            try:service.wait(timeout=5)
            except subprocess.TimeoutExpired:
                service.kill();service.wait()


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--qemu",type=Path,required=True)
    p.add_argument("--profile",type=Path,required=True)
    a=p.parse_args()
    run(a.qemu,a.profile)
