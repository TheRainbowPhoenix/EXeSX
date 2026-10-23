#!/usr/bin/env python3
"""Original DY357 physical M4 matrix keys -> original firmware, NO debugger.

The host closes/opens only the opt-in EXESX_M4_KEY_MATRIX_FILE contact.
QMP reads original RAM/MMIO registers and restores a PRIVATE QCOW2 checkpoint.
No GDB server, breakpoint, guest-register/memory write, synthetic IPC, or
A7 event-reader replacement. A genuine M4 queue record is NOT proof the
mailbox or A7 received it, and is NEVER treated as factory-menu success.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
from drive_factory_menu import QMP, connect, choose_port, voltage, PTA_READY, PTB_READY


def ram(qmp, addr, count=1):
    value=qmp.hmp(f"xp /{count}wx 0x{addr:x}")
    result=[]
    for line in value.splitlines():
        if ":" in line:
            result.extend(int(x,16) for x in
                          re.findall(r"0x[0-9a-fA-F]{1,8}",line.split(":",1)[1]))
    return result[:count]


def press(file, keys, hold, gap, delay, start, log, observations,
          idle_timeout, wait_idle=True):
    time.sleep(delay)
    for index,key in enumerate(keys):
        voltage(file,key)
        log.append({"host_elapsed":round(time.monotonic()-start,4),
                    "action":"physical_contact_close","requested_key":hex(key)})
        time.sleep(hold)
        voltage(file,0)
        released=round(time.monotonic()-start,4)
        log.append({"host_elapsed":released,
                    "action":"physical_contact_open","requested_key":hex(key)})
        time.sleep(gap)
        if index + 1 == len(keys) or not wait_idle:
            continue
        # Original M4 firmware must ACK release and finish debounce.
        # Merely setting contact=0 is NOT a complete key-up cycle.
        # QMP's independent sampler appends real firmware state; this
        # host-only wait never writes M4 RAM, IRQs or the A7 queue.
        deadline=time.monotonic()+idle_timeout
        while time.monotonic()<deadline:
            if len(observations)>1 and all(
                x["m4_state"]==0 and x["host_elapsed"]>released
                for x in observations[-2:]):
                log.append({"host_elapsed":round(time.monotonic()-start,4),
                            "action":"observed_real_M4_keyboard_idle",
                            "after_key":hex(key)})
                break
            time.sleep(.008)
        else:
            log.append({"host_elapsed":round(time.monotonic()-start,4),
                        "action":"M4_keyboard_release_not_confirmed",
                        "after_key":hex(key)})
            return


def run(a):
    dest=a.output_dir.resolve()
    dest.mkdir(parents=True,exist_ok=True)
    source=(a.checkpoint or dest/"dy357-menu-checkpoint.qcow2").resolve()
    elf=(a.elf or dest/"a7-bios-os.elf").resolve()
    profile=(a.profile or dest/"diagnostic-memory-profile.ini").resolve()
    for path in (source,elf,profile):
        if not path.is_file():
            raise FileNotFoundError(f"Missing PRIVATE original-firmware prerequisite: {path}")
    overlay=dest/"physical-keys-replay.qcow2"
    if overlay==source:
        raise ValueError("Input QCOW2 must not be the new replay image")
    if overlay.exists() and not a.overwrite:
        raise FileExistsError(f"Use --overwrite to replace private {overlay}")
    shutil.copyfile(source,overlay)
    keyfile=dest/"physical-keys-contact.txt"
    pta=dest/"physical-keys-pta.txt"
    ptb=dest/"physical-keys-ptb.txt"
    voltage(keyfile,0)
    voltage(pta,PTA_READY)
    voltage(ptb,PTB_READY)
    env=os.environ.copy()
    env.update(EXESX_MEMORY_PROFILE=str(profile),
               EXESX_EXPERIMENTAL_M4_BOOT="1",
               EXESX_EXPERIMENTAL_MU_IRQ="1",
               EXESX_EXPERIMENTAL_LPIT1_IRQ="1",
               EXESX_EXPERIMENTAL_LPTMR_IRQ="1",
               EXESX_EXPERIMENTAL_M4_PORT_IRQ="1",
               EXESX_EXPERIMENTAL_M4_TPM0_IRQ="1",
               EXESX_EXPERIMENTAL_LCD="1",
               EXESX_EXPERIMENTAL_DMA1_M2M="1",
               EXESX_USDHC1_EMMC="1",
               EXESX_I2C4B_REGISTER_MIRROR="1",
               EXESX_I2C40_REGISTER_MIRROR="1",
               EXESX_SNVS_DIAGNOSTIC_SECURITY_PULSES="1",
               EXESX_GPIOA_INPUT_MASK="0",
               EXESX_GPIOB_INPUT_MASK="0x88",
               EXESX_GPIOA_INPUT_MASK_FILE=str(pta),
               EXESX_GPIOB_INPUT_MASK_FILE=str(ptb),
               EXESX_M4_KEY_MATRIX_FILE=str(keyfile),
               EXESX_LCD_SCREENSHOT=str(dest/"physical-keys-lcd.ppm"))
    qemu=a.qemu.resolve()
    if (qemu.parent/"lib").is_dir():
        env["LD_LIBRARY_PATH"]=str(qemu.parent/"lib")+os.pathsep+env.get("LD_LIBRARY_PATH","")
    port=choose_port()
    cmd=[str(qemu),"-machine","exesx","-m","64M","-accel","tcg",
         "-display","none","-serial","none","-monitor","none","-no-reboot",
         "-drive",f"if=none,id=exesx-emmc,file={overlay},format=qcow2",
         "-device",f"loader,file={elf},cpu-num=0",
         "-S","-qmp",f"tcp:127.0.0.1:{port},server=on,wait=off"]
    trace=dest/"physical-keys-original-trace-private.log"
    if a.trace:
        cmd+=["-d","exec,guest_errors","-D",str(trace)]
    report={"mode":"physical GPIO contacts, no debugger/no event injection",
            "key_sequence":[hex(x) for x in a.keys],
            "hold_seconds":a.hold,"gap_seconds":a.gap,
            "contacts":[],"observations":[],
            "m4_keydown_observed":False,
            "a7_received_keydown_proven":False,
            "mu_payload_delivery_proven":False,
            "factory_menu_observed":False}
    with (dest/"physical-keys-console-private.log").open("w") as output:
        proc=subprocess.Popen(cmd,env=env,stdout=output,
                              stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL)
        try:
            with connect(port,proc) as connection:
                qmp=QMP(connection)
                if a.tag not in qmp.hmp("info snapshots"):
                    raise RuntimeError("Original BIOS wait checkpoint not present")
                error=qmp.hmp("loadvm "+a.tag)
                if error.strip():
                    raise RuntimeError("Cannot resume owner-private checkpoint: "+error)
                begin=time.monotonic()
                worker=threading.Thread(target=press,
                         args=(keyfile,a.keys,a.hold,a.gap,a.delay,begin,report["contacts"],
                               report["observations"],a.idle_timeout,not a.no_wait_idle),
                         daemon=True)
                worker.start()
                qmp.execute("cont")
                next_sample=begin
                while time.monotonic()-begin<a.seconds and proc.poll() is None:
                    if time.monotonic()<next_sample:
                        time.sleep(min(.01,next_sample-time.monotonic()))
                        continue
                    # All commands below READ original SRAM and MMIO only.
                    queue=ram(qmp,0x1ffea34c,5)
                    state=ram(qmp,0x1ffea320,6)
                    mua=ram(qmp,0x41022060,2)
                    mub=ram(qmp,0x40220060,2)
                    regs=qmp.hmp("info registers")
                    pc=re.search(r"R15=([0-9a-fA-F]{8})",regs)
                    observation={
                        "host_elapsed":round(time.monotonic()-begin,4),
                        "m4_state":state[0] if state else None,
                        "m4_counter":state[1] if len(state)>1 else None,
                        "m4_selected_row_column":state[5] if len(state)>5 else None,
                        "m4_queue_type":queue[0]&0xffff if queue else None,
                        "m4_queue_subtype":queue[0]>>16 if queue else None,
                        "m4_queue_key":queue[2]&0xffff if len(queue)>2 else None,
                        "mua_sr_cr":mua,"mub_sr_cr":mub,
                        "a7_pc_sample":pc.group(1) if pc else None}
                    report["observations"].append(observation)
                    if observation["m4_queue_type"]==2 and \
                       observation["m4_queue_subtype"]==1:
                        report["m4_keydown_observed"]=True
                    next_sample+=a.poll
                worker.join(timeout=max(0,a.seconds))
                qmp.execute("stop")
                if a.trace and trace.exists():
                    # Passive QEMU TB execution trace; CPU TB boundaries are
                    # not always identical to the original function entry.
                    with trace.open(errors="replace") as tracefile:
                        menu=False
                        for line in tracefile:
                            if "/000000006003a878/" in line:
                                menu=True
                    report["factory_menu_observed"]=menu
                    report["private_trace_path"]=str(trace)
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=8)
            (dest/"physical-keys-results-private.json").write_text(
                json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:v for k,v in report.items()
                      if k not in ("contacts","observations")},indent=2))


if __name__=="__main__":
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--qemu",type=Path,default=Path("qemu-system-arm"))
    ap.add_argument("--output-dir",type=Path,default=Path("private/factory-menu"))
    ap.add_argument("--checkpoint",type=Path)
    ap.add_argument("--elf",type=Path)
    ap.add_argument("--profile",type=Path)
    ap.add_argument("--tag",default="version-event-wait")
    ap.add_argument("--keys",default="0x93,0x93,0x94")
    ap.add_argument("--hold",type=float,default=.12)
    ap.add_argument("--gap",type=float,default=.06)
    ap.add_argument("--delay",type=float,default=0.0)
    ap.add_argument("--seconds",type=float,default=1.8)
    ap.add_argument("--poll",type=float,default=.035)
    ap.add_argument("--idle-timeout",type=float,default=1.0,
                    help="Bounded host seconds to observe original M4 state0 after each release")
    ap.add_argument("--no-wait-idle",action="store_true",
                    help="Skip QMP-confirmed release gate (may turn a second press into subtype2 repeat)")
    ap.add_argument("--trace",action="store_true",
                    help="Log passive guest TB execution and MU MMIO to PRIVATE file")
    ap.add_argument("--overwrite",action="store_true")
    args=ap.parse_args()
    args.keys=tuple(int(x,0) for x in args.keys.split(","))
    if not args.keys or any(x not in (0x93,0x94,0x95,0x80) for x in args.keys):
        ap.error("Only owner-ROM decoded matrix keys 0x93/0x94/0x95/0x80 are supported")
    if args.seconds<=0 or args.poll<=0 or args.hold<=0 or args.gap<0 or args.idle_timeout<=0:
        ap.error("Require positive --seconds/--poll/--hold and nonnegative --gap")
    run(args)
