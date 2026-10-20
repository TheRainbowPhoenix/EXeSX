#!/usr/bin/env python3
"""Group QEMU LPI2C MTDR command attempts by START and STOP.

Classifies write payloads, requested read sizes, NACK logs, and synthetic
ACK tags. A two-byte write is NOT assumed to be a 16-bit register pointer.
"""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path
import re

MTDR = re.compile(r"EXeSX LPI2C WRITE @0x([0-9a-fA-F]+) data=0x([0-9a-fA-F]+)")
NACK = re.compile(r"EXeSX LPI2C @0x([0-9a-fA-F]+) address=0x([0-9a-fA-F]+): NACK")
DIAGNOSTIC = re.compile(r"EXeSX DIAGNOSTIC I2C4B ACK @0x([0-9a-fA-F]+) rw=(read|write)")


def decode(trace: str) -> dict:
    buses = {}
    for line in trace.splitlines():
        m = MTDR.search(line)
        if m:
            addr = int(m.group(1), 16)
            if (addr & 0xfff) != 0x60:
                continue
            base = f"0x{addr - 0x60:08x}"
            obj = buses.setdefault(base, {"transactions": [], "active": None})
            bits = int(m.group(2), 16)
            cmd, byte = (bits >> 8) & 7, bits & 0xff
            if cmd in (4, 5):
                tx = {
                    "start_word": f"0x{bits:04x}",
                    "address_7bit": f"0x{byte >> 1:02x}",
                    "direction": "read" if byte & 1 else "write",
                    "write_bytes": [], "read_requests": [],
                    "nack_logged": False, "diagnostic_ack_logged": False,
                    "stop_observed": False,
                    "previous_start_without_stop": bool(obj["active"] is not None),
                }
                obj["transactions"].append(tx)
                obj["active"] = tx
            elif obj["active"] is not None:
                tx = obj["active"]
                if cmd == 0 and tx["direction"] == "write":
                    tx["write_bytes"].append(f"0x{byte:02x}")
                elif cmd == 1 and tx["direction"] == "read":
                    tx["read_requests"].append(byte + 1)
                elif cmd == 2:
                    tx["stop_observed"] = True
                    obj["active"] = None
            continue
        m = NACK.search(line)
        if m:
            bus = f"0x{int(m.group(1),16):08x}"
            active = buses.get(bus, {}).get("active")
            if active is not None and active["address_7bit"] == f"0x{int(m.group(2),16) >> 1:02x}":
                active["nack_logged"] = True
            continue
        m = DIAGNOSTIC.search(line)
        if m:
            bus = f"0x{int(m.group(1),16):08x}"
            active = buses.get(bus, {}).get("active")
            if active is not None and active["direction"] == m.group(2):
                active["diagnostic_ack_logged"] = True
    out = {}
    for bus, obj in buses.items():
        txs = obj["transactions"]
        shapes = Counter()
        for tx in txs:
            key = f"{tx['address_7bit']}:{tx['direction']}:{len(tx['write_bytes'])}w:{','.join(map(str, tx['read_requests']))}r"
            shapes[key] += 1
        out[bus] = {
            "count": len(txs),
            "nack_count": sum(t["nack_logged"] for t in txs),
            "shapes": dict(shapes), "transactions": txs,
        }
    return {"buses": out, "warning":
            "MTDR intentions only: no proven physical ACK, device identity, or LE pointer; no-NACK is not proof of ACK"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    result = json.dumps(decode(args.trace.read_text(errors="replace")), indent=2) + "\n"
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(result)
    print(result, end="")


if __name__ == "__main__":
    main()
