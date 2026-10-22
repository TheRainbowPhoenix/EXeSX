"""Firmware-free tests for direct ARM BL metadata extraction."""
import importlib.util
import struct
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / "scripts/scan_arm_bl_calls.py"
spec = importlib.util.spec_from_file_location("armcalls", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def synthetic_elf():
    data = bytearray(0x200)
    hdr = struct.pack("<16sHHIIIIIHHHHHH",
                      b"\x7fELF\x01\x01\x01" + bytes(9),
                      2, 40, 1, 0x60000000, 52, 0, 0, 52, 32, 1, 0, 0, 0)
    data[:len(hdr)] = hdr
    struct.pack_into("<8I", data, 52, 1, 0x100, 0x60000000,
                     0x60000000, 16, 16, 5, 0x100)
    # at 0x60000000: BL to 0x60000010 (offset +8 => imm +2)
    struct.pack_into("<I", data, 0x100, 0xeb000002)
    # at 0x60000004: backward BL to 0x60000000 (offset +8 => imm -3)
    struct.pack_into("<I", data, 0x104, 0xebfffffd)
    struct.pack_into("<I", data, 0x108, 0xeafffffe)  # B, not BL
    return bytes(data)


class ArmCallTests(unittest.TestCase):
    def test_both_directions_and_ignores_plain_branch(self):
        x = mod.scan(synthetic_elf(), {0x60000000, 0x60000010})
        self.assertEqual(x["0x60000010"], ["0x60000000"])
        self.assertEqual(x["0x60000000"], ["0x60000004"])

    def test_rejects_wrong_architecture(self):
        b = bytearray(synthetic_elf())
        struct.pack_into("<H", b, 18, 3)
        with self.assertRaisesRegex(ValueError, "ARM"):
            mod.scan(b, {0x60000000})


if __name__ == "__main__":
    unittest.main()
