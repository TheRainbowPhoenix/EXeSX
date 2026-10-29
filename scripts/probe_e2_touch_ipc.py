#!/usr/bin/env python3
"""Firmware-free safety checks for debugger-assisted original touch IPC."""
import tempfile
from pathlib import Path

from e2_original_touch_ipc import (
    FUNC, MARKER, rewrite_regs, wait_for_original_e2,
)
from probe_postdma_handoff import decode_registers
from factory_control_panel import e2_debug_options
from drive_e2_cross import genuine_e2_exit_contact


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
    assert e2_debug_options({}) == ("none", [], "exec")
    hmp, gdb, trace = e2_debug_options({
        "EXESX_E2_GDB_PORT": "27871",
        "EXESX_E2_HMP_PORT": "27872",
        "EXESX_E2_TRACE_I2C": "1",
    })
    assert hmp == "tcp:127.0.0.1:27872,server=on,wait=off"
    assert gdb == ["-gdb", "tcp:127.0.0.1:27871"]
    assert trace == "exec,guest_errors,unimp"
    for invalid in ("27871x", "0", "65536", "-1"):
        try:
            e2_debug_options({"EXESX_E2_GDB_PORT": invalid})
        except ValueError:
            pass
        else:
            raise AssertionError("Unsafe debugger port accepted: " + invalid)
    try:
        e2_debug_options({
            "EXESX_E2_GDB_PORT": "27871", "EXESX_E2_HMP_PORT": "27871",
        })
    except ValueError:
        pass
    else:
        raise AssertionError("Overlapping HMP/GDB ports accepted")
    class FakeContact:
        def __init__(self):
            self.writes = []
        def write_text(self, value, encoding):
            self.writes.append((value, encoding))
    c = FakeContact()
    duration = []
    genuine_e2_exit_contact(c, .06, sleeper=duration.append)
    assert c.writes == [("0x94\n", "ascii"), ("0\n", "ascii")]
    assert duration == [.06]
    print("PASS E2 original 0x180C: A7 call target, arm/disarm arg,"
          " register preservation, return-PC validation, E2 gate")


if __name__ == "__main__":
    main()
