#!/usr/bin/env python3
"""Inspect original DY357 BIOS callback gate from a privately held ARM ELF.

Output only instruction addresses, decoded pointers and branch-site evidence.
Never export firmware instructions, flash sectors, or private RAM bytes.
Fails closed on a firmware revision with different critical ARM opcodes.
"""
import argparse
import json
import struct
from pathlib import Path

GATE_OPCODES = {
    0x60049be8: 0xe5911000,  # LDR R1,[R1] (ready bit owner)
    0x60049bec: 0xe3110002,  # TST R1,#2
    0x60049bf0: 0x0a000006,  # BEQ return-zero
    0x60049bf8: 0xe3510000,  # CMP R1,#0 (callback installed?)
    0x60049bfc: 0x0a000003,  # BEQ return-zero
    0x60049c00: 0xe5900000,  # LDR R0,[R0] (callback target)
    0x60049c04: 0xe12fff30,  # BLX R0
    0x60049c10: 0xe3a00000,  # MOV R0,#0
}
LITERALS = {
    "callback_storage": 0x6004a2ec,  # 0x622e6fbc
    "ready_structure_pointer": 0x6004a2f0,  # 0x6232d5c8
}
STARTUP_CALL_SITES = (
    0x6004a1bc, 0x6004a1c0, 0x6004a1c4,
    0x6004a1c8, 0x6004a1cc, 0x6004a1d0,
    0x6004a1d4, 0x6004a224, 0x6004a228,
    0x6004a22c, 0x6004a24c, 0x6004a2cc,
)


def read_va(elf, addr):
    if elf[:6] != b"\x7fELF\x01\x01":
        raise ValueError("Expected little-endian ELF32")
    h = struct.unpack_from("<16sHHIIIIIHHHHHH", elf)
    if h[2] != 40:
        raise ValueError("Expected ARM ELF32")
    phoff, entsize, count = h[5], h[9], h[10]
    for i in range(count):
        kind, off, va, _, n, _, _, _ = struct.unpack_from(
            "<8I", elf, phoff + i * entsize)
        if kind == 1 and va <= addr and addr + 4 <= va + n:
            return struct.unpack_from("<I", elf, off + addr - va)[0]
    raise ValueError(f"Address 0x{addr:08x} not in an ELF loadable segment")


def inspect(elf):
    for addr, opcode in GATE_OPCODES.items():
        if read_va(elf, addr) != opcode:
            raise ValueError(f"Unrecognized firmware callback gate at 0x{addr:08x}")
    ptr = {k: f"0x{read_va(elf, addr):08x}" for k, addr in LITERALS.items()}
    calls = {}
    for addr in STARTUP_CALL_SITES:
        opcode = read_va(elf, addr)
        if opcode & 0x0f000000 != 0x0b000000:
            raise ValueError(f"Expected ARM BL at 0x{addr:08x}")
        displacement = opcode & 0xffffff
        if displacement & 0x800000:
            displacement -= 0x1000000
        calls[f"0x{addr:08x}"] = f"0x{addr + 8 + displacement*4:08x}"
    return {
        "callback_gate": "0x60049bcc",
        "ready_pointer_location": ptr["ready_structure_pointer"],
        "callback_storage_location": ptr["callback_storage"],
        "ready_test_bit_mask": "0x00000002",
        "callback_callsite": "0x60049c04",
        "callback_indirect": True,
        "zero_return_when_unready_or_unregistered": True,
        "startup_direct_calls": calls,
        "warning": "Runtime callback target and bit owner require private A7 RAM watchpoints; not an authenticated OS-launch gate.",
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("private_elf", type=Path)
    args = ap.parse_args()
    print(json.dumps(inspect(args.private_elf.read_bytes()), indent=2))


if __name__ == "__main__":
    main()
