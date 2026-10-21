#!/usr/bin/env python3
"""Firmware-free i.MX7ULP DMA1 TCD and original DY357 BIOS PC analyzer.

Inputs are local, user-owned ARM ELF and a QEMU-monitor text capture.
Never uploads the ELF, proprietary bytes, memory dumps, or sector data.
Uses stdlib; llvm-objdump is optional for the BIOS disassembly.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import re
import struct
import subprocess
import json

DMA1 = 0x40080000
TCD_BASE = DMA1 + 0x1000
STRIDE = 32
BIOS_PC = 0x601B82B8
FIELDS = ("SADDR", "SOFF_ATTR", "NBYTES", "SLAST",
          "DADDR", "DOFF_CITER", "DLAST_SGA", "CSR_BITER")

def parse_monitor(text):
    """Parse 'xp /1wx ADDRESS' lines including 64-bit zero-padded addresses."""
    ansi = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
    clean = ansi.sub("", text)
    return {int(addr, 16): int(value, 16) for addr, value in
            re.findall(r"(?im)^\s*(?:0x)?([0-9a-f]{8,16}):\s+0x([0-9a-f]{8})\b", clean)}

def decode_tcd(regs, channel):
    if not 0 <= channel <= 31:
        raise ValueError("DMA1 has 32 TCD channels")
    base = TCD_BASE + channel * STRIDE
    missing = [base + off for off in range(0, 32, 4) if base + off not in regs]
    if missing:
        raise ValueError("Need 8 TCD words; missing " +
                         ", ".join(f"0x{addr:08x}" for addr in missing))
    v = [regs[base + off] for off in range(0, 32, 4)]
    csr = v[7] & 0xffff
    citer = (v[5] >> 16) & 0xffff
    biter = (v[7] >> 16) & 0xffff
    return dict(channel=channel, base=f"0x{base:08x}",
                words={k: f"0x{x:08x}" for k, x in zip(FIELDS, v)},
                source=f"0x{v[0]:08x}", destination=f"0x{v[4]:08x}",
                source_offset=struct.unpack("<h", struct.pack("<H", v[1]&0xffff))[0],
                dest_offset=struct.unpack("<h", struct.pack("<H", v[5]&0xffff))[0],
                attr=f"0x{v[1]>>16:04x}", minor_bytes=v[2],
                citer=citer, biter=biter, csr=f"0x{csr:04x}",
                start=bool(csr & 1), interrupt_major=bool(csr & 2),
                disable_request=bool(csr & 8), scatter_gather=bool(csr & 16),
                active=bool(csr & 64), done=bool(csr & 128),
                ram_to_ram_candidate=(0x60000000 <= v[0] < 0x70000000 and
                                       0x60000000 <= v[4] < 0x70000000))

def disassemble(path, start=0x601b8090, end=0x601b8540):
    if not path:
        return None
    args = ["llvm-objdump", "-d", f"--start-address={start:#x}",
            f"--stop-address={end:#x}", str(path)]
    r = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       text=True, check=False)
    return r.stdout if r.returncode == 0 else (
        "llvm-objdump unavailable or failed: " + r.stderr[:500])

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("monitor",type=Path,help="local QEMU monitor xp output")
    parser.add_argument("--channel",type=int,default=15)
    parser.add_argument("--elf",type=Path,help="private OSUP-derived A7 ELF, local only")
    parser.add_argument("--json",type=Path,help="write decoded register metadata (no firmware)")
    args=parser.parse_args()
    regs=parse_monitor(args.monitor.read_text(errors="replace"))
    details=decode_tcd(regs,args.channel)
    if args.json:
        args.json.write_text(json.dumps(details,indent=2)+"\n")
    print(json.dumps(details,indent=2))
    if args.elf:
        print(disassemble(args.elf))

if __name__=="__main__":
    main()
