"""Log-before-MTDR ACK/NACK correlation in QEMU peripheral logs."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from decode_i2c_transactions import decode


class I2CEventOrderTests(unittest.TestCase):
    def test_nack_before_start_is_attributed_to_that_start(self):
        logs = (
            "EXeSX LPI2C @0x41035000 address=0x96: NACK (no slave attached)\n"
            "EXeSX LPI2C WRITE @0x41035060 data=0x00000496\n"
            "EXeSX LPI2C WRITE @0x41035060 data=0x00000014\n"
            "EXeSX LPI2C @0x41035000 address=0x97: NACK (no slave attached)\n"
            "EXeSX LPI2C WRITE @0x41035060 data=0x00000497\n"
        )
        bus = decode(logs)["buses"]["0x41035000"]
        self.assertEqual(bus["nack_count"], 2)
        self.assertEqual([t["nack_logged"] for t in bus["transactions"]],
                         [True, True])

    def test_diagnostic_ack_precedes_qemu_mtdr_log(self):
        logs = (
            "EXeSX DIAGNOSTIC I2C4B ACK @0x41035000 rw=write (register mirror)\n"
            "EXeSX LPI2C WRITE @0x41035060 data=0x00000496\n"
            "EXeSX DIAGNOSTIC I2C4B ACK @0x41035000 rw=read (register mirror)\n"
            "EXeSX LPI2C WRITE @0x41035060 data=0x00000497\n"
            "EXeSX LPI2C WRITE @0x41035060 data=0x00000108\n"
        )
        tx = decode(logs)["buses"]["0x41035000"]["transactions"]
        self.assertTrue(all(t["diagnostic_ack_logged"] for t in tx))
        self.assertEqual(tx[1]["read_requests"], [9])

    def test_other_peripheral_logs_not_classified_as_commands(self):
        self.assertEqual(
            decode("EXeSX LPI2C WRITE @0x41035014 data=0x00000496\n")["buses"],
            {},
        )


if __name__ == "__main__":
    unittest.main()
