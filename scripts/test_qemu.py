#!/usr/bin/env python3
"""Run firmware-free A7 CP15 probe in QEMU and read guest RAM via monitor."""
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from hmp_memory import qmp_memory_words

root = Path(__file__).resolve().parents[1]
qemu = Path(os.environ.get("EXESX_QEMU", str(root / "build" /
            ("qemu-system-arm.exe" if os.name == "nt" else "qemu-system-arm"))))
elf = root / "build/cp15-probe.elf"
cmd = [str(qemu), "-machine", "exesx", "-m", "64M", "-accel", "tcg",
       "-display", "none", "-serial", "none", "-monitor", "stdio",
       "-no-reboot", "-device", f"loader,file={elf},cpu-num=0"]

if os.name == "nt":
    # Avoid QEMU HMP readline echo/control sequences on Windows pipes.
    # The QMP helper also spools device-profile diagnostics to a disk file.
    marker, sctlr = qmp_memory_words(cmd, os.environ.copy(), 0x62000000, 2, delay=1.5)
    if marker != 0x45585358:
        raise AssertionError(f"Guest marker missing: {marker:#x}")
    print(f"CP15 guest marker={marker:#x}, SCTLR readback={sctlr:#010x}")
else:
    p = subprocess.Popen(cmd, cwd=root, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, bufsize=1)
    try:
        time.sleep(1.5)
        output, _ = p.communicate("xp /2wx 0x62000000\nquit\n", timeout=12)
        print(output)
        if "0x45585358" not in output.lower():
            raise AssertionError("Guest marker missing; QEMU privileged startup did not complete")
        if not re.search(r"0x45585358\s+0x[0-9a-fA-F]{8}", output, re.I):
            raise AssertionError("Missing SCTLR read-back")
    finally:
        if p.poll() is None:
            p.kill()
            p.wait()

print("PASS: real QEMU guest executed CP15 MRC/MCR, DSB/ISB and RAM store")
