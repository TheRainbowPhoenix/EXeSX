#!/usr/bin/env python3
"""Prove the factory driver upgrades only missing I2S mappings in stale profiles.

No owner firmware, QEMU, SD card or guest RAM required.
"""
from pathlib import Path
import tempfile
import os
import queue
from types import SimpleNamespace
from unittest.mock import patch
from auto_driver import profile_with_lcd
from factory_control_panel import EmulatorWorker


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
    # Start GUI's real worker only up to its first status update. This
    # checks the initialization order and chord selection WITHOUT booting
    # QEMU or accessing proprietary OSUP/media, and catches using args
    # before 'args = self.args' inside start_vm().
    class StopAtStatus(Exception):
        pass

    for bus, release, expected in ((None, 1.2, 1.2),
                                   ("2", 1.2, 4.0),
                                   ("2", 2.5, 2.5)):
        with tempfile.TemporaryDirectory() as td:
            args = SimpleNamespace(release_at=release, output_dir=Path(td))
            worker = EmulatorWorker(args, queue.Queue(), queue.Queue())
            def abort_on_first_status(*_):
                raise StopAtStatus()
            worker.post = abort_on_first_status
            with patch.dict(os.environ,
                            {"EXESX_BU21029_LPI2C_BUS": bus} if bus else {},
                            clear=False):
                if bus is None:
                    os.environ.pop("EXESX_BU21029_LPI2C_BUS", None)
                try:
                    worker.start_vm("menu")
                except StopAtStatus:
                    pass
                else:
                    raise AssertionError("GUI worker did not reach a status update")
            assert worker.boot_chord_seconds == expected, (
                bus, release, worker.boot_chord_seconds, expected)
    print("PASS factory profile backfill: stale I2S0/I2S1 fixed, LCD preserved, idempotent")
    print("PASS factory GUI: boot chord initialized before use; BU21029 default 4s / explicit override")


if __name__ == "__main__":
    run()
