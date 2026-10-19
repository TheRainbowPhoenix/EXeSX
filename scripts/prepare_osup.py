#!/usr/bin/env python3
"""Locally extract validated A7 BIOS + OS ELF from a user-supplied DY3xx OSUP.
No firmware data is included or uploaded. Refuses unfamiliar/checksum-bad ROMs.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct

def u32(buf, pos):
    return struct.unpack_from("<I", buf, pos)[0]

def checked_header(data, pos, size, prefix):
    h = data[pos:pos + size]
    if (len(h) != size or not h.startswith(prefix)
            or (sum(h[:-2]) & 0xffff) != int.from_bytes(h[-2:], "little")):
        raise ValueError("Invalid header " + repr(prefix) + " at " + hex(pos))
    return h

def extract(source):
    data = Path(source).read_bytes()
    if not data.startswith(b"CASIO DY3xx ADDIN MODULE FOR RELEASE ROM\0"):
        raise ValueError("Not a recognized DY3xx update container")
    if (sum(data[:-2]) & 0xffff) != int.from_bytes(data[-2:], "little"):
        raise ValueError("Update checksum mismatch")
    positions = []
    pos = 0
    while (pos := data.find(b"CASIOIPL_V00", pos)) != -1:
        try:
            checked_header(data, pos, 64, b"CASIOIPL_V00")
            positions.append(pos)
        except ValueError:
            pass
        pos += 1
    if len(positions) != 1:
        raise ValueError("Expected exactly one validated IPL header")
    ipos = positions[0]
    pvos = checked_header(data, ipos + 0x60000, 512, b"CASIOPVOS800")
    if struct.unpack_from("<HH", pvos, 12) != (0x55aa, 512):
        raise ValueError("PVOS sector/marker mismatch")
    pos = ipos + 0xc0000 + u32(pvos, 0x28) * 512
    sections = []
    for tag, name in ((b"B", "bios"), (b"A", "os")):
        h = checked_header(data, pos, 512, b"CASIODICS06" + tag)
        nbytes = u32(h, 0x24) * 512
        if nbytes < 512 or pos + nbytes > len(data) - 2:
            raise ValueError("Invalid " + name + " extent")
        body = data[pos + 512:pos + nbytes]
        if (sum(body) & 0xffffffff) != u32(h, 0x30):
            raise ValueError("Invalid " + name + " payload checksum")
        base, entry = u32(h, 0x28), u32(h, 0x2c)
        if not base <= entry < base + len(body):
            raise ValueError("Invalid " + name + " entry")
        sections.append((name, base, entry, body))
        pos += nbytes
    if sections[0][3][:8] != bytes.fromhex("0e0000ea18f09fe5"):
        raise ValueError("Unsupported BIOS reset vector")
    if sections[1][3][:8] != bytes.fromhex("00e09fe51eff2fe1"):
        raise ValueError("Unsupported OS trampoline")
    return sections, hashlib.sha256(data).hexdigest()

def elf32(sections):
    raw = bytearray(52 + 32 * len(sections))
    offsets = []
    for name, base, entry, body in sections:
        raw.extend(bytes((-len(raw)) % 4096))
        offsets.append(len(raw))
        raw.extend(body)
    ident = b"\x7fELF\x01\x01\x01" + bytes(9)
    raw[:52] = struct.pack("<16sHHIIIIIHHHHHH", ident, 2, 40, 1,
                           sections[0][2], 52, 0, 0x05000000,
                           52, 32, len(sections), 0, 0, 0)
    for i, ((name, base, entry, body), off) in enumerate(zip(sections, offsets)):
        struct.pack_into("<8I", raw, 52 + 32 * i, 1,
                         off, base, base, len(body), len(body), 5, 4096)
    return raw

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("osup", type=Path)
    p.add_argument("-o", "--output", type=Path,
                   default=Path("private/a7-firmware.elf"))
    args = p.parse_args()
    sections, sha = extract(args.osup)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(elf32(sections))
    print(json.dumps(dict(source_sha256=sha, output=str(args.output),
                          sections=[dict(name=n, base=hex(b), entry=hex(e),
                                         size=len(d)) for n, b, e, d in sections]),
                     indent=2))

if __name__ == "__main__":
    main()
