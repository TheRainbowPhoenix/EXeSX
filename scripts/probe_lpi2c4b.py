#!/usr/bin/env python3
"""Real ARM CPU differential test: missing I2C slave vs opt-in scripted reply.

No proprietary firmware or chip identity. The diagnostic slave is enabled
only for this one process, only on LPI2C2 and only at 7-bit address 0x4B.
"""
import argparse
import os
from pathlib import Path
import re
import struct
import subprocess
import time

BASE=0x60000000
OUT=0x62005000

def firmware_free_elf():
    insns=[]
    literals=[]
    def ins(word):
        insns.append(word)
    def lit(reg,val):
        literals.append((len(insns),reg,val))
        ins(0)
    def load(reg,base,off=0):
        ins(0xe5900000 | (base<<16) | (reg<<12) | off)
    def store(reg,base,off=0):
        ins(0xe5800000 | (base<<16) | (reg<<12) | off)

    lit(7,OUT)
    lit(0,0x41035000)
    lit(1,1)
    store(1,0,0x10)       # MCR MEN
    lit(1,0x496)
    store(1,0,0x60)       # MTDR START 0x4b write
    load(2,0,0x14)
    store(2,7,0)
    lit(1,0x497)
    store(1,0,0x60)       # repeated START read
    lit(1,0x100)
    store(1,0,0x60)       # receive 1 byte
    load(2,0,0x14)
    store(2,7,4)
    load(2,0,0x70)
    store(2,7,8)         # MRDR first byte
    load(2,0,0x70)
    store(2,7,12)        # MRDR RXEMPTY
    ins(0xeafffffe)
    for n,reg,value in literals:
        pool=len(insns)*4
        insns.append(value)
        disp=pool-(n*4+8)
        assert 0<=disp<4096
        insns[n]=0xe59f0000 | (reg<<12) | disp
    payload=struct.pack('<%dI'%len(insns),*insns)
    ident=b'\x7fELF\x01\x01\x01'+bytes(9)
    head=struct.pack('<16sHHIIIIIHHHHHH',ident,2,40,1,BASE,52,0,
                     0x05000000,52,32,1,0,0,0)
    phdr=struct.pack('<8I',1,0x100,BASE,BASE,len(payload),len(payload),5,0x100)
    return head+phdr+bytes(0x100-len(head)-len(phdr))+payload

def run(qemu,profile,elf,probe):
    env=os.environ.copy()
    env['EXESX_MEMORY_PROFILE']=str(profile.resolve())
    env.pop('EXESX_I2C4B_REPLY_HEX',None)
    if probe:
        env['EXESX_I2C4B_REPLY_HEX']='ab12'
    lib=qemu.resolve().parent/'lib'
    if lib.is_dir():
        env['LD_LIBRARY_PATH']=str(lib)+':'+env.get('LD_LIBRARY_PATH','')
    cmd=[str(qemu.resolve()),'-machine','exesx','-m','64M',
         '-accel','tcg','-display','none','-serial','none',
         '-monitor','stdio','-no-reboot',
         '-device',f'loader,file={elf.resolve()},cpu-num=0']
    child=subprocess.Popen(cmd,env=env,stdin=subprocess.PIPE,
                           stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                           text=True)
    try:
        time.sleep(.6)
        monitor=''.join(f'xp /1wx 0x{OUT+4*i:08x}\n' for i in range(4))+'quit\n'
        output,_=child.communicate(monitor,timeout=15)
    finally:
        if child.poll() is None:
            child.kill();child.wait()
    found=[]
    for i in range(4):
        match=re.search(r'(?im)^0*'+f'{OUT+4*i:08x}'+r':\s+0x([0-9a-f]+)',output)
        if not match:
            raise AssertionError(f'missing word {i} from ARM test: '+output[-1500:])
        found.append(int(match.group(1),16))
    return found

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--qemu',type=Path,default=Path('build/qemu-system-arm'))
    p.add_argument('--profile',type=Path,
                   default=Path('profiles/imx7ulp-early-boot.ini'))
    p.add_argument('--elf',type=Path,default=Path('build/i2c4b-compare.elf'))
    args=p.parse_args()
    args.elf.parent.mkdir(parents=True,exist_ok=True)
    args.elf.write_bytes(firmware_free_elf())
    no_slave=run(args.qemu,args.profile,args.elf,False)
    scripted=run(args.qemu,args.profile,args.elf,True)
    print('Actual ARM statuses: NACK',list(map(hex,no_slave)),
          'vs scripted',list(map(hex,scripted)))
    if no_slave != [0x401,0x401,0x4000,0x4000]:
        raise AssertionError('Unattached I2C must NACK and signal RXEMPTY')
    if scripted != [1,3,0xab,0x4000]:
        raise AssertionError('Only opt-in diagnostic I2C 0x4B should ACK and return supplied byte')
    print('PASS: default NACK, opt-in test ACK/RDF/byte/RXEMPTY isolated')

if __name__=='__main__':
    main()
