#!/usr/bin/env python3
"""Metadata-only study of an owner-supplied Casio DY3xx OSUP install layout.

Verifies updater, IPL, PVOS, BIOS and OS checksums and known updater opcodes.
Never uploads ROM bytes or flash sectors. Opt-in private sparse QEMU media
contains only original PVOS metadata and is explicitly SYNTHETIC.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

SECTOR = 512
BOOT_SIZE = 4 * 1024 * 1024
QEMU_SYNTHETIC_SIZE = 15642656768
UPDSIG = b"CASIO DY3xx ADDIN MODULE FOR RELEASE ROM\0"
IPLSIG = b"CASIOIPL_V00"
PVOSSIG = b"CASIOPVOS800"
DICSSIG = b"CASIODICS06"


def u32(data, off):
    return struct.unpack_from("<I", data, off)[0]


def sum16(data):
    return (sum(data[:-2]) & 0xffff) == int.from_bytes(data[-2:], "little")


def checked(data, off, size, prefix):
    h = data[off:off + size]
    if len(h) != size or not h.startswith(prefix) or not sum16(h):
        raise ValueError("Invalid checksum or signature " + repr(prefix))
    return h


# Exact, firmware-version-specific *ARM opcodes*, not source firmware bytes.
# Unknown versions must be examined independently, not silently classified.
UPDATER_OPCODES = {
    "cmd6_partconfig_or": (0x64004a44, 0xe38217ec),
    "cmd6_partconfig_value": (0x64004a48, 0xe1811400),
    "cmd6_send": (0x64004a50, 0xebfffc3f),
    "cmd25_command_write": (0x64004264, 0xe585000c),
    "cmd24_command_write": (0x6400435c, 0xe5850008),
    "cmd24_fifo_write": (0x640043a0, 0xe585301c),
    "cmd24_bwr_ack": (0x640043b4, 0xe585202c),
    "seek_ipl_offset": (0x6400ed74, 0xe2801a80),
    "call_sector_writer": (0x6400edec, 0xebfffc9d),
    "boot1_pvos_signature_check": (0x64007270, 0xe59f3908),
    "boot1_header_marker_check": (0x64007328, 0xe1d000bc),
    "boot1_read_partition_selector": (0x640074a0, 0xe3a03001),
    "boot1_primary_lba": (0x640074ac, 0xe3a00000),
    "boot1_primary_read": (0x640074b0, 0xeb00003f),
    "boot1_backup_lba": (0x640074e0, 0xe3a00020),
    "boot1_backup_read": (0x640074e4, 0xeb000032),
    "boot1_part_config_access2": (0x640075e0, 0xe3e03001),
    "logical_to_physical_partition": (0x64004a34, 0xe2866004),
    "bulk_writer_logical_region0": (0x6400ecb0, 0xe3a00000),
    "bulk_writer_select": (0x6400ecb4, 0xebffd847),
    "bulk_writer_start_sector0": (0x6400ede4, 0xe3a01000),
}


def analyze(data):
    if not data.startswith(UPDSIG) or not sum16(data):
        raise ValueError("Unrecognized or checksum-invalid OSUP")
    load, length, entry = (u32(data, x) for x in (0x30, 0x34, 0x38))
    if load != 0x64000000 or not 0x100 <= entry-load < length or length >= len(data):
        raise ValueError("Unexpected release-ROM updater layout")
    for name, (addr, expected) in UPDATER_OPCODES.items():
        if u32(data, addr-load) != expected:
            raise ValueError("Updater opcode not recognized: " + name)
    pos, matches = 0, []
    while (pos := data.find(IPLSIG, pos)) != -1:
        try:
            checked(data, pos, 64, IPLSIG)
            matches.append(pos)
        except ValueError:
            pass
        pos += len(IPLSIG)
    if len(matches) != 1:
        raise ValueError("Expected exactly one valid IPL")
    ipos = matches[0]
    ipl = checked(data, ipos, 64, IPLSIG)
    ipl_size = u32(ipl, 0x20)
    if ipl_size < 64 or ipos + ipl_size > len(data):
        raise ValueError("Invalid IPL extent")
    if (sum(data[ipos+64:ipos+ipl_size]) & 0xffffffff) != u32(ipl, 0x24):
        raise ValueError("IPL payload checksum")
    pvpos = ipos + 0x60000
    pvos = checked(data, pvpos, SECTOR, PVOSSIG)
    if struct.unpack_from("<HH", pvos, 12) != (0x55aa, SECTOR):
        raise ValueError("PVOS marker or sector size mismatch")
    cursor = ipos + 0xc0000 + u32(pvos, 0x28)*SECTOR
    comps = []
    for tag in ("B", "A", "F"):
        h = checked(data, cursor, SECTOR, DICSSIG + tag.encode())
        extent = u32(h, 0x24)*SECTOR
        info = dict(type=tag, header_osup_offset=cursor,
                    source_sector_relative_to_ipl=(cursor-ipos)//SECTOR,
                    declared_sectors=u32(h, 0x24),
                    declared_bytes=extent,
                    mapped_load_address=hex(u32(h, 0x28)))
        if tag != "F":
            if extent < SECTOR or cursor + extent > len(data)-2:
                raise ValueError("Invalid " + tag + " extent")
            body = data[cursor+SECTOR:cursor+extent]
            if (sum(body) & 0xffffffff) != u32(h, 0x30):
                raise ValueError("Invalid " + tag + " body checksum")
            info["payload_bytes"] = len(body)
            cursor += extent
        else:
            info["stored_payload_bytes"] = len(data)-cursor-SECTOR-2
            info["declared_minus_stored_bytes"] = (
                extent-SECTOR-info["stored_payload_bytes"])
        comps.append(info)
    # Updater's boot1 reader tests this 12-byte literal at both LBA0/32.
    # It matches checksum-valid OSUP PVOS, not CASIOIPL_V00.
    signature_ptr = u32(data, 0x7b80)
    if signature_ptr < load or signature_ptr + len(PVOSSIG) > load + length:
        raise ValueError("Unrecognized updater boot1 signature pointer")
    if data[signature_ptr-load:signature_ptr-load+len(PVOSSIG)] != PVOSSIG:
        raise ValueError("Updater boot1 validator signature mismatch")
    candidates = [dict(boot1_lba=lba, possible_osup_offset=pvpos,
                       expected_signature="CASIOPVOS800",
                       sha256=hashlib.sha256(pvos).hexdigest(),
                       status="UNVERIFIED exact installed byte identity; "
                              "firmware validates PVOS signature and checksum")
                  for lba in (0, 32)]
    return dict(source_sha256=hashlib.sha256(data).hexdigest(),
        total_bytes=len(data),
        updater=dict(load=hex(load), entry=hex(entry), length=length),
        ipl=dict(osup_offset=ipos, length=ipl_size),
        pvos=dict(osup_offset=pvpos,
                  component_start_sector=u32(pvos, 0x28),
                  extent_or_capacity_field_0x2c_sectors=u32(pvos, 0x2c),
                  field_0x2c_bytes=u32(pvos, 0x2c)*SECTOR),
        components=comps, boot1_hypotheses=candidates,
        boot1_reader=dict(partition_access=2, primary_lba=0, backup_lba=32,
                          metadata_signature="CASIOPVOS800",
                          next_observed_cmd23_block_count=32,
                          next_observed_cmd18_lba=64,
                          payload_after_lba64="UNKNOWN"),
        bulk_writer=dict(logical_region=0, start_lba=0,
                         physical_partition_if_ext_csd155_bit0_clear="user",
                         physical_partition_if_ext_csd155_bit0_set="GP1 if provisioned",
                         boot1_write_proven=False),
        updater_opcode_addresses={k:hex(addr) for k,(addr,_) in UPDATER_OPCODES.items()},
        warnings=[
            "Code confirms CMD6 PARTITION_CONFIG, CMD24/CMD25 and sector writes, not their complete destination mapping.",
            "PVOS[0x2c] exceeds 4MiB boot-partition size; a whole-image boot1 copy is impossible.",
            "F declared extent is larger than stored payload; this is not a complete disk image.",
            "Original BIOS accepts OSUP PVOS at either boot1 LBA0 or LBA32; installed byte identity not verified.",
            "The main updater writer's logical region0 targets user or provisioned GP1, NOT boot1.",
            "IPL at boot1 LBA0 contradicts the PVOS reader; payload after CMD18 LBA64 is unknown.",
        ])

def write_private_pvos_test_image(path, pvos, placement):
    """EXPLICITLY SYNTHETIC sparse QEMU image. Exclusive creation; no IPL."""
    with open(path, "xb") as out:
        out.truncate(QEMU_SYNTHETIC_SIZE)
        if placement in ("primary", "both"):
            out.seek(BOOT_SIZE)
            out.write(pvos)
        if placement in ("backup", "both"):
            out.seek(BOOT_SIZE + 32 * SECTOR)
            out.write(pvos)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("osup", type=Path, help="privately held OSUP.BIN")
    p.add_argument("--json", type=Path, help="metadata-only JSON; no ROM content")
    p.add_argument("--private-pvos-test-image", type=Path,
                   help="opt-in exclusive synthetic 15.64GB sparse QEMU media; NO IPL")
    p.add_argument("--placement", choices=("primary", "backup", "both"),
                   default="both")
    a = p.parse_args()
    data = a.osup.read_bytes()
    result = analyze(data)
    if a.private_pvos_test_image:
        off = result["pvos"]["osup_offset"]
        write_private_pvos_test_image(
            a.private_pvos_test_image, data[off:off+SECTOR], a.placement)
        result["synthetic_image"] = str(a.private_pvos_test_image)
        result["synthetic_warning"] = "TEST HYPOTHESIS; NOT PHYSICAL CASIO EMMC"
    output = json.dumps(result, indent=2) + "\n"
    if a.json:
        a.json.write_text(output)
    print(output)


if __name__ == "__main__":
    main()
