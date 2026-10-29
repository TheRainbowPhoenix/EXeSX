#!/usr/bin/env python3
"""Owner-firmware factory KEY AUTO TEST(COVERING) physical replay.

Decode key order from the owner's private, unchanged 32-bit LE A7 ELF.
Only write the opt-in M4 electrical contact file; no A7 queue, IPC, CPU
register, factory result or private ROM content is changed or published.
This helper cannot declare a factory pass: observe original LCD/firmware.
"""
import argparse
import json
import os
from pathlib import Path
import re
import struct
import time

# The 48/49 logical-key variants selected by original FUN_6005c50c.
# Only pointers, never original ROM contents, are stored in this file.
TABLES = {"48": 0x60161fc8, "49": 0x60161f00}


def read_elf_table(data, addr):
    if data[:4] != b"\x7fELF" or data[4:6] != b"\x01\x01":
        raise ValueError("expected original 32-bit little-endian A7 ELF")
    hdr = struct.unpack_from("<16sHHIIIIIHHHHHH", data)
    _, _, _, _, _, phoff, _, _, _, phentsize, phnum, *_ = hdr
    found = None
    for n in range(phnum):
        kind, offset, vaddr, _, size, _, _, _ = struct.unpack_from(
            "<8I", data, phoff + n * phentsize)
        if kind == 1 and vaddr <= addr < vaddr + size:
            found = offset + addr - vaddr
            break
    if found is None:
        raise ValueError("key table not mapped in private ELF")
    pairs = []
    for i in range(100):
        num, code = struct.unpack_from("<hH", data, found + i * 4)
        if num == -1:
            break
        if num != len(pairs) + 1 or not code:
            raise ValueError("not a sequential factory covering-key table")
        pairs.append((num, code))
    else:
        raise ValueError("missing key-list terminator")
    return pairs


def matrix_codes(path):
    text = path.read_text(encoding="utf-8")
    # Read the public electrical keyboard map, not guessed A7 events.
    return {int(x, 16) for x in re.findall(
        r"\{\s*(0x[0-9a-fA-F]+)\s*,\s*\d+\s*,\s*\d+\s*\}", text)}


def write_contact(path, code):
    temp = path.with_name(path.name + ".tmp")
    temp.write_text("0\n" if code is None else f"0x{code:x}\n", encoding="ascii")
    os.replace(temp, path)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--elf", type=Path, required=True,
                   help="Owner-private unmodified A7 BIOS/OS ELF")
    p.add_argument("--variant", choices=tuple(TABLES), required=True,
                   help="48 or 49 key mode selected by the running original firmware")
    p.add_argument("--matrix-file", type=Path, default=(
        Path(__file__).resolve().parents[1] /
        "hw/arm/exesx-imx7ulp-keyboard.inc"))
    p.add_argument("--contact-file", type=Path)
    p.add_argument("--ready-file", type=Path,
                   help="Host marker issued only after actual AUTO KEY CHECK screen appears")
    p.add_argument("--execute", action="store_true",
                   help="Without this flag, merely validate the original key table")
    p.add_argument("--hold", type=float, default=0.14)
    p.add_argument("--gap", type=float, default=0.23)
    p.add_argument("--max-wait", type=float, default=60.0)
    p.add_argument("--report", type=Path)
    args = p.parse_args(argv)
    if min(args.hold, args.gap, args.max_wait) <= 0:
        p.error("all timing values must be positive")
    pairs = read_elf_table(args.elf.read_bytes(), TABLES[args.variant])
    required = matrix_codes(args.matrix_file)
    missing = [hex(c) for _, c in pairs if c not in required]
    if missing:
        raise ValueError("Unemulated physical M4 key(s): " + ", ".join(missing))
    report = {
        "variant": args.variant,
        "expected_key_count": len(pairs),
        "codes": [f"0x{code:02x}" for _, code in pairs],
        "method": "physical M4 matrix contacts, not firmware event injection",
        "executed": args.execute,
        "original_factory_ok_observed": False,
    }
    if args.execute:
        if not args.contact_file or not args.ready_file:
            p.error("--execute requires --contact-file AND --ready-file")
        deadline = time.monotonic() + args.max_wait
        while not args.ready_file.exists():
            if time.monotonic() >= deadline:
                raise TimeoutError("genuine AUTO KEY CHECK ready marker was not observed")
            time.sleep(0.1)
        args.contact_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            for index, code in pairs:
                write_contact(args.contact_file, code)
                print(f"original key {index}/{len(pairs)}: 0x{code:02x}", flush=True)
                time.sleep(args.hold)
                write_contact(args.contact_file, None)
                time.sleep(args.gap)
        finally:
            write_contact(args.contact_file, None)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"keys_validated": len(pairs),
                      "host_contacts_sent": args.execute,
                      "factory_pass_claimed": False}))


if __name__ == "__main__":
    main()
