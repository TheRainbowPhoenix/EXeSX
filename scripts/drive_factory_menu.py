#!/usr/bin/env python3
"""Private original DY357 firmware: host-controlled M4 GPIO candidates and VM snapshots.

This is NOT a firmware key-event injector. M4 matrix row/scan scheduling must
actually run for these column pulses to become A7 key-down events. Check the
original decoder and menu PC; never report success based only on pin changes.
"""
import argparse
import json
import os
from pathlib import Path
import re
import socket
import struct
import subprocess
import sys
import threading
import time

from probe_postdma_handoff import RSP, choose_port, encode_packet, decode_registers
from probe_ipc_0804 import stopped_thread
from run_osup import prepare

PTA_READY = 0x808c6008
PTB_READY = 0xc8
PINS = {0x93: ("a", 0x80000000), 0x94: ("a", 0x00800000),
        0x95: ("a", 0x00800000), 0x80: ("b", 0x40)}
A7 = {0x60011860:"bios_startup_task",
      0x60011a30:"bios_startup_event_initialization",
      0x60011250:"bios_startup_selector_from_sim0",
      0x60011ca4:"bios_startup_main",
      0x6001d93c:"startup_chord_80_95_92",
      0x6001d94c:"startup_chord_80_90_96",
      0x60010868:"bios_version_key_sequence",
      0x60008cbc:"power_a002_read",0x601782c8:"ipc_sync_dispatch",0x60010898:"m4_service_0804_result",0x600108a8:"event_wait",
      0x600108b4:"event_reader_return",0x600108cc:"event_type_check",
      0x60010928:"diagnostic_key_accept",
      0x60010910:"diagnostic_sequence",0x60010974:"dialog_exit",
      0x6003a878:"factory_test_menu",0x60058008:"lcd_unit_check",
      0x60400000:"os_entry"}
M4 = {0x1ffd7d2e:"m4_pctla_irq56_wake",
      0x1ffd53ba:"m4_rtos_post_event_flags",
      0x1ffd7d5a:"m4_post_keyboard_bit2_callback",
      0x1ffd8088:"m4_keyboard_bit2_debounce_state",
      0x1ffd809e:"m4_keyboard_state2_resample_column",
      0x1ffd7fa0:"m4_post_keyboard_bit1_timer",
      0x1ffd7b42:"m4_worker_dispatch_bit2",
      0x1ffd7b0c:"keyboard_event_flags_wait",
      0x1ffd7b28:"keyboard_event_flags_received",
      0x1ffd7b2e:"keyboard_event_bit0_dispatch",
      0x1ffd7fb0:"scan_task_entry",0x1ffd7fca:"scan_full_matrix_call",
      0x1ffd8634:"scan_full_matrix",0x1ffed3b0:"lptmr0_isr",
      0x1ffd8412:"row_drive",0x1ffd8564:"column_scan",
      0x1ffd85c6:"gpio_column_read",0x1ffd8610:"key_debounce",
      0x1ffd838a:"m4_key_queue_consume",
      0x1ffd874a:"m4_keyboard_ipc_router",
      0x1ffde672:"m4_ipc_envelope_build",
      0x1ffde74a:"m4_ipc_envelope_queue",
      0x1ffe0cce:"m4_ipc_notify"}


