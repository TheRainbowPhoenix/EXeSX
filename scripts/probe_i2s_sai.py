#!/usr/bin/env python3
"""Real ARM M4-domain SAI0/I2S0 + I2S1 MMIO regression, no Casio ROM.

The A7 synthetic ARM instructions execute real bus reads/writes (no host-side
register writes). Assert supported registers, command self-clear and reserved
hole access is rejected by read-only QMP. An opt-out profile control removes
the two documented SAI windows; expected native MMIO reads then fail.
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

PC = 0x60000000
OUT = 0x62008000

def make_elf():
    code, literals = [], []
    def emit(w): code.append(w)
    def lit(reg, value):
        literals.append((len(code), reg, value))
        emit(0)
    def load(dest, base, off=0):
        emit(0xe5900000 | base << 16 | dest << 12 | off)
    def store(src, base, off=0):
        emit(0xe5800000 | base << 16 | src << 12 | off)
    lit(7, OUT)
    for bank, addr in enumerate((0x41037000, 0x410aa000)):
        lit(0, addr)
        load(2,0,0x08); store(2,7,bank*32+0)  # TCSR reset 0
        lit(1,0x00004009)
        store(1,0,0x10)                        # TCR2 config
        load(2,0,0x10); store(2,7,bank*32+4)
        lit(1,0x80000100)                      # TE + FRIE
        store(1,0,0x08)
        load(2,0,0x08); store(2,7,bank*32+8)
        lit(1,0x01000000)                      # SR selfclear, reset configs
        store(1,0,0x08)
        load(2,0,0x08); store(2,7,bank*32+12)
        load(2,0,0x10); store(2,7,bank*32+16)
        lit(1,0x00200040);store(1,0,0x94)      # RCR3
        load(2,0,0x94); store(2,7,bank*32+20)
        lit(1,0x02000000)                      # FR bit25 selfclear per NXP header
        store(1,0,0x88)
        load(2,0,0x88);store(2,7,bank*32+24)
    emit(0xeafffffe)
    for pos,reg,value in literals:
        displacement=len(code)*4-pos*4-8
        if displacement>4095 or displacement<0:
            raise RuntimeError("literal too far")
        code[pos]=0xe59f0000 | reg << 12 | displacement
        code.append(value)
    code_bytes=struct.pack("<%dI"%len(code),*code)
    identity=b"\x7fELF\x01\x01\x01"+bytes(9)
    head=struct.pack("<16sHHIIIIIHHHHHH",identity,2,40,1,PC,52,0,
                     0x05000000,52,32,1,0,0,0)
    phdr=struct.pack("<8I",1,0x100,PC,PC,len(code_bytes),len(code_bytes),5,0x100)
    return head+phdr+bytes(0x100-len(head)-len(phdr))+code_bytes

def run(qemu, profile, with_i2s=True):
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        elf=root/"sai-test.elf"
        elf.write_bytes(make_elf())
        text=profile.read_text(encoding="utf-8")
        if with_i2s:
            assert "kind=imx7ulp-i2s" in text, "profile missing SAI mapping"
        else:
            text=re.sub(r"(?ms)^\[i2s[01]-m4\]\n.*?(?=^\[|\Z)", "", text)
            assert "kind=imx7ulp-i2s" not in text
        ini=root/"profile.ini";ini.write_text(text, encoding="utf-8")
        env=os.environ.copy();env["EXESX_MEMORY_PROFILE"]=str(ini)
        lib=qemu.resolve().parent/"lib"
        if lib.is_dir():
            env["LD_LIBRARY_PATH"]=str(lib)+os.pathsep+env.get("LD_LIBRARY_PATH","")
        port=choose_port()
        cmd=[str(qemu.resolve()),"-machine","exesx","-m","64M",
             "-accel","tcg","-display","none","-serial","none","-monitor",
             "none","-no-reboot","-S","-qmp",
             "tcp:127.0.0.1:{},server=on,wait=off".format(port),
             "-device","loader,file={},cpu-num=0".format(elf)]
        with (root/"qemu-console-private.log").open("wb") as log:
            proc=subprocess.Popen(cmd,env=env,stdin=subprocess.DEVNULL,
                                  stdout=log,stderr=subprocess.STDOUT)
            try:
                with connect(port,proc) as sock:
                    qmp=QMP(sock)
                    for base in (0x41037000,0x410aa000):
                        valid=qmp.hmp("xp /1wx 0x{:x}".format(base+0x08))
                        invalid=qmp.hmp("xp /1wx 0x{:x}".format(base+0x30))
                        if with_i2s:
                            assert "0x00000000" in valid, valid
                        else:
                            assert "Cannot access memory" in valid, valid
                        assert "Cannot access memory" in invalid, invalid
                    if with_i2s:
                        qmp.execute("cont")
                        time.sleep(.7)
                        values=[]
                        for bank in range(2):
                            for off in range(0,28,4):
                                addr=OUT+bank*32+off
                                result=qmp.hmp("xp /1wx 0x{:x}".format(addr))
                                m=re.search(r":\s+0x([0-9a-fA-F]+)",result)
                                if not m: raise AssertionError(result)
                                values.append(int(m.group(1),16))
                        expect=[0,0x4009,0x80000100,0,0,0x200040,0]*2
                        assert values==expect, (list(map(hex,values)),list(map(hex,expect)))
            finally:
                proc.terminate()
                try: proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    proc.kill();proc.wait()
    print("PASS SAI0/SAI1", "real ARM control/read/FR-reset and reserved gaps" if with_i2s
          else "unmapped fault control", flush=True)

if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--qemu",type=Path,required=True)
    p.add_argument("--profile",type=Path,required=True)
    a=p.parse_args()
    run(a.qemu.resolve(),a.profile.resolve(),True)
    run(a.qemu.resolve(),a.profile.resolve(),False)
