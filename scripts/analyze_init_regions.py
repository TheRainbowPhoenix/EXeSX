#!/usr/bin/env python3
"""Inspect, but never execute, firmware BIOS init-table entries.

Argument: locally extracted ELF from prepare_osup.py.
No proprietary bytes are committed.
"""
import argparse
import json
import struct
from pathlib import Path

TABLE_START=0x602547EC
TABLE_END=0x602548BC  # end marker starts here, no zeroing beyond it
TARGETS=(0x61080000, 0x67100000)
# Firmware blocks, NOT independently confirmed physical RAM.
GUEST_MMU_REGIONS=[
    (0x61000000, 0x05D80000, "bios-page-table: large backing aperture"),
    (0x67100000, 0x00500000, "bios-page-table: first upper aperture"),
    (0x67600000, 0x00A00000, "bios-page-table: second upper aperture"),
]

def load_memory_image(data):
    if data[:4] != b"\x7fELF" or data[4:6] != b"\x01\x01":
        raise ValueError("expected ELF32 little-endian")
    if struct.unpack_from("<H",data,18)[0]!=40:
        raise ValueError("expected EM_ARM")
    phoff=struct.unpack_from("<I",data,28)[0]
    phentsize,phnum=struct.unpack_from("<HH",data,42)
    if phentsize<32 or phnum>24 or phoff+phentsize*phnum>len(data):
        raise ValueError("invalid program headers")
    entries=[]
    for i in range(phnum):
        p_type,p_off,vaddr,phys,sz,memsz,flags,align=struct.unpack_from("<8I",data,phoff+i*phentsize)
        if p_type!=1: continue
        if p_off+sz>len(data): raise ValueError("invalid PT_LOAD extent")
        entries.append((vaddr,data[p_off:p_off+sz]))
    def read(addr,length):
        for base,blob in entries:
            if base<=addr and addr+length<=base+len(blob):
                return blob[addr-base:addr-base+length]
        raise ValueError("address unavailable in loadable ELF: "+hex(addr))
    return read

def inspect(data):
    rd=load_memory_image(data)
    raw=rd(TABLE_START,TABLE_END-TABLE_START)
    rec=[]
    for idx in range(0,len(raw),8):
        start,size=struct.unpack_from("<II",raw,idx)
        if size==0:
            break
        if start+size>0x100000000:
            raise ValueError("wrapped initialization region")
        rec.append(dict(table_address=f"0x{TABLE_START+idx:08x}",
                        destination=f"0x{start:08x}",
                        size_bytes=size,end_exclusive=f"0x{start+size:08x}",
                        operation="write zeroes, not a device-register poll"))
    highlights=[]
    for target in TARGETS:
        matches=[r for r in rec if int(r["destination"],16)<=target<int(r["end_exclusive"],16)]
        highlights.append(dict(address=f"0x{target:08x}",matching_records=matches,
            evidence="BIOS Thumb STR r3,[r1],#4 at 0x60254714; r3=0"))
    return dict(table_start=f"0x{TABLE_START:08x}",entries=rec,
                targets=highlights,mmu_regions=[
                dict(base=f"0x{b:08x}",size_bytes=s,
                     end_exclusive=f"0x{b+s:08x}",source=description)
                for b,s,description in GUEST_MMU_REGIONS],
                caveat="Addresses and extents do not identify the physical chip or prove full device RAM size")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("elf",type=Path)
    p.add_argument("--json",type=Path)
    args=p.parse_args()
    result=inspect(args.elf.read_bytes())
    output=json.dumps(result,indent=2)
    if args.json: args.json.write_text(output+"\n")
    print(output)

if __name__=="__main__":
    main()
