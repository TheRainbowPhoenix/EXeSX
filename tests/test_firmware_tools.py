"""Tests use synthetic bytes only; no Casio proprietary firmware."""
import struct
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from prepare_osup import checked_header, elf32

class FirmwareToolsTests(unittest.TestCase):
    def test_header_checksum_validation(self):
        h = bytearray(64)
        h[:7] = b"EXeSX00"
        h[-2:] = struct.pack("<H", sum(h[:-2]) & 0xffff)
        self.assertEqual(checked_header(h, 0, 64, b"EXeSX00"), h)
        h[10] ^= 1
        with self.assertRaises(ValueError):
            checked_header(h, 0, 64, b"EXeSX00")

    def test_elf_load_addresses(self):
        binary = elf32([
            ("bios", 0x60000000, 0x60000000, b"\x00"*64),
            ("os", 0x60400000, 0x60400000, b"\x00"*64),
        ])
        self.assertEqual(binary[:7], b"\x7fELF\x01\x01\x01")
        self.assertEqual(struct.unpack_from("<I", binary, 24)[0], 0x60000000)
        self.assertEqual(struct.unpack_from("<I", binary, 52 + 8)[0], 0x60000000)
        self.assertEqual(struct.unpack_from("<I", binary, 52 + 32 + 8)[0], 0x60400000)

if __name__ == "__main__":
    unittest.main()
