#!/usr/bin/env python3
"""Diagnostic only: ask the ORIGINAL A7 firmware to send touch IPC 0x180C.

With the unchanged DY357 original ROM already displaying E2, this tool
temporarily redirects the suspended A7 CPU to its existing
FUN_6001ec84(arg), returns at the interrupted original PC, restores
the original register packet, and resumes. That routine itself issues
0x180C(arg) over the original M4 IPC transport. The script does NOT
write PORTB.PCR3, fabricate touch events or alter E2 result bytes.

WARNING: This is a debugger-assisted firmware call, not unassisted
factory behavior. Use only with private, disposable snapshot-on media.
"""
import argparse
from pathlib import Path
import re
import socket
import time

from probe_postdma_handoff import RSP, decode_registers, encode_packet

FUNC = 0x6001EC84
PCR3 = 0x4104000C
MARKER = "ENTER confirmed menu row 13"


def rewrite_regs(payload, *, arg, retpc, entry=FUNC):
    """Preserve the full GDB packet, replacing ARM r0/r14/r15 only."""
    if len(payload) < 16 * 8 or len(payload) % 2:
        raise ValueError("Short/odd ARM remote register packet")
    if not 0x60000000 <= retpc <= 0x61FFFFFF or retpc & 3:
        raise ValueError("Not halted at aligned A7 BIOS code")
    result = payload
    for reg, value in ((0, arg), (14, retpc), (15, entry)):
        offset = reg * 8
        result = (result[:offset] +
                  (value & 0xFFFFFFFF).to_bytes(4, "little").hex() +
                  result[offset + 8:])
    return result


def wait_for_original_e2(log, seconds):
    if log is None:
        return
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if log.exists() and MARKER in log.read_text(
                encoding="utf-8", errors="replace"):
            return
        time.sleep(0.15)
    raise TimeoutError("Original LCD-confirmed E2 ENTER was not observed")


def invoke(gdb_port, hmp_port, arg):
    with socket.create_connection(("127.0.0.1", hmp_port), 5) as hmp:
        hmp.settimeout(3)
        hmp.recv(4096)  # QEMU HMP greeting
        hmp.sendall(b"stop\n")
        time.sleep(0.35)
        with socket.create_connection(("127.0.0.1", gdb_port), 5) as sock:
            rsp = RSP(sock)
            stopped = rsp.command("?")
            if not stopped.startswith(("T", "S")):
                raise RuntimeError("GDB did not acknowledge stopped CPU: " + stopped)
            if rsp.command("Hg1") != "OK":
                raise RuntimeError("Cannot select original Cortex-A7 CPU 1")
            saved = rsp.command("g")
            original_pc = decode_registers(saved)["r15"] & ~3
            call_regs = rewrite_regs(saved, arg=arg, retpc=original_pc)
            breakpoint = f"0,{original_pc:x},4"
            if rsp.command("Z" + breakpoint) != "OK":
                raise RuntimeError("Cannot set temporary return breakpoint")
            completed = False
            try:
                if rsp.command("G" + call_regs) != "OK":
                    raise RuntimeError("Cannot invoke original A7 routine")
                sock.sendall(encode_packet("c"))
                report = rsp.receive(25)
                if not report.startswith(("T", "S")):
                    raise RuntimeError("Original firmware did not stop: " + report)
                actual_pc = decode_registers(rsp.command("g"))["r15"] & ~3
                if actual_pc != original_pc:
                    raise RuntimeError(
                        f"Call interrupted at 0x{actual_pc:08x}, "
                        f"expected return to 0x{original_pc:08x}")
                completed = True
            finally:
                if completed:
                    rsp.command("z" + breakpoint)
                    if rsp.command("G" + saved) != "OK":
                        raise RuntimeError("Failed restoring original A7 CPU registers")
                else:
                    # Preserve a halted guest for user diagnosis instead
                    # of continuing after an incomplete/unsafe call.
                    raise RuntimeError("Original firmware call not completed; guest halted")
            if rsp.command("Hg2") != "OK":
                raise RuntimeError("Cannot select M4 CPU")
            pcr3 = rsp.memory(PCR3, 4)
            nvic_enabled = rsp.memory(0xE000E104, 4)  # M4 ISER1
            nvic_pending = rsp.memory(0xE000E204, 4)  # M4 ISPR1
            if pcr3 is None or nvic_enabled is None or nvic_pending is None:
                raise RuntimeError("Cannot inspect M4 PORTB/NVIC state")
            print(f"Original 0x180C({arg}) returned: "
                  f"PORTB.PCR3=0x{pcr3:08x}, "
                  f"M4 NVIC IRQ57 enabled="
                  f"{bool(nvic_enabled & (1 << 25))}, pending="
                  f"{bool(nvic_pending & (1 << 25))}", flush=True)
            if not (nvic_enabled & (1 << 25)):
                print("WARNING: Original M4 NVIC IRQ57 is DISABLED;"
                      " PCR3 arming alone cannot deliver pen interrupts",
                      flush=True)
            if rsp.command("Hc-1") != "OK":
                raise RuntimeError("Cannot select all CPUs for resume")
            sock.sendall(encode_packet("c"))
            return pcr3


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--gdb-port", type=int, required=True)
    p.add_argument("--hmp-port", type=int, required=True)
    p.add_argument("--e2-runner-log", type=Path)
    p.add_argument("--wait-seconds", type=float, default=150)
    p.add_argument("--command", choices=("arm", "disarm"), default="arm")
    p.add_argument("--assert-pcr3", action="store_true")
    args = p.parse_args()
    if not (0 < args.gdb_port < 65536 and 0 < args.hmp_port < 65536):
        p.error("Ports must be 1..65535")
    if args.gdb_port == args.hmp_port:
        p.error("The GDB and HMP endpoints must be distinct")
    wait_for_original_e2(args.e2_runner_log, args.wait_seconds)
    arg = 0 if args.command == "arm" else 1
    actual = invoke(args.gdb_port, args.hmp_port, arg)
    expected = 0x00080000 if arg == 0 else 0
    if args.assert_pcr3 and actual != expected:
        raise RuntimeError(f"Original command returned, but PORTB.PCR3"
                           f" 0x{actual:08x} != 0x{expected:08x}")
    print("Original firmware command delivered; E2 coverage/result not inferred")


if __name__ == "__main__":
    main()
