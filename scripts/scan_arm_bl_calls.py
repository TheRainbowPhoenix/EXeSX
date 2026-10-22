#!/usr/bin/env python3
"""Metadata-only direct ARM BL callsite scanner for a local owner-held ELF32."""
import argparse
import json
import struct
from pathlib import Path


def scan(source, targets):
    if source[:6] != b"\x7fELF\x01\x01":
        raise ValueError("Requires little-endian ELF32")
    h = struct.unpack_from("<16sHHIIIIIHHHHHH", source)
    if h[2] != 40:
        raise ValueError("Requires ARM")
    offset, entsize, count = h[5], h[9], h[10]
    found = {f"0x{t:08x}": [] for t in targets}
    for i in range(count):
        kind, start, vaddr, _, filesz, _, _, _ = struct.unpack_from(
            "<8I", source, offset + i * entsize)
        if kind != 1:
            continue
        for delta in range(0, filesz - 3, 4):
            op = struct.unpack_from("<I", source, start + delta)[0]
            if op & 0x0f000000 != 0x0b000000:
                continue
            disp = op & 0xffffff
            if disp & 0x800000:
                disp -= 0x1000000
            addr = vaddr + delta
            target = addr + 8 + disp * 4
            if target in targets:
                found[f"0x{target:08x}"].append(f"0x{addr:08x}")
    return found


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("private_elf", type=Path)
    p.add_argument("--target", action="append", type=lambda v:int(v, 0),
                   required=True)
    args = p.parse_args()
    print(json.dumps(scan(args.private_elf.read_bytes(),
                          set(args.target)), indent=2))


if __name__ == "__main__":
    main()
