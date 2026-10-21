#!/usr/bin/env python3
"""Trace the M4 GPIOB7 -> A7 shared start-permission -> startup/shutdown path.

Private, checksum-validated A7 firmware ELF required; never add it or any
generated execution log to Git. This is a clean-cold-run read-only probe,
not an altered register/PC experiment. Opt-in I2C mirrors and SNVS security
pulse ignore are explicitly diagnostic and not actual peripherals/security.
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
from fuzz_mmio import RSP

M4_GATE_STORES = (0x1FFD7798, 0x1FFD77A0)
A7_GATE_CHECK = 0x6004A19C
A7_SHUTDOWN = 0x6004A1B4
A7_STARTUP = 0x6004A1BC
SHARED = 0x2F029284
GPIOB_PDIR = 0x4100F050


def connect(proc: subprocess.Popen, port: int) -> socket.socket:
    for _ in range(400):
        if proc.poll() is not None:
            raise RuntimeError(f"QEMU exited before GDB connection: {proc.returncode}")
        try:
            return socket.create_connection(("127.0.0.1",port),0.15)
        except OSError:
            time.sleep(0.025)
    raise TimeoutError("GDB remote unavailable")


def read_word(rsp: RSP, address: int) -> int:
    data=rsp.request(f"m{address:x},4")
    if len(data)!=8 or data.startswith("E"):
        raise RuntimeError(f"Cannot read private guest address {address:#x}: {data}")
    return int.from_bytes(bytes.fromhex(data),"little")


def run_case(args, mask: str, out: Path) -> dict:
    env=os.environ.copy()
    env.update(EXESX_MEMORY_PROFILE=str(args.profile.resolve()),
               EXESX_EXPERIMENTAL_M4_BOOT="1",
               EXESX_EXPERIMENTAL_MU_IRQ="1",
               EXESX_I2C4B_REGISTER_MIRROR="1",
               EXESX_I2C40_REGISTER_MIRROR="1",
               EXESX_SNVS_DIAGNOSTIC_SECURITY_PULSES="1",
               EXESX_GPIOB_INPUT_MASK=mask)
    qemu=args.qemu.resolve()
    lib=qemu.parent/"lib"
    if lib.is_dir():
        env["LD_LIBRARY_PATH"]=str(lib)+":"+env.get("LD_LIBRARY_PATH","")
    portsock=socket.socket()
    portsock.bind(("127.0.0.1",0))
    port=portsock.getsockname()[1]
    portsock.close()
    cmd=[str(qemu),"-machine","exesx","-m","64M","-accel","tcg",
         "-display","none","-serial","none","-monitor","none","-no-reboot",
         "-S","-gdb",f"tcp:127.0.0.1:{port}",
         "-device",f"loader,file={args.elf.resolve()},cpu-num=0"]
    with out.open("w") as logfile:
        process=subprocess.Popen(cmd,env=env,stdout=logfile,stderr=subprocess.STDOUT)
        sock=None
        try:
            sock=connect(process,port)
            rsp=RSP(sock)
            rsp.s.settimeout(args.timeout)
            rsp.request("qSupported:multiprocess+;qXfer:features:read+")
            rsp.request("?")
            for pc in M4_GATE_STORES:
                if rsp.request(f"Z0,{pc:x},2")!="OK":
                    raise RuntimeError(f"Cannot break at M4 gate writer {pc:#x}")
            if rsp.request(f"Z0,{A7_GATE_CHECK:x},4")!="OK":
                raise RuntimeError("Cannot break at A7 gate check")
            stop=rsp.request("c")
            if "thread:p01.02" not in stop:
                raise RuntimeError("Unexpected first stop, expected M4 gate writer: "+stop)
            rsp.request("Hgp01.02")
            writer_pc=rsp.reg(15)
            if writer_pc not in M4_GATE_STORES:
                raise RuntimeError(f"Wrong M4 gate-write site {writer_pc:#x}")
            before=read_word(rsp,SHARED)
            physical=read_word(rsp,GPIOB_PDIR)
            value_to_store=rsp.reg(1)
            for pc in M4_GATE_STORES:
                rsp.request(f"z0,{pc:x},2")
            rsp.request("s")
            after=read_word(rsp,SHARED)
            stop=rsp.request("c")
            if "thread:p01.01" not in stop:
                raise RuntimeError("Unexpected A7 gate stop: "+stop)
            rsp.request("Hgp01.01")
            a7_pc=rsp.reg(15)
            if a7_pc!=A7_GATE_CHECK:
                raise RuntimeError(f"Expected A7 gate check {A7_GATE_CHECK:#x}, got {a7_pc:#x}")
            a7_result=rsp.reg(0)
            latest=read_word(rsp,SHARED)
            rsp.request(f"z0,{A7_GATE_CHECK:x},4")
            for pc in (A7_SHUTDOWN,A7_STARTUP):
                if rsp.request(f"Z0,{pc:x},4")!="OK":
                    raise RuntimeError(f"Cannot set branch-site breakpoint {pc:#x}")
            rsp.request("s")
            branch_stop=rsp.request("c")
            if "thread:p01.01" not in branch_stop:
                raise RuntimeError("Unexpected branch stop: "+branch_stop)
            rsp.request("Hgp01.01")
            route_pc=rsp.reg(15)
            if route_pc not in (A7_SHUTDOWN,A7_STARTUP):
                raise RuntimeError(f"Unexpected A7 branch {route_pc:#x}")
            return {
                "input_mask":mask,
                "m4_write_pc":f"0x{writer_pc:08x}",
                "gpiob_pdir_at_first_write":f"0x{physical:08x}",
                "m4_intended_value":f"0x{value_to_store:08x}",
                "shared_before_first_write":f"0x{before:08x}",
                "shared_after_first_write":f"0x{after:08x}",
                "shared_at_a7_gate":f"0x{latest:08x}",
                "a7_gate_result":f"0x{a7_result:08x}",
                "a7_selected_route":"normal_startup" if route_pc==A7_STARTUP else "shutdown",
                "a7_route_pc":f"0x{route_pc:08x}",
            }
        finally:
            if sock:
                sock.close()
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:process.kill();process.wait()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("elf",type=Path,help="private SHA-verified A7 ELF from OSUP")
    p.add_argument("--qemu",type=Path,default=Path("build/qemu-system-arm"))
    p.add_argument("--profile",type=Path,default=Path("profiles/imx7ulp-early-boot.ini"))
    p.add_argument("--out",type=Path,default=Path("private/gpiob-boot-gate"))
    p.add_argument("--timeout",type=int,default=20)
    a=p.parse_args()
    for path in (a.elf,a.qemu,a.profile):
        if not path.is_file():
            p.error(f"Missing required local file: {path}")
    a.out.mkdir(parents=True,exist_ok=True)
    a.out.chmod(0o700)
    records=[]
    for mask in ("0","0x80"):
        records.append(run_case(a,mask,a.out/f"private-qemu-{mask}.log"))
    result={"cases":records,
            "meaning":"Private real Casio firmware; synthetic I2C mirrors and ignored SNVS security pulses; GPIOB7 input override, not proven hardware wiring",
            "no_rom_or_guest_memory_uploaded":True}
    dest=a.out/"gpio-boot-gate-private.json"
    dest.write_text(json.dumps(result,indent=2)+"\n")
    dest.chmod(0o600)
    for r in records:
        print("GPIOB",r["input_mask"],"PDIR",r["gpiob_pdir_at_first_write"],
              "shared",r["shared_at_a7_gate"],"route",r["a7_selected_route"])
    print("Private result:",dest)


if __name__=="__main__":
    main()
