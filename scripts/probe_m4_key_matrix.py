#!/usr/bin/env python3
"""Actual ARM/QEMU test: opt-in M4 keyboard column requires matching driven row.

No original Casio firmware or simulated A7 key event injected. The A7
synthetic program drives authentic M4 GPIO row output registers, samples
the PDIR column and saves the three readings in private synthetic RAM.
"""
import argparse
import os
from pathlib import Path
import struct
import tempfile
from hmp_memory import qmp_memory_words

BASE=0x60000000
RESULT=0x6200B600
GPIOA=0x4100F000
A_HIGH=0x808C6008
ROW8=(1<<21)
ROW6=(1<<17)
COL93=(1<<31)
COL94=(1<<23)


def make_elf(output_override=False):
    words, lits=[],[]
    def lit(reg,val):
        lits.append((len(words),reg,val));words.append(0)
    def store(src,reg,off):
        words.append(0xe5800000 | reg<<16 | src<<12 | off)
    def load(dst,reg,off):
        words.append(0xe5900000 | reg<<16 | dst<<12 | off)
    lit(0,GPIOA)
    lit(7,RESULT)
    lit(1,ROW8|ROW6|(COL93 if output_override else 0))
    store(1,0,0x14)      # PDDR rows are outputs
    lit(1,ROW8|ROW6|(COL93 if output_override else 0))
    store(1,0,4)         # PSOR idle high
    lit(1,ROW8)
    store(1,0,8)         # PCOR: original M4 drove row8 low
    load(2,0,0x10)
    store(2,7,0)
    lit(1,ROW8)
    store(1,0,4)         # release row8 before selecting row6
    lit(1,ROW6)
    store(1,0,8)         # PCOR: drive different row6 low
    load(2,0,0x10)
    store(2,7,4)
    lit(1,ROW6)
    store(1,0,4)         # release row6 before selecting row8
    lit(1,ROW8)
    store(1,0,8)         # select row8 again
    load(2,0,0x10)
    store(2,7,8)
    words.append(0xeafffffe)
    pool=len(words)
    for n,(pos,reg,val) in enumerate(lits):
        offset=4*(pool+n-pos)-8
        if not 0<=offset<=4095:raise ValueError('Literals beyond ARM LDR reach')
        words[pos]=0xe59f0000 | reg<<12 | offset
        words.append(val)
    body=struct.pack('<%dI'%len(words),*words)
    ident=b'\x7fELF\x01\x01\x01'+bytes(9)
    head=struct.pack('<16sHHIIIIIHHHHHH',ident,2,40,1,BASE,52,0,
                     0x05000000,52,32,1,0,0,0)
    phdr=struct.pack('<8I',1,0x100,BASE,BASE,len(body),len(body),5,0x100)
    return head+phdr+bytes(0x100-len(head)-len(phdr))+body


def read(qemu, profile, key, enable=True, output_override=False):
    with tempfile.TemporaryDirectory() as root:
        d=Path(root)
        file=d/'key-contact.txt';file.write_text(hex(key)+'\n')
        elf=d/'synthetic-m4-matrix.elf';elf.write_bytes(make_elf(output_override))
        env=os.environ.copy()
        env['EXESX_MEMORY_PROFILE']=str(profile.resolve())
        env['EXESX_GPIOA_INPUT_MASK']=hex(A_HIGH)
        env['EXESX_GPIOB_INPUT_MASK']='0xc8'
        env.pop('EXESX_M4_KEY_MATRIX_FILE',None)
        if enable:
            env['EXESX_M4_KEY_MATRIX_FILE']=str(file.resolve())
        library=qemu.resolve().parent/'lib'
        if library.is_dir():
            env['LD_LIBRARY_PATH']=str(library)+os.pathsep+env.get('LD_LIBRARY_PATH','')
        cmd=[str(qemu.resolve()),'-machine','exesx','-m','64M','-accel','tcg',
             '-display','none','-serial','none','-monitor','stdio','-no-reboot',
             '-device',f'loader,file={elf.resolve()},cpu-num=0']
        return qmp_memory_words(cmd,env,RESULT,3,delay=0.6)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--qemu',type=Path,default=Path('build/qemu-system-arm'))
    ap.add_argument('--profile',type=Path,default=Path('profiles/imx7ulp-early-boot.ini'))
    args=ap.parse_args()
    for name,key,enabled,over in (
        ('no-file control',0x93,False,False),
        ('key released',0,True,False),
        ('0x93 row8 col7',0x93,True,False),
        ('0x94 row6 col6',0x94,True,False),
        ('0x93 output direction',0x93,True,True),
    ):
        first,second,third=read(args.qemu,args.profile,key,enabled,over)
        if key==0x93 and enabled and not over:
            assert first & COL93==0 and second & COL93 and third & COL93==0, (
                name, hex(first),hex(second),hex(third))
        elif key==0x94 and enabled:
            assert first & COL94 and second & COL94==0 and third & COL94, (
                name,hex(first),hex(second),hex(third))
        else:
            assert first & COL93 and second & COL93 and third & COL93, (
                name,hex(first),hex(second),hex(third))
        print(f'PASS {name}: PDIR row8={first:#010x} row6={second:#010x} row8-again={third:#010x}')
    print('PASS genuine ARM MMIO row-gated M4 key contact, no A7 event fabrication')


if __name__=='__main__':
    main()
