#!/usr/bin/env python3
"""Firmware-free ARM check for NXP DMA0 CR and idle flags (not DMA copies)."""
from pathlib import Path
import argparse
import os
import re
import struct
import subprocess
import time

BASE=0x60000000
OUT=0x62007200

def elf():
    w=[]
    lits=[]
    def ins(x): w.append(x)
    def lit(reg,val):
        lits.append((len(w),reg,val))
        ins(0)
    def load(reg,base,off=0):
        ins(0xe5900000 | (base<<16) | (reg<<12) | off)
    def store(reg,base,off=0):
        ins(0xe5800000 | (base<<16) | (reg<<12) | off)
    lit(7,OUT)
    lit(0,0x41008000)
    lit(1,0x00000100)
    store(1,0,0)   # DMA CR, do not begin transfer
    load(2,0,0);store(2,7,0)
    load(2,0,4);store(2,7,4)   # ES idle
    load(2,0,0x34);store(2,7,8) # HRS idle
    lit(1,0x3)
    store(1,0,0x0c)  # ERQ readback; no channel is serviced
    load(2,0,0x0c);store(2,7,12)
    ins(0xeafffffe)
    for at,reg,val in lits:
        off=len(w)*4-(at*4+8)
        assert 0<=off<4096
        w[at]=0xe59f0000 | (reg<<12) | off
        w.append(val)
    body=struct.pack(f'<{len(w)}I',*w)
    ident=b'\x7fELF\x01\x01\x01'+bytes(9)
    head=struct.pack('<16sHHIIIIIHHHHHH',ident,2,40,1,BASE,52,0,0x05000000,52,32,1,0,0,0)
    ph=struct.pack('<8I',1,0x100,BASE,BASE,len(body),len(body),5,0x100)
    return head+ph+bytes(0x100-len(head)-len(ph))+body

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--qemu',type=Path,default=Path('build/qemu-system-arm'))
    p.add_argument('--profile',type=Path,default=Path('profiles/imx7ulp-early-boot.ini'))
    p.add_argument('--elf',type=Path,default=Path('build/dma0-early.elf'))
    args=p.parse_args()
    args.elf.parent.mkdir(parents=True,exist_ok=True)
    args.elf.write_bytes(elf())
    env=os.environ.copy()
    env['EXESX_MEMORY_PROFILE']=str(args.profile.resolve())
    lib=args.qemu.resolve().parent/'lib'
    if lib.is_dir():env['LD_LIBRARY_PATH']=str(lib)+':'+env.get('LD_LIBRARY_PATH','')
    cmd=[str(args.qemu.resolve()),'-machine','exesx','-m','64M','-accel','tcg',
         '-display','none','-serial','none','-monitor','stdio','-no-reboot',
         '-device',f'loader,file={args.elf.resolve()},cpu-num=0']
    child=subprocess.Popen(cmd,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT,text=True)
    try:
        time.sleep(.5)
        script=''.join(f'xp /1wx 0x{OUT+4*i:08x}\n' for i in range(4))+'quit\n'
        result,_=child.communicate(script,timeout=15)
    finally:
        if child.poll() is None: child.kill();child.wait()
    values=[]
    for i in range(4):
        m=re.search(r'(?im)^0*'+f'{OUT+4*i:08x}'+r':\s+0x([0-9a-f]+)',result)
        if not m:raise AssertionError('Missing ARM guest result: '+result[-800:])
        values.append(int(m.group(1),16))
    if values != [0x100,0,0,3]:
        raise AssertionError(f'DMA0 early-control mismatch: {list(map(hex,values))}')
    print('PASS real ARM DMA0 CR/ES/HRS/ERQ subset; NO DMA transfers emulated')

if __name__=='__main__':
    main()
