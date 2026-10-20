#!/usr/bin/env python3
"""Snapshot-checked EXeSX MMIO read-site differential fuzzer.

Debugs actual ARM firmware through QEMU's remote GDB protocol, injects the
result of exactly one MMIO LDR, and single-steps to see which path was taken.
Attempts savevm/loadvm on a disposable QCOW2; rejects broken CPU/MMU state
restores and cold-replays to the identical breakpoint instead. No build needed.

Output is local-only; NEVER commit private firmware or generated dump files.
"""
import argparse
import json
import os
import shutil
import socket
import struct
import subprocess
import tempfile
import time
from pathlib import Path

SITES={"initial":0x6004992c,"poll":0x60049938,"second-poll":0x60049950}
REGISTERS={"initial":0x4102603c,"poll":0x4102603c,"second-poll":0x410260fc}

def cases():
    return [("zero",0)] + [(f"bit{i:02d}",1<<i) for i in range(32)] + [("all_ones",0xffffffff)]

def make_qcow2(path):
    """Small empty QCOW2 v3 metadata disk, independently of qemu-img."""
    c=65536
    head=struct.pack(">IIQIIQIIQQIIQQQQII",0x514649fb,3,0,0,16,
                     8*1024*1024,0,1,3*c,c,1,0,0,0,0,0,4,104)
    b=bytearray(4*c);b[:len(head)]=head
    struct.pack_into(">Q",b,c,2*c)
    for i in range(4):struct.pack_into(">H",b,2*c+2*i,1)
    Path(path).write_bytes(b)

class RSP:
    def __init__(self,s):
        self.s=s;s.settimeout(15)
    def request(self,command):
        data=command.encode()
        self.s.sendall(b"$"+data+b"#"+f"{sum(data)%256:02x}".encode())
        if self.s.recv(1)!=b"+" or self.s.recv(1)!=b"$":
            raise RuntimeError("GDB remote handshake failed")
        out=bytearray()
        while True:
            x=self.s.recv(1)
            if not x:raise EOFError("GDB remote disconnected")
            if x==b"#":break
            out+=x
        self.s.recv(2);self.s.sendall(b"+")
        return out.decode()
    def reg(self,index):
        val=self.request(f"p{index:x}")
        if val.startswith("E"):raise RuntimeError(f"GDB register read: {val}")
        return int.from_bytes(bytes.fromhex(val),"little")
    def setreg(self,index,value):
        result=self.request(f"P{index:x}="+struct.pack("<I",value).hex())
        if result!="OK":raise RuntimeError(f"GDB register write: {result}")

class QMP:
    def __init__(self,s):
        self.s=s;self.f=s.makefile("rb")
        if "QMP" not in json.loads(self.f.readline()):
            raise RuntimeError("QMP greeting missing")
        self.command("qmp_capabilities")
    def command(self,command,**args):
        self.s.sendall((json.dumps({"execute":command,"arguments":args,"id":"fuzz"})+"\n").encode())
        while True:
            data=self.f.readline()
            if not data:raise EOFError("QMP disconnected")
            result=json.loads(data)
            if result.get("id")=="fuzz":
                if "error" in result:raise RuntimeError(str(result["error"]))
                return result.get("return")
    def hmp(self,line):
        return self.command("human-monitor-command",**{"command-line":line})

