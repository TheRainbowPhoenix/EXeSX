#!/usr/bin/env python3
"""Real ARM MMIO / virtual-time PCTLA IRQ56 from an external GPIO pin edge.

No Casio ROM. Synthetic ARM enables PORTA.PCR[23] IRQC=0xb, host
toggles M4 PTA23 electrically. Checks PORTA.ISFR and M4 NVIC IRQ56;
negative controls prove no automatic interrupt with IRQC=0 or bridge off.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import time
from probe_postdma_handoff import RSP,choose_port
from hmp_memory import memory_words

PORTA=0x4103f000
ISFR=PORTA+0xa0
NVIC_PENDING_1=0xe000e204
PIN=23
BASE=0x60000000
MASK=0x808c6008


def synthetic_arm(irqc):
    words=[];literals=[]
    def lit(reg,value):
        literals.append((len(words),reg,value));words.append(0)
    lit(0,PORTA)
    lit(1,irqc<<16)
    words.append(0xe5801000 | (PIN*4))  # STR r1,[r0,#PCR23]
    words.append(0xeafffffe)
    pool=len(words)
    for n,(pos,reg,value) in enumerate(literals):
        offset=4*(pool+n-pos)-8
        assert 0<=offset<4096
        words[pos]=0xe59f0000|reg<<12|offset
        words.append(value)
    body=struct.pack("<%dI"%len(words),*words)
    ident=b"\x7fELF\x01\x01\x01"+bytes(9)
    head=struct.pack("<16sHHIIIIIHHHHHH",ident,2,40,1,BASE,52,0,
                     0x05000000,52,32,1,0,0,0)
    phdr=struct.pack("<8I",1,0x100,BASE,BASE,len(body),len(body),5,0x100)
    return head+phdr+bytes(0x100-len(head)-len(phdr))+body


def experiment(qemu,profile,bridge,irqc):
    with tempfile.TemporaryDirectory() as root:
        folder=Path(root)
        elf=folder/"port-a-irq-probe.elf"
        elf.write_bytes(synthetic_arm(irqc))
        inputs=folder/"pta-inputs.txt"
        inputs.write_text(f"{MASK:#x}\n")
        env=os.environ.copy()
        env.update(EXESX_MEMORY_PROFILE=str(profile.resolve()),
                   EXESX_EXPERIMENTAL_M4_PORT_IRQ="1" if bridge else "0",
                   EXESX_GPIOA_INPUT_MASK_FILE=str(inputs.resolve()),
                   EXESX_GPIOA_INPUT_MASK=hex(MASK))
        library=qemu.resolve().parent/"lib"
        if library.is_dir():
            env["LD_LIBRARY_PATH"]=str(library)+os.pathsep+env.get("LD_LIBRARY_PATH","")
        mp=choose_port();gp=choose_port()
        while gp==mp:gp=choose_port()
        argv=[str(qemu.resolve()),"-machine","exesx","-m","64M",
              "-accel","tcg","-display","none","-serial","none",
              "-monitor","none","-no-reboot",
              "-device",f"loader,file={elf.resolve()},cpu-num=0",
              "-qmp",f"tcp:127.0.0.1:{mp},server=on,wait=off",
              "-gdb",f"tcp:127.0.0.1:{gp}"]
        p=subprocess.Popen(argv,env=env,stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            def connect(port):
                for _ in range(100):
                    if p.poll() is not None:
                        raise AssertionError("Synthetic QEMU exited")
                    try:return socket.create_connection(("127.0.0.1",port),.3)
                    except OSError:time.sleep(.05)
                raise AssertionError("QEMU monitor unavailable")
            with connect(mp) as q,connect(gp) as g:
                q.settimeout(8)
                with q.makefile("rb") as reader:
                    assert "QMP" in json.loads(reader.readline())
                    def call(op,args=None):
                        obj={"execute":op,"id":"port"}
                        if args is not None:obj["arguments"]=args
                        q.sendall((json.dumps(obj)+"\n").encode())
                        while True:
                            record=json.loads(reader.readline())
                            if record.get("id")!="port":continue
                            if "error" in record:raise AssertionError(record["error"])
                            return record["return"]
                    call("qmp_capabilities")
                    def memory(addr):
                        text=call("human-monitor-command",
                                  {"command-line":f"xp /1wx {addr:#x}"})
                        return memory_words(text,addr,1)[0]
                    # Let ARM program PCR and QEMU establish idle high sample.
                    time.sleep(.35)
                    initial=memory(ISFR)
                    if initial & (1<<PIN):
                        raise AssertionError(f"Spurious initial IRQ {initial:#x}")
                    new=folder/"new-input.txt"
                    new.write_text(hex(MASK & ~(1<<PIN))+"\n")
                    os.replace(new,inputs)
                    time.sleep(.35)
                    # Pause the guest before inspecting M4 NVIC through GDB.
                    # M-profile SCS is not an A7 monitor-visible MMIO window.
                    call("stop")
                    status=memory(ISFR)
                    rsp=RSP(g);rsp.command("?")
                    assert rsp.command("Hg2")=="OK"
                    pending=rsp.memory(NVIC_PENDING_1,4)
                    if pending is None:
                        raise AssertionError("Could not inspect Cortex-M4 NVIC")
                    expected=(1<<PIN) if bridge and irqc==11 else 0
                    if status & (1<<PIN)!=expected:
                        raise AssertionError(f"PORTA IRQ bridge={bridge} IRQC={irqc} "
                                             f"ISFR={status:#x}, expected bit={expected:#x}")
                    nv_expected=(1<<(56-32)) if bridge and irqc==11 else 0
                    if pending & (1<<(56-32))!=nv_expected:
                        raise AssertionError(f"M4 NVIC IRQ56 bridge={bridge}, "
                                             f"IRQC={irqc}, pending={pending:#x}")
                    print(f"PASS PORTA IRQC={irqc:#x} enabled={bridge} "
                          f"ISFR={status:#x} NVIC.ISPR1={pending:#x}")
        finally:
            if p.poll() is None:p.kill()
            p.wait(timeout=5)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--qemu",type=Path,default=Path("build/qemu-system-arm"))
    ap.add_argument("--profile",type=Path,
                    default=Path("profiles/imx7ulp-early-boot.ini"))
    args=ap.parse_args()
    for enabled,irqc in ((False,11),(True,0),(True,11)):
        experiment(args.qemu,args.profile,enabled,irqc)
    print("PASS physical M4 PORTA pin edge -> PCR.ISF/ISFR -> NVIC IRQ56; no forged RTOS flag")


if __name__=="__main__":
    main()
