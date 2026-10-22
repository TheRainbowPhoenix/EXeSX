"""Firmware-free regression of one-command OSUP synthetic storage builder."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
spec=importlib.util.spec_from_file_location("run_osup",ROOT/"scripts/run_osup.py")
runner=importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
from test_analyze_osup_install_layout import fixture


class RunOSUPTests(unittest.TestCase):
    def test_private_synthetic_storage_and_manifest(self):
        data=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            osup=base/"OSUPD.bin"
            osup.write_bytes(data)
            sections=[("bios",0x60000000,0x60000000,b"\x00"*16),
                      ("os",0x60400000,0x60400000,b"\x11"*16)]
            with patch.object(runner.prepare_osup,"extract",
                              return_value=(sections,"synthetic-only")):
                elf,media,report=runner.prepare(osup,base/"out")
            self.assertTrue(elf.read_bytes().startswith(b"\x7fELF"))
            self.assertFalse(report["actual_media"])
            self.assertEqual([c["user_lba"] for c in report["user_components"]],
                             [0,2,4])
            self.assertEqual(media.stat().st_size,
                             runner.layout.QEMU_SYNTHETIC_SIZE)
            with media.open("rb") as card:
                card.seek(runner.layout.BOOT_SIZE)
                self.assertEqual(card.read(12),b"CASIOPVOS800")
                card.seek(runner.layout.BOOT_SIZE+32*512)
                self.assertEqual(card.read(12),b"CASIOPVOS800")
                user=2*runner.layout.BOOT_SIZE
                for lba, tag in ((0,b"B"),(2,b"A"),(4,b"F")):
                    card.seek(user+lba*512)
                    self.assertEqual(card.read(12),b"CASIODICS06"+tag)
                card.seek(user+6*512)
                self.assertEqual(card.read(512),bytes(512))
            self.assertTrue((base/"out"/"manifest.json").exists())



    def test_private_runner_gpiob3_diagnostic_is_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            qemu, elf, media, profile = (
                base/"qemu-system-arm", base/"a7.elf",
                base/"card.raw", base/"board.ini")
            for file in (qemu, elf, media):
                file.write_bytes(b"fixture")
            profile.write_text("[test]\nkind=ram\n", encoding="utf-8")
            for gpio_high, expected in ((False, "0x80"), (True, "0x88")):
                dest = base/("high" if gpio_high else "control")
                dest.mkdir()
                with patch.object(runner.subprocess, "run") as mock_run:
                    runner.launch(qemu, elf, media, profile, dest, 1.0, False,
                                  None, dma1_m2m=True, gpiob3_high=gpio_high)
                env = mock_run.call_args.kwargs["env"]
                self.assertEqual(env["EXESX_GPIOB_INPUT_MASK"], expected)
                self.assertEqual(env["EXESX_EXPERIMENTAL_DMA1_M2M"], "1")
                self.assertEqual(mock_run.call_args.kwargs["timeout"], 1.0)

if __name__=="__main__":
    unittest.main()
