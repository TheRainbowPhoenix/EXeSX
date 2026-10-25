#!/usr/bin/env python3
"""Real ARM ADC FIFO/watermark regression; no Casio firmware or guest patch.

Tests the original empty-source baseline and explicitly opt-in raw sample.
Both test cases execute real ARM MMIO reads/writes; no direct register
modification by host and no fake IPC or menu response.
"""
import argparse
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import time

ARM_PC=0x60000000
OUT=0x62007000

def make_elf():
    words, literals = [], []
    def op(x): words.append(x)
    def lit(reg,val): literals.append((len(words),reg,val));op(0)
    def load(reg,base,off=0): op(0xe5900000|(base<<16)|(reg<<12)|off)
    def store(reg,base,off=0): op(0xe5800000|(base<<16)|(reg<<12)|off)
    lit(7, OUT)
    for bank,addr in enumerate((0x41041000,0x410ad000)):
        lit(0,addr)
        lit(1,1)
        store(1,0,0x10)      # CTRL.ADCEN
        store(1,0,0xc0)      # TCTRL0.TCMD=1
        store(1,0,0x100)     # CMD1L initialized (reference channel value)
        lit(1,0x00020000)
        store(1,0,0x30)      # FIFO watermark 2, hardware count=0
        lit(1,1)
        store(1,0,0x18)      # IE.FWMIE0
        for k in range(3):
            store(1,0,0x34)  # SWTRIG0, one genuine conversion attempt
        load(2,0,0x14);store(2,7,bank*48)     # STAT.RDY0
        load(2,0,0x30);store(2,7,bank*48+4)   # FCOUNT==3 if sourced
        load(2,0,0x300);store(2,7,bank*48+8)  # first FIFO
        load(2,0,0x14);store(2,7,bank*48+12)  # ready deasserted at count=2
        load(2,0,0x300);store(2,7,bank*48+16)
        load(2,0,0x300);store(2,7,bank*48+20)
        load(2,0,0x30);store(2,7,bank*48+24)  # FCOUNT0 after pop
        load(2,0,0x300);store(2,7,bank*48+28) # empty
        load(2,0,0x14);store(2,7,bank*48+32)  # STATUS
    op(0xeafffffe)           # harmless infinite original-ARM loop
    for pos,reg,value in literals:
        dest=len(words)*4
        words.append(value)
        disp=dest-(pos*4+8)
        if not 0<=disp<=4095:
            raise ValueError("ARM literal pool overflow")
        words[pos]=0xe59f0000|(reg<<12)|disp
    body=struct.pack("<%dI"%len(words),*words)
    ident=b"\x7fELF\x01\x01\x01"+bytes(9)
    header=struct.pack("<16sHHIIIIIHHHHHH",ident,2,40,1,ARM_PC,52,0,
                       0x05000000,52,32,1,0,0,0)
    phdr=struct.pack("<8I",1,0x100,ARM_PC,ARM_PC,len(body),len(body),5,0x100)
    return header+phdr+bytes(0x100-len(header)-len(phdr))+body

def run(qemu,profile,raw0,raw1):
    with tempfile.TemporaryDirectory() as folder:
        temp=Path(folder)
        elf=temp/"adc-conv.elf"
        elf.write_bytes(make_elf())
        env=os.environ.copy()
        env["EXESX_MEMORY_PROFILE"]=str(profile.resolve())
        if raw0 is None:
            env.pop("EXESX_ADC0_SAMPLE_RAW",None)
            env.pop("EXESX_ADC1_SAMPLE_RAW",None)
        else:
            env["EXESX_ADC0_SAMPLE_RAW"]=hex(raw0)
            env["EXESX_ADC1_SAMPLE_RAW"]=hex(raw1)
        lib=qemu.resolve().parent/"lib"
        if lib.is_dir():
            env["LD_LIBRARY_PATH"]=str(lib)+os.pathsep+env.get("LD_LIBRARY_PATH","")
        # Native Windows HMP stdio echo is asynchronous and can corrupt
        # interleaved monitor commands. QMP gives one command/response pair
        # and never blocks on an unread child stderr pipe.
        from drive_factory_menu import QMP, choose_port, connect
        port=choose_port()
        cmd=[str(qemu.resolve()),"-machine","exesx","-m","64M",
             "-accel","tcg","-display","none","-serial","none",
             "-monitor","none","-no-reboot","-S",
             "-qmp",f"tcp:127.0.0.1:{port},server=on,wait=off",
             "-device",f"loader,file={elf},cpu-num=0"]
        fields={}
        with (temp/"qemu-private-console.log").open("wb") as console:
            proc=subprocess.Popen(cmd,env=env,stdin=subprocess.DEVNULL,
                                  stdout=console,stderr=subprocess.STDOUT)
            try:
                with connect(port,proc) as sock:
                    qmp=QMP(sock)
                    qmp.execute("cont")
                    time.sleep(.65)
                    for n in range(21):
                        address=OUT+n*4
                        output=qmp.hmp(f"xp /1wx 0x{address:08x}")
                        m=re.search(r"(?im)^0*"+f"{address:08x}"+r":\s+0x([0-9a-f]+)",output)
                        if not m:
                            raise AssertionError(f"Missing guest result {n} at {address:#x}: {output}")
                        fields[n]=int(m.group(1),16)
            finally:
                proc.terminate()
                try: proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
        for bank,raw in enumerate((raw0,raw1)):
            n=bank*12
            if raw is None:
                expected=[0,0x20000,0,0,0,0,0x20000,0,0]
            else:
                fifoword=0x80000000 | (1<<24) | raw
                expected=[1,0x00020003,fifoword,0,fifoword,fifoword,0x20000,0,0]
            got=[fields[i] for i in range(n,n+9)]
            if got!=expected:
                raise AssertionError(f"ADC{bank}: {list(map(hex,got))} != {list(map(hex,expected))}")
        print("PASS actual ARM ADC FIFO/watermark", "source off" if raw0 is None else "source explicitly configured")

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--qemu",type=Path,required=True)
    p.add_argument("--profile",type=Path,required=True)
    a=p.parse_args()
    run(a.qemu,a.profile,None,None)
    run(a.qemu,a.profile,0x1230,0x4560)
