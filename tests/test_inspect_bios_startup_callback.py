"""Synthetic tests for owner-only callback-gate ARM ELF inspection."""
import importlib.util
import struct
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "callback", Path(__file__).resolve().parents[1] /
    "scripts/inspect_bios_startup_callback.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture():
    base = 0x60000000
    size = 0x50000
    data = bytearray(0x100 + size)
    ident = b"\x7fELF\x01\x01\x01" + bytes(9)
    header = struct.pack("<16sHHIIIIIHHHHHH", ident, 2, 40, 1, base,
                         52, 0, 0, 52, 32, 1, 0, 0, 0)
    data[:len(header)] = header
    struct.pack_into("<8I", data, 52, 1, 0x100, base, base, size, size, 5, 0x100)
    for addr, opcode in module.GATE_OPCODES.items():
        struct.pack_into("<I", data, 0x100 + addr-base, opcode)
    for addr in module.STARTUP_CALL_SITES:
        # BL +8, target address PC+8+8.
        struct.pack_into("<I", data, 0x100 + addr-base, 0xeb000002)
    struct.pack_into("<I", data, 0x100 + 0x6004a2ec-base, 0x622e6fbc)
    struct.pack_into("<I", data, 0x100 + 0x6004a2f0-base, 0x6232d5c8)
    return data


class CallbackInspectTests(unittest.TestCase):
    def test_known_gate_and_direct_calls(self):
        result = module.inspect(fixture())
        self.assertEqual(result["ready_pointer_location"], "0x6232d5c8")
        self.assertEqual(result["callback_storage_location"], "0x622e6fbc")
        self.assertEqual(result["ready_test_bit_mask"], "0x00000002")
        self.assertEqual(result["startup_direct_calls"]["0x6004a1c0"],
                         "0x6004a1d0")
        self.assertTrue(result["callback_indirect"])

    def test_unknown_firmware_fails_closed(self):
        data = fixture()
        data[0x100 + 0x60049bec - 0x60000000] ^= 1
        with self.assertRaisesRegex(ValueError, "Unrecognized firmware"):
            module.inspect(data)


if __name__ == "__main__":
    unittest.main()
