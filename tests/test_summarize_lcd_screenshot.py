"""Firmware-free synthetic P6 RGB pixel statistics regression."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "lcdsummary", ROOT / "scripts/summarize_lcd_screenshot.py")
summary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(summary)


class ScreenshotSummaryTests(unittest.TestCase):
    def test_synthetic_pixels_and_bounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            ppm = Path(tmp) / "fixture.ppm"
            # 4x2 RGB888: 2 black pixels, one on each row.
            colors = [(255, 255, 255)] * 8
            colors[1] = (0, 0, 0)
            colors[6] = (0, 0, 0)
            ppm.write_bytes(b"P6\n4 2\n255\n" +
                            b"".join(bytes(rgb) for rgb in colors))
            record = summary.summarize(ppm)
            self.assertEqual(record["nonwhite_pixels"], 2)
            self.assertEqual(record["white_pixels"], 6)
            self.assertEqual(record["distinct_colors"], 2)
            self.assertEqual(record["nonwhite_bbox_xyxy"], [1, 0, 3, 2])

    def test_reject_incomplete_ppm(self):
        with tempfile.TemporaryDirectory() as tmp:
            ppm = Path(tmp) / "broken.ppm"
            ppm.write_bytes(b"P6\n864 480\n255\n\x00")
            with self.assertRaises(ValueError):
                summary.summarize(ppm)


if __name__ == "__main__":
    unittest.main()
