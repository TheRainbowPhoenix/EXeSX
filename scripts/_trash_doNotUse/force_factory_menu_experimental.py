#!/usr/bin/env python3
"""EXPERIMENTAL: enter the ORIGINAL A7 test menu via GDB at a running checkpoint.

This is NOT natural factory entry. Original ROM code and LCD renderer execute,
but A7 PC is redirected to 0x6003A878 and 0x6002D5D0 is skipped if hit.
No firmware bytes, checkpoint, or eMMC image are distributed.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bundle", type=Path, required=True, help="Unpacked native EXeSX archive containing qemu-system-arm, lib/ and probe_postdma_handoff.py")
    p.add_argument("--elf", type=Path, required=True, help="Locally reconstructed owner-held A7 BIOS/OS ELF")
    p.add_argument("--checkpoint", type=Path, required=True, help="Owner-held qcow2 checkpoint, with eMMC backing path accessible")
    p.add_argument("--profile", type=Path, required=True, help="Early-boot memory profile including LCD window")
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--prelude-seconds", type=float, default=8)
    p.add_argument("--trace-seconds", type=float, default=13)
    p.add_argument("--tpm0-mhz", type=int, default=48)
    a = p.parse_args()
    sys.path.insert(0, str(a.bundle.resolve()))
    from probe_postdma_handoff import RSP, encode_packet, decode_registers, choose_port
    from drive_factory_menu import connect, QMP

    out = a.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    for path in (a.elf, a.checkpoint, a.profile, a.bundle / "qemu-system-arm"):
        if not path.is_file():
            p.error(f"Missing required input: {path}")
    disk = out / "disk.qcow2"
    shutil.copy2(a.checkpoint, disk)
    (out / "key.txt").write_text("0x80,0x95,0x92\n")
    env = os.environ.copy()
    env.update(
        EXESX_MEMORY_PROFILE=str(a.profile.resolve()),
        EXESX_EXPERIMENTAL_M4_BOOT="1",
        EXESX_EXPERIMENTAL_MU_IRQ="1",
        EXESX_EXPERIMENTAL_LPIT1_IRQ="1",
        EXESX_EXPERIMENTAL_LPTMR_IRQ="1",
        EXESX_EXPERIMENTAL_LPTMR_PCS_CLOCKS="1",
        EXESX_EXPERIMENTAL_M4_PORT_IRQ="1",
        EXESX_EXPERIMENTAL_M4_TPM0_IRQ="1",
        EXESX_EXPERIMENTAL_M4_TPM0_INPUT_MHZ=str(a.tpm0_mhz),
        EXESX_DIAGNOSTIC_A7_TPM6_KHZ="32",
        EXESX_EXPERIMENTAL_LCD="1",
        EXESX_EXPERIMENTAL_DMA1_M2M="1",
        EXESX_USDHC1_EMMC="1",
        EXESX_I2C4B_REGISTER_MIRROR="1",
        EXESX_I2C40_REGISTER_MIRROR="1",
        EXESX_GPIOA_INPUT_MASK="0x808c6008",
        EXESX_GPIOB_INPUT_MASK="0xc8",
        EXESX_M4_KEY_MATRIX_FILE=str(out / "key.txt"),
        EXESX_LCD_SCREENSHOT=str(out / "test-menu.ppm"),
        LD_LIBRARY_PATH=str((a.bundle / "lib").resolve()) + os.pathsep + env.get("LD_LIBRARY_PATH", ""),
    )
    gp, qp = choose_port(), choose_port()
    cmd = [
        str((a.bundle / "qemu-system-arm").resolve()),
        "-machine", "exesx", "-m", "64M", "-accel", "tcg", "-display", "none",
        "-serial", "none", "-monitor", "none", "-no-reboot",
        "-drive", f"if=none,id=exesx-emmc,file={disk},format=qcow2",
        "-device", f"loader,file={a.elf.resolve()},cpu-num=0",
        "-S", "-gdb", f"tcp:127.0.0.1:{gp}",
        "-qmp", f"tcp:127.0.0.1:{qp},server=on,wait=off",
        "-d", "guest_errors,unimp", "-D", str(out / "qemu.log"),
    ]
    breakpoints = [
        0x6003A878, 0x6003A7D4, 0x6000FF90, 0x60008E28,
        0x60008EC0, 0x6002D5D0, 0x6000FEE8, 0x6004CE6C,
        0x6004DEE0, 0x6001EC84, 0x6003A890, 0x6001D49C,
        0x600516F8, 0x60048218, 0x60057550, 0x60057668,
        0x60057720,
    ]
    report = {"mode": "EXPERIMENTAL forced PC+init bypass, not natural cold boot",
              "interventions": ["set A7 PC=0x6003a878", "skip 0x6002d5d0 by return to LR"],
              "hits": []}
    with (out / "console.log").open("w") as log:
        proc = subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            with connect(gp, proc) as gs, connect(qp, proc) as qs:
                rsp = RSP(gs)
                q = QMP(qs)
                rsp.command("?")
                rsp.command("Hg1")
                rsp.command("Hc-1")
                gs.sendall(encode_packet("c"))
                time.sleep(a.prelude_seconds)
                gs.sendall(b"\x03")
                rsp.receive(5)
                rsp.command("Hg1")
                regs = decode_registers(rsp.command("g"))
                report["before_pc"] = hex(regs["r15"])
                rsp.command("Pf=" + struct.pack("<I", 0x6003A878).hex())
                for pc in breakpoints:
                    rsp.command(f"Z0,{pc:x},4")
                gs.sendall(encode_packet("c"))
                deadline = time.monotonic() + a.trace_seconds
                while time.monotonic() < deadline:
                    try:
                        rsp.receive(1)
                    except TimeoutError:
                        continue
                    rsp.command("Hg1")
                    r = decode_registers(rsp.command("g"))
                    pc = r["r15"]
                    report["hits"].append({"pc": hex(pc), "lr": hex(r["r14"]),
                                           "sp": hex(r["r13"])})
                    rsp.command(f"z0,{pc:x},4")
                    if pc == 0x6002D5D0:
                        rsp.command("Pf=" + struct.pack("<I", r["r14"]).hex())
                    gs.sendall(encode_packet("c"))
                gs.sendall(b"\x03")
                try:
                    rsp.receive(3)
                    rsp.command("Hg1")
                    r = decode_registers(rsp.command("g"))
                    report["final_pc"] = hex(r["r15"])
                except (TimeoutError, OSError):
                    pass
        finally:
            proc.kill()
            proc.wait()
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    hits = {int(h["pc"], 16) for h in report["hits"]}
    print("Original renderer reached:", {hex(x): x in hits for x in (0x60057550, 0x60057668, 0x60057720)})
    print("Diagnostic artifacts:", out)

if __name__ == "__main__":
    main()
