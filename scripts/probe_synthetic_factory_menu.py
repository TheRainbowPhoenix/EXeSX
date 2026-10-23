#!/usr/bin/env python3
"""DIAGNOSTIC ONLY: synthesize A7 keyboard event-return records (NOT hardware).

This intentionally bypasses the missing M4 scanner/A7 RTOS queue at one
firmware call site. Useful for checking the untouched BIOS factory menu and
saving a VM checkpoint, but MUST NOT be described as an authentic keypress.
Never uploads the user's ROM, image, snapshot, or decoded event records.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import time

from drive_factory_menu import QMP, connect, choose_port, voltage, PTA_READY, PTB_READY
from probe_postdma_handoff import RSP, encode_packet, decode_registers
from probe_ipc_0804 import stopped_thread

KEY_CALL=0x600108b0
KEY_RETURN=0x600108b4
MENU_ENTRY=0x6003a878
CODES=(0x93,0x93,0x94)


def run(args):
    folder=args.output_dir.resolve()
    image=folder/"a7-bios-os.elf"
    disk=folder/"dy357-menu-checkpoint.qcow2"
    profile=folder/"diagnostic-memory-profile.ini"
    if not all(p.exists() for p in (image,disk,profile)):
        raise FileNotFoundError(
            "First run drive_factory_menu.py to create the private event-wait checkpoint")
    voltage(folder/"gpioa-input-mask.txt",PTA_READY)
    voltage(folder/"gpiob-input-mask.txt",PTB_READY)
    qemu=args.qemu.resolve()
    env=os.environ.copy()
    env.update(EXESX_MEMORY_PROFILE=str(profile),
               EXESX_EXPERIMENTAL_M4_BOOT="1",EXESX_EXPERIMENTAL_MU_IRQ="1",
               EXESX_EXPERIMENTAL_LPIT1_IRQ="1",
               EXESX_EXPERIMENTAL_LPTMR_IRQ="1" if args.lptmr_irq else "0",
               EXESX_I2C4B_REGISTER_MIRROR="1",EXESX_I2C40_REGISTER_MIRROR="1",
               EXESX_SNVS_DIAGNOSTIC_SECURITY_PULSES="1",
               EXESX_USDHC1_EMMC="1",EXESX_EXPERIMENTAL_LCD="1",
               EXESX_EXPERIMENTAL_DMA1_M2M="1",
               EXESX_GPIOA_INPUT_MASK="0",EXESX_GPIOB_INPUT_MASK="0x88",
               EXESX_GPIOA_INPUT_MASK_FILE=str(folder/"gpioa-input-mask.txt"),
               EXESX_GPIOB_INPUT_MASK_FILE=str(folder/"gpiob-input-mask.txt"),
               EXESX_LCD_SCREENSHOT=str(folder/"lcd-synthetic-menu.ppm"))
    library=qemu.parent/"lib"
    if library.is_dir():
        env["LD_LIBRARY_PATH"]=str(library)+os.pathsep+env.get("LD_LIBRARY_PATH","")
    gd=choose_port()
    qm=choose_port()
    while qm==gd:
        qm=choose_port()
    cmd=[str(qemu),"-machine","exesx","-m","64M","-accel","tcg",
         "-display","none","-serial","none","-monitor","none","-no-reboot",
         "-drive",f"if=none,id=exesx-emmc,file={disk},format=qcow2",
         "-device",f"loader,file={image},cpu-num=0",
         "-S","-gdb",f"tcp:127.0.0.1:{gd}",
         "-qmp",f"tcp:127.0.0.1:{qm},server=on,wait=off"]
    data={"source":"owner's unchanged BIOS",
          "method":"SYNTHETIC debugger A7 event-reader return; NOT keyboard hardware",
          "codes":[hex(x) for x in CODES],"bios_factory_menu_entry_observed":False,
          "checkpoint_saved":False,"events":[]}
    start=time.monotonic()
    with (folder/"qemu-synthetic-events-private.log").open("w") as console:
        process=subprocess.Popen(cmd,env=env,stdout=console,
                                 stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL)
        try:
            with connect(gd,process) as gdb,connect(qm,process) as monitor:
                rsp=RSP(gdb)
                rsp.command("?")
                if rsp.command("Hg1")!="OK" or rsp.command("Hc-1")!="OK":
                    raise RuntimeError("Cannot select CPU0 A7")
                qmp=QMP(monitor)
                if "version-event-wait" not in qmp.hmp("info snapshots"):
                    raise RuntimeError("Original version-dialog snapshot absent")
                error=qmp.hmp("loadvm version-event-wait")
                if error.strip():
                    raise RuntimeError("Cannot load checkpoint: "+error)
                checkpoints={KEY_CALL:"key_event_reader_call",0x60010910:"keycode_0x93_test",
                             0x60010928:"keycode_0x94_test",MENU_ENTRY:"factory_test_menu"}
                for pc in checkpoints:
                    if rsp.command(f"Z0,{pc:x},4")!="OK":
                        raise RuntimeError("GDB breakpoint failed")
                sent=0
                hitcounts={}
                gdb.sendall(encode_packet("c"))
                deadline=time.monotonic()+args.seconds
                while time.monotonic()<deadline and process.poll() is None:
                    try:
                        stop=rsp.receive(min(1,deadline-time.monotonic()))
                    except TimeoutError:
                        continue
                    if stopped_thread(stop)!=1:
                        data["events"].append({"unexpected_stop":stop[:90]})
                        break
                    regs=decode_registers(rsp.command("g"))
                    pc=regs["r15"]
                    event={"pc":hex(pc),"name":checkpoints.get(pc,"unexpected"),
                           "r0":hex(regs["r0"]),"r4":hex(regs["r4"]),
                           "elapsed":round(time.monotonic()-start,2)}
                    data["events"].append(event)
                    print("BIOS",event,flush=True)
                    if pc==MENU_ENTRY:
                        data["bios_factory_menu_entry_observed"]=True
                        result=qmp.hmp("savevm factory-menu-synthetic")
                        if not result.strip() and "factory-menu-synthetic" in qmp.hmp("info snapshots"):
                            data["checkpoint_saved"]=True
                            print("SYNTHETIC-ENTRY MENU CHECKPOINT SAVED",flush=True)
                        else:
                            data["events"].append({"snapshot_error":result})
                        break
                    if pc==KEY_CALL and sent<len(CODES):
                        # At this real BL site, r0=sp+20 points to the 40-byte
                        # event destination used by the original ABI. Its
                        # header+8 is the event status, +16 starts the copied
                        # 20-byte record, and +24 is its 16-bit key code.
                        code=CODES[sent]
                        packet=bytearray(40)
                        struct.pack_into("<I",packet,8,0)
                        struct.pack_into("<HHH",packet,16,2,1,0)
                        struct.pack_into("<H",packet,24,code)
                        buf=regs["r0"]
                        if rsp.command(f"M{buf:x},{len(packet):x}:{packet.hex()}")!="OK":
                            raise RuntimeError("Diagnostic synthetic-event memory write failed")
                        if rsp.command("P0="+struct.pack("<I",0).hex())!="OK":
                            raise RuntimeError("Diagnostic synthetic-event status write failed")
                        if rsp.command("Pf="+struct.pack("<I",KEY_RETURN).hex())!="OK":
                            raise RuntimeError("Diagnostic synthetic-event BL skip failed")
                        sent+=1
                        data["events"].append({"SYNTHETIC_event_code":hex(code),"buffer":hex(buf)})
                    if pc not in checkpoints:
                        break
                    if rsp.command(f"z0,{pc:x},4")!="OK":
                        raise RuntimeError("Could not clear breakpoint")
                    hitcounts[pc]=hitcounts.get(pc,0)+1
                    if pc==KEY_CALL and sent<len(CODES):
                        if rsp.command(f"Z0,{pc:x},4")!="OK":
                            raise RuntimeError("Could not re-arm event reader call")
                    if pc in (0x60010910,0x60010928) and hitcounts[pc]<4:
                        gdb.sendall(encode_packet("s"))
                        if stopped_thread(rsp.receive(4))!=1:
                            raise RuntimeError("A7 diagnostic single-step failed")
                        if rsp.command(f"Z0,{pc:x},4")!="OK":
                            raise RuntimeError("Could not re-arm key compare")
                    gdb.sendall(encode_packet("c"))
                    if not qmp.execute("query-status")["running"]:
                        qmp.execute("cont")
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=8)
            (folder/"synthetic-factory-menu-results.json").write_text(
                json.dumps(data,indent=2)+"\n")
    return data


if __name__=="__main__":
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lptmr-irq",action="store_true",help="Opt-in M4 LPTMR0/1 NVIC compare interrupts")
    ap.add_argument("--qemu",type=Path,default=Path("build/qemu-system-arm"))
    ap.add_argument("--output-dir",type=Path,default=Path("private/factory-menu"))
    ap.add_argument("--seconds",type=float,default=15)
    ap.add_argument("--allow-synthetic-events",action="store_true",
                    help="Explicitly acknowledge this DEBUGGER BYPASS IS NOT KEYBOARD EMULATION")
    args=ap.parse_args()
    if not args.allow_synthetic_events:
        ap.error("Provide --allow-synthetic-events: this intentionally bypasses the keyboard driver")
    if args.seconds<=0:
        ap.error("--seconds must be positive")
    report=run(args)
    print(json.dumps({k:v for k,v in report.items() if k!="events"},indent=2))
