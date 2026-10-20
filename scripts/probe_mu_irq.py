#!/usr/bin/env python3
"""First M4 MU IRQ22 entry-to-entry probe; safe read-only SR/CR sampling.

Uses private A7 firmware and both explicitly diagnostic I2C mirrors. It NEVER
reads MU RRn registers (which would release real receiver-full flags).
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
from fuzz_mmio import RSP, QMP, make_qcow2

HANDLER = 0x1FFED180
MUA, MUB = 0x41022000, 0x40220000


def decode(sr: int, cr: int) -> dict:
    te, rf, gp = (sr >> 20) & 15, (sr >> 24) & 15, (sr >> 28) & 15
    ti, ri, gi = (cr >> 20) & 15, (cr >> 24) & 15, (cr >> 28) & 15
    return {"sr":f"0x{sr:08x}","cr":f"0x{cr:08x}","te":te,"rf":rf,
            "gip":gp,"tien":ti,"rien":ri,"gien":gi,
            "irq_sources":{"tx_empty":te&ti,"rx_full":rf&ri,"general":gp&gi}}


def nonconsuming_state(rsp: RSP) -> dict:
    record={}
    for name,base in (("MUA_M4",MUA),("MUB_A7",MUB)):
        words=[]
        for offset in (0x60,0x64): # Only SR and CR: never RR0...RR3 (+0x40..0x4c)
            payload=rsp.request(f"m{base+offset:x},4")
            if len(payload)!=8:raise RuntimeError(f"Unmapped {name}+{offset:x}: {payload}")
            words.append(int.from_bytes(bytes.fromhex(payload),"little"))
        record[name]=decode(*words)
    return record


def socket_wait(proc, endpoint, unix=False):
    for _ in range(400):
        if proc.poll() is not None:raise RuntimeError(f"QEMU exited {proc.returncode}")
        try:
            if unix:
                s=socket.socket(socket.AF_UNIX);s.connect(endpoint)
            else:s=socket.create_connection(endpoint,.15)
            return s
        except OSError:time.sleep(.025)
    raise TimeoutError("QEMU debugger/monitor unavailable")


def run(args) -> dict:
    qemu=args.qemu.resolve()
    env=os.environ.copy()
    env.update(EXESX_MEMORY_PROFILE=str(args.profile.resolve()),
               EXESX_EXPERIMENTAL_M4_BOOT="1",EXESX_EXPERIMENTAL_MU_IRQ="1",
               EXESX_I2C4B_REGISTER_MIRROR="1",EXESX_I2C40_REGISTER_MIRROR="1")
    env.pop("EXESX_I2C4B_REPLY_HEX",None)
    lib=qemu.parent/"lib"
    if lib.is_dir():env["LD_LIBRARY_PATH"]=str(lib)+":"+env.get("LD_LIBRARY_PATH","")
    with tempfile.TemporaryDirectory(prefix="exesx-mu-irq-") as temp:
        tmp=Path(temp)
        port_sock=socket.socket();port_sock.bind(("127.0.0.1",0))
        port=port_sock.getsockname()[1];port_sock.close()
        make_qcow2(tmp/"snapshots.qcow2")
        cmd=[str(qemu),"-machine","exesx","-m","64M","-accel","tcg",
             "-display","none","-serial","none","-S",
             "-gdb",f"tcp:127.0.0.1:{port}",
             "-qmp",f"unix:{tmp}/qmp.sock,server=on,wait=off",
             "-monitor","none","-no-reboot",
             "-device",f"loader,file={args.elf.resolve()},cpu-num=0",
             "-drive",f"file={tmp}/snapshots.qcow2,if=none,format=qcow2,id=vmstate",
             "-d","guest_errors,int","-D",str((args.out/"guest-private.log").resolve())]
        with (args.out/"qemu-console-private.log").open("w") as console:
            proc=subprocess.Popen(cmd,env=env,stdout=console,stderr=subprocess.STDOUT)
            gs=qs=None
            try:
                gs=socket_wait(proc,("127.0.0.1",port))
                rsp=RSP(gs);rsp.request("qSupported:multiprocess+;qXfer:features:read+")
                rsp.request("?")
                qs=socket_wait(proc,str(tmp/"qmp.sock"),True);qmp=QMP(qs)
                if rsp.request("Hgp01.02")!="OK":raise RuntimeError("M4 GDB thread missing")
                if rsp.request(f"Z0,{HANDLER:x},2")!="OK":raise RuntimeError("ISR breakpoint unsupported")
                entries=[]
                for i in range(1,args.entries+1):
                    if i>1:
                        step=rsp.request("s")
                        if not step.startswith(("T","S")):raise RuntimeError("M4 step failed: "+step)
                        if rsp.reg(15)==HANDLER:raise RuntimeError("ISR did not advance")
                    stop=rsp.request("c")
                    if not stop.startswith("T05thread:p01.02;"):
                        raise RuntimeError("Unexpected IRQ stop "+stop)
                    if rsp.request("Hgp01.02")!="OK" or rsp.reg(15)!=HANDLER:
                        raise RuntimeError("Not stopped at real M4 IRQ22 entry")
                    row={"entry":i,"m4_irq_vector_pc":hex(HANDLER),**nonconsuming_state(rsp)}
                    entries.append(row)
                    if i==1:
                        qmp.hmp("savevm first_irq22")
                        if "first_irq22" not in qmp.hmp("info snapshots"):
                            raise RuntimeError("First IRQ snapshot unavailable")
                qmp.hmp("loadvm first_irq22")
                if rsp.request("Hgp01.02")!="OK" or rsp.reg(15)!=HANDLER:
                    raise RuntimeError("QEMU snapshot did not restore M4 entry PC")
                restored=nonconsuming_state(rsp)
                if restored!={k:v for k,v in entries[0].items() if k.startswith("MU")}:
                    raise RuntimeError("Snapshot did not restore MU device state")
                first,last=entries[0],entries[-1]
                return {"entries":entries,"snapshot_mu_and_cpu_restored":True,
                        "results":{"first_irq_sources":first["MUA_M4"]["irq_sources"],
                                   "last_irq_sources":last["MUA_M4"]["irq_sources"],
                                   "last_mub_tr0_busy":not bool(last["MUB_A7"]["te"]&1),
                                   "last_mub_tr2_busy":not bool(last["MUB_A7"]["te"]&4)},
                        "scope":"EMU MODEL read-only SR/CR; no RR registers or guest code patched; both I2C mirrors artificial"}
            finally:
                if gs:gs.close()
                if qs:qs.close()
                if proc.poll() is None:
                    proc.terminate()
                    try:proc.wait(timeout=4)
                    except subprocess.TimeoutExpired:proc.kill();proc.wait()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("elf",type=Path,help="PRIVATE, validated A7 firmware ELF")
    p.add_argument("--qemu",type=Path,default=Path("build/qemu-system-arm"))
    p.add_argument("--profile",type=Path,default=Path("profiles/imx7ulp-early-boot.ini"))
    p.add_argument("--out",type=Path,default=Path("private/mu-irq-first-handler"))
    p.add_argument("--entries",type=int,default=6)
    a=p.parse_args()
    if not 2<=a.entries<=20:p.error("Use 2..20 IRQ entries")
    for f in (a.elf,a.qemu,a.profile):
        if not f.is_file():p.error("Missing local file: "+str(f))
    a.out.mkdir(parents=True,exist_ok=True);a.out.chmod(0o700)
    report=run(a)
    dest=a.out/"mu-irq-readonly.json";dest.write_text(json.dumps(report,indent=2)+"\n");dest.chmod(0o600)
    for row in report["entries"]:
        mua=row["MUA_M4"]
        print(f"IRQ#{row['entry']}: SR={mua['sr']} CR={mua['cr']} "
              f"RF={mua['rf']:#x} RIE={mua['rien']:#x} GIP={mua['gip']:#x} "
              f"pending={mua['irq_sources']}")
    print("Verified snapshot restore; private report:",dest)


if __name__=="__main__":main()
