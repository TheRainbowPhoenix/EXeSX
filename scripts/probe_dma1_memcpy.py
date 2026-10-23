#!/usr/bin/env python3
"""Real ARM synthetic 32-byte eDMA1 channel15 request/copy regression."""
import argparse,os,re,struct,subprocess,time
from pathlib import Path
from hmp_memory import memory_words, qmp_memory_words
BASE=0x60000000
SRC=0x62016000
DST=0x62017000
RESULT=0x62018000
def guest():
    w=[];lits=[]
    def emit(v):w.append(v)
    def lit(r,v):lits.append((len(w),r,v));emit(0)
    def sw(r,b,off=0):emit(0xe5800000|(b<<16)|(r<<12)|off)
    def lw(r,b,off=0):emit(0xe5900000|(b<<16)|(r<<12)|off)
    def sb(r,b,off=0):emit(0xe5c00000|(b<<16)|(r<<12)|off)
    lit(0,SRC);lit(1,0x12345678)
    for off in range(0,32,4): sw(1,0,off)
    lit(4,0x400811e0);lit(5,0x40210000)
    lit(2,SRC);sw(2,4,0)
    lit(2,0x05050020);sw(2,4,4)
    lit(2,32);sw(2,4,8)
    lit(2,0);sw(2,4,12);sw(2,4,24)
    lit(2,DST);sw(2,4,16)
    lit(2,0x00010020);sw(2,4,20)
    lit(2,0x0001000a);sw(2,4,28)
    lit(2,0xa0000000);sw(2,5,15*4)
    lit(6,0x40080000)
    lit(2,15);sb(2,6,0x1b)
    lw(2,4,28);lit(7,RESULT);sw(2,7)
    lit(0,DST);lw(2,0);sw(2,7,4)
    lw(2,0,28);sw(2,7,8)
    emit(0xeafffffe)
    for i,r,v in lits:
        off=len(w)*4-i*4-8
        assert 0<=off<4096
        w[i]=0xe59f0000|(r<<12)|off
        w.append(v)
    body=struct.pack('<%dI'%len(w),*w)
    ident=b'\x7fELF\x01\x01\x01'+bytes(9)
    h=struct.pack('<16sHHIIIIIHHHHHH',ident,2,40,1,BASE,52,0,0x05000000,52,32,1,0,0,0)
    p=struct.pack('<8I',1,0x100,BASE,BASE,len(body),len(body),5,0x100)
    return h+p+bytes(0x100-len(h)-len(p))+body
def run(qemu,profile,elf,enabled):
    elf.write_bytes(guest())
    env=os.environ.copy();env['EXESX_MEMORY_PROFILE']=str(profile.resolve())
    if enabled:env['EXESX_EXPERIMENTAL_DMA1_M2M']='1'
    else:env.pop('EXESX_EXPERIMENTAL_DMA1_M2M',None)
    lib=qemu.resolve().parent/'lib'
    if lib.is_dir():env['LD_LIBRARY_PATH']=str(lib)+':'+env.get('LD_LIBRARY_PATH','')
    cmd=[str(qemu.resolve()),'-machine','exesx','-m','64M','-accel','tcg',
         '-display','none','-serial','none','-monitor','stdio','-no-reboot',
         '-device',f'loader,file={elf.resolve()},cpu-num=0']
    if os.name == 'nt':
        return qmp_memory_words(cmd, env, RESULT, 3)
    proc=subprocess.Popen(cmd,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    try:
        time.sleep(2.0 if os.name == 'nt' else .6)
        output,_=proc.communicate(f'stop\nxp /3wx 0x{RESULT:08x}\nquit\n',timeout=12)
    finally:
        if proc.poll() is None:proc.kill();proc.wait()
    return memory_words(output,RESULT,3)
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--qemu',type=Path,default=Path('build/qemu-system-arm'))
    ap.add_argument('--profile',type=Path,default=Path('profiles/imx7ulp-early-boot.ini'))
    ap.add_argument('--elf',type=Path,default=Path('build/dma1-copy-probe.elf'))
    a=ap.parse_args();a.elf.parent.mkdir(parents=True,exist_ok=True)
    off=run(a.qemu,a.profile,a.elf,False)
    on=run(a.qemu,a.profile,a.elf,True)
    if off[0]&0x80 or off[1]!=0:raise AssertionError('disabled DMA falsely copied '+str(off))
    if on[0]&0x80==0 or on[1]!=0x12345678 or on[2]!=0x12345678:
        raise AssertionError('DMA copy/CSR mismatch '+str(on))
    print('PASS DMA1 disabled: no copy, no DONE')
    print('PASS DMA1 enabled: actual RAM copy and CSR.DONE')
if __name__=='__main__':main()
