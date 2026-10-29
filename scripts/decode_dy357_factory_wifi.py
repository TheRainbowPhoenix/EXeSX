#!/usr/bin/env python3
"""Decode actual DY357 WIFI AUTO TEST six-byte frames. No guest writes.

Original A7 FUN_60059808 reads six bytes using FUN_60059a00.
Request header's native short at byte 4 implies little-endian length.
Some outgoing response constructors instead use byte4=0/byte5=0x40,
so the two endian interpretations are both exposed, not reconciled.
"""
import argparse
import json
import struct

ACTIONS = {
    1: "HELLO/ACK (FUN_60059a34)",
    2: "EXIT/CLEANUP (FUN_60059a70)",
    3: "RUN WLAN subcommands 1..5 (FUN_60059ab8)",
    4: "GET WLAN data subcommands 1..5 (FUN_6005a134)",
    5: "UNSUPPORTED (FUN_6005a5d8)",
    6: "UNSUPPORTED (FUN_6005a618)",
}
RESPONSES = {0x80: "accepted/status OK (verify original handler)",
             0x81: "unknown/unsupported", 0x82: "handler failure"}


def parse_frame(blob):
    if len(blob) < 6:
        raise ValueError("need a complete six-byte header")
    marker, cmd, sub, length = struct.unpack_from("<HBBH", blob)
    if marker != 0xffff:
        raise ValueError("unexpected magic, not original factory header")
    if length < 6:
        raise ValueError("invalid little-endian frame length")
    return {
        "magic": "ffff", "code": cmd, "argument": sub,
        "length_field_le": length,
        "length_field_be": (blob[4] << 8) | blob[5],
        "available_payload_bytes": len(blob) - 6,
        "complete_under_le_length": len(blob) >= length,
        "action": ACTIONS.get(cmd, "unrecognized inbound command"),
        "response": RESPONSES.get(cmd) if cmd >= 0x80 else None,
        "raw_hex": blob.hex(),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("hex_bytes", help="actual captured bytes, e.g. 'ff ff 03 01 06 00'")
    args = p.parse_args()
    print(json.dumps(parse_frame(bytes.fromhex(args.hex_bytes)), indent=2))


if __name__ == "__main__":
    main()
