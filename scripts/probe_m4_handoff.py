#!/usr/bin/env python3
"""Firmware-free A7->M4 ROM-handoff test using REAL Thumb code on CPU1.

Builds a tiny two-segment ARM ELF: the A7 writes the CM4 reset vector to
SIM0_DGO_GP7 and triggers its update; the M4 reset handler writes a magic
value in shared DRAM. This test cannot pass if the QEMU M4 never executes.
No proprietary Casio bytes are used.
"""
from pathlib import Path
import argparse
import os
import re
import struct
import subprocess
import time

A7=0x60000000
M4=0x1ffd0000
RESULT=0x6200c000
MAGIC=0x4d344d34

def elf():
    # ARM A7 bootstrap: LDR literals, write GP7, write UPDATE_DGO_GP7.
    # Literal pool follows the loop, with immediate offsets from PC+8.
    code=[0xe59f0014,  # ldr r0,[pc,#20] => at 0x1c: GP7
          0xe59f1014,  # ldr r1,[pc,#20] => at 0x20: M4 thumb PC
          0xe5801000,  # str r1,[r0]
          0xe59f0010,  # ldr r0,[pc,#16] => at 0x24: DGO_CTRL1
          0xe3a01001,  # mov r1,#1
          0xe5801000,  # str r1,[r0]
          0xeafffffe,  # infinite loop
          0x410a3070,  # at 0x1c
          0x1ffd0101,  # at 0x20
          0x410a3054]  # at 0x24
    a7=struct.pack('<%dI'%len(code),*code)
    # 0x1ffd0100 thumb:
    # ldr r0,[pc,#8]  -> 0x1ffd010c => shared result address
    # ldr r1,[pc,#12] -> 0x1ffd0110 => expected magic
    # str r1,[r0]; b . ; nop;nop
    m4=bytearray(0x120)
    struct.pack_into('<2I',m4,0,0x20001c00,0x1ffd0101)
    struct.pack_into('<6H2I',m4,0x100,0x4802,0x4903,0x6001,0xe7fe,
                     0xbf00,0xbf00,RESULT,MAGIC)
    ident=b'\x7fELF\x01\x01\x01'+bytes(9)
    head=struct.pack('<16sHHIIIIIHHHHHH',ident,2,40,1,A7,52,0,
                     0x05000000,52,32,2,0,0,0)
    offset0=0x100
    offset1=0x200
    ph0=struct.pack('<8I',1,offset0,A7,A7,len(a7),len(a7),5,0x100)
    ph1=struct.pack('<8I',1,offset1,M4,M4,len(m4),len(m4),7,0x100)
    blob=bytearray(head+ph0+ph1)
    blob+=bytes(offset0-len(blob))
    blob+=a7
    blob+=bytes(offset1-len(blob))
    blob+=m4
    return blob

def run(qemu,profile,elffile,enabled):
    env=os.environ.copy()
    env['EXESX_MEMORY_PROFILE']=str(profile.resolve())
    env['EXESX_EXPERIMENTAL_M4_BOOT']='1' if enabled else '0'
    lib=qemu.resolve().parent/'lib'
    if lib.is_dir():
        env['LD_LIBRARY_PATH']=str(lib)+':'+env.get('LD_LIBRARY_PATH','')
    cmd=[str(qemu.resolve()),'-machine','exesx','-m','64M',
         '-accel','tcg','-display','none','-serial','none','-monitor','stdio',
         '-no-reboot','-device',f'loader,file={elffile.resolve()},cpu-num=0']
    proc=subprocess.Popen(cmd,env=env,stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                          text=True)
    try:
        time.sleep(0.75)
        output,_=proc.communicate(f'xp /1wx 0x{RESULT:x}\nquit\n',
                                  timeout=12)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    match=re.search(r'(?im)^0*'+f'{RESULT:x}'+r':\s+0x([0-9a-f]+)',output)
    if not match:
        raise AssertionError('Missing QEMU monitor result: '+output[-1600:])
    return int(match.group(1),16),output

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--qemu',type=Path,default=Path('build/qemu-system-arm'))
    p.add_argument('--profile',type=Path,default=Path('profiles/imx7ulp-early-boot.ini'))
    p.add_argument('--elf',type=Path,default=Path('build/m4-boot-probe.elf'))
    args=p.parse_args()
    args.elf.parent.mkdir(parents=True,exist_ok=True)
    args.elf.write_bytes(elf())
    val_off,off=run(args.qemu,args.profile,args.elf,False)
    val_on,on=run(args.qemu,args.profile,args.elf,True)
    if val_off!=0 or val_on!=MAGIC:
        raise AssertionError(f'M4 handoff failed: disabled={val_off:#x}, '
                             f'enabled={val_on:#x}\n'+on[-1400:])
    print('PASS: M4 ran real Thumb code and wrote shared DRAM only after GP7 handoff')
    print(f'disabled=0x{val_off:08x}, enabled=0x{val_on:08x}')

if __name__=='__main__':
    main()
