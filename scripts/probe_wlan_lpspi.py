#!/usr/bin/env python3
"""Real ARM guest test of the opt-in DY357 LPSPI2 PIO host.

The default disconnected bus remains CR-only, preserving old behavior.
The loopback case is SYNTHETIC host wiring and cannot prove a Wi-Fi
card exists, transmits WLAN packets, or passes the original factory test.
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
OUT = 0x6200a000
BASE = 0x40290000

def probe_elf():
    code, literals = [], []
    def emit(word): code.append(word)
    def lit(reg, value):
        literals.append((len(code),reg,value));emit(0)
    def ld(reg, basereg, off=0):
        emit(0xe5900000 | (basereg << 16) | (reg << 12) | off)
    def st(reg, basereg, off=0):
        emit(0xe5800000 | (basereg << 16) | (reg << 12) | off)
    lit(7,OUT)
    lit(0,BASE)
    ld(2,0,0x00);st(2,7,0)
    ld(2,0,0x04);st(2,7,4)
    lit(1,1);st(1,0,0x10)           # CR.MEN
    st(1,0,0x24)                   # CFGR1.MASTER
    lit(1,7);st(1,0,0x60)           # 8-bit frame
    lit(1,0x3c);st(1,0,0x64)        # one genuine host PIO TX
    ld(2,0,0x14);st(2,7,8)         # SR.TCF + SR.RDF + TDF
    ld(2,0,0x5c);st(2,7,12)        # FSR.RXCOUNT=1
    ld(2,0,0x74);st(2,7,16)        # receive physical SPI MISO
    ld(2,0,0x5c);st(2,7,20)        # RXCOUNT now 0
    ld(2,0,0x70);st(2,7,24)        # RSR.RXEMPTY
    lit(1,0x201);st(1,0,0x10)      # CR.RRF+MEN
    ld(2,0,0x10);st(2,7,28)        # self-cleared RRF
    emit(0xeafffffe)
    for pos,reg,value in literals:
        displacement=len(code)*4 - pos*4 - 8
        if not 0 <= displacement <= 4095: raise ValueError("ARM literal too far")
        code[pos]=0xe59f0000 | reg << 12 | displacement
        code.append(value)
    binary=struct.pack("<{}I".format(len(code)),*code)
    header=struct.pack("<16sHHIIIIIHHHHHH",
        b"\\x7fELF\\x01\\x01\\x01"+bytes(9),2,40,1,ENTRY,52,0,
        0x05000000,52,32,1,0,0,0)
    phdr=struct.pack("<8I",1,0x100,ENTRY,ENTRY,len(binary),len(binary),5,0x100)
    return header+phdr+bytes(0x100-len(header)-len(phdr))+binary

def read_word(q, addr):
    data=q.hmp("xp /1wx 0x{:x}".format(addr))
    match=re.search(r":\\s+0x([0-9a-fA-F]+)",data)
    if not match:raise AssertionError("Unavailable MMIO / original memory: "+data)
    return int(match.group(1),16)

def exercise(qemu, profile, mode):
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);elf=root/"arm-lpspi.elf";elf.write_bytes(probe_elf())
        env=os.environ.copy()
        env["EXESX_MEMORY_PROFILE"]=str(profile.resolve())
        env.pop("EXESX_EXPERIMENTAL_LPSPI2_FIFO",None)
        env.pop("EXESX_DIAGNOSTIC_LPSPI2_LOOPBACK",None)
        if mode!="disabled":
            env["EXESX_EXPERIMENTAL_LPSPI2_FIFO"]="1"
        if mode=="loopback":
            env["EXESX_DIAGNOSTIC_LPSPI2_LOOPBACK"]="1"
        lib=qemu.resolve().parent/"lib"
        if lib.is_dir():
            env["LD_LIBRARY_PATH"]=str(lib)+os.pathsep+env.get("LD_LIBRARY_PATH","")
        port=choose_port()
        cmd=[str(qemu.resolve()),"-machine","exesx","-m","64M",
             "-accel","tcg,thread=single","-display","none","-serial","none",
             "-monitor","none","-no-reboot","-S","-qmp",
             "tcp:127.0.0.1:{},server=on,wait=off".format(port),
             "-device","loader,file={},cpu-num=0".format(elf)]
        with (root/"qemu.log").open("wb") as log:
            proc=subprocess.Popen(cmd,env=env,stdin=subprocess.DEVNULL,
                                  stdout=log,stderr=subprocess.STDOUT)
            try:
                with connect(port,proc) as sock:
                    q=QMP(sock)
                    if mode=="disabled":
                        assert "Cannot access memory" in q.hmp("xp /1wx 0x40290000")
                        assert read_word(q,BASE+0x10)==0
                        print("PASS LPSPI2 disabled: prior strict CR-only mode",flush=True)
                        return
                    assert read_word(q,BASE)==0x01000003
                    assert read_word(q,BASE+0x04)==0x00000202
                    assert "Cannot access memory" in q.hmp("xp /1wx 0x40290028")
                    q.execute("cont")
                    time.sleep(.7)
                    words=[read_word(q,OUT+i*4) for i in range(8)]
                    expected_rx=0x3c if mode=="loopback" else 0xff
                    assert words[0]==0x01000003
                    assert words[1]==0x00000202
                    assert words[2] & 0x403 == 0x403, list(map(hex,words))
                    assert words[3]==0x00010000, list(map(hex,words))
                    assert words[4]==expected_rx, list(map(hex,words))
                    assert words[5]==0
                    assert words[6]==2
                    assert words[7]==1
                    print("PASS native ARM LPSPI2 {}: TX, RX, TCF, "
                          "watermark, empty, reset".format(mode),flush=True)
            finally:
                proc.terminate()
                try:proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    proc.kill();proc.wait()

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--qemu",type=Path,required=True)
    p.add_argument("--profile",type=Path,required=True)
    a=p.parse_args()
    for mode in ("disabled","disconnected","loopback"):
        exercise(a.qemu.resolve(),a.profile.resolve(),mode)
    print("No WINC chip, WLAN authentication or factory PASS is modeled.",flush=True)
