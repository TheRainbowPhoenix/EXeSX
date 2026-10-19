"""Hardware-free regressions for the differential MMIO fuzzer."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fuzz_mmio.py"
SPEC = importlib.util.spec_from_file_location("exesx_fuzz_mmio", SCRIPT)
FUZZ = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FUZZ)

class FuzzerTests(unittest.TestCase):
    def test_all_thirty_two_individual_bits(self):
        selected = FUZZ.cases()
        self.assertEqual(len(selected), 34)
        self.assertEqual(selected[0], ("zero", 0))
        self.assertEqual(selected[31], ("bit30", 0x40000000))
        self.assertEqual(selected[-1], ("all_ones", 0xffffffff))
        self.assertEqual(len({v for _, v in selected}), 34)

    def test_qcow2_header_and_refcounts(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "state.qcow2"
            FUZZ.make_qcow2(path)
            data = path.read_bytes()
            self.assertEqual(len(data), 4 * 65536)
            self.assertEqual(data[:4], bytes.fromhex("514649fb"))
            self.assertEqual(struct.unpack_from(">I", data, 4)[0], 3)
            self.assertEqual(struct.unpack_from(">Q", data, 65536)[0], 131072)
            for i in range(4):
                self.assertEqual(struct.unpack_from(">H",data,131072+i*2)[0], 1)

    def test_firmware_sites_are_distinct(self):
        self.assertEqual(FUZZ.SITES["initial"], 0x6004992c)
        self.assertEqual(FUZZ.SITES["poll"], 0x60049938)
        self.assertEqual(FUZZ.SITES["second-poll"], 0x60049950)
        self.assertEqual(FUZZ.REGISTERS["second-poll"],0x410260fc)

if __name__ == "__main__":
    unittest.main()
