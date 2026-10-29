#!/usr/bin/env python3
"""Inspect owner-private A7 factory touch acceptance rectangles.

This outputs *diagnostic raw BU21029 electrode candidates*, not calibrated
touch events or factory results. The original M4 must read 14 I2C bytes,
post genuine IPC, and cause A7 type 0x6000 events before they can pass.
Private firmware is only read on the owner's machine and never uploaded.
"""
import argparse
import json
from pathlib import Path
import struct
import time

TABLES = {"four": 0x60174D88, "two": 0x60174DC4}


def mapped_offset(elf, address):
    if elf[:6] != b"\x7fELF\x01\x01":
        raise ValueError("Expected a private 32-bit little-endian A7 ELF")
    hdr = struct.unpack_from("<16sHHIIIIIHHHHHH", elf)
    offset, entry_size, count = hdr[5], hdr[9], hdr[10]
    for i in range(count):
        kind, file_off, virtual, _, size, *_ = struct.unpack_from(
            "<8I", elf, offset + i * entry_size)
        if kind == 1 and virtual <= address < virtual + size:
            return file_off + address - virtual
    raise ValueError("Original calibration data not in an ELF PT_LOAD segment")


def source_rectangles(elf, variant):
    file_off = mapped_offset(elf, TABLES[variant])
    result = []
    for i in range(5):
        number, x0, y0, x1, y1 = struct.unpack_from(
            "<iHHHH", elf, file_off + i * 12)
        if number == -1:
            break
        if number != i or not (0 <= x0 < x1 <= 4095 and
                               0 <= y0 < y1 <= 4095):
            raise ValueError("Original region table invalid")
        x, y = (x0 + x1) // 2, (y0 + y1) // 2
        z1, z2 = 800, 1200
        # The original M4's 14-byte BU21029 report consumes Y, then X,
        # then Z1 and Z2. The final PX/PY/GH words are zero for one pen.
        packet = b"".join(struct.pack(">H", v << 4) for v in
                          (y, x, z1, z2, 0, 0, 0))
        result.append({
            "target": i,
            "firmware_region": [x0, y0, x1, y1],
            "candidate_raw_x": x,
            "candidate_raw_y": y,
            "physical_contact": f"1 {x} {y} {z1} {z2}",
            "serial_14_byte_hex": packet.hex(),
        })
    if len(result) != (4 if variant == "four" else 2):
        raise ValueError("Original region-count mismatch")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--elf", type=Path, required=True,
                   help="Owner-private unchanged original A7 ELF")
    p.add_argument("--variant", choices=tuple(TABLES), required=True)
    p.add_argument("--output", type=Path, required=True,
                   help="Private generated JSON report")
    p.add_argument("--contact-file", type=Path)
    p.add_argument("--ready-file", type=Path,
                   help="Explicit marker after real LCD calibration target")
    p.add_argument("--execute", action="store_true",
                   help="Play contacts only after ready marker; default plan only")
    p.add_argument("--hold", type=float, default=2.0)
    p.add_argument("--gap", type=float, default=0.8)
    args = p.parse_args()
    if args.hold <= 0 or args.gap <= 0:
        p.error("--hold/--gap must be positive")
    regions = source_rectangles(args.elf.read_bytes(), args.variant)
    report = {
        "variant": args.variant, "regions": regions,
        "warning": "Candidates assume uncalibrated raw electrode units "
                   "match A7 region values. No A7 type 0x6000 event "
                   "or factory OK is asserted.",
        "executed": False,
    }
    if args.execute:
        if not args.contact_file or not args.ready_file or not args.ready_file.is_file():
            p.error("Only execute after genuine test LCD verified via --ready-file")
        try:
            for region in regions:
                args.contact_file.write_text(region["physical_contact"] + "\n")
                time.sleep(args.hold)
                args.contact_file.write_text("0 0 0 800 1200\n")
                time.sleep(args.gap)
            report["executed"] = True
        finally:
            args.contact_file.write_text("0 0 0 800 1200\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print("Planned", len(regions), "raw physical touch samples; "
          "original M4/A7 delivery and LCD verdict not inferred")


if __name__ == "__main__":
    main()
