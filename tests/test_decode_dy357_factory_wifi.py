"""Synthetic headers only: checks decoder, not original factory success."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from decode_dy357_factory_wifi import parse_frame


class FactoryWlanHeaderTests(unittest.TestCase):
    def test_original_six_command_dispatch_ids(self):
        for code in range(1, 7):
            value = parse_frame(bytes([255, 255, code, 0, 6, 0]))
            self.assertEqual(value["code"], code)
            self.assertTrue(value["complete_under_le_length"])
            self.assertEqual(value["available_payload_bytes"], 0)

    def test_payload_and_response(self):
        packet = parse_frame(bytes.fromhex("ffff03020a0011223344"))
        self.assertEqual(packet["length_field_le"], 10)
        self.assertEqual(packet["available_payload_bytes"], 4)
        reply = parse_frame(bytes.fromhex("ffff80000600"))
        self.assertEqual(reply["response"],
                         "accepted/status OK (verify original handler)")

    def test_rejects_unproven_length_or_magic(self):
        for sample in (b"", b"12345", bytes.fromhex("00ff01000600"),
                       bytes.fromhex("ffff01000000")):
            with self.assertRaises(ValueError):
                parse_frame(sample)
        # Firmware *outgoing* command 4 response writes 00 40 for 64
        # bytes, conflicting with the received LE-short interpretation.
        # Keep both hypotheses visible until the bus is captured.
        packet = parse_frame(bytes.fromhex("ffff80050040"))
        self.assertEqual(packet["length_field_be"], 64)
        self.assertEqual(packet["length_field_le"], 16384)
        self.assertFalse(packet["complete_under_le_length"])


if __name__ == "__main__":
    unittest.main()
