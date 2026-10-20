"""Firmware-free regression tests for attempted I2C transactions."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from i2c_boot_triage import attempted_pointer_reads


def trace(*words, base=0x41035060):
    return "".join(
        f"EXeSX LPI2C WRITE @0x{base:08x} data=0x{word:08x}\n"
        for word in words
    )


class I2CBootTriageTests(unittest.TestCase):
    def test_le_pointer_and_four_byte_receive_request(self):
        report = attempted_pointer_reads(trace(0x496, 0x14, 0x62, 0x497, 0x103, 0x200))
        pair = "0x41035000:slave=0x4b:pointer_le=0x6214"
        self.assertEqual(report["attempted_pointer_read_starts"], {pair: 1})
        self.assertEqual(report["attempted_rx_requests"], {f"{pair}:bytes=4": 1})

    def test_not_a_false_pointer_if_only_one_byte_sent(self):
        log = trace(0x496, 0x14, 0x497, 0x100)
        report = attempted_pointer_reads(log)
        self.assertFalse(report["attempted_pointer_read_starts"])
        self.assertEqual(
            report["attempted_rx_requests"],
            {"0x41035000:unpaired-read:bytes=1": 1},
        )

    def test_retry_start_resets_previous_pointer(self):
        report = attempted_pointer_reads(
            trace(0x496, 0x14, 0x62, 0x496, 0x14, 0x62, 0x497)
        )
        self.assertEqual(sum(report["attempted_pointer_read_starts"].values()), 1)
        self.assertFalse(report["attempted_rx_requests"])

    def test_unrelated_mmio_writes_and_buses_are_not_mixed(self):
        log = "EXeSX LPI2C WRITE @0x41035010 data=0x00000496\n"
        log += trace(0x496, 0x14, 0x62, 0x497, 0x100)
        log += trace(0x497, 0x100, base=0x41034060)
        report = attempted_pointer_reads(log)
        self.assertEqual(len(report["attempted_pointer_read_starts"]), 1)
        self.assertEqual(len(report["attempted_rx_requests"]), 2)


if __name__ == "__main__":
    unittest.main()
