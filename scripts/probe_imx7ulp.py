#!/usr/bin/env python3
"""Firmware-free real ARM instruction probe for early i.MX7ULP peripherals."""
from pathlib import Path
import argparse
import os
import re
import struct
import subprocess
import time

RESET=0x60000000
OUT=0x62002000

def probe_elf():
    op=[]
    literals=[]
    def ins(word): op.append(word)
    def literal(reg,value):
        literals.append((len(op),reg,value));ins(0)
    def ldr(reg,base,off=0):
        ins(0xe5900000 | (base<<16) | (reg<<12) | off)
    def store(reg,base,off=0):
        ins(0xe5800000 | (base<<16) | (reg<<12) | off)
    literal(7,OUT)
    literal(0,0x4100f000)
    literal(1,0x10)
    store(1,0,4)       # GPIO PSOR set 0x10
    ldr(2,0)
    store(2,7,0)       # PDOR must reflect set
    store(1,0,8)       # GPIO PCOR clear 0x10
    ldr(2,0)
    store(2,7,4)
    store(1,0,0x14)    # GPIO PDDR direction
    ldr(2,0,0x14)
    store(2,7,8)
    literal(0,0x41026000)
    literal(1,0x40000000)
    store(1,0,0x3c)    # PCC0 RGPIO2P0
    ldr(2,0,0x3c)
    store(2,7,12)
    literal(0,0x403f0000)
    store(1,0,0x40)    # PCC2 FlexBus
    ldr(2,0,0x40)
    store(2,7,16)
    literal(0,0x4103d000)
    literal(1,0x20100)
    store(1,0,0x10)    # PCTLA PCR4
    ldr(2,0,0x10)
    store(2,7,20)
    literal(0,0x410a3c08)
    ldr(2,0,0)         # TSTMRB low
    store(2,7,24)
    ldr(2,0,4)         # TSTMRB high
    store(2,7,28)
    # SIM_DGO_CTRL1: GP7 update must trigger the ACK bit 13.
    literal(0,0x410a3054)
    literal(1,0x00000001)
    store(1,0)
    ldr(2,0)
    store(2,7,32)     # 0x2000, UPDATE strobe self-cleared
    literal(1,0x00002000)
    store(1,0)        # ACK W1C
    ldr(2,0)
    store(2,7,36)     # 0
    # SIM_DGO_CTRL0: GP1/GP2 simultaneous update => ACK bits 13/14.
    literal(0,0x410a3050)
    literal(1,0x00000003)
    store(1,0)
    ldr(2,0)
    store(2,7,40)     # 0x6000
    # SIM retention GP7 ordinary storage
    literal(0,0x410a3070)
    literal(1,0x0000abcd)
    store(1,0)
    ldr(2,0)
    store(2,7,44)     # 0x0000abcd
    # SCG1: FIRC is valid when enabled at direct BIOS entry.
    literal(0,0x403e0000)
    ldr(2,0,0x300)
    store(2,7,48)     # FIRC CSR = EN|VALID
    # SPLL enable -> VALID (bit24) status; disable -> no VALID.
    literal(1,0)
    store(1,0,0x600)
    ldr(2,0,0x600)
    store(2,7,52)     # 0
    literal(1,1)
    store(1,0,0x600)
    ldr(2,0,0x600)
    store(2,7,56)     # 0x01000001
    # SPLLPFD0 fractional divider 29: ungated => VALID bit6.
    literal(1,0x1d)
    store(1,0,0x60c)
    ldr(2,0,0x60c)
    store(2,7,60)     # 0x5d
    # Gate it: VALID bit clears; read-only status cannot be forced.
    literal(1,0x9d)
    store(1,0,0x60c)
    ldr(2,0,0x60c)
    store(2,7,64)     # 0x9d
    literal(1,0x40)
    store(1,0,0x60c)
    ldr(2,0,0x60c)
    store(2,7,68)     # 0
    # TPM6 SC/CNT/MOD control, matches the BIOS timer initialization.
    literal(0,0x40a10000)
    literal(1,0)
    store(1,0,0x10)  # Stop
    store(1,0,0x14)  # Reset counter
    literal(1,0xffffffff)
    store(1,0,0x18)  # Set full modulo
    literal(1,8)
    store(1,0,0x10)  # CMOD=1, PS=0, start counter
    ldr(2,0,0x10)
    store(2,7,72)    # SC=8
    ldr(2,0,0x18)
    store(2,7,76)    # MOD=0xffffffff
    # PMC1 +0x14 (VLPS): guest modifies the LDO voltage level field.
    literal(0,0x40400000)
    literal(1,0x40000)
    store(1,0,0x14)
    ldr(2,0,0x14)
    store(2,7,80)
    ins(0xeafffffe)   # final infinite loop
    for n,reg,value in literals:
        pos=len(op)*4
        op.append(value)
        off=pos-(n*4+8)
        assert 0<=off<=4095
        op[n]=0xe59f0000 | (reg<<12) | off
    data=struct.pack('<%dI'%len(op),*op)
    ident=b'\x7fELF\x01\x01\x01'+bytes(9)
    hdr=struct.pack('<16sHHIIIIIHHHHHH',ident,2,40,1,RESET,52,0,
                    0x05000000,52,32,1,0,0,0)
    phdr=struct.pack('<8I',1,0x100,RESET,RESET,len(data),len(data),5,0x100)
    return hdr+phdr+bytes(0x100-len(hdr)-len(phdr))+data

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--qemu',type=Path,default=Path('build/qemu-system-arm'))
    p.add_argument('--profile',type=Path,default=Path('profiles/imx7ulp-early-boot.ini'))
    p.add_argument('--elf',type=Path,default=Path('build/imx7ulp-probe.elf'))
    args=p.parse_args()
    args.elf.parent.mkdir(parents=True,exist_ok=True)
    args.elf.write_bytes(probe_elf())
    env=os.environ.copy()
    env['EXESX_MEMORY_PROFILE']=str(args.profile.resolve())
    lib=args.qemu.resolve().parent/'lib'
    if lib.is_dir():
        env['LD_LIBRARY_PATH']=str(lib)+':'+env.get('LD_LIBRARY_PATH','')
    cmd=[str(args.qemu.resolve()),'-machine','exesx','-m','64M',
         '-accel','tcg','-display','none','-serial','none','-monitor','stdio',
         '-no-reboot','-device',
         f'loader,file={args.elf.resolve()},cpu-num=0']
    proc=subprocess.Popen(cmd,env=env,stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                          text=True)
    try:
        time.sleep(0.65)
        commands=''.join(f'xp /1wx 0x{OUT+i*4:08x}\n' for i in range(21))+'quit\n'
        output,_=proc.communicate(commands,timeout=12)
    finally:
        if proc.poll() is None:
            proc.kill();proc.wait()
    values=[]
    for i in range(21):
        match=re.search(r'(?im)^0*'+f'{OUT+i*4:08x}'+
                        r':\s+0x([0-9a-f]+)',output)
        if not match:
            raise AssertionError(f'Missing guest result {i}: {output[-1200:]}')
        values.append(int(match.group(1),16))
    expected=[0x10,0,0x10,0xc0000000,0xc0000000,0x20100]
    expected += [0x2000,0,0x6000,0xabcd,0x01000001,0,0x01000001,0x5d,0x9d,0,8,0xffffffff,0x40000]
    if values[:6]+values[8:]!=expected:
        raise AssertionError(f'Guest outputs: {[hex(v) for v in values]}')
    print('PASS: ARM guest PCC0/PCC2, GPIO, PCTLA, TSTMRB, SIM DGO ACK/W1C, SCG1 oscillator/PLL PFD and TPM6 control/modulo and PMC1 VLPS')
    print('Guest results:',*[hex(v) for v in values])

if __name__=='__main__':
    main()
