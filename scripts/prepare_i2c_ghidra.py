#!/usr/bin/env python3
"""Prepare private XD-SX9850 A7/M4 ELFs and static I2C xrefs.

Requires this repo's prepare_osup.py. Fingerprints bind every annotated
address to one validated firmware; no firmware is uploaded or embedded.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess

from prepare_osup import extract, elf32

BIOS_SHA = "eb7dafa1b544bbb8d79081866af280e6c0f88197de9f635c6887f8486155da66"
M4_SHA = "25f95e3a5cfe2a898b2110d874075e6da5b288c706c03bc5a051a1f8c8e54fb0"
M4_BASE = 0x1ffd0000
M4_SOURCE = 0x600ad6a0
M4_SIZE = 0x14f70
M4_RESET = 0x1ffe19e4
FUNCTIONS = {
    0x1ffd2e50: "M4_Kernel_DispatchRegisteredIRQCallbacks",
    0x1ffd3270: "M4_Kernel_CommonInterruptDispatch",
    0x1ffd5712: "M4_MU_ReceiveAndGIP_IRQHandler",
    0x1ffd6c48: "M4_LPI2C_ClearState",
    0x1ffd6cb6: "M4_LPI2C_CheckErrors",
    0x1ffd6cf8: "M4_LPI2C_SendStart",
    0x1ffd6d52: "M4_LPI2C_WaitComplete",
    0x1ffd6da0: "M4_LPI2C_TransmitBytes",
    0x1ffd6e28: "M4_LPI2C_ReceiveBytes",
    0x1ffd6f4c: "M4_I2C4B_ReadByte",
    0x1ffd6f7e: "M4_I2C4B_WriteTwoBytes",
    0x1ffd6fa6: "M4_I2C6B_ReadByte_Candidate",
    0x1ffd6fd8: "M4_I2C6B_WriteTwoBytes_Candidate",
}
LITERALS = {
    0x1ffd6f34: (0x41035014, "MSR (status)"),
    0x1ffd6f38: (0x41035010, "MCR (control)"),
    0x1ffd6f3c: (0x4103505c, "MFSR (FIFO counts)"),
    0x1ffd6f48: (0x41035018, "MIER (interrupt enable)"),
}
CALL_RE = re.compile(r"^\s*([0-9a-fA-F]+):.*?\t(?:bl|blx)\s+0x([0-9a-fA-F]+)\b", re.M)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def m4_elf(data: bytes) -> bytes:
    """ELF32 little-endian EABI5: program/section headers and Thumb symbols."""
    raw = bytearray(0x1000)
    raw.extend(data)
    symbols = [("$t", M4_RESET, 0), ("M4_Reset", M4_RESET, 2)]
    symbols += [(name, address, 2) for address, name in sorted(FUNCTIONS.items())]
    strings = bytearray(b"\0")
    symtab = bytearray(16)
    for name, address, typ in symbols:
        off = len(strings)
        strings.extend(name.encode("ascii") + b"\0")
        info = 0 if name == "$t" else 0x10 | typ
        symtab.extend(struct.pack("<IIIBBH", off, address, 0, info, 0, 1))
    raw.extend(bytes(-len(raw) % 4))
    symoff = len(raw)
    raw.extend(symtab)
    stroff = len(raw)
    raw.extend(strings)
    shnames = b"\0.text\0.symtab\0.strtab\0.shstrtab\0"
    shstroff = len(raw)
    raw.extend(shnames)
    raw.extend(bytes(-len(raw) % 4))
    shoff = len(raw)
    def sh(name, kind, flags, address, offset, length, link=0,
           info=0, align=1, entsize=0):
        return struct.pack("<10I", name, kind, flags, address, offset,
                           length, link, info, align, entsize)
    raw.extend(bytes(40))
    raw.extend(sh(1, 1, 6, M4_BASE, 0x1000, len(data), align=2))
    raw.extend(sh(7, 2, 0, 0, symoff, len(symtab), link=3,
                  info=1, align=4, entsize=16))
    raw.extend(sh(15, 3, 0, 0, stroff, len(strings)))
    raw.extend(sh(23, 3, 0, 0, shstroff, len(shnames)))
    ident = b"\x7fELF\x01\x01\x01" + bytes(9)
    raw[:52] = struct.pack("<16sHHIIIIIHHHHHH", ident, 2, 40, 1,
                           M4_RESET, 52, shoff, 0x05000000,
                           52, 32, 1, 40, 5, 4)
    struct.pack_into("<8I", raw, 52, 1, 0x1000, M4_BASE, M4_BASE,
                     len(data), len(data), 5, 0x1000)
    return bytes(raw)


def static_xrefs(m4: bytes, elf_file: Path, llvm: str | None):
    report = {
        "firmware_sha256": sha(m4), "m4_base": hex(M4_BASE),
        "functions": {hex(a): n for a, n in FUNCTIONS.items()},
        "literal_refs": [], "calls": [], "disassembler": None,
        "limitations": "Static disassembly, not runtime I2C traffic or ACKs",
    }
    for address, (expected, meaning) in LITERALS.items():
        actual = struct.unpack_from("<I", m4, address - M4_BASE)[0]
        if actual != expected:
            raise ValueError(f"Literal mismatch {address:#x}: {actual:#x} != {expected:#x}")
        report["literal_refs"].append({
            "address": hex(address), "value": hex(actual), "meaning": meaning,
        })
    if llvm:
        result = subprocess.run(
            [llvm, "--disassemble", "--triple=thumbv7em-none-eabi", str(elf_file)],
            capture_output=True, text=True, check=True,
        )
        report["disassembler"] = str(llvm)
        insns = {}
        for line in result.stdout.splitlines():
            fields = line.split("\t")
            match = re.match(r"^\s*([0-9a-fA-F]{8}):", fields[0])
            if match and len(fields) >= 2:
                insns[int(match.group(1), 16)] = (
                    fields[1].strip().lower(),
                    fields[2].strip().lower() if len(fields) >= 3 else "",
                )
        recent = {}
        prev = []
        for address in sorted(insns):
            recent[address] = prev[-4:]
            prev.append(address)
        for site, target in CALL_RE.findall(result.stdout):
            dst = int(target, 16)
            if dst not in FUNCTIONS:
                continue
            source = int(site, 16)
            record = {"site": f"0x{source:08x}",
                      "callee": hex(dst), "name": FUNCTIONS[dst]}
            if dst == 0x1ffd6e28:
                record["rx_bytes_literal"] = None
                record["length_basis"] = "unknown: caller register r1"
                for previous in reversed(recent.get(source, [])):
                    mnemonic, operands = insns[previous]
                    if mnemonic in ("bl", "blx", "b", "b.w", "bx"):
                        break
                    if re.match(r"^r1\s*,", operands):
                        immediate = re.match(r"r1\s*,\s*#(0x[0-9a-f]+|[0-9]+)$", operands)
                        if mnemonic in ("movs", "mov.w", "mov") and immediate:
                            record["rx_bytes_literal"] = int(immediate.group(1), 0)
                            record["length_basis"] = f"immediate r1 at 0x{previous:08x}"
                        break
            report["calls"].append(record)
    return report


def prepare(osup: Path, output: Path, llvm: str | None = None):
    sections, source_sha = extract(osup)
    bios = next(s for s in sections if s[0] == "bios")
    if bios[1] != 0x60000000 or sha(bios[3]) != BIOS_SHA:
        raise ValueError("BIOS not verified SX9850; fixed M4 offsets rejected")
    offset = M4_SOURCE - bios[1]
    m4 = bios[3][offset:offset + M4_SIZE]
    if len(m4) != M4_SIZE or sha(m4) != M4_SHA:
        raise ValueError("Copied M4 region fingerprint mismatch")
    stack, reset = struct.unpack_from("<II", m4)
    if (stack, reset) != (0x20001c00, M4_RESET | 1):
        raise ValueError("M4 vector mismatch")
    output.mkdir(parents=True, exist_ok=True)
    output.chmod(0o700)
    a7 = output / "a7-firmware.elf"
    m4file = output / "m4-firmware.elf"
    a7.write_bytes(elf32(sections))
    m4file.write_bytes(m4_elf(m4))
    a7.chmod(0o600)
    m4file.chmod(0o600)
    refs = static_xrefs(m4, m4file, llvm)
    (output / "m4-i2c-static-xrefs.json").write_text(json.dumps(refs, indent=2) + "\n")
    meta = {
        "source_sha256": source_sha, "bios_sha256": sha(bios[3]),
        "m4_sha256": sha(m4), "m4_source": hex(M4_SOURCE),
        "m4_base": hex(M4_BASE), "m4_size": len(m4),
        "m4_initial_msp": hex(stack), "m4_reset_thumb_pointer": hex(reset),
        "m4_reset_entry": hex(M4_RESET),
        "elfs": [a7.name, m4file.name],
        "warning": "PRIVATE firmware ELFs; never commit, publish or put into public CI",
    }
    (output / "manifest.json").write_text(json.dumps(meta, indent=2) + "\n")
    return meta, refs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("osup", type=Path)
    parser.add_argument("--out", type=Path, default=Path("private/i2c-ghidra"))
    parser.add_argument("--llvm-objdump", default=shutil.which("llvm-objdump"),
                        help="optional Thumb callsite disassembly")
    args = parser.parse_args()
    meta, refs = prepare(args.osup, args.out, args.llvm_objdump)
    print(json.dumps({"metadata": meta, "direct_i2c_calls": len(refs["calls"]),
                      "results": str(args.out)}, indent=2))


if __name__ == "__main__":
    main()
