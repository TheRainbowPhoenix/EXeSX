"""Firmware-free validation of the original-ROM menu sweep planner and retries."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import sweep_original_menus as sweep


class SweepTests(unittest.TestCase):
    def test_manifest_covers_wlan_and_marks_unsafe_actions(self):
        cases = {case.key: case for case in sweep.all_cases()}
        self.assertGreaterEqual(len(cases), 35)
        self.assertEqual(cases["wlan-version-check"].route,
                         (1, 8, 4, 2))
        self.assertEqual(cases["wlan-get-mac"].route,
                         (1, 8, 5, 1))
        self.assertEqual(cases["wlan-rssi"].route, (1, 8, 1, 1))
        self.assertEqual(cases["factory-wifi-auto-usb"].route, (8,))
        self.assertEqual(cases["wlan-firmware-update"].kind, "unsafe")
        self.assertEqual(cases["wlan-dhcp"].kind, "blocked")
        self.assertEqual(len({c.key for c in cases.values()}), len(cases))
        self.assertGreaterEqual(
            len([c for c in sweep.ROOT_UNMAPPED]), 10)

    def test_original_wlan_route_cannot_be_confused_with_display(self):
        captured = sweep.ORIGINAL_WLAN_ROUTE_HEADERS
        for route, heading in captured.items():
            sweep.require_original_menu_header(route, heading)
        # Original DISPLAY MENU heading from previous original-ROM run.
        wrong_display = "9713b41f998d654760eb741eab783f1ef3ab0b64d043792843717e110e33bc29"
        with self.assertRaisesRegex(RuntimeError, "heading mismatch"):
            sweep.require_original_menu_header((1, 8, 1), wrong_display)
        with self.assertRaisesRegex(RuntimeError, "heading mismatch"):
            sweep.require_original_menu_header((1, 8), "not-the-wlan-header")
        # Unmapped test results remain UNKNOWN, not a guessed PASS.
        sweep.require_original_menu_header((1, 8, 1, 1), "unverified-result")

    def test_nested_manual_menu_requires_original_row_captions(self):
        from ci_e2e_display_advanced import HEADERS
        # These two original menus reuse the same title, so a generic
        # changed-frame or header-only check was a false RSSI result.
        with self.assertRaisesRegex(RuntimeError, "identical titles"):
            sweep.require_original_menu_header(
                (1,), HEADERS["manual-menu"], bytes(864 * 480 * 3))
        with self.assertRaisesRegex(RuntimeError, "identical titles"):
            sweep.require_original_menu_header(
                (1,), HEADERS["manual-menu"])
        self.assertEqual(
            len(sweep.ORIGINAL_MANUAL_CHECK_ROWS_SHA256), 64)

    def test_no_backend_does_not_mark_wlan_pass(self):
        class Config:
            winc_port = None
            fixture_ssid = None
        c = Config()
        for name in ("wlan-version-check", "wlan-get-mac", "wlan-rssi",
                     "factory-wifi-auto-usb", "wlan-firmware-update"):
            case = next(x for x in sweep.all_cases() if x.key == name)
            self.assertTrue(sweep.skip_reason(case, c))

    def test_list_without_private_rom_or_firmware(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = sweep.main(["--list", "--scope", "all"])
        self.assertEqual(status, 0)
        rows = json.loads(output.getvalue())
        self.assertTrue(any(x["case"] == "wlan-get-mac" for x in rows))
        self.assertTrue(next(x for x in rows if x["case"] ==
                             "factory-wifi-auto-usb")["skip"])

    def test_retry_reboots_then_writes_machine_readable_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("qemu", "profile", "elf", "emmc", "sd"):
                (root / name).write_bytes(b"placeholder")
            args = []
            for name in ("qemu", "profile", "elf", "emmc", "sd"):
                args.extend(("--" + name, str(root / name)))
            args += ["--output", str(root / "results"),
                     "--scope", "all", "--only", "wlan-version-check",
                     "--winc-port", "50991", "--attempts", "2"]
            success = {"status": "SCREEN_OBSERVED_NOT_HARDWARE_VERDICT",
                       "tcg": "single", "media_snapshot": True}
            with patch.object(sweep, "run_case",
                              side_effect=[RuntimeError("missed physical key"),
                                           success]) as run:
                with contextlib.redirect_stdout(io.StringIO()):
                    code = sweep.main(args)
            self.assertEqual(code, 0)
            self.assertEqual(run.call_count, 2)
            report = json.loads((root / "results" /
                                 "summary.json").read_text())
            item = report["cases"]["wlan-version-check"]
            self.assertEqual(item["attempt"], 2)
            self.assertEqual(item["status"],
                             "SCREEN_OBSERVED_NOT_HARDWARE_VERDICT")
            self.assertTrue((root / "results" /
                             "wlan-version-check" / "attempt-1" /
                             "private-error.txt").exists())


if __name__ == "__main__":
    unittest.main()