class Guest:
    def __init__(self,args,out,label,snapshot=False):
        self.args=args;self.out=out;self.label=label;self.snapshot=snapshot
        self.proc=None;self.gdb_socket=None;self.qmp_socket=None
    def __enter__(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="exesx-fuzz-")
        monitor=str(Path(self.tmp.name)/"qmp.sock")
        portsocket=socket.socket();portsocket.bind(("127.0.0.1",0))
        port=portsocket.getsockname()[1];portsocket.close()
        q=Path(self.args.qemu).resolve()
        env=os.environ.copy()
        env["EXESX_MEMORY_PROFILE"]=str(Path(self.args.profile).resolve())
        lib=q.parent/"lib"
        if lib.is_dir():env["LD_LIBRARY_PATH"]=str(lib)+":"+env.get("LD_LIBRARY_PATH","")
        cmd=[str(q),"-machine","exesx","-m","64M","-accel","tcg",
             "-display","none","-serial","none","-S",
             "-gdb",f"tcp:127.0.0.1:{port}",
             "-qmp",f"unix:{monitor},server=on,wait=off",
             "-monitor","none","-no-reboot",
             "-device",f"loader,file={Path(self.args.elf).resolve()},cpu-num=0"]
        if self.snapshot:
            qcow=Path(self.tmp.name)/"snapshot.qcow2"
            make_qcow2(qcow)
            cmd+=["-drive",f"file={qcow},if=none,format=qcow2,id=vmstate"]
        self.log=open(self.out/(self.label+".qemu.log"),"w")
        self.proc=subprocess.Popen(cmd,env=env,stdout=self.log,stderr=subprocess.STDOUT)
        try:
            for _ in range(400):
                if self.proc.poll() is not None:raise RuntimeError(f"QEMU exited {self.proc.returncode}")
                try:
                    self.gdb_socket=socket.create_connection(("127.0.0.1",port),.15)
                    break
                except OSError:time.sleep(.025)
            if self.gdb_socket is None:raise TimeoutError("GDB connection")
            self.rsp=RSP(self.gdb_socket)
            self.rsp.request("qSupported:multiprocess+;qXfer:features:read+")
            self.rsp.request("?")
            for _ in range(400):
                try:
                    self.qmp_socket=socket.socket(socket.AF_UNIX)
                    self.qmp_socket.connect(monitor)
                    break
                except OSError:time.sleep(.025)
            if self.qmp_socket is None:raise TimeoutError("QMP connection")
            self.qmp=QMP(self.qmp_socket)
            return self
        except Exception:
            self.__exit__(None,None,None);raise
    def __exit__(self,*unused):
        for s in (self.gdb_socket,self.qmp_socket):
            if s:s.close()
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:self.proc.kill();self.proc.wait()
        self.log.close()
        self.tmp.cleanup()
    def break_at(self,pc):
        res=self.rsp.request(f"Z0,{pc:x},4")
        if res!="OK":raise RuntimeError(f"Cannot set breakpoint: {res}")
        stop=self.rsp.request("c")
        actual=self.rsp.reg(15)
        if not stop.startswith(("S","T")) or actual!=pc:
            raise RuntimeError(f"Expected breakpoint {pc:#x}; reached {actual:#x}: {stop}")
    def inject_and_trace(self,pc,value,steps):
        self.rsp.setreg(1,value)
        self.rsp.setreg(15,pc+4)  # skip only the faulting 32-bit ARM LDR
        events=[];outcome="step_limit"
        for _ in range(steps):
            start=self.rsp.reg(15)
            r1=self.rsp.reg(1)
            cpsr=self.rsp.reg(25)
            stop=self.rsp.request("s")
            if not stop.startswith(("S","T")):
                outcome="gdb_stop_"+stop[:20];break
            end=self.rsp.reg(15)
            events.append({"pc":f"0x{start:08x}","next":f"0x{end:08x}",
                           "r1":f"0x{r1:08x}","cpsr":f"0x{cpsr:08x}",
                           "branch":end!=start+4})
            if end in (0x6000000c,0x60000010):
                outcome="exception_vector";break
            if not (0x60040000<=end<0x60050000):
                outcome="left_initialization_function";break
        return outcome,events

def check_snapshot(g,pc):
    oldpc=g.rsp.reg(15)
    oldcode=g.rsp.request("m60049920,4")
    oldmmio=g.rsp.request("m4102603c,4")
    g.qmp.hmp("savevm before_mmio")
    if "before_mmio" not in g.qmp.hmp("info snapshots"):
        return {"usable":False,"reason":"savevm failed"}
    # Intentionally mutate a modelled MMIO register after saving. A PC-only
    # or ROM-only check would fail to detect stale C device state.
    tamper = (~int.from_bytes(bytes.fromhex(oldmmio), "little")) & 0xffffffff
    tamper_hex=struct.pack("<I",tamper).hex()
    write=g.rsp.request("M4102603c,4:"+tamper_hex)
    observed=g.rsp.request("m4102603c,4")
    g.rsp.setreg(15,pc+4)
    g.qmp.hmp("loadvm before_mmio")
    newpc=g.rsp.reg(15)
    newcode=g.rsp.request("m60049920,4")
    newmmio=g.rsp.request("m4102603c,4")
    device_test=(write=="OK" and observed==tamper_hex and oldmmio!=tamper_hex)
    ok=(oldpc==newpc and oldcode==newcode and oldmmio==newmmio
        and device_test and not newcode.startswith("E")
        and not newmmio.startswith("E"))
    return {"usable":ok,"saved_pc":f"0x{oldpc:08x}","restored_pc":f"0x{newpc:08x}",
            "code_before":oldcode,"code_after":newcode,
            "mmio_before":oldmmio,"mmio_after":newmmio,
            "mmio_tamper_observed":observed,
            "mmio_serialization_verified":device_test and oldmmio==newmmio,
            "reason":"CPU, guest MMU, RAM and mutable MMIO readback verified" if ok else
            "loadvm failed CPU/MMU/device state validation; cold replay required",
            "snapshot_bytes":(Path(g.tmp.name)/"snapshot.qcow2").stat().st_size}

