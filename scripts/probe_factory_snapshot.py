#!/usr/bin/env python3
"""Firmware-free real QEMU QCOW2 save/load test across separate processes."""
import argparse
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
from drive_factory_menu import QMP, backed_qcow2, connect
from probe_gpiob_input import guest_elf
from hmp_memory import memory_words

SCRATCH=0x6200b400


def verify(qemu,profile):
    with tempfile.TemporaryDirectory() as name:
        root=Path(name)
        raw=root/"synthetic-emmc.raw"
        with raw.open("wb") as f:
            f.truncate(8*1024*1024)
        overlay=root/"snapshot.qcow2"
        backed_qcow2(overlay,raw)
        elf=root/"synthetic.elf"
        elf.write_bytes(guest_elf())
        env=os.environ.copy()
        env["EXESX_MEMORY_PROFILE"]=str(profile.resolve())
        library=qemu.resolve().parent/"lib"
        if library.is_dir():
            env["LD_LIBRARY_PATH"]=str(library)+os.pathsep+env.get("LD_LIBRARY_PATH","")

        def start():
            with socket.socket() as s:
                s.bind(("127.0.0.1",0))
                port=s.getsockname()[1]
            cmd=[str(qemu.resolve()),"-machine","exesx","-m","64M",
                 "-accel","tcg","-display","none","-serial","none",
                 "-monitor","none","-no-reboot","-S",
                 "-drive",f"if=none,id=exesx-emmc,file={overlay},format=qcow2",
                 "-qmp",f"tcp:127.0.0.1:{port},server=on,wait=off",
                 "-device",f"loader,file={elf},cpu-num=0"]
            log=(root/"qemu-private.log").open("a")
            proc=subprocess.Popen(cmd,env=env,stdin=subprocess.DEVNULL,
                                  stdout=log,stderr=subprocess.STDOUT)
            return proc,connect(port,proc),log

        def finish(session):
            session[1].close()
            session[0].kill()
            session[0].wait(timeout=8)
            session[2].close()

        session=start()
        try:
            q=QMP(session[1])
            q.execute("cont")
            time.sleep(.5)
            q.execute("stop")
            expected=memory_words(q.hmp(f"xp /3wx {SCRATCH:#x}"),SCRATCH,3)
            if expected != [0,0x80,0]:
                raise AssertionError(f"Original synthetic ARM GPIO result not produced: {expected}")
            if q.hmp("savevm factory-resume").strip():
                raise AssertionError("Could not save QCOW2 VM checkpoint")
            if "factory-resume" not in q.hmp("info snapshots"):
                raise AssertionError("Saved snapshot missing")
        finally:
            finish(session)

        session=start()
        try:
            q=QMP(session[1])
            cold=memory_words(q.hmp(f"xp /3wx {SCRATCH:#x}"),SCRATCH,3)
            if cold == expected:
                raise AssertionError("Cold-start RAM unexpectedly contains prior guest execution")
            if q.hmp("loadvm factory-resume").strip():
                raise AssertionError("Could not load snapshot in fresh QEMU")
            restored=memory_words(q.hmp(f"xp /3wx {SCRATCH:#x}"),SCRATCH,3)
            if restored != expected:
                raise AssertionError(f"Restored guest RAM corrupted: {restored}")
            print("PASS real QEMU QCOW2 raw-backed savevm/loadvm across separate QEMU processes")
        finally:
            finish(session)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu",type=Path,default=Path("build/qemu-system-arm"))
    parser.add_argument("--profile",type=Path,default=Path("profiles/imx7ulp-early-boot.ini"))
    a=parser.parse_args()
    verify(a.qemu,a.profile)
