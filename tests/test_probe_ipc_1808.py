"""Synthetic regression of IPC 0x1808 watch address and thread decoding."""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"scripts"))
spec = importlib.util.spec_from_file_location("ipc1808", ROOT/"scripts/probe_ipc_1808.py")
ipc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ipc)


class IPC1808Tests(unittest.TestCase):
    def test_shared_slot_stride_and_bounds(self):
        self.assertEqual(ipc.response_word_address(0), 0x2F02800C)
        self.assertEqual(ipc.response_word_address(1), 0x2F028054)
        self.assertEqual(ipc.response_word_address(31), 0x2F0288C4)
        for x in (-1, 32, "0"):
            with self.assertRaises(ValueError):
                ipc.response_word_address(x)

    def test_stop_thread_and_key_breakpoints(self):
        self.assertEqual(ipc.stopped_thread("T05thread:01;"), 1)
        self.assertEqual(ipc.stopped_thread("T05thread:02;watch:2f02800c;"), 2)
        self.assertIsNone(ipc.stopped_thread("S05"))
        self.assertIn(0x60177FD8, ipc.MILESTONES)
        self.assertIn(0x60178048, ipc.MILESTONES)
        self.assertIn(0x600488A4, ipc.MILESTONES)
        self.assertIn(0x60400000, ipc.MILESTONES)


if __name__ == "__main__":
    unittest.main()
