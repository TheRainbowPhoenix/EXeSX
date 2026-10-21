"""No proprietary bytes: exercise update layout parser against fabricated OSUP."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "layout", ROOT / "scripts" / "analyze_osup_install_layout.py")
layout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(layout)


def write32(data, offset, value):
    struct.pack_into("<I", data, offset, value)


def fix_header(data, offset, n):
    data[offset+n-2:offset+n] = (sum(data[offset:offset+n-2]) & 65535).to_bytes(2, "little")


def fixture():
    data = bytearray(0x140e02)
    data[:len(layout.UPDSIG)] = layout.UPDSIG
    write32(data, 0x30, 0x64000000)
    write32(data, 0x34, 0x4f40a)
    write32(data, 0x38, 0x64000100)
    for _, (addr, opcode) in layout.UPDATER_OPCODES.items():
        write32(data, addr-0x64000000, opcode)
    write32(data, 0x7b80, 0x6401df44)
    data[0x1df44:0x1df50] = b"CASIOPVOS800"
    ipos = 0x80000
    data[ipos:ipos+len(layout.IPLSIG)] = layout.IPLSIG
    write32(data, ipos+0x20, 0x5000)
    for off in range(ipos+64, ipos+0x5000):
        data[off] = off & 255
    write32(data, ipos+0x24, sum(data[ipos+64:ipos+0x5000]) & 0xffffffff)
    fix_header(data, ipos, 64)
    pvpos = ipos+0x60000
    data[pvpos:pvpos+len(layout.PVOSSIG)] = layout.PVOSSIG
    struct.pack_into("<HH", data, pvpos+12, 0x55aa, 512)
    write32(data, pvpos+0x2c, 0x14000)
    fix_header(data, pvpos, 512)
    for tag, off in (("B", 0x140000), ("A", 0x140400), ("F", 0x140800)):
        sig = layout.DICSSIG+tag.encode()
        data[off:off+len(sig)] = sig
        write32(data, off+0x24, 2 if tag != "F" else 100)
        if tag != "F":
            data[off+512:off+1024] = bytes([ord(tag)])*512
            write32(data, off+0x30, 512*ord(tag))
        fix_header(data, off, 512)
    refresh_trailer(data)
    return data


def refresh_trailer(data):
    data[-2:] = (sum(data[:-2]) & 65535).to_bytes(2, "little")


class OSUPLayoutTests(unittest.TestCase):
    def test_happy_path_is_explicitly_not_verified_boot1(self):
        result = layout.analyze(fixture())
        self.assertEqual(result["pvos"]["field_0x2c_bytes"], 40*1024*1024)
        self.assertEqual([x["source_sector_relative_to_ipl"]
                          for x in result["components"]], [1536, 1538, 1540])
        self.assertEqual([x["boot1_lba"] for x in result["boot1_hypotheses"]], [0, 32])
        self.assertTrue(all(x["possible_osup_offset"] == 0xe0000
                            for x in result["boot1_hypotheses"]))
        self.assertTrue(all(x["expected_signature"] == "CASIOPVOS800"
                            for x in result["boot1_hypotheses"]))
        self.assertEqual(result["boot1_reader"]["partition_access"], 2)
        self.assertEqual(result["boot1_reader"]["next_observed_cmd18_lba"], 64)
        self.assertEqual(result["bulk_writer"]["physical_partition_if_ext_csd155_bit0_clear"], "user")
        self.assertFalse(result["bulk_writer"]["boot1_write_proven"])
        self.assertTrue(all("UNVERIFIED" in x["status"]
                            for x in result["boot1_hypotheses"]))
        self.assertGreater(result["components"][2]["declared_minus_stored_bytes"], 0)

    def test_corrupt_global_checksum_is_rejected(self):
        data=fixture()
        data[-1] ^= 1
        with self.assertRaisesRegex(ValueError, "OSUP"):
            layout.analyze(data)

    def test_corrupt_payload_even_with_valid_global_checksum(self):
        data=fixture()
        data[0x140200] ^= 1
        refresh_trailer(data)
        with self.assertRaisesRegex(ValueError, "body checksum"):
            layout.analyze(data)

    def test_different_updater_code_is_not_silently_classified(self):
        data=fixture()
        data[0x4a48] ^= 1
        refresh_trailer(data)
        with self.assertRaisesRegex(ValueError, "opcode"):
            layout.analyze(data)

    def test_boot1_part_selector_opcode_revision_is_checked(self):
        data = fixture()
        data[0x75e0] ^= 1
        refresh_trailer(data)
        with self.assertRaisesRegex(ValueError, "opcode"):
            layout.analyze(data)

    def test_boot1_reader_signature_pointer_is_checked(self):
        data = fixture()
        write32(data, 0x7b80, 0x6404f40a)
        refresh_trailer(data)
        with self.assertRaisesRegex(ValueError, "signature pointer"):
            layout.analyze(data)

    def test_synthetic_sparse_pvos_primary_and_backup_only(self):
        data = fixture()
        pvos = data[0xe0000:0xe0200]
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "test-sparse.raw"
            layout.write_private_pvos_test_image(target, pvos, "both")
            self.assertEqual(target.stat().st_size, layout.QEMU_SYNTHETIC_SIZE)
            with target.open("rb") as stream:
                stream.seek(layout.BOOT_SIZE)
                self.assertEqual(stream.read(512), pvos)
                stream.seek(layout.BOOT_SIZE + 32 * 512)
                self.assertEqual(stream.read(512), pvos)
                stream.seek(layout.BOOT_SIZE + 64 * 512)
                self.assertEqual(stream.read(512), bytes(512))
            with self.assertRaises(FileExistsError):
                layout.write_private_pvos_test_image(target, pvos, "both")

    def test_invalid_ipl_header_is_rejected(self):
        data=fixture()
        data[0x80000+0x18] ^= 1
        refresh_trailer(data)
        with self.assertRaisesRegex(ValueError, "exactly one valid IPL"):
            layout.analyze(data)


if __name__ == "__main__":
    unittest.main()
