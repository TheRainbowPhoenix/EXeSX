"""Firmware-free checks for standalone recovery script and release integrity."""
import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "recover_exesx.py"
SPEC = importlib.util.spec_from_file_location("exesx_recover", SCRIPT)
R = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(R)


class TestRecovery(unittest.TestCase):
    def test_check_sha256_good_and_bad(self):
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / R.ARCHIVE
            a.write_bytes(b"firmware-free test tar placeholder")
            checksum = hashlib.sha256(a.read_bytes()).hexdigest()
            self.assertEqual(R.validate_hashes(checksum + "  " + a.name, a), checksum)
            with self.assertRaises(ValueError):
                R.validate_hashes("0" * 64 + "  " + a.name, a)
            with self.assertRaises(ValueError):
                R.validate_hashes(checksum + "  wrong-file.tar.gz", a)

    def test_accept_known_tree_and_reject_path_traversal(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            good = root / "good.tar.gz"
            with tarfile.open(good, "w:gz") as tar:
                for filename in ("qemu-system-arm", "prepare_osup.py",
                                 "run_firmware.py", "profiles/imx7ulp-early-boot.ini"):
                    content = b"#!/usr/bin/env python3\n"
                    info = tarfile.TarInfo(R.ROOT + "/" + filename)
                    info.size = len(content)
                    tar.addfile(info, io.BytesIO(content))
            dest = R.unpack_verified(good, root / "ok")
            self.assertTrue((dest / "qemu-system-arm").is_file())
            bad = root / "bad.tar.gz"
            with tarfile.open(bad, "w:gz") as tar:
                content = b"danger"
                info = tarfile.TarInfo(R.ROOT + "/../../escape")
                info.size = len(content)
                tar.addfile(info, io.BytesIO(content))
            with self.assertRaises(ValueError):
                R.unpack_verified(bad, root / "notok")
            self.assertFalse((root / "escape").exists())

    def test_no_symlink_extract(self):
        with tempfile.TemporaryDirectory() as d:
            tarpath = Path(d) / "link.tar.gz"
            with tarfile.open(tarpath, "w:gz") as tar:
                info = tarfile.TarInfo(R.ROOT + "/qemu-system-arm")
                info.type = tarfile.SYMTYPE
                info.linkname = "/etc/passwd"
                tar.addfile(info)
            with self.assertRaises(ValueError):
                R.unpack_verified(tarpath, Path(d) / "extract")


if __name__ == "__main__":
    unittest.main()
