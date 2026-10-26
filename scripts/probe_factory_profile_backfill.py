#!/usr/bin/env python3
"""Prove the factory driver upgrades only missing I2S mappings in stale profiles.

No owner firmware, QEMU, SD card or guest RAM required.
"""
from pathlib import Path
import tempfile
from auto_driver import profile_with_lcd


def run():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        old = root / "old.ini"
        old.write_text(
            "[lpi2c2]\nkind=imx7ulp-lpi2c\nbase=0x41035000\nsize=0x200\n",
            encoding="utf-8")
        generated = profile_with_lcd(old, root).read_text(encoding="utf-8")
        for name, addr in (("i2s0-m4", "0x41037000"),
                           ("i2s1-m4", "0x410aa000")):
            assert generated.count("["+name+"]") == 1, (name, generated)
            assert ("base="+addr+"\nsize=0x100") in generated, (addr, generated)
        assert "[lpi2c2]" in generated and "base=0x41035000" in generated
        assert generated.count("[diagnostic-flexbus-lcd]") == 1
        # Existing current mappings must not be duplicated.
        new = root / "new.ini"
        new.write_text(generated, encoding="utf-8")
        stable = profile_with_lcd(new, root).read_text(encoding="utf-8")
        assert stable == generated, "Current profile was altered unnecessarily"
    print("PASS factory profile backfill: stale I2S0/I2S1 fixed, LCD preserved, idempotent")


if __name__ == "__main__":
    run()
