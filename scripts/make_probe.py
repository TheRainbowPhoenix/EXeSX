#!/usr/bin/env python3
"""Build firmware-free ARMv7-A ELF proving real QEMU CP15 execution."""
from pathlib import Path
import struct
import sys

BASE = 0x60000000
WORDS = [
    0xee112f10,  # mrc p15,0,r2,c1,c0,0
    0xe3c22001,  # bic r2,r2,#1 (MMU off)
    0xee012f10,  # mcr p15,0,r2,c1,c0,0
    0xf57ff04f,  # dsb sy
    0xf57ff06f,  # isb sy
    0xe59f3010,  # ldr r3, [pc,#16] -> RAM address at 0x2c
    0xe59f0010,  # ldr r0, [pc,#16] -> marker at 0x30
    0xe5830000,  # str r0,[r3]
    0xee111f10,  # mrc p15,0,r1,c1,c0,0
    0xe5831004,  # str r1,[r3,#4]
    0xeafffffe,  # infinite loop
    0x62000000,  # guest physical RAM destination
    0x45585358,  # probe marker
]

def create_elf():
    raw = struct.pack("<%dI" % len(WORDS), *WORDS)
    ident = b"\x7fELF\x01\x01\x01" + bytes(9)
    header = struct.pack("<16sHHIIIIIHHHHHH", ident, 2, 40, 1,
                         BASE, 52, 0, 0x05000000, 52, 32, 1, 0, 0, 0)
    ph = struct.pack("<8I", 1, 0x100, BASE, BASE,
                     len(raw), len(raw), 5, 0x100)
    return header + ph + bytes(0x100 - len(header) - len(ph)) + raw

if __name__ == "__main__":
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "build/cp15-probe.elf")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(create_elf())
    print(path)
