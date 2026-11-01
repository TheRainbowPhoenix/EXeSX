#!/usr/bin/env python3
"""Explicit opt-in original OSUP TEST MENU regression (private CI only).

Never runs on fork pull requests or automatically downloads ROM from a
public release. The maintainer supplies an access-controlled URL, SHA-256,
and optional bearer token via Actions secrets. Prints no URL or token.
Owner ROM and extracted media stay in a temporary directory and are not
uploaded as Actions artifacts.
"""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen

MAX_ROM = 128 * 1024 * 1024


def retrieve_private_osup(url, expected_sha256, dest, token=None):
    if not url.startswith("https://"):
        raise ValueError("private fixture URL must use HTTPS")
    if len(expected_sha256) != 64 or any(c not in "0123456789abcdef"
                                         for c in expected_sha256.lower()):
        raise ValueError("missing or invalid required OSUP SHA256")
    headers = {"User-Agent": "EXeSX-private-ROM-regression"}
    if token:
        headers["Authorization"] = "Bearer " + token
    digest = hashlib.sha256()
    length = 0
    with urlopen(Request(url, headers=headers), timeout=35) as response:
        with dest.open("wb") as out:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                length += len(chunk)
                if length > MAX_ROM:
                    raise ValueError("private fixture too large")
                digest.update(chunk)
                out.write(chunk)
    if length < 1024 or digest.hexdigest() != expected_sha256.lower():
        dest.unlink(missing_ok=True)
        raise ValueError("private firmware size or SHA-256 mismatch")
    return length


def run(qemu, profile, url, sha256, token=None):
    with tempfile.TemporaryDirectory(prefix="exesx-owner-private-") as root:
        p = Path(root)
        osup = p / "OSUP.BIN"
        size = retrieve_private_osup(url, sha256, osup, token)
        print("Private OSUP SHA-256 verified, {} bytes.".format(size),
              flush=True)
        cmd = [
            sys.executable, str(Path(__file__).with_name(
                "headless_factory_menu_checks.py")), str(osup),
            "--qemu", str(qemu),
            "--profile", str(profile),
            "--output-dir", str(p / "private-boot-capture"),
            "--tcg-thread", "single",
            "--seconds", "210",
            "--retries", "8",
            "--retry-after", "24",
            "--release-at", "4",
            "--adc0-sample", "0x7000",
            "--adc1-sample", "0x7000",
        ]
        # The original guest and host-generated logs stay in the private
        # temp directory and are deleted on process exit. Only report
        # checkpoint names and exit code, never output ROM bytes/media.
        completed = subprocess.run(cmd, timeout=300, check=False)
        if completed.returncode:
            raise RuntimeError("original TEST MENU failed; code {}".format(
                completed.returncode))
        print("PASS original unchanged TEST MENU and physical DOWN "
              "navigation; screenshot generated transiently.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    args = parser.parse_args()
    url = os.environ.get("EXESX_PRIVATE_OSUP_URL")
    sha = os.environ.get("EXESX_PRIVATE_OSUP_SHA256")
    if not url or not sha:
        parser.error("maintainer must configure two private fixture secrets")
    try:
        run(args.qemu.resolve(), args.profile.resolve(), url, sha,
            os.environ.get("EXESX_PRIVATE_ASSET_TOKEN"))
    except Exception as exc:
        # Never print url, bearer headers or private OSUP content.
        parser.exit(2, "Original private OSUP regression failed: {}.\n".format(
            type(exc).__name__))


if __name__ == "__main__":
    main()