def disassemble(elf):
    """Extract local BIOS instructions, use standard llvm-objdump disassembler."""
    llvm=shutil.which("llvm-objdump")
    if not llvm:return "llvm-objdump missing; the numeric PC path is still logged\n"
    blob=Path(elf).read_bytes()
    phoff=struct.unpack_from("<I",blob,28)[0]
    phentsize,phnum=struct.unpack_from("<HH",blob,42)
    base=0x60049920;size=0xc0
    code=None
    for i in range(phnum):
        typ,off,vaddr,paddr,filesz,memsz,flags,align=struct.unpack_from("<8I",blob,phoff+i*phentsize)
        if typ==1 and vaddr<=base and base+size<=vaddr+filesz:
            code=blob[off+base-vaddr:off+base-vaddr+size]
            break
    if code is None:return "BIOS code not present in an ELF PT_LOAD segment\n"
    # Build an ephemeral ELF32 containing a mapped .text section; no ROM in git.
    with tempfile.TemporaryDirectory(prefix="exesx-disasm-") as tmp:
        path=Path(tmp)/"snippet.elf"
        names=b"\0.text\0.shstrtab\0"
        names_off=0x100+len(code)
        section_off=(names_off+len(names)+3)&~3
        ident=b"\x7fELF\x01\x01\x01"+bytes(9)
        header=struct.pack("<16sHHIIIIIHHHHHH",ident,2,40,1,base,0,
                           section_off,0x05000000,52,0,0,40,3,2)
        text_section=struct.pack("<10I",1,1,6,base,0x100,len(code),0,0,4,0)
        names_section=struct.pack("<10I",7,3,0,0,names_off,len(names),0,0,1,0)
        out=bytearray(section_off+120)
        out[:len(header)]=header
        out[0x100:0x100+len(code)]=code
        out[names_off:names_off+len(names)]=names
        out[section_off:section_off+120]=bytes(40)+text_section+names_section
        path.write_bytes(out)
        result=subprocess.run([llvm,"-d","--start-address=0x60049920",
                               "--stop-address=0x600499e0",str(path)],
                              text=True,capture_output=True,timeout=20)
        return result.stdout or result.stderr

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("elf",type=Path,help="private user-extracted firmware ELF")
    p.add_argument("--qemu",type=Path,default=Path("build/qemu-system-arm"))
    p.add_argument("--profile",type=Path,default=Path("profiles/clock-registers-probe-only.ini"))
    p.add_argument("--out",type=Path,default=Path("private/fuzz-mmio"))
    p.add_argument("--site",choices=list(SITES),default="poll")
    p.add_argument("--steps",type=int,default=13)
    p.add_argument("--limit",type=int,default=34)
    p.add_argument("--only",help="comma-separated cases e.g. zero,bit30,all_ones")
    p.add_argument("--rollback",choices=["auto","require-snapshot","restart"],default="auto")
    args=p.parse_args()
    for path in (args.elf,args.qemu,args.profile):
        if not path.is_file():p.error(f"missing file: {path}")
    if not (1<=args.limit<=34 and 1<=args.steps<=200):
        p.error("invalid --limit or --steps")
    args.out.mkdir(parents=True,exist_ok=True)
    pc=SITES[args.site]
    asm=disassemble(args.elf)
    (args.out/"disassembly.txt").write_text(asm)
    snapshot={"skipped":True,"reason":"restart explicitly requested"}
    if args.rollback!="restart":
        with Guest(args,args.out,"snapshot-check",True) as g:
            g.break_at(pc)
            snapshot=check_snapshot(g,pc)
        print("Snapshot:",json.dumps(snapshot),flush=True)
        if args.rollback=="require-snapshot" and not snapshot.get("usable"):
            raise RuntimeError("snapshot failed validation; refusing to corrupt fuzz results")
    chosen=cases()
    if args.only:
        names={x.strip() for x in args.only.split(",")}
        chosen=[x for x in chosen if x[0] in names]
        if len(chosen)!=len(names):p.error("invalid --only name")
    chosen=chosen[:args.limit]
    events=[]
    backend="cold_replay_to_breakpoint"
    def run_case(g,name,value):
        original_r0=g.rsp.reg(0)
        outcome,trace=g.inject_and_trace(pc,value,args.steps)
        row={"case":name,"injected_value":f"0x{value:08x}",
             "source_pc":f"0x{pc:08x}","mmio_address":f"0x{REGISTERS[args.site]:08x}",
             "r0_at_break":f"0x{original_r0:08x}",
             "outcome":outcome,"trace":trace}
        events.append(row)
        first=next((f"{x['pc']} -> {x['next']}" for x in trace if x["branch"]),None)
        print(f"{name}: {value:#010x}; branch={first}; end={outcome}",flush=True)
    if snapshot.get("usable"):
        # Fresh instance owns the snapshot throughout all trials. The file
        # created by the earlier validation instance has been cleaned up.
        with Guest(args,args.out,"fast-snapshot-fuzz",True) as g:
            g.break_at(pc)
            repeat_check=check_snapshot(g,pc)
            if not repeat_check.get("usable"):
                raise RuntimeError("snapshot unexpectedly failed repeat validation")
            backend="qemu_savevm_loadvm_per_trial"
            for name,value in chosen:
                g.qmp.hmp("loadvm before_mmio")
                if g.rsp.reg(15)!=pc or g.rsp.request("m4102603c,4")!=repeat_check["mmio_before"]:
                    raise RuntimeError("snapshot verification failed in the experiment loop")
                run_case(g,name,value)
    else:
        # Old QEMU builds may silently lose secure CP15/MMU registers on
        # loadvm. Never let a broken rollback corrupt differential results.
        for name,value in chosen:
            with Guest(args,args.out,"case-"+name) as g:
                g.break_at(pc)
                run_case(g,name,value)
    baseline=[e["pc"] for e in events[0]["trace"]] if events else []
    for event in events:
        seq=[e["pc"] for e in event["trace"]]
        mismatch=next((i for i,(a,b) in enumerate(zip(baseline,seq)) if a!=b),None)
        if mismatch is None and len(seq)!=len(baseline):
            mismatch=min(len(seq),len(baseline))
        event["first_divergence_step"]=mismatch
    report={"site":args.site,"read_pc":f"0x{pc:08x}",
            "address":f"0x{REGISTERS[args.site]:08x}",
            "snapshot_validation":snapshot,
            "rollback_method":backend,
            "injection":"RSP: set ARM r1 to candidate; advance PC by 4 past only the LDR",
            "hardware_confirmed":False,"cases":events}
    (args.out/"results.json").write_text(json.dumps(report,indent=2)+"\n")
    lines=["# EXeSX differential MMIO execution","",
           "These are firmware code paths under injected values, **not proven silicon behavior**.","",
           f"Read site: `0x{pc:08x}`; register: `0x{REGISTERS[args.site]:08x}`.","",
           f"Snapshot check: `{snapshot}`.","",
           "| Value | First branch | First difference (step) | Outcome |",
           "|---|---|---|---|"]
    for e in events:
        branch=next((f"{x['pc']} → {x['next']}" for x in e["trace"] if x["branch"]),"none")
        lines.append(f"| {e['injected_value']} | {branch} | {e['first_divergence_step']} | {e['outcome']} |")
    lines+=["","## Native ARM disassembly","", "```asm",asm.strip(),"```",
            "","A QEMU checkpoint is actually created and loadvm attempted before the trial sweep.",
            "Snapshot restoration is used only if ROM, secure MMU and deliberate MMIO",
            "register mutations all pass before/after rollback validation.",
            "Older QEMU builds are automatically cold-replayed for independence.",
            "No LCD or OS boot is claimed."]
    (args.out/"report.md").write_text("\n".join(lines)+"\n")
    print("Wrote",args.out/"results.json",args.out/"report.md",flush=True)

if __name__=="__main__":
    main()
