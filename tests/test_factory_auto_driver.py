"""Firmware-free regression tests for the cross-platform factory auto-driver."""
import importlib.util
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "auto_driver.py"
spec = importlib.util.spec_from_file_location("exesx_auto_driver", SCRIPT)
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


class AutoDriverTests(unittest.TestCase):
    def test_success_addresses_are_executed_tb_only(self):
        text = ("Disassembly mentions 0x6003a878 but does not execute it\n"
                "Trace 0: 0x0 [00000000/00000000600108a8/00000000/00000000]\n"
                "Trace 0: 0x0 [00000000/000000006003a878/00000000/00000000]\n")
        self.assertEqual(driver.milestone_addresses(text),
                         {driver.PC["event_wait"], driver.PC["factory_menu"]})

    def test_snapshot_statistics_and_stdlib_png(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            ppm = output / "popup.ppm"
            w, h = 864, 480
            rgb = b"\x00\x00\x00" * (w * h - 1) + b"\xff\xff\xff"
            ppm.write_bytes(b"P6\n864 480\n255\n" + rgb)
            values = driver.ppm_stats(ppm)
            self.assertEqual(values["black_pixels"], w*h-1)
            self.assertEqual(values["white_pixels"], 1)
            self.assertEqual(values["other_pixels"], 0)
            dest = output / "popup.png"
            driver.convert_png(ppm, dest)
            data = dest.read_bytes()
            self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertEqual(struct.unpack(">II", data[16:24]), (w, h))
            self.assertIn(b"IDAT", data)
            i = data.index(b"IDAT") + 4
            # One filter byte (zero) per row plus the original exact RGB bytes.
            self.assertEqual(zlib.decompress(data[i:i+struct.unpack(">I",data[i-8:i-4])[0]]),
                             b"".join(b"\x00" + rgb[n:n+3*w]
                                      for n in range(0, len(rgb), 3*w)))

    def test_partial_screenshot_not_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            ppm = Path(temp)/"partial.ppm"
            ppm.write_bytes(b"P6\n864 480\n255\n\x00" * 5)
            self.assertIsNone(driver.wait_for_image(ppm))

    def test_request_is_atomic_and_never_injects_guest_ram(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = root/"capture-request.txt"
            output = root/"menu.ppm"
            driver.request_capture(request, output)
            self.assertEqual(request.read_text().strip(), output.resolve().as_posix())
            self.assertFalse((root/"capture-request.txt.tmp").exists())


if __name__ == "__main__":
    unittest.main()
