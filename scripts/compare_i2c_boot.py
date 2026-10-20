#!/usr/bin/env python3
"""Compare actual A7/M4 firmware progress under isolated I2C read hypotheses.

Produces JSON with both CPU PCs, the shared IPC word and ARM exceptions;
does not presume a device identity or fabricate an LCD screenshot.
Requires your private a7-firmware.elf generated from your own OSUP.BIN.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time

def one(args, case: str):
    env=os.environ.copy()
    env["EXESX_MEMORY_PROFILE"]=str(args.profile.resolve())
    env["EXESX_EXPERIMENTAL_M4_BOOT"]="1"
    env.pop("EXESX_I2C4B_REPLY_HEX",None)
    if case!="none":
        if len(case)%2 or len(case)>128 or not re.fullmatch(r"[0-9a-fA-F]+",case):
            raise ValueError("I2C reply must be 1–64 complete hex bytes")
        env["EXESX_I2C4B_REPLY_HEX"]=case
    lib=args.qemu.resolve().parent/"lib"
    if lib.is_dir():
        env["LD_LIBRARY_PATH"]=str(lib)+":"+env.get("LD_LIBRARY_PATH","")
    directory=args.out/case
    directory.mkdir(parents=True,exist_ok=True)
    logfile=directory/"qemu-exceptions.log"
    cmd=[str(args.qemu.resolve()),"-machine","exesx","-m","64M",
         "-accel","tcg","-display","none","-serial","none",
         "-monitor","stdio","-no-reboot",
         "-device",f"loader,file={args.elf.resolve()},cpu-num=0",
         "-d","int,unimp,guest_errors","-D",str(logfile.resolve())]
    guest=subprocess.Popen(cmd,env=env,stdin=subprocess.PIPE,
                           stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                           text=True,bufsize=1)
    try:
        time.sleep(args.seconds)
        if guest.poll() is not None:
            raise RuntimeError(f"guest exited early: {guest.returncode}")
        monitor=("info cpus\ninfo registers\ncpu 1\ninfo registers\n"
                 "xp /1wx 0x2f028000\nquit\n")
        output,_=guest.communicate(monitor,timeout=12)
    finally:
        if guest.poll() is None:
            guest.kill()
            guest.wait()
    (directory/"monitor.txt").write_text(output)
    text=re.sub(r"\x1b\[[0-9;]*[a-zA-Z]","",output)
    pcs=re.findall(r"(?m)^R15=([0-9a-fA-F]{8})\b",text)
    word=re.search(r"(?m)^0*2f028000:\s+0x([0-9a-fA-F]{8})",text)
    faulttext=logfile.read_text(errors="replace")
    exceptions=re.findall(
        r"Taking exception[^\n]*|fault address 0x[0-9a-fA-F]+",
        faulttext
    )
    return {
        "case":case,
        "diagnostic_slave_enabled":case!="none",
        "a7_pc":f"0x{pcs[0].lower()}" if pcs else None,
        "m4_pc":f"0x{pcs[1].lower()}" if len(pcs)>1 else None,
        "ipc_0x2f028000":f"0x{word.group(1).lower()}" if word else None,
        "exceptions":exceptions[-12:],
        "log_path":str(logfile),
    }

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("elf",type=Path)
    p.add_argument("--qemu",type=Path,default=Path("build/qemu-system-arm"))
    p.add_argument("--profile",type=Path,default=Path("profiles/imx7ulp-early-boot.ini"))
    p.add_argument("--seconds",type=float,default=0.8)
    p.add_argument("--cases",default="none,00,ff",help="comma-separated: none, hex byte sequences")
    p.add_argument("--out",type=Path,default=Path("private/i2c-differential"))
    args=p.parse_args()
    if not 0.1<=args.seconds<=20:
        p.error("--seconds must be between 0.1 and 20")
    for f in (args.elf,args.qemu,args.profile):
        if not f.is_file():
            p.error(f"missing {f}")
    cs=[x.strip() for x in args.cases.split(",")]
    if not cs or any(not x for x in cs):
        p.error("empty --cases entry")
    args.out.mkdir(parents=True,exist_ok=True)
    report={
        "hardware_verified":False,
        "warning":"Artificial I2C replies are a controlled software experiment, not a maXTouch or Casio hardware emulation.",
        "runs":[one(args,c) for c in cs]
    }
    (args.out/"comparison.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))

if __name__=="__main__":
    main()
