"""Firmware-free negative/positive controls for the physical E2 replay."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from drive_e2_original_ok import (
    CROSS_BLACK, CROSS_POINT, HEIGHT, WIDTH, HEADER, atomic_contact,
    frame_info, verdict_after_offset,
)


class E2OriginalPCVerificationTests(unittest.TestCase):
    def test_guest_pc_verdict_ignores_stale_results(self):
        with tempfile.TemporaryDirectory() as folder:
            trace = Path(folder) / "original.log"
            trace.write_text(
                "Trace 0: [00000080/000000006005cd08/00000070/ff020000]\n")
            offset = trace.stat().st_size
            self.assertIsNone(verdict_after_offset(trace, offset))
            with trace.open("a") as stream:
                stream.write("Trace 0: [00000080/000000006005cd30/00000070/ff020000]\n")
            self.assertEqual(verdict_after_offset(trace, offset), "NG")
            offset = trace.stat().st_size
            with trace.open("a") as stream:
                stream.write("Trace 0: [00000080/000000006005cd08/00000070/ff020000]\n")
            self.assertEqual(verdict_after_offset(trace, offset), "OK")

    def test_accepts_original_cross_then_one_native_touch_erasure(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "lcd.ppm"
            rgb = bytearray(b"\xff" * (WIDTH * HEIGHT * 3))
            # Put the synthetic black pixels *away* from CROSS_POINT,
            # so adding the one E2 target pixel increases the count.
            for n in range(CROSS_BLACK - 1):
                off_bg = 3*(200000+n)
                rgb[off_bg:off_bg + 3] = b"\x00\x00\x00"
            x, y = CROSS_POINT
            off = 3*(WIDTH*y+x)
            rgb[off:off+3] = b"\x00\x00\x00"
            path.write_bytes(HEADER + rgb)
            original = frame_info(path)
            self.assertEqual(original["black"], CROSS_BLACK)
            self.assertEqual(original["pixel"], b"\x00\x00\x00")
            rgb[off:off+3] = b"\xff\xff\xff"
            path.write_bytes(HEADER + rgb)
            erased = frame_info(path)
            self.assertEqual(erased["black"], CROSS_BLACK-1)
            self.assertEqual(erased["pixel"], b"\xff\xff\xff")
            path.write_bytes(HEADER + rgb[:-6])
            with self.assertRaises(ValueError):
                frame_info(path)

    def test_physical_contact_has_explicit_release_and_no_ipc(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "keyboard.txt"
            atomic_contact(path, "0x94")
            self.assertEqual(path.read_text(encoding="ascii"), "0x94\n")
            atomic_contact(path, "0")
            self.assertEqual(path.read_text(encoding="ascii"), "0\n")
            self.assertFalse(path.with_name(path.name+".physical.tmp").exists())


if __name__ == "__main__":
    unittest.main()
