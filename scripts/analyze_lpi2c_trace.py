#!/usr/bin/env python3
"""Summarize real M4 LPI2C2 commands from a local QEMU trace.

Decodes START/STOP and DATA bytes, and attempts no chip identification
from the I2C address alone. Useful to compare NACK against diagnostic
reply experiments without sharing ROM images.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re

MTDR = re.compile(r"EXeSX LPI2C WRITE @0x([0-9a-fA-F]+) data=0x([0-9a-fA-F]+)")
NACK = re.compile(r"EXeSX LPI2C @0x([0-9a-fA-F]+) address=0x([0-9a-fA-F]+): NACK")
PROBE = re.compile(r"EXeSX DIAGNOSTIC I2C4B (ACK|READ|RX_REQUEST|pointer)")
CMD = {0: "TX_BYTE", 1: "RX_REQUEST", 2: "STOP", 3: "RECEIVE_DISCARD",
       4: "START", 5: "START_NACK", 6: "START_HIGH_SPEED"}

def analyze(trace: str):
    by_bus = {}
    for m in MTDR.finditer(trace):
        addr = int(m.group(1), 16)
        bits = int(m.group(2), 16)
        cmd = (bits >> 8) & 7
        data = bits & 0xff
        key = f"0x{addr - 0x60:08x}"
        bus = by_bus.setdefault(key, {"commands": Counter(),
                                      "starts": Counter(), "data_bytes": Counter(),
                                      "first_commands": [], "transactions": 0})
        bus["commands"][CMD.get(cmd, "OTHER")] += 1
        if cmd in (4, 5):
            bus["starts"][f"0x{data:02x}"] += 1
            bus["transactions"] += 1
        elif cmd == 0:
            bus["data_bytes"][f"0x{data:02x}"] += 1
        if len(bus["first_commands"]) < 90:
            bus["first_commands"].append(dict(command=CMD.get(cmd,"OTHER"),
                                              word=f"0x{bits:04x}", data=f"0x{data:02x}"))
    result = {
        "buses": by_bus,
        "nacks": Counter(f"0x{int(addr,16):08x}:0x{int(val,16):02x}"
                         for addr, val in NACK.findall(trace)),
        "scripted_probe_operations": Counter(PROBE.findall(trace)),
        "guidance": "I2C address bytes are 8-bit SLA+R/W; shift >> 1 for the 7-bit address. Byte sequences are hardware observations, NOT evidence of chip identity."
    }
    return result

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("trace", type=Path)
    p.add_argument("--json", type=Path, help="optional report path")
    args = p.parse_args()
    report = analyze(args.trace.read_text(errors="replace"))
    output = json.dumps(report, indent=2)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(output + "\n")
    print(output)

if __name__ == "__main__":
    main()
