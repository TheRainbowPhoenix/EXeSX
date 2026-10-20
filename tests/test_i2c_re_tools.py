"""Firmware-free I2C reconstruction tool tests."""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from decode_i2c_transactions import decode
from prepare_i2c_ghidra import m4_elf, M4_BASE, M4_RESET


def log(*words):
    return "".join(f"EXeSX LPI2C WRITE @0x41035060 data=0x{word:08x}\n"
                   for word in words)


class I2CReToolsTests(unittest.TestCase):
    def test_two_byte_write_separated_from_one_byte_pointer_read(self):
        result = decode(log(0x496, 0x14, 0x62, 0x200,
                            0x496, 0x2d, 0x497, 0x108, 0x200))
        txs = result["buses"]["0x41035000"]["transactions"]
        self.assertEqual(txs[0]["write_bytes"], ["0x14", "0x62"])
        self.assertTrue(txs[0]["stop_observed"])
        self.assertEqual(txs[1]["write_bytes"], ["0x2d"])
        self.assertTrue(txs[2]["previous_start_without_stop"])
        self.assertEqual(txs[2]["read_requests"], [9])

    def test_nack_does_not_imply_ack(self):
        result = decode(log(0x496) +
                        "EXeSX LPI2C @0x41035000 address=0x96: NACK\n" +
                        log(0x14))
        tx = result["buses"]["0x41035000"]["transactions"][0]
        self.assertTrue(tx["nack_logged"])
        self.assertFalse(tx["diagnostic_ack_logged"])

    def test_controller_register_write_not_treated_as_command(self):
        self.assertFalse(
            decode("EXeSX LPI2C WRITE @0x41035010 data=0x00000496\n")["buses"]
        )

    def test_elf_metadata(self):
        original = bytes(256)
        image = m4_elf(original)
        self.assertEqual(image[:7], b"\x7fELF\x01\x01\x01")
        self.assertEqual(struct.unpack_from("<I", image, 24)[0], M4_RESET)
        self.assertEqual(struct.unpack_from("<I", image, 52 + 8)[0], M4_BASE)
        self.assertEqual(image[0x1000:0x1000 + len(original)], original)
        self.assertEqual(struct.unpack_from("<H", image, 48)[0], 5)


if __name__ == "__main__":
    unittest.main()
