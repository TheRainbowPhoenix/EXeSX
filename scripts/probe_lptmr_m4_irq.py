#!/usr/bin/env python3
"""Firmware-free original A7 instructions driving M4 NVIC IRQ36 via LPTMR0.

No Casio ROM. Three cases prove that an enabled timer alone does not
raise IRQ36: opt-in bridge + CSR.TIE + compare flag are all necessary.
"""
import argparse
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import time
from probe_postdma_handoff import RSP, choose_port, encode_packet

BASE = 0x4102e000
ENTRY = 0x60000000
NVIC_ISPR1 = 0xe000e204
LPTMR0_BIT = 1 << (36-32)


def elf_bytes(tie):
    words, literals = [], []
    def lit(reg,val):
        literals.append((len(words),reg,val));words.append(0)
    def store(src, base, off):
        words.append(0xe5800000 | base << 16 | src << 12 | off)
    lit(0,BASE)
    lit(1,4)                 # PSR.PBYP bypass prescale (1MHz provisional)
    store(1,0,4)
    lit(1,10000)             # 10ms compare period
    store(1,0,8)
    lit(1,0x41 if tie else 1) # TEN=1, optionally TIE=1, TCF not forced
    store(1,0,0)
    words.append(0xeafffffe) # tight wait, timer event is hardware driven
    start=len(words)
    for pool_index,(i,r,v) in enumerate(literals):
        diff = 4*(start+pool_index-i)-8
        assert 0 <= diff < 4096
        words[i]=0xe59f0000 | r << 12 | diff
        words.append(v)
    body=struct.pack('<%dI'%len(words),*words)
    ident=b'\x7fELF\x01\x01\x01'+bytes(9)
    hdr=struct.pack('<16sHHIIIIIHHHHHH',ident,2,40,1,ENTRY,52,0,0x05000000,52,32,1,0,0,0)
    phdr=struct.pack('<8I',1,0x100,ENTRY,ENTRY,len(body),len(body),5,0x100)
    return hdr+phdr+bytes(0x100-len(hdr)-len(phdr))+body


def probe(qemu, profile, enabled, tie):
    with tempfile.TemporaryDirectory() as tmp:
        elf=Path(tmp)/'m4-lptmr0-a7.elf'
        elf.write_bytes(elf_bytes(tie))
        env=os.environ.copy()
        env['EXESX_MEMORY_PROFILE']=str(profile.resolve())
        env['EXESX_EXPERIMENTAL_LPTMR_IRQ']='1' if enabled else '0'
        lib=qemu.resolve().parent/'lib'
        if lib.is_dir():
            env['LD_LIBRARY_PATH']=str(lib)+os.pathsep+env.get('LD_LIBRARY_PATH','')
        port=choose_port()
        cmd=[str(qemu.resolve()),'-machine','exesx','-m','64M','-accel','tcg',
             '-display','none','-serial','none','-monitor','none','-no-reboot',
             '-device',f'loader,file={elf},cpu-num=0','-S','-gdb',f'tcp:127.0.0.1:{port}']
        p=subprocess.Popen(cmd,env=env,stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            import socket
            conn=None
            for _ in range(80):
                if p.poll() is not None:
                    raise AssertionError('QEMU exited before GDB')
                try:
                    conn=socket.create_connection(('127.0.0.1',port),timeout=.3)
                    break
                except OSError:time.sleep(.075)
            if conn is None:raise AssertionError('QEMU GDB not ready')
            with conn:
                rsp=RSP(conn)
                rsp.command('?')
                if rsp.command('Hc-1')!='OK':raise AssertionError('Cannot run both CPUs')
                conn.sendall(encode_packet('c'))
                time.sleep(.7)
                conn.sendall(b'\x03')
                if not rsp.receive(3).startswith('T'):
                    raise AssertionError('Could not pause actual guest')
                if rsp.command('Hg2')!='OK':raise AssertionError('Cannot select M4 NVIC')
                pending=rsp.memory(NVIC_ISPR1,4)
                csr=rsp.memory(BASE,4)
                assert csr is not None and csr & 0x81 == 0x81, (enabled,tie,csr)
                return pending,csr
        finally:
            if p.poll() is None:p.kill()
            p.wait(timeout=5)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu',type=Path,default=Path('build/qemu-system-arm'))
    parser.add_argument('--profile',type=Path,default=Path('profiles/imx7ulp-early-boot.ini'))
    a=parser.parse_args()
    for enabled,tie,expected in ((False,True,0),(True,False,0),(True,True,LPTMR0_BIT)):
        pending,csr=probe(a.qemu,a.profile,enabled,tie)
        assert pending is not None and (pending & LPTMR0_BIT)==expected, (
            f'LPTMR M4 NVIC IRQ36 expected={expected:#x}, got={pending:#x}, '
            f'bridge={enabled}, TIE={tie}, CSR={csr:#x}')
        print(f'PASS actual guest LPTMR0 bridge={enabled} TIE={tie} '
              f'CSR={csr:#x} NVIC pending={pending:#x}',flush=True)
    print('PASS M4 NVIC IRQ36 raised by real LPTMR0 compare only when CSR.TIE and bridge enabled')


if __name__=='__main__':main()
