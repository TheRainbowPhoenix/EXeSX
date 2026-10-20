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
    # PMC0 has a different layout: M4-domain VLPS at offset +0x18.
    literal(0,0x410a1000)
    literal(1,0x10000000)
    store(1,0,0x18)
    ldr(2,0,0x18)
    store(2,7,84)
    # Cortex-A7's CBAR identifies the GIC private peripheral region.
    # MRC p15,4,r2,c15,c0,0 (verified via ARM clang/llvm-objdump).
    ins(0xee9f2f10)
    store(2,7,88)    # CBAR must be 0x40020000
    literal(0,0x40022000)
    ldr(2,0,0x0c)
    store(2,7,92)    # GICC_IAR returns 0x3ff (no pending IRQ)
    literal(0,0x40021000)
    ldr(2,0,4)
    store(2,7,96)    # GICD_TYPER, 160 interrupts => TYPER[4:0]==4
    literal(0,0x40022000)
    ldr(2,0,4)
    store(2,7,100)   # GICC_PMR reset state
    # PORTF PCR0 guest writes and reads the actual new peripheral.
    literal(0,0x40b10000)
    literal(1,0x00090000)
    store(1,0,0)     # IRQC pin interrupt configuration
    ldr(2,0,0)
    store(2,7,104)
    literal(1,0x01090000)
    store(1,0,0)     # ISF bit24 should be W1C, not latched.
    ldr(2,0,0)
    store(2,7,108)
    # LPIT1 MCR +0x8, ch0 TVAL/TCTRL, channel enable.
    literal(0,0x40270000)
    literal(1,1)
    store(1,0,8)     # M_CEN: module clock on
    literal(1,0xffff)
    store(1,0,0x20)  # LPIT ch0 TVAL
    literal(1,1)
    store(1,0,0x14)  # SETTEN ch0
    ldr(2,0,8)
    store(2,7,112)   # MCR = 1
    ldr(2,0,0x20)
    store(2,7,116)   # TVAL = 0xffff
    ldr(2,0,0x28)
    store(2,7,120)   # TCTRL0 enable bit=1
    # SEMA42_0 GATE0 lives at +0x03 and uses byte-sized access.
    literal(0,0x4101b000)
    literal(1,1)
    ins(0xe5c01003)  # strb r1,[r0,#3], acquire as domain 1
    ins(0xe5d02003)  # ldrb r2,[r0,#3]
    store(2,7,124)
    literal(1,0)
    ins(0xe5c01003)  # strb r1,[r0,#3], release
    ins(0xe5d02003)
    store(2,7,128)
    # M4 SCG0 first firmware poll: FIRC CSR.VLD bit24 present at ROM handoff.
    literal(0,0x41027000)
    ldr(2,0,0x300)
    store(2,7,132)   # FIRC.EN=1 & VLD=1 => 0x01000001
    literal(1,0)
    store(1,0,0x300)
    ldr(2,0,0x300)
    store(2,7,136)   # disabled oscillator loses VLD
    literal(1,1)
    store(1,0,0x300)
    ldr(2,0,0x300)
    store(2,7,140)   # enabled: VLD is restored
    # LPTMR0 register state after M4 startup. No external input modeled.
    literal(0,0x4102e000)
    literal(1,4)
    store(1,0,4)       # PBYP: internal clock without divider
    literal(1,0x1000)
    store(1,0,8)       # compare
    literal(1,1)
    store(1,0,0)       # enable
    ldr(2,0,0)
    store(2,7,144)     # CSR TEN
    ldr(2,0,4)
    store(2,7,148)     # PSR PBYP
    ldr(2,0,8)
    store(2,7,152)     # CMR
    # TPM1 must use the same counter/control semantics as TPM6.
    literal(0,0x41031000)
    literal(1,0)
    store(1,0,0x10)
    store(1,0,0x14)
    literal(1,0xffff)
    store(1,0,0x18)
    literal(1,8)
    store(1,0,0x10)
    ldr(2,0,0x10)
    store(2,7,156)     # SC=8
    ldr(2,0,0x18)
    store(2,7,160)     # MOD=0xffff
    # MU v1 A/B actual register exchange: MUA TR0 -> MUB RR0.
    literal(0,0x41022000)
    literal(1,0x12345678)
    store(1,0,0x20)    # A transmit channel 0
    literal(0,0x40220000)
    ldr(2,0,0x60)
    store(2,7,164)     # B SR receive-full flag bit24
    ldr(2,0,0x40)
    store(2,7,168)     # B RR0 must contain actual A payload
    ldr(2,0,0x60)
    store(2,7,172)     # B RF cleared after consume
    literal(0,0x41022000)
    ldr(2,0,0x60)
    store(2,7,176)     # A TE0 restored
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
        commands=''.join(f'xp /1wx 0x{OUT+i*4:08x}\n' for i in range(45))+'quit\n'
        output,_=proc.communicate(commands,timeout=12)
    finally:
        if proc.poll() is None:
            proc.kill();proc.wait()
    values=[]
    for i in range(45):
        match=re.search(r'(?im)^0*'+f'{OUT+i*4:08x}'+
                        r':\s+0x([0-9a-f]+)',output)
        if not match:
            raise AssertionError(f'Missing guest result {i}: {output[-1200:]}')
        values.append(int(match.group(1),16))
    expected=[0x10,0,0x10,0xc0000000,0xc0000000,0x20100]
    expected += [0x2000,0,0x6000,0xabcd,0x01000001,0,0x01000001,0x5d,0x9d,0,8,0xffffffff,0x40000,0x10000000,0x40020000,0x3ff]
    if values[:6]+values[8:24]!=expected or (values[24] & 0x1f)!=4 or values[25]!=0 or values[26:41]!=[0x90000,0x90000,1,0xffff,1,1,0,0x01000001,0,0x01000001,1,4,0x1000,8,0xffff] or values[41:]!=[0x01f00000,0x12345678,0x00f00000,0x00f00000]:
        raise AssertionError(f'Guest outputs: {[hex(v) for v in values]}')
    print('PASS: ARM guest PCC0/PCC2, GPIO, PCTLA, TSTMRB, SIM DGO ACK/W1C, SCG1 oscillator/PLL PFD and TPM6 control/modulo PMC1/PMC0 VLPS and GICv2 CBAR/physical interfaces and PORTF PCR0 and LPIT1 and SEMA42 byte gate ownership and M4 SCG0 FIRC ready status and LPTMR0, TPM1 and two-sided MUA/MUB mailbox exchange')
    print('Guest results:',*[hex(v) for v in values])

if __name__=='__main__':
    main()
