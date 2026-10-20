#!/usr/bin/env python3
"""Reconstruct attempted LPI2C pointer reads from local EXeSX QEMU MTDR logs.

This decodes *software controller commands*, not physical I2C traffic.
Attempts may NACK. A two-byte little-endian register pointer is a
hypothesis only; it does not identify an external chip.
"""
from collections import Counter
import argparse
import json
from pathlib import Path
import re

MTDR = re.compile(r"EXeSX LPI2C WRITE @0x([0-9a-fA-F]+) data=0x([0-9a-fA-F]+)")


def attempted_pointer_reads(trace: str):
    state = {}
    read_starts = Counter()
    rx_requests = Counter()
    samples = []
    for match in MTDR.finditer(trace):
        address = int(match.group(1), 16)
        if (address & 0xfff) != 0x60:
            continue  # only the LPI2C master transmit command register
        bus = f"0x{address - 0x60:08x}"
        current = state.setdefault(bus, {"mode": None, "slave": None,
                                         "written": [], "pending": None})
        word = int(match.group(2), 16)
        cmd, byte = (word >> 8) & 7, word & 0xff
        if cmd in (4, 5):  # START/START_NACK carrying SLA+R/W
            slave = byte >> 1
            pending = None
            if (byte & 1 and current["mode"] == "write"
                    and current["slave"] == slave and len(current["written"]) >= 2):
                # Expose the first two transmitted bytes as a possible pointer.
                pointer = current["written"][0] | (current["written"][1] << 8)
                pending = f"{bus}:slave=0x{slave:02x}:pointer_le=0x{pointer:04x}"
                read_starts[pending] += 1
            current.update(mode="read" if byte & 1 else "write",
                           slave=slave, written=[], pending=pending)
        elif cmd == 0 and current["mode"] == "write":
            if len(current["written"]) < 2:
                current["written"].append(byte)
        elif cmd == 1 and current["mode"] == "read":
            count = byte + 1  # RECEIVE_DATA is encoded as (count - 1)
            key = current["pending"] or f"{bus}:unpaired-read"
            rx_requests[f"{key}:bytes={count}"] += 1
            if len(samples) < 30:
                samples.append({"bus": bus, "slave": f"0x{current['slave']:02x}",
                                "paired_write": current["pending"],
                                "requested_bytes": count})
        elif cmd == 2:  # STOP
            current.update(mode=None, slave=None, written=[], pending=None)
    return {
        "attempted_pointer_read_starts": dict(read_starts),
        "attempted_rx_requests": dict(rx_requests),
        "first_rx_requests": samples,
        "warning": ("Software MTDR intentions only: NACK/ACK and slave identity "
                    "need separate verification; 16-bit LE pointer is a hypothesis."),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path, help="private QEMU guest_errors trace")
    parser.add_argument("--json", type=Path, help="optional output report file")
    args = parser.parse_args()
    report = attempted_pointer_reads(args.trace.read_text(errors="replace"))
    output = json.dumps(report, indent=2) + "\n"
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(output)
    print(output, end="")


if __name__ == "__main__":
    main()
