#!/usr/bin/env python3
"""Firmware-free safety checks for debugger-assisted original touch IPC."""
import tempfile
from pathlib import Path

from e2_original_touch_ipc import (
    FUNC, MARKER, rewrite_regs, wait_for_original_e2,
)
from probe_postdma_handoff import decode_registers


def main():
    raw = "".join((0x10203000 + i).to_bytes(4, "little").hex()
                  for i in range(16)) + "ff" * 40
    saved = decode_registers(raw)
    call = rewrite_regs(raw, arg=0, retpc=0x601cbb90)
    updated = decode_registers(call)
    assert updated["r0"] == 0
    assert updated["r14"] == 0x601cbb90
    assert updated["r15"] == FUNC
    for reg in range(16):
        if reg not in (0, 14, 15):
            assert updated[f"r{reg}"] == saved[f"r{reg}"]
    assert call[16 * 8:] == raw[16 * 8:]
    disarm = decode_registers(rewrite_regs(raw, arg=1,
                                          retpc=0x601cbb90))
    assert disarm["r0"] == 1
    for bad in (0x4104000c, 0x601cbb92, 0x62000000):
        try:
            rewrite_regs(raw, arg=0, retpc=bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Accepted bad guest PC 0x{bad:x}")
    with tempfile.TemporaryDirectory() as td:
        log = Path(td) / "e2-runner.log"
        log.write_text(f"unrelated\n{MARKER}\n", encoding="utf-8")
        wait_for_original_e2(log, 0.01)
    print("PASS E2 original 0x180C: A7 call target, arm/disarm arg,"
          " register preservation, return-PC validation, E2 gate")


if __name__ == "__main__":
    main()
