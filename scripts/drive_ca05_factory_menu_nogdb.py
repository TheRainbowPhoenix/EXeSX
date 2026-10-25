#!/usr/bin/env python3
"""Reproduce the genuine DY357 factory-menu entry without GDB or guest patching.

Owner-owned OSUP-derived ELF and synthetic eMMC/SD remain private.
Host writes only opt-in electrical matrix contacts; original guest scans,
debounces, dispatches and decides whether to branch to the TEST MENU.
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import subprocess
import time

# Original ROM, not hardcoded key-event injection:
BOOT_CHORD = "0x9c,0x90"  # M4 early boot checks these simultaneously -> CA05
DIALOG_KEYS = ("0x93", "0x93", "0x94")  # Later A7 type2/subtype1 key events
CHECKPOINTS = {
    "ca05_setter": 0x6001EE68,
    "version_dialog": 0x60010868,
    "dialog_event_wait": 0x600108A8,
    "key93_check": 0x60010910,
    "key94_check": 0x60010928,
    "key94_success": 0x60010930,
    "factory_menu": 0x6003A878,
    "menu_service_400b": 0x60006240,
    "menu_service_return": 0x60006268,
    "menu_paint": 0x60057668,
}
TB_PATTERN = re.compile(r"^Trace \d+:.*?/00000000([0-9a-fA-F]{8})/", re.M)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("qemu", "elf", "emmc", "profile", "output-dir"):
        p.add_argument("--" + name, required=True, type=Path)
    p.add_argument("--sd", type=Path, help="Optional disposable >=2GiB raw SD; snapshot=on")
    p.add_argument("--seconds", type=float, default=35)
    p.add_argument("--release-at", type=float, default=1.2,
                   help="Host seconds after boot; M4 chord must already have been read")
    p.add_argument("--hold", type=float, default=.060)
    p.add_argument("--gap", type=float, default=.025)
    p.add_argument("--post-menu", type=float, default=0,
                   help="Additional guest running time to observe service/paint after menu entry")
    args = p.parse_args()
    if args.seconds <= 0 or args.release_at < 0 or args.hold <= 0 or args.gap < 0 or args.post_menu < 0:
        p.error("Invalid timing")
    required = [args.qemu, args.elf, args.emmc, args.profile] + ([args.sd] if args.sd else [])
    for path in required:
        if not path.is_file():
            p.error("Missing private input " + str(path))

    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    keyfile = out / "m4-physical-contacts-private.txt"
    keyfile.write_text(BOOT_CHORD + "\n", encoding="ascii")

    env = os.environ.copy()
    env.update({
        "EXESX_MEMORY_PROFILE": str(args.profile.resolve()),
        "EXESX_EXPERIMENTAL_M4_BOOT": "1",
        "EXESX_EXPERIMENTAL_MU_IRQ": "1",
        "EXESX_EXPERIMENTAL_LPIT1_IRQ": "1",
        "EXESX_EXPERIMENTAL_LPTMR_IRQ": "1",
        "EXESX_EXPERIMENTAL_LPTMR_PCS_CLOCKS": "1",
        "EXESX_EXPERIMENTAL_M4_PORT_IRQ": "1",
        "EXESX_EXPERIMENTAL_M4_TPM0_IRQ": "1",
        "EXESX_EXPERIMENTAL_M4_TPM0_INPUT_MHZ": "48",
        "EXESX_DIAGNOSTIC_A7_TPM6_KHZ": "32",
        "EXESX_EXPERIMENTAL_LCD": "1",
        "EXESX_EXPERIMENTAL_DMA1_M2M": "1",
        "EXESX_USDHC1_EMMC": "1",
        "EXESX_USDHC0_SD": "1" if args.sd else "0",
        "EXESX_USDHC0_SD_DETECT_GPIO": "1" if args.sd else "0",
        "EXESX_I2C4B_REGISTER_MIRROR": "1",
        "EXESX_I2C40_REGISTER_MIRROR": "1",
        "EXESX_SNVS_DIAGNOSTIC_SECURITY_PULSES": "1",
        "EXESX_GPIOA_INPUT_MASK": "0x808c6008",
        "EXESX_GPIOB_INPUT_MASK": "0xc8",
        "EXESX_M4_KEY_MATRIX_FILE": str(keyfile),
    })
    lib = args.qemu.resolve().parent / "lib"
    if lib.is_dir():
        env["LD_LIBRARY_PATH"] = str(lib) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    trace = out / "original-execution-private.log"
    command = [
        str(args.qemu.resolve()), "-machine", "exesx", "-m", "64M",
        "-accel", "tcg", "-display", "none", "-serial", "none",
        "-monitor", "none", "-no-reboot",
        "-drive", f"if=none,id=exesx-emmc,file={args.emmc.resolve()},format=raw,snapshot=on",
        "-device", f"loader,file={args.elf.resolve()},cpu-num=0",
        "-d", "exec", "-dfilter",
        ("0x60048e08+0x40,0x60010868+0x130,0x6003a878+0x400,"
         "0x60057668+0x20,0x60006240+0x40,0x601786c8+0x20,"
         "0x6001ee68+0x20"),
        "-D", str(trace),
    ]
    if args.sd:
        command.extend(["-drive", f"if=none,id=exesx-sd,file={args.sd.resolve()},format=raw,snapshot=on"])
    report = {
        "inputs": {"boot_chord": BOOT_CHORD, "dialog_keys": list(DIALOG_KEYS),
                   "hold": args.hold, "gap": args.gap},
        "physical_contacts": [], "checkpoints": {},
        "a7_menu_executed": False, "menu_paint_executed": False,
        "method": "original-ROM executed TBs; no GDB or guest patch",
    }
    t0 = time.monotonic()
    released = False
    sent = False
    menu_time = None
    observed = set()
    with (out / "console-private.log").open("w") as log:
        proc = subprocess.Popen(command, env=env, stdout=log,
                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        try:
            while not trace.exists() and time.monotonic() - t0 < 5 and proc.poll() is None:
                time.sleep(.025)
            with trace.open("r", errors="replace") as stream:
                tail = ""
                while time.monotonic() - t0 < args.seconds and proc.poll() is None:
                    now = time.monotonic() - t0
                    if not released and now >= args.release_at:
                        keyfile.write_text("0\n", encoding="ascii")
                        report["physical_contacts"].append({"t": round(now, 3), "action": "release early chord"})
                        released = True
                    tail = (tail + stream.read())[-8192:]
                    for label, pc in CHECKPOINTS.items():
                        if label not in observed and re.search(
                                rf"/00000000{pc:08x}/", tail, re.I):
                            observed.add(label)
                            report["checkpoints"][label] = round(now, 3)
                            print("OBSERVED", label, round(now, 3), flush=True)
                            if label == "factory_menu":
                                menu_time = time.monotonic()
                    if "dialog_event_wait" in observed and not sent:
                        sent = True
                        for code in DIALOG_KEYS:
                            keyfile.write_text(code + "\n", encoding="ascii")
                            report["physical_contacts"].append(
                                {"t": round(time.monotonic() - t0, 3), "action": "press", "key": code})
                            time.sleep(args.hold)
                            keyfile.write_text("0\n", encoding="ascii")
                            report["physical_contacts"].append(
                                {"t": round(time.monotonic() - t0, 3), "action": "release", "key": code})
                            time.sleep(args.gap)
                    if menu_time is not None and time.monotonic() - menu_time >= args.post_menu:
                        break
                    time.sleep(.02)
        finally:
            keyfile.write_text("0\n", encoding="ascii")
            proc.kill()
            proc.wait(timeout=5)

    counts = Counter(int(pc, 16) for pc in TB_PATTERN.findall(trace.read_text(errors="replace")))
    report["guest_pc_tb_counts"] = {
        label: sum(n for pc, n in counts.items() if start <= pc < start + (4 if label != "factory_menu" else 32))
        for label, start in CHECKPOINTS.items()
    }
    report["a7_menu_executed"] = report["guest_pc_tb_counts"]["factory_menu"] > 0
    report["menu_paint_executed"] = report["guest_pc_tb_counts"]["menu_paint"] > 0
    (out / "summary-private.json").write_text(json.dumps(report, indent=2) + "\n")
    print("AUTHENTIC MENU PC:", report["a7_menu_executed"])
    print("MENU PAINT PC:", report["menu_paint_executed"])
    print("Private evidence:", out)


if __name__ == "__main__":
    main()
