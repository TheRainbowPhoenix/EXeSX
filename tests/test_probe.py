import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from make_probe import BASE, WORDS, create_elf

class ProbeTests(unittest.TestCase):
    def test_elf_header(self):
        data = create_elf()
        self.assertEqual(data[:7], b"\x7fELF\x01\x01\x01")
        self.assertEqual(struct.unpack_from("<I", data, 24)[0], BASE)
        self.assertEqual(struct.unpack_from("<I", data, 52 + 8)[0], BASE)
    def test_real_cp15_encoding_and_sentinel(self):
        self.assertEqual(WORDS[0], 0xee112f10)
        self.assertEqual(WORDS[2], 0xee012f10)
        self.assertEqual(WORDS[8], 0xee111f10)
        self.assertEqual(WORDS[-2:], [0x62000000, 0x45585358])
    def test_literal_offsets(self):
        self.assertEqual(5*4+8+16, 11*4)
        self.assertEqual(6*4+8+16, 12*4)
    def test_data_is_at_expected_segment_offset(self):
        self.assertEqual(struct.unpack_from("<I",create_elf(),256)[0],WORDS[0])

if __name__ == "__main__":
    unittest.main()