def backed_qcow2(path, raw):
    """QCOW2 v3 64K cluster overlay, explicit raw backing (no qemu-img).

    Persist QEMU savevm state + eMMC COW sectors. Absolute backing path must
    remain unchanged between starts. Never alter the source-derived raw image.
    """
    if path.exists():
        raise FileExistsError(f"Checkpoint exists: {path}; use --resume")
    c = 65536
    backing = str(raw.resolve()).encode("utf-8")
    if len(backing) > c - 128:
        raise ValueError("Backing filename is too long")
    size = raw.stat().st_size
    l1 = (size + c*c//8 - 1) // (c*c//8)
    if l1*8 > c:
        raise ValueError("Backing size exceeds one L1 table")
    head = struct.pack(">IIQIIQIIQQIIQQQQII",0x514649fb,3,128,len(backing),
                       16,size,0,l1,c,2*c,1,0,0,0,0,0,4,104)
    buf = bytearray(4*c)
    buf[:len(head)] = head
    struct.pack_into(">II",buf,104,0xe2792aca,3)  # backing format extension
    buf[112:115] = b"raw"
    struct.pack_into(">II",buf,120,0,0)
    buf[128:128+len(backing)] = backing
    struct.pack_into(">Q",buf,2*c,3*c)
    for i in range(4):
        struct.pack_into(">H",buf,3*c+2*i,1)
    path.write_bytes(buf)


def voltage(path, bits):
    temporary = path.with_suffix(".new")
    temporary.write_text(hex(bits)+"\n",encoding="ascii")
    os.replace(temporary,path)


class QMP:
    def __init__(self, sock):
        self.sock=sock
        sock.settimeout(12)
        self.file=sock.makefile("rb")
        if "QMP" not in json.loads(self.file.readline()):
            raise RuntimeError("Missing QMP greeting")
        self.execute("qmp_capabilities")

    def execute(self, command, arguments=None):
        request={"execute":command,"id":"factory"}
        if arguments is not None:
            request["arguments"]=arguments
        self.sock.sendall((json.dumps(request)+"\n").encode())
        while True:
            line=self.file.readline()
            if not line:
                raise ConnectionError("QMP disconnected")
            reply=json.loads(line)
            if reply.get("id")=="factory":
                if "error" in reply:
                    raise RuntimeError(f"QMP {command}: {reply['error']}")
                return reply["return"]

    def hmp(self, line):
        return self.execute("human-monitor-command",{"command-line":line})


def connect(port, proc):
    for _ in range(120):
        if proc.poll() is not None:
            raise RuntimeError("QEMU exited before monitor connection")
        try:
            return socket.create_connection(("127.0.0.1",port),.25)
        except OSError:
            time.sleep(.1)
    raise TimeoutError("QEMU connection timed out")


def pulse(keys, a_file, b_file, hold, gap, events, matrix_file=None):
    for key in keys:
        if matrix_file is not None:
            # Physical contact only: QEMU gates low columns on real
            # M4 GPIO row drive, and original firmware must generate events.
            voltage(matrix_file, key)
            events.append({"event":"physical_matrix_contact_closed","key_guess":hex(key)})
            time.sleep(hold)
            voltage(matrix_file, 0)
            events.append({"event":"physical_matrix_contact_open","key_guess":hex(key)})
            time.sleep(gap)
            continue
        bank, bit = PINS[key]
        a = PTA_READY & ~bit if bank=="a" else PTA_READY
        b = PTB_READY & ~bit if bank=="b" else PTB_READY
        voltage(a_file,a);voltage(b_file,b)
        events.append({"event":"candidate_pin_low","key_guess":hex(key),
                       "a":hex(a),"b":hex(b)})
        time.sleep(hold)
        voltage(a_file,PTA_READY);voltage(b_file,PTB_READY)
        events.append({"event":"candidate_pin_high","key_guess":hex(key)})
        time.sleep(gap)


def run(args):
    dest=args.output_dir.resolve()
    dest.mkdir(parents=True,exist_ok=True)
    raw=dest/"source-derived-synthetic-emmc.raw"
    elf=dest/"a7-bios-os.elf"
    if not raw.exists() or not elf.exists():
        if args.resume:
            raise FileNotFoundError("Missing private raw media or ELF for --resume")
        prepare(args.osup.resolve(),dest)
    overlay=dest/"dy357-menu-checkpoint.qcow2"
    if not overlay.exists():
        if args.resume:
            raise FileNotFoundError("No saved QCOW2 overlay")
        backed_qcow2(overlay,raw)
    elif not args.resume:
        raise FileExistsError("Existing overlay; pass --resume or use new --output-dir")

    profile=dest/"diagnostic-memory-profile.ini"
    profile_data=args.profile.read_text()
    if "base=0xb0000000" not in profile_data.lower():
        profile_data+="\n[diagnostic-flexbus-lcd]\nkind=exesx-lcd\nbase=0xb0000000\nsize=0x1000\n"
    profile.write_text(profile_data)
    pa=dest/"gpioa-input-mask.txt";pb=dest/"gpiob-input-mask.txt"
    voltage(pa,PTA_READY if (args.resume or args.startup_chord) else 0)
    voltage(pb,PTB_READY if (args.resume or args.startup_chord) else 0x88)
    matrix_file = dest/"m4-key-matrix-contact.txt" if args.matrix_keys else None
    if matrix_file is not None:
        if args.startup_chord and not args.resume:
            # Contacts are closed BEFORE the original A7 BIOS startup
            # performs its direct GPIO/IOMUX key-chord checks.
            matrix_file.write_text(args.startup_chord + "\n", encoding="ascii")
        else:
            voltage(matrix_file, 0)
    env=os.environ.copy()
    env.update(EXESX_MEMORY_PROFILE=str(profile),
               EXESX_EXPERIMENTAL_M4_BOOT="1",EXESX_EXPERIMENTAL_MU_IRQ="1",
               EXESX_EXPERIMENTAL_LPIT1_IRQ="1",
               EXESX_EXPERIMENTAL_LPTMR_IRQ="1" if args.lptmr_irq else "0",
               EXESX_EXPERIMENTAL_LPTMR_PCS_CLOCKS="1",
               EXESX_EXPERIMENTAL_M4_PORT_IRQ="1" if args.port_irq else "0",
               EXESX_EXPERIMENTAL_M4_TPM0_IRQ="1" if args.tpm0_irq else "0",
               EXESX_I2C4B_REGISTER_MIRROR="1",EXESX_I2C40_REGISTER_MIRROR="1",
               EXESX_SNVS_DIAGNOSTIC_SECURITY_PULSES="1",
               EXESX_USDHC1_EMMC="1",EXESX_EXPERIMENTAL_LCD="1",
               EXESX_EXPERIMENTAL_DMA1_M2M="1",
               EXESX_GPIOA_INPUT_MASK="0",EXESX_GPIOB_INPUT_MASK="0x88",
               EXESX_GPIOA_INPUT_MASK_FILE=str(pa),
               EXESX_GPIOB_INPUT_MASK_FILE=str(pb),
               EXESX_LCD_SCREENSHOT=str(dest/"lcd-screenshot.ppm"))
    if matrix_file is not None:
        env["EXESX_M4_KEY_MATRIX_FILE"] = str(matrix_file)
    q=args.qemu.resolve()
    if (q.parent/"lib").is_dir():
        env["LD_LIBRARY_PATH"]=str(q.parent/"lib")+os.pathsep+env.get("LD_LIBRARY_PATH","")
    gd=choose_port();qm=choose_port()
    while qm==gd:qm=choose_port()
    cmd=[str(q),"-machine","exesx","-m","64M","-accel","tcg",
         "-display","none","-serial","none","-monitor","none","-no-reboot",
         "-drive",f"if=none,id=exesx-emmc,file={overlay},format=qcow2",
         "-device",f"loader,file={elf},cpu-num=0",
         "-S","-gdb",f"tcp:127.0.0.1:{gd}",
         "-qmp",f"tcp:127.0.0.1:{qm},server=on,wait=off"]
    events=[]
    result={"source":"owner-private original DY357","overlay":str(overlay),
            "snapshot_tag":args.tag,"resume":args.resume,
            "candidate_codes":[hex(k) for k in args.keys],
            "original_startup_chord":args.startup_chord,
            "events":events,"factory_menu_observed":False}
    started=time.monotonic()
    gdb=None
    with (dest/"qemu-console-private.log").open("w") as console:
        proc=subprocess.Popen(cmd,env=env,stdout=console,
                              stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL)
        try:
            gdb=connect(gd,proc)
            rsp=RSP(gdb)
            rsp.command("?")
            if rsp.command("Hg1")!="OK" or rsp.command("Hc-1")!="OK":
                raise RuntimeError("Failed to select Cortex-A7 and both CPUs")
            with connect(qm,proc) as monitor:
                qmp=QMP(monitor)
                if args.resume:
                    if args.tag not in qmp.hmp("info snapshots"):
                        raise RuntimeError("Named checkpoint not in QCOW2")
                    error=qmp.hmp("loadvm "+args.tag)
                    if error.strip():
                        raise RuntimeError("VM load failed: "+error)
                    events.append({"event":"snapshot_reloaded"})
                marks={pc:name for pc,name in A7.items()
                       if not args.resume or pc!=0x60010898}
                if args.trace_m4:
                    marks.update(M4)
                for pc in marks:
                    if rsp.command(f"Z0,{pc:x},{2 if pc in M4 else 4}")!="OK":
                        raise RuntimeError(f"Breakpoint failed at {pc:#x}")
                gdb.sendall(encode_packet("c"))
                saved=args.resume
                ready=args.resume
                sender=None
                if args.contact_delay is not None and args.keys:
                    # Diagnostic: close actual virtual matrix contacts even
                    # if cold boot never reaches the A7 version dialog.
                    # This does NOT inject a firmware or mailbox event.
                    def cold_contact_sender():
                        time.sleep(args.contact_delay)
                        pulse(args.keys,pa,pb,args.hold,args.gap,events,
                              matrix_file)
                    sender=threading.Thread(target=cold_contact_sender,
                                            daemon=True)
                    sender.start()
                    events.append({"event":"independent_physical_key_probe_scheduled",
                                   "delay_seconds":args.contact_delay})
                counts={}
                deadline=time.monotonic()+args.seconds
                while time.monotonic()<deadline and proc.poll() is None:
                    try:
                        stop=rsp.receive(min(1,deadline-time.monotonic()))
                    except TimeoutError:
                        continue
                    tid=stopped_thread(stop)
                    if tid not in (1,2):
                        events.append({"event":"unexpected_cpu_stop","reply":stop[:90]})
                        break
                    rsp.command(f"Hg{tid}")
                    registers=decode_registers(rsp.command("g"))
                    pc=registers["r15"]
                    hit={"event":"guest_breakpoint","pc":hex(pc),
                         "name":marks.get(pc,"unknown"),"thread":tid,
                         "r0":hex(registers["r0"]),
                         "r1":hex(registers["r1"]),
                         "r2":hex(registers["r2"]),
                         "r3":hex(registers["r3"]),
                         "seconds":round(time.monotonic()-started,2)}
                    if tid==2 and pc==0x1ffd7b28:
                        bits=rsp.memory(registers["r13"]+4,4)
                        hit["m4_keyboard_rtos_event_bits"]=(
                            None if bits is None else hex(bits))
                    if tid==2 and args.trace_m4:
                        # Read the original M4 scan task's state fields,
                        # not a synthetic keyboard status or virtual event.
                        for label,address in (
                            ("scan_task_state",0x1ffea320),
                            ("scan_task_count",0x1ffea324),
                            ("keyboard_event_object10_flags",0x1fff4f08),
                            ("port_a_isfr",0x4103f0a0),
                            ("port_a_pcr23",0x4103f05c),
                            ("port_a_pcr31",0x4103f07c),
                            ("lptmr0_csr",0x4102e000),
                            ("m4_nvic_enabled_32_63",0xe000e104),
                            ("m4_nvic_pending_32_63",0xe000e204),
                        ):
                            value=rsp.memory(address,4)
                            hit[label]=None if value is None else hex(value)
                    if tid==1 and pc==0x600108cc:
                        # Original BIOS has copied the event's 20-byte payload
                        # from [SP+0x24] to [SP]. Read the genuine copied
                        # record, not stale mailbox data and not a host pulse.
                        sp=registers["r13"]
                        raw=rsp.command(f"m{sp:x},24")
                        if not raw.startswith("E"):
                            record=bytes.fromhex(raw)
                            hit["bios_event_type"]=int.from_bytes(record[0:2],"little")
                            hit["bios_event_subtype"]=int.from_bytes(record[2:4],"little")
                            hit["bios_key_code"]=hex(int.from_bytes(record[8:10],"little"))
                            hit["bios_event_status"]=int.from_bytes(record[0x1c:0x20],"little")
                            hit["genuine_key_down"]=(
                                hit["bios_event_type"]==2 and
                                hit["bios_event_subtype"]==1)
                    if tid==1 and pc in (0x60011860,0x60011a30,
                                           0x60011250,0x60011ca4,
                                           0x6001d93c,0x6001d94c):
                        hit["original_sim0_start_selector"]=qmp.hmp(
                            "xp /1wx 0x410a3064")[:220]
                        hit["original_ram_start_selector"]=qmp.hmp(
                            "xp /1wx 0x6232e33c")[:220]
                        hit["original_ipc_slot"]=qmp.hmp(
                            "xp /6wx 0x2f028000")[:400]
                    if tid==1 and pc==0x601782c8:
                        # Service is in R1, not R0. Preserve the authentic
                        # shared slot at submission without fabricating ACKs.
                        hit["original_ipc_service"]=hex(registers["r1"])
                        hit["ipc_shared_slot_at_entry"]=qmp.hmp(
                            "xp /6wx 0x2f028000")[:450]
                    events.append(hit)
                    print("HIT",hit,flush=True)
                    if pc==0x60010898 and not ready:
                        voltage(pa,PTA_READY);voltage(pb,PTB_READY)
                        ready=True
                        events.append({"event":"external_input_ready"})
                    if pc==0x600108a8:
                        if args.startup_chord and matrix_file is not None:
                            voltage(matrix_file, 0)
                            events.append({"event":"original_startup_chord_released",
                                           "codes":args.startup_chord})
                        if not saved:
                            err=qmp.hmp("savevm "+args.tag)
                            if err.strip() or args.tag not in qmp.hmp("info snapshots"):
                                raise RuntimeError("VM checkpoint failed: "+err)
                            events.append({"event":"snapshot_saved","pc":hex(pc)})
                            print("SAVED VM CHECKPOINT",overlay,flush=True)
                            saved=True
                        if sender is None and args.keys:
                            def after_startup_chord():
                                if args.startup_chord:
                                    time.sleep(args.startup_release_delay)
                                pulse(args.keys,pa,pb,args.hold,args.gap,
                                      events,matrix_file)
                            sender=threading.Thread(target=after_startup_chord,
                                                    daemon=True)
                            sender.start()
                    if pc==0x6003a878:
                        result["factory_menu_observed"]=True
                        if not qmp.hmp("savevm factory-menu").strip():
                            events.append({"event":"factory_menu_snapshot_saved"})
                        break
                    if pc not in marks:
                        break
                    if rsp.command(f"z0,{pc:x},{2 if pc in M4 else 4}")!="OK":
                        raise RuntimeError("Cannot disarm breakpoint")
                    counts[pc]=counts.get(pc,0)+1
                    # Re-arm the two original A7 event breakpoints. A
                    # status-5 timer event is NOT a keyboard press;
                    # the initial one-shot debugger missed later input.
                    if tid==2 and args.trace_m4 and pc in (
                        0x1ffd838a,0x1ffd874a,0x1ffde672,
                        0x1ffde74a,0x1ffe0cce,
                        0x1ffd7d2e,0x1ffd53ba,0x1ffd7d5a,
                        0x1ffd8088,0x1ffd809e,0x1ffd7fa0,0x1ffd7b42,
                        0x1ffd7b0c,0x1ffd7b28,0x1ffd7b2e,
                        0x1ffd7fb0,0x1ffd7fca,0x1ffd8634,
                        0x1ffd8412,0x1ffd8564,0x1ffd85c6,
                        0x1ffd8610,0x1ffed3b0) and counts[pc]<32:
                        # A repeatable scan cycle needs multiple original
                        # Thumb breakpoint samples. Step once then rearm.
                        gdb.sendall(encode_packet("s"))
                        if stopped_thread(rsp.receive(4))!=2:
                            raise RuntimeError("M4 scanner single-step failed")
                        if rsp.command(f"Z0,{pc:x},2")!="OK":
                            raise RuntimeError("Could not re-arm M4 task breakpoint")
                    if tid==1 and pc in (0x601782c8,0x60008cbc,0x600108b4,0x600108cc,
                                          0x60010910,0x60010928) and counts[pc]<100:
                        gdb.sendall(encode_packet("s"))
                        if stopped_thread(rsp.receive(4))!=1:
                            raise RuntimeError("A7 event inspection single-step failed")
                        if rsp.command(f"Z0,{pc:x},4")!="OK":
                            raise RuntimeError("Could not re-arm original event breakpoint")
                    if pc==0x60010898 and counts[pc]<12:
                        gdb.sendall(encode_packet("s"))
                        if stopped_thread(rsp.receive(4))!=1:
                            raise RuntimeError("A7 single-step failed")
                        if rsp.command(f"Z0,{pc:x},4")!="OK":
                            raise RuntimeError("A7 rearm failed")
                    if tid==2:
                        rsp.command("Hg1")
                    gdb.sendall(encode_packet("c"))
                    # QMP savevm/loadvm may preserve QEMU debug runstate.
                    if not qmp.execute("query-status")["running"]:
                        qmp.execute("cont")
                if not saved:
                    # An absent snapshot is not a missing key event. Preserve
                    # independent CPU state to distinguish pre-dialog boot
                    # divergence from a genuine factory-menu IPC stall.
                    qmp.execute("stop")
                    result["cold_start_cpu_state"]={}
                    for cpu,name in ((0,"a7"),(1,"m4")):
                        output=qmp.execute("human-monitor-command",{
                            "command-line":"info registers",
                            "cpu-index":cpu})
                        result["cold_start_cpu_state"][name]=str(output)[:2000]
                    result["cold_start_ipc_request"]=qmp.hmp(
                        "xp /6wx 0x2f028000")[:600]
                    result["cold_start_original_mode_selector"]=qmp.hmp(
                        "xp /1wx 0x6232e33c")[:250]
                    result["cold_start_mua_status"]=qmp.hmp(
                        "xp /2wx 0x41022060")[:300]
                    result["cold_start_mub_status"]=qmp.hmp(
                        "xp /2wx 0x40220060")[:300]
                result["startup_chord_main_observed"]=any(
                    e.get("pc")==hex(0x60011ca4) for e in events)
                result["startup_chord_primary_check_observed"]=any(
                    e.get("pc")==hex(0x6001d93c) for e in events)
                result["startup_chord_secondary_check_observed"]=any(
                    e.get("pc")==hex(0x6001d94c) for e in events)
                result["saved_checkpoint"]=saved
                result["event_reader_seen"]=any(
                    e.get("pc")==hex(0x600108b4) for e in events)
        finally:
            if gdb:
                gdb.close()
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=8)
            result["elapsed_seconds"]=round(time.monotonic()-started,2)
            (dest/"factory-menu-probe.json").write_text(json.dumps(result,indent=2)+"\n")
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("osup",type=Path,help="Original private OSUP.BIN")
    parser.add_argument("--lptmr-irq",action="store_true",help="Opt-in M4 LPTMR0/1 NVIC compare interrupts")
    parser.add_argument("--tpm0-irq",action="store_true",
                        help="Enable guest-register driven M4 TPM0 overflow IRQ38 for real keyboard debounce")
    parser.add_argument("--port-irq",action="store_true",help="Opt-in register-driven M4 PCTLA/PCTLB NVIC IRQ56/57 from external GPIO pin voltage changes")
    parser.add_argument("--qemu",type=Path,default=Path("build/qemu-system-arm"))
    parser.add_argument("--profile",type=Path,default=Path("profiles/imx7ulp-early-boot.ini"))
    parser.add_argument("--output-dir",type=Path,default=Path("private/factory-menu"))
    parser.add_argument("--seconds",type=float,default=90)
    parser.add_argument("--keys",default="0x93,0x93,0x94")
    parser.add_argument("--hold",type=float,default=.7)
    parser.add_argument("--gap",type=float,default=.6)
    parser.add_argument("--tag",default="version-event-wait")
    parser.add_argument("--resume",action="store_true")
    parser.add_argument("--contact-delay",type=float,default=None,
                        help="Diagnostic physical-key probe after N host seconds, even if A7 event-wait never occurs; no mailbox injection")
    parser.add_argument("--startup-chord",
                        choices=["0x9c,0x90","0x80,0x95,0x92","0x80,0x90,0x96"],
                        help="Close genuine M4 0x9c+0x90 CA05 chord (or later A7 triple-key chord) before cold boot; release at event wait")
    parser.add_argument("--startup-release-delay",type=float,default=0.08,
                        help="Time between releasing startup chord and sending version-dialog keys")
    parser.add_argument("--trace-m4",action="store_true")
    parser.add_argument("--matrix-keys",action="store_true",
                        help="Drive opt-in real M4 row-gated keyboard matrix contacts, not bare GPIO columns")
    args=parser.parse_args()
    args.keys=[int(x.strip(),0) for x in args.keys.split(",") if x.strip()]
    if not all(k in PINS for k in args.keys):
        parser.error("Only mapped candidate column codes 0x93,0x94,0x95,0x80 allowed")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,32}",args.tag):
        parser.error("Snapshot tag must be ASCII alphanumeric/underscore/hyphen")
    if args.startup_chord and (not args.matrix_keys or args.resume):
        parser.error("--startup-chord requires --matrix-keys and cold boot (no --resume)")
    if args.startup_release_delay < 0:
        parser.error("--startup-release-delay must be nonnegative")
    if args.seconds<=0 or args.hold<=0 or args.gap<0:
        parser.error("Invalid timing")
    result=run(args)
    print(json.dumps({k:v for k,v in result.items() if k!="events"},indent=2))


if __name__=="__main__":
    main()
