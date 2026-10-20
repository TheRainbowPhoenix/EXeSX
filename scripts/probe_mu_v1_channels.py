#!/usr/bin/env python3
"""Firmware-free real ARM verification of NXP i.MX7ULP MU v1 bit numbering.

Checks all four TRn->RRn handshakes plus GIRn/GIPn/W1C status using actual
ARM guest instructions. NXP/Linux MU v1 channel0=bit3, channel3=bit0.
"""
import argparse
import os
from pathlib import Path
import re
import struct
import subprocess
import time

RESET = 0x60000000
OUT = 0x6200B000


def probe_elf():
    op = []
    literals = []
    def ins(word):
        op.append(word)
    def literal(reg, val):
        literals.append((len(op), reg, val))
        ins(0)
    def ldr(reg, base, off=0):
        ins(0xe5900000 | (base << 16) | (reg << 12) | off)
    def store(reg, base, off=0):
        ins(0xe5800000 | (base << 16) | (reg << 12) | off)
    literal(7, OUT)
    # Record channel 0..3 at distinct guest RAM positions, each 6 words:
    for channel in range(4):
        i = channel * 24
        literal(0, 0x41022000)  # MU side A
        literal(1, 0xA7C30000 + channel)
        store(1, 0, 0x20 + 4*channel)  # TR[channel]
        literal(0, 0x40220000)  # peer side B
        ldr(2, 0, 0x60)
        store(2, 7, i)  # peer SR, RF bit for channel
        ldr(2, 0, 0x40 + 4*channel)
        store(2, 7, i+4)  # actual payload
        ldr(2, 0, 0x60)
        store(2, 7, i+8)  # peer RF flag should now be clear
        literal(0, 0x41022000)
        ldr(2, 0, 0x60)
        store(2, 7, i+12)  # sender TEn restored
        literal(1, 1 << (16+3-channel)) # GIRn hardware v1 MSB channel0
        store(1, 0, 0x64)  # peer GP pending
        literal(0, 0x40220000)
        ldr(2, 0, 0x60)
        store(2, 7, i+16)  # peer GIPn
        literal(1, 1 << (28+3-channel))
        store(1, 0, 0x60)  # W1C only this GIP
        ldr(2, 0, 0x60)
        store(2, 7, i+20)  # GP cleared
    ins(0xeafffffe)
    for n, reg, value in literals:
        pos = len(op)*4
        op.append(value)
        offset = pos - (n*4+8)
        assert 0 <= offset <= 4095
        op[n] = 0xe59f0000 | (reg << 12) | offset
    payload = struct.pack('<%dI' % len(op), *op)
    ident = b'\x7fELF\x01\x01\x01' + bytes(9)
    hdr = struct.pack('<16sHHIIIIIHHHHHH',ident,2,40,1,RESET,52,0,
                      0x05000000,52,32,1,0,0,0)
    phdr = struct.pack('<8I',1,0x100,RESET,RESET,len(payload),len(payload),5,0x100)
    return hdr+phdr+bytes(0x100-len(hdr)-len(phdr))+payload


def run(qemu: Path, profile: Path, elf: Path):
    env=os.environ.copy()
    env['EXESX_MEMORY_PROFILE']=str(profile.resolve())
    env.pop('EXESX_EXPERIMENTAL_MU_IRQ',None)
    lib=qemu.resolve().parent/'lib'
    if lib.is_dir():
        env['LD_LIBRARY_PATH']=str(lib)+':'+env.get('LD_LIBRARY_PATH','')
    cmd=[str(qemu.resolve()),'-machine','exesx','-m','64M','-accel','tcg',
         '-display','none','-serial','none','-monitor','stdio',
         '-no-reboot','-device',f'loader,file={elf.resolve()},cpu-num=0']
    proc=subprocess.Popen(cmd,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT,text=True)
    try:
        time.sleep(.45)
        script=''.join(f'xp /1wx 0x{OUT+i*4:08x}\n' for i in range(24))+'quit\n'
        result,_=proc.communicate(script,timeout=15)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    values=[]
    for i in range(24):
        m=re.search(r'(?im)^0*'+f'{OUT+i*4:08x}'+r':\s+0x([0-9a-f]+)',result)
        if not m:
            raise AssertionError(f'Missing ARM guest result {i}: {result[-1600:]}')
        values.append(int(m.group(1),16))
    return values


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--qemu',type=Path,default=Path('build/qemu-system-arm'))
    p.add_argument('--profile',type=Path,default=Path('profiles/imx7ulp-early-boot.ini'))
    p.add_argument('--elf',type=Path,default=Path('build/mu-v1-bits.elf'))
    args=p.parse_args()
    args.elf.parent.mkdir(parents=True,exist_ok=True)
    args.elf.write_bytes(probe_elf())
    vals=run(args.qemu,args.profile,args.elf)
    for ch in range(4):
        bit = 1 << (3-ch)
        expected=[(bit << 24) | (15 << 20),
                  0xA7C30000+ch,
                  (15 << 20),
                  (15 << 20),
                  (bit << 28) | (15 << 20),
                  (15 << 20)]
        actual=vals[ch*6:(ch+1)*6]
        if actual!=expected:
            raise AssertionError(f'NXP MU v1 channel {ch}: actual '
                                 f'{list(map(hex,actual))} != '
                                 f'{list(map(hex,expected))}')
    print('PASS: all four real ARM TR/RR channels use bit (3-channel);')
    print('PASS: sending and reading clears RF/restores TE; GP GIR/GIP W1C per channel.')


if __name__=='__main__':main()
