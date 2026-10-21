#!/usr/bin/env python3
"""Decode *actual QEMU traces* of MMC CMD6 partition switches and CMD17 reads.

This is metadata-only; does NOT make, infer, or fake boot partition sectors.
Use native QEMU -trace enable=sdhci_send_command on user-owned firmware.
"""
import argparse
import re
import json
from pathlib import Path

COMMAND = re.compile(r"sdhci_send_command\s+CMD(\d+)\s+ARG\[0x([0-9a-fA-F]+)\]")
PARTS = {0: "user", 1: "boot0", 2: "boot1", 3: "RPMB",
         4: "GP1", 5: "GP2", 6: "GP3", 7: "GP4"}

def decode(text):
    partition = 0
    records = []
    for m in COMMAND.finditer(text):
        cmd, arg = int(m[1]), int(m[2], 16)
        if cmd == 6:
            access = (arg >> 24) & 3
            index = (arg >> 16) & 0xff
            value = (arg >> 8) & 0xff
            item = dict(cmd=cmd, arg=f"0x{arg:08x}", index=index,
                        value=value, access=access)
            if access == 3 and index == 179:
                partition = value & 7
                item["selected_partition"] = PARTS[partition]
            records.append(item)
        elif cmd in (17, 18):
            records.append(dict(cmd=cmd, arg=f"0x{arg:08x}",
                                partition=PARTS[partition],
                                block_address=arg,
                                byte_offset=arg*512,
                                note="Assumes sector addressing; verify OCR high-capacity status"))
    return records

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("trace",type=Path)
    p.add_argument("--output",type=Path,help="metadata JSON; no proprietary data")
    a=p.parse_args()
    data=decode(a.trace.read_text(errors="replace"))
    out=json.dumps(data,indent=2)+"\n"
    if a.output:a.output.write_text(out)
    print(out)

if __name__=="__main__":
    main()
