"""Host-only regressions for full 49-key original-ROM map and worker UI."""
import importlib.util
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import factory_control_panel as gui
from lcd_qmp import rgb565_to_rgb888, FRAME_BYTES


class FloatingKeyboardTests(unittest.TestCase):
    def test_49_original_m4_keys_and_all_letters(self):
        source = (ROOT / "hw/arm/exesx-imx7ulp-keyboard.inc").read_text()
        m = re.search(r"static const EXeSXM4KeyContact exesx_m4_key_contacts\[\] = \{(.*?)\};",
                      source, re.S)
        self.assertIsNotNone(m)
        entries = [(int(code,16), int(row), int(col))
                   for code,row,col in re.findall(
                       r"\{\s*0x([0-9a-fA-F]+),\s*(\d+),\s*(\d+)\s*\}", m[1])]
        self.assertEqual(len(entries),49)
        self.assertEqual(len({code for code,_,_ in entries}),49)
        by_code = {code:(row,col) for code,row,col in entries}
        self.assertEqual(by_code[0x9c], (4,5))
        self.assertEqual(by_code[0x90], (7,6))
        self.assertEqual(by_code[0x93], (8,7))
        self.assertEqual(by_code[0x94], (6,6))
        self.assertEqual(by_code[0x91], (6,7))
        for label in "".join(gui.ASCII_ROWS):
            self.assertIn(ord(label.lower()), by_code)

    def test_rgb565_reads_only_original_pixels(self):
        self.assertEqual(FRAME_BYTES,829440)
        class FakeMmap:
            def __len__(self): return FRAME_BYTES
            def __getitem__(self, item):
                if isinstance(item,slice): return b"\x00\xf8"*414720
                raise IndexError
        pixels = gui.pure_rgb565_lcd(FakeMmap())
        self.assertEqual(pixels[:6], b"\xff\x00\x00"*2)
        self.assertEqual(len(pixels),864*480*3)

    def test_raw_key_labels_are_not_guessed(self):
        self.assertIn(("DOWN",0x91), gui.KNOWN)
        self.assertIn(("BOOT",0x9c), gui.KNOWN)
        self.assertIn(("0x94",0x94), gui.KNOWN)


if __name__ == "__main__":
    unittest.main()
