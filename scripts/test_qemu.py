#!/usr/bin/env python3
"""Run firmware-free A7 CP15 probe in QEMU and read guest RAM via monitor."""
import os
from pathlib import Path
import re
import subprocess
import sys
import time

root = Path(__file__).resolve().parents[1]
qemu = root / "build/qemu-system-arm"
elf = root / "build/cp15-probe.elf"
cmd = [str(qemu), "-machine", "exesx", "-m", "64M", "-accel", "tcg",
       "-display", "none", "-serial", "none", "-monitor", "stdio",
       "-no-reboot", "-device", f"loader,file={elf},cpu-num=0"]
p = subprocess.Popen(cmd, cwd=root, stdin=subprocess.PIPE,
                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                     text=True, bufsize=1)
try:
    # Poll the monitor; guest writes the marker and CP15 read-back to RAM.
    # stdout is not assumed to have a complete line, use communicate with quit.
    time.sleep(1.5)
    output, _ = p.communicate("xp /2wx 0x62000000\nquit\n", timeout=12)
    print(output)
    if "0x45585358" not in output.lower():
        raise AssertionError("Guest marker missing; QEMU privileged startup did not complete")
    # The second value is the actual guest CP15 SCTLR read-back.
    if not re.search(r"0x45585358\\s+0x[0-9a-fA-F]{8}", output, re.I):
        raise AssertionError("Missing SCTLR read-back")
    print("PASS: real QEMU guest executed CP15 MRC/MCR, DSB/ISB and RAM store")
finally:
    if p.poll() is None:
        p.kill()
        p.wait()
