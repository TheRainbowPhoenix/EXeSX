"""Regression: a popup-to-menu redraw is NOT proof that DOWN navigated."""
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from headless_factory_menu_checks import menu_lcd_state


class NativeMenuLcdTests(unittest.TestCase):
    @staticmethod
    def frame(path, *, menu=False, highlighted=None):
        header = b"P6\n864 480\n255\n"
        pixel = bytearray(b"\xff" * (864 * 480 * 3))
        def black_row(y, x0, x1):
            offset = (y * 864 + x0) * 3
            pixel[offset:offset + 3*(x1-x0)] = b"\x00" * (3*(x1-x0))
        if menu:
            black_row(10, 0, 864)
        if highlighted is not None:
            for y in range(highlighted, highlighted+15):
                black_row(y, 0, 864)
        path.write_bytes(header + pixel)

    def test_popup_rejected_not_a_navigation_frame(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = pathlib.Path(tmp) / "screen.ppm"
            self.frame(p)
            self.assertIsNone(menu_lcd_state(p))
            self.frame(p, menu=True)
            frame = menu_lcd_state(p)
            self.assertIsNotNone(frame)
            self.assertEqual(frame["selection_bands"], [])
            self.frame(p, menu=True, highlighted=51)
            selected = menu_lcd_state(p)
            self.assertEqual(selected["selection_bands"], [[51, 65]])
            self.assertNotEqual(selected["sha256"], frame["sha256"])

    def test_partial_frame_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = pathlib.Path(tmp) / "screen.ppm"
            p.write_bytes(b"P6\n864 480\n255\n" + b"\x00"*9)
            self.assertIsNone(menu_lcd_state(p))


if __name__ == "__main__":
    unittest.main()
