"""Firmware-free tests for original factory covering-key physical replay."""
import importlib.util
from pathlib import Path
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts" / "replay_factory_key_coverage.py"
spec = importlib.util.spec_from_file_location("replay_factory_key_coverage", PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def fake_elf(keylist, addr=0x60161f00):
    image = bytearray(0x2000)
    image[:16] = b"\x7fELF\x01\x01\x01" + bytes(9)
    struct.pack_into("<HHIIIIIHHHHHH", image, 16,
                     2, 40, 1, 0x60000000, 52, 0, 0,
                     52, 32, 1, 0, 0, 0)
    struct.pack_into("<8I", image, 52,
                     1, 0x100, addr, addr, 0x1000, 0x1000, 5, 0x100)
    for index, code in enumerate(keylist, 1):
        struct.pack_into("<hH", image, 0x100+(index-1)*4, index, code)
    struct.pack_into("<hH", image, 0x100+len(keylist)*4, -1, 0)
    return bytes(image)


class ReplayKeyCoverageTests(unittest.TestCase):
    def test_exact_sequence_from_private_elf_only(self):
        assert mod.read_elf_table(fake_elf([0x91,0x94,0x80]),0x60161f00) == [
            (1,0x91),(2,0x94),(3,0x80)]
        assert mod.read_elf_table(fake_elf([0x93],0x60161fc8),0x60161fc8) == [
            (1,0x93)]

    def test_invalid_indices_and_missing_segment_fail_closed(self):
        with self.assertRaises(ValueError):
            mod.read_elf_table(fake_elf([0x91]),0x60162000)
        buf=bytearray(fake_elf([0x91,0x94]))
        struct.pack_into("<h",buf,0x104,17)
        with self.assertRaises(ValueError):
            mod.read_elf_table(bytes(buf),0x60161f00)

    def test_public_matrix_is_source_of_supported_physical_contacts(self):
        matrix=mod.matrix_codes(ROOT/"hw"/"arm"/"exesx-imx7ulp-keyboard.inc")
        assert {0x80,0x90,0x91,0x93,0x94,0x95}.issubset(matrix)
        assert len(matrix)==49
        assert 0xffff not in matrix


if __name__=="__main__":
    unittest.main()
