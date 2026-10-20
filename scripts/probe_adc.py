#!/usr/bin/env python3
"""Firmware-free ARM regression for real NXP ADC0/ADC1 register behavior.

No analog input is invented. Real CPU writes CTRL, CFG, FCTRL and SWTRIG,
and confirms reset self-clears, FIFO hardware count is zero, and there
is no fabricated VALID data bit.
"""
from pathlib import Path
import argparse
import os
import re
import struct
import subprocess
import time

BASE=0x60000000
OUT=0x62007000

def elf():
    words=[]
    pool=[]
    def raw(x): words.append(x)
    def lit(reg,val):
        pool.append((len(words),reg,val))
        raw(0)
    def load(reg,base,off=0):
        raw(0xe5900000|(base<<16)|(reg<<12)|off)
    def store(reg,base,off=0):
        raw(0xe5800000|(base<<16)|(reg<<12)|off)
    lit(7,OUT)
    lit(0,0x41041000)
    lit(1,3)
    store(1,0,0x10)  # CTRL: EN+RST, RST self-clears
    load(2,0,0x10);store(2,7,0)
    lit(1,0x10400000)
    store(1,0,0x20)
    load(2,0,0x20);store(2,7,4)
    lit(1,0x0003001f)
    store(1,0,0x30)
    load(2,0,0x30);store(2,7,8)
    lit(1,1)
    store(1,0,0x34)
    load(2,0,0x34);store(2,7,12)
    load(2,0,0x300);store(2,7,16)
    load(2,0,0x14);store(2,7,20)
    lit(0,0x410ad000)
    store(1,0,0x10)
    load(2,0,0x10);store(2,7,24)
    raw(0xeafffffe)
    for at,reg,val in pool:
        dest=len(words)*4
        words.append(val)
        disp=dest-(at*4+8)
        assert 0<=disp<4096
        words[at]=0xe59f0000|(reg<<12)|disp
    body=struct.pack(f'<{len(words)}I',*words)
    ident=b'\x7fELF\x01\x01\x01'+bytes(9)
    head=struct.pack('<16sHHIIIIIHHHHHH',ident,2,40,1,BASE,52,0,0x05000000,
                     52,32,1,0,0,0)
    ph=struct.pack('<8I',1,0x100,BASE,BASE,len(body),len(body),5,0x100)
    return head+ph+bytes(0x100-len(head)-len(ph))+body

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--qemu',type=Path,default=Path('build/qemu-system-arm'))
    p.add_argument('--profile',type=Path,default=Path('profiles/imx7ulp-early-boot.ini'))
    p.add_argument('--elf',type=Path,default=Path('build/adc-probe.elf'))
    args=p.parse_args()
    args.elf.parent.mkdir(parents=True,exist_ok=True)
    args.elf.write_bytes(elf())
    env=os.environ.copy()
    env['EXESX_MEMORY_PROFILE']=str(args.profile.resolve())
    lib=args.qemu.resolve().parent/'lib'
    if lib.is_dir():
        env['LD_LIBRARY_PATH']=str(lib)+':'+env.get('LD_LIBRARY_PATH','')
    cmd=[str(args.qemu.resolve()),'-machine','exesx','-m','64M',
         '-accel','tcg','-display','none','-serial','none','-monitor','stdio',
         '-no-reboot','-device',f'loader,file={args.elf.resolve()},cpu-num=0']
    proc=subprocess.Popen(cmd,env=env,stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    try:
        time.sleep(.55)
        script=''.join(f'xp /1wx 0x{OUT+i*4:08x}\n' for i in range(7))+'quit\n'
        output,_=proc.communicate(script,timeout=15)
    finally:
        if proc.poll() is None:
            proc.kill();proc.wait()
    result=[]
    for i in range(7):
        m=re.search(r'(?im)^0*'+f'{OUT+i*4:08x}'+r':\s+0x([0-9a-f]+)',output)
        if not m:
            raise AssertionError(f'no guest word {i}: '+output[-1400:])
        result.append(int(m.group(1),16))
    expect=[1,0x10400000,0x00030000,0,0,0,1]
    if result != expect:
        raise AssertionError(f'ADC mismatch: got {[hex(x) for x in result]}')
    print('PASS: real ARM ADC0/ADC1 reset/config/FIFO/trigger/readback')
    print('Observed:',*[hex(v) for v in result])

if __name__=='__main__':
    main()
