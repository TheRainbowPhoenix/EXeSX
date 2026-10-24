#!/usr/bin/env python3
"""Audit PRIVATE OSUP-derived eMMC coverage; never publish source bytes.

QEMU eMMC layout is boot0 4 MiB, boot1 4 MiB, then user area.
Every range is labelled source-derived, partial, or unknown.  No
fabricated bytes or unproven installed flash locations.
"""
import argparse
import hashlib
import json
from pathlib import Path
import analyze_osup_install_layout as layout

def audit(osup, media, partition, lba, sectors):
    data = osup.read_bytes()
    info = layout.analyze(data)
    if sectors < 1 or lba < 0:
        raise ValueError("LBA must be nonnegative and sector count positive")
    start = lba * layout.SECTOR
    size = sectors * layout.SECTOR
    if partition in ("boot0", "boot1") and start + size > layout.BOOT_SIZE:
        raise ValueError("Read extends beyond 4 MiB eMMC boot partition")
    base = {"boot0": 0, "boot1": layout.BOOT_SIZE,
            "user": 2 * layout.BOOT_SIZE}[partition]
    if base + start + size > layout.QEMU_SYNTHETIC_SIZE:
        raise ValueError("Read extends beyond synthetic eMMC geometry")
    covered = []
    pvos = info["pvos"]["osup_offset"]
    if partition == "boot1":
        for pos in (0, 32 * layout.SECTOR):
            covered.append((pos, pos + layout.SECTOR,
                            pvos, "PVOS metadata (hypothesized placement)"))
    if partition == "user":
        offset = 0
        for c in info["components"]:
            src = c["header_osup_offset"]
            available = max(0, min(c["declared_bytes"], len(data) - 2 - src))
            covered.append((offset, offset + available, src,
                            f"component {c['type']} source bytes"))
            offset += c["declared_bytes"]
    with media.open("rb") as f:
        f.seek(base + start)
        present = f.read(size)
    if len(present) != size:
        raise ValueError("Media truncated")
    matched = 0
    missing = []
    mismatched = []
    idx = start
    while idx < start + size:
        candidate = next((r for r in covered if r[0] <= idx < r[1]), None)
        end = min(start + size, candidate[1] if candidate else
                  min((r[0] for r in covered if r[0] > idx), default=start + size))
        actual = present[idx - start:end - start]
        if candidate:
            source = data[candidate[2] + idx - candidate[0]:
                          candidate[2] + end - candidate[0]]
            if source == actual:
                matched += end - idx
            else:
                mismatched.append({"byte_start": idx, "byte_end": end,
                                   "source": candidate[3]})
        else:
            missing.append({"byte_start": idx, "byte_end": end,
                            "observed_zero": not any(actual)})
        idx = end
    return {"partition": partition, "lba": lba, "sectors": sectors,
            "source_verified_bytes": matched,
            "requested_bytes": size, "unknown_ranges": missing,
            "source_mismatch_ranges": mismatched,
            "flash_read_sha256": hashlib.sha256(present).hexdigest(),
            "note": "Source match validates synthetic reconstruction only; not real installed flash"}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("osup", type=Path)
    parser.add_argument("media", type=Path)
    parser.add_argument("--partition", choices=["boot0","boot1","user"], required=True)
    parser.add_argument("--lba", type=int, required=True)
    parser.add_argument("--sectors", type=int, default=1)
    args = parser.parse_args()
    report = audit(args.osup, args.media, args.partition, args.lba, args.sectors)
    print(json.dumps(report, indent=2))
    if report["source_mismatch_ranges"]:
        raise SystemExit(2)

if __name__ == "__main__":
    main()
