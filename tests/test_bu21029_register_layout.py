"""Guard the ROHM BU21029 private LPI2C register-file slots.

A regression once stored pen IRQ scan flags at +0x208, which is already
the PAGE1 firmware-written bitmask (the M4 uses e.g. PAGE1 register 6).
Linux and Windows ARM MMIO probes did not detect that hidden-state alias.
The scan flags/deadline are NOT guest-visible silicon registers; they
must not overlap either actual LPI2C registers or the model's existing
private 0x1c0..0x208 I2C state and the 0x300+ ROHM register mirror.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOUCH = ROOT / "hw/arm/exesx-imx7ulp-touch.inc"
I2C = ROOT / "hw/arm/exesx-imx7ulp-lpi2c.inc"


class BU21029PrivateStateTests(unittest.TestCase):
    def test_original_cfr2_interval_is_not_linux_default(self):
        pen = TOUCH.read_text(encoding="utf-8")
        i2c = I2C.read_text(encoding="utf-8")
        # Original DY357 M4 writes CFR2=0x4a, selecting 0x4 = 256us.
        # Generic Linux often writes 0xc9, selecting 0xc = 20480us.
        us = [0, 0, 0, 0, 256, 1024, 2048, 4096,
              5120, 8912, 10240, 15360, 20480, 20480, 20480, 20480]
        self.assertEqual(us[0x4a >> 4], 256)
        self.assertEqual(us[0xc9 >> 4], 20480)
        self.assertIn("exesx_bu21029_config(w, 2, 0x04)", pen)
        self.assertIn("256, 1024, 2048, 4096", pen)
        self.assertIn("exesx_bu21029_interval_us(w)", i2c)
        self.assertIn("exesx_bu21029_conversion_us(w)", i2c)

    def test_scan_slots_do_not_alias_bank1_write_mask(self):
        pen = TOUCH.read_text(encoding="utf-8")
        i2c = I2C.read_text(encoding="utf-8")
        for offset in (0x240, 0x244):
            ref = f"w->regfile[0x{offset:x} / 4]"
            self.assertIn(ref, pen)
            self.assertIn(ref, i2c)
            self.assertGreaterEqual(offset, 0x220)
            self.assertLess(offset, 0x300)
        for offset in (0x204, 0x208):
            self.assertNotIn(f"w->regfile[0x{offset:x} / 4]", pen)
        self.assertIn("w->regfile[0x204 / 4 + bank]", i2c)
        self.assertNotIn("w->regfile[0x208 / 4]", i2c)


if __name__ == "__main__":
    unittest.main()
