#!/usr/bin/env python3
"""Bounded local EXeSX QEMU run of your own A7 ELF, with evidence logs.
An instruction trace does not imply an OS boot; LCD/touch hardware is missing.
"""
from pathlib import Path
import argparse
import os
import json
import re
import shlex
import subprocess
import time

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("elf", type=Path)
    p.add_argument("--qemu", type=Path, default=Path("build/qemu-system-arm"))
    p.add_argument("--seconds", type=float, default=3.0)
    p.add_argument("--results", type=Path, default=Path("private/firmware-trace"))
    args = p.parse_args()
    if not args.qemu.is_file():
        p.error("QEMU executable missing: " + str(args.qemu))
    if not args.elf.is_file():
        p.error("Firmware ELF missing: " + str(args.elf))
    args.results.mkdir(parents=True, exist_ok=True)
    log = args.results / "qemu-instructions.log"
    cmd = [str(args.qemu.resolve()), "-machine", "exesx",
           "-m", "64M", "-accel", "tcg", "-display", "none",
           "-serial", "none", "-monitor", "none", "-no-reboot",
           "-device", "loader,file=" + str(args.elf.resolve()) + ",cpu-num=0",
           "-d", "in_asm,guest_errors,cpu_reset", "-D", str(log.resolve())]
    print("Experimental execution (no LCD):", shlex.join(cmd), flush=True)
    env = os.environ.copy()
    lib = args.qemu.resolve().parent / "lib"
    if lib.is_dir():
        env["LD_LIBRARY_PATH"] = str(lib) + ":" + env.get("LD_LIBRARY_PATH", "")
    started = time.monotonic()
    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, env=env, timeout=max(0.1, args.seconds))
        code, output, stopped = r.returncode, r.stdout, False
    except subprocess.TimeoutExpired as e:
        code, stopped = None, True
        output = e.stdout or b""
        if isinstance(output, bytes):
            output = output.decode(errors="replace")
    (args.results / "qemu-console.txt").write_text(output)
    trace = log.read_text(errors="replace") if log.exists() else ""
    pcs = re.findall(r"0x([0-9a-f]{8}):\s+[0-9a-f ]+\s+[^\n]+", trace, re.I)
    report = {
        "seconds_elapsed": round(time.monotonic() - started, 2),
        "timed_out": stopped,
        "process_exit_code": code,
        "trace_bytes": len(trace),
        "instruction_lines": len(pcs),
        "first_instruction_addresses": pcs[:12],
        "last_instruction_addresses": pcs[-12:],
        "firmware_boot_verified": False,
        "limitations": "No LCD, touchscreen or inter-core release controller",
    }
    (args.results / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    if output:
        print("QEMU console:", output[:2500])

if __name__ == "__main__":
    main()
