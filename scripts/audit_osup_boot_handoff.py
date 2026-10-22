#!/usr/bin/env python3
"""Report real SD/MMC command sequence, ROM execution ranges and A7 idle sites.

Input: privately captured native-QEMU text log (trace sdhci_send_command
and -d in_asm). Output: metadata only. This neither publishes private
firmware bytes nor infers successful OS boot from a static ELF section.
"""
import argparse
import json
import re
from collections import Counter
from pathlib import Path

CMD = re.compile(r"sdhci_send_command CMD(\d+) ARG\[0x([0-9a-fA-F]+)\]")
TB = re.compile(r"(?m)^0x([0-9a-fA-F]{8}):\s*$")
PARTITIONS = {0:"user",1:"boot0",2:"boot1",3:"RPMB",
              4:"GP1",5:"GP2",6:"GP3",7:"GP4"}
OS_START = 0x60400000
OS_END = 0x60400000 + 8923136
OS_ENTRY = 0x605e3ad0
BIOS_IDLE = {0x601cbcf0, 0x601cbcf4, 0x601cbcf8}


def audit(text):
    current = "user"
    commands = []
    reads = []
    for found in CMD.finditer(text):
        cmd, arg = int(found[1]), int(found[2],16)
        item = {"cmd":cmd, "argument":f"0x{arg:08x}"}
        if cmd == 6 and (arg >> 24) & 3 == 3 and (arg >> 16) & 255 == 179:
            current = PARTITIONS[arg >> 8 & 7]
            item["partition_access"] = current
        if cmd in (17,18):
            item["partition"] = current
            item["lba"] = arg
            reads.append({"cmd":cmd,"partition":current,"lba":arg})
        commands.append(item)
    pcs = [int(x,16) for x in TB.findall(text)]
    in_os = [x for x in pcs if OS_START <= x < OS_END]
    io = [x for x in pcs if x in BIOS_IDLE]
    return {
        "card_commands":commands,
        "read_lbas":reads,
        "translated_blocks":len(pcs),
        "distinct_translated_blocks":len(set(pcs)),
        "translated_in_os_region":len(in_os),
        "os_entry_translation_observed":OS_ENTRY in pcs,
        "bios_idle_sites_seen":[hex(x) for x in sorted(set(io))],
        "translation_is_not_execution_count":True,
        "user_region_capacity_probe_hypothesis":
            any(x["partition"]=="user" and x["lba"]==0x01af5fff for x in reads),
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("trace",type=Path,help="private QEMU -d in_asm trace")
    p.add_argument("--output",type=Path,help="metadata JSON, no ROM/sector bytes")
    a=p.parse_args()
    report=audit(a.trace.read_text(errors="replace"))
    output=json.dumps(report,indent=2)+"\n"
    if a.output:
        a.output.write_text(output)
    print(output)


if __name__=="__main__":
    main()
