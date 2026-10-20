#!/usr/bin/env python3
"""Rebuild an EXeSX investigation from your own OSUP.BIN / OSUPD.bin.

Standalone: Python stdlib only for prebuilt Linux x86_64 mode.
  python3 recover_exesx.py /path/to/OSUP.BIN --workdir ~/exesx-recovered
Also works from a cold environment / independently of the repository:
  curl -fsSLO https://raw.githubusercontent.com/TheRainbowPhoenix/EXeSX/main/scripts/recover_exesx.py

Firmware is validated and extracted LOCALLY; never uploaded to GitHub.
The firmware-free compiled emulator is verified against SHA256SUMS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

REPO = "https://github.com/TheRainbowPhoenix/EXeSX"
RELEASE = REPO + "/releases/download/dev-native/"
ARCHIVE = "exesx-qemu-linux-x86_64.tar.gz"
ROOT = "exesx-qemu-linux-x86_64"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fd:
        for chunk in iter(lambda: fd.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def get_file(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".part")
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": "EXeSX-recovery/1"}),
            timeout=90,
        ) as response, temp.open("wb") as dst:
            shutil.copyfileobj(response, dst)
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)


def validate_hashes(checksums: str, archive: Path) -> str:
    for line in checksums.splitlines():
        parts = line.strip().split()
        if len(parts) == 2 and parts[1].lstrip("*") == archive.name:
            expected = parts[0].lower()
            if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
                raise ValueError("Malformed checksum")
            actual = sha256(archive)
            if actual != expected:
                raise ValueError(f"QEMU release SHA256 mismatch: {actual} != {expected}")
            return actual
    raise ValueError(f"No checksum for {archive.name} in SHA256SUMS")


def unpack_verified(archive: Path, destination: Path) -> Path:
    """Extract only regular files, with no traversal, symlinks or special nodes."""
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        if len(members) > 500:
            raise ValueError("Unexpected number of archive entries")
        for member in members:
            parts = Path(member.name).parts
            if not parts or parts[0] != ROOT or ".." in parts:
                raise ValueError(f"Unsafe archive path: {member.name}")
            if not (member.isfile() or member.isdir()):
                raise ValueError(f"Unsupported archive entry type: {member.name}")
            if member.size > 200 * 1024 * 1024:
                raise ValueError(f"Unreasonably large archive member: {member.name}")
            path = destination.joinpath(*parts)
            if member.isdir():
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                content = tar.extractfile(member)
                if content is None:
                    raise ValueError(f"Cannot read archive member {member.name}")
                with content, path.open("wb") as fd:
                    shutil.copyfileobj(content, fd)
                if member.mode & 0o111:
                    path.chmod(0o755)
    installed = destination / ROOT
    for name in ("qemu-system-arm", "prepare_osup.py", "run_firmware.py"):
        if not (installed / name).is_file():
            raise ValueError(f"Release archive missing {name}")
    if not (installed / "profiles" / "imx7ulp-early-boot.ini").is_file():
        raise ValueError("Release archive missing complete machine profile")
    return installed


def obtain_release(work: Path, force: bool = False) -> Path:
    if platform.system() != "Linux" or platform.machine() not in ("x86_64", "AMD64"):
        raise RuntimeError("Native release requires Linux x86_64; choose --mode source")
    cache = work / "cache"
    archive = cache / ARCHIVE
    checks = cache / "SHA256SUMS"
    # Always refresh checksum so a rolling dev-native release cannot silently
    # be mistaken for an old emulator from a prior session.
    get_file(RELEASE + "SHA256SUMS", checks)
    if force or not archive.is_file():
        get_file(RELEASE + ARCHIVE, archive)
    try:
        expected = validate_hashes(checks.read_text(), archive)
    except ValueError:
        # Publish tag is rolling: archive may have changed. Retry once.
        get_file(RELEASE + ARCHIVE, archive)
        get_file(RELEASE + "SHA256SUMS", checks)
        expected = validate_hashes(checks.read_text(), archive)
    dst = work / "native-release"
    installed = dst / ROOT
    if force or not (installed / "qemu-system-arm").is_file() or (
        (installed / ".verified-release-sha256").read_text().strip()
        if (installed / ".verified-release-sha256").is_file() else ""
    ) != expected:
        with tempfile.TemporaryDirectory(dir=work, prefix="extract-") as scratch:
            staged = unpack_verified(archive, Path(scratch))
            if installed.exists():
                shutil.rmtree(installed)
            dst.mkdir(exist_ok=True)
            shutil.move(str(staged), str(installed))
        (installed / ".verified-release-sha256").write_text(expected + "\n")
    return installed


def obtain_source(work: Path, force: bool = False) -> Path:
    source = work / "source"
    if not source.is_dir():
        subprocess.run(["git", "clone", "--depth", "1", REPO + ".git",
                        str(source)], check=True)
    elif force:
        subprocess.run(["git", "-C", str(source), "fetch", "--depth", "1",
                        "origin", "main"], check=True)
        subprocess.run(["git", "-C", str(source), "reset", "--hard",
                        "origin/main"], check=True)
    # QEMU 10.1.0 and build dependencies are downloaded by build.sh; see README.
    subprocess.run(["bash", str(source / "scripts" / "build.sh")],
                   check=True, cwd=source)
    return source


def recover(osup: Path, work: Path, mode: str, qemu_arg: Path | None,
            profile_arg: Path | None, seconds: float, force: bool) -> Path:
    work.mkdir(parents=True, exist_ok=True)
    if mode == "release":
        installed = obtain_release(work, force)
        qemu = installed / "qemu-system-arm"
        root = installed
        prepare = installed / "prepare_osup.py"
        runner = installed / "run_firmware.py"
    else:
        root = Path(__file__).resolve().parents[1] if mode == "local" else obtain_source(work, force)
        qemu = (qemu_arg or (root / "build" / "qemu-system-arm")).resolve()
        prepare = root / "scripts" / "prepare_osup.py"
        runner = root / "scripts" / "run_firmware.py"
    if qemu_arg:
        qemu = qemu_arg.resolve()
    profile = (profile_arg or root / "profiles" / "imx7ulp-early-boot.ini").resolve()
    for path in (qemu, prepare, runner, profile):
        if not path.is_file():
            raise FileNotFoundError(f"Required runtime file absent: {path}")
    private = work / "private"
    private.mkdir(exist_ok=True)
    private.chmod(0o700)
    firmware = private / "a7-firmware.elf"
    print(f"Validating and locally extracting {osup}", flush=True)
    subprocess.run([sys.executable, str(prepare), str(osup.resolve()),
                    "-o", str(firmware)], check=True)
    firmware.chmod(0o600)
    results = work / "results" / "latest"
    results.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["EXESX_EXPERIMENTAL_M4_BOOT"] = "1"
    cmd = [sys.executable, str(runner), str(firmware),
           "--qemu", str(qemu), "--profile", str(profile),
           "--seconds", str(seconds), "--results", str(results)]
    print("Starting experimental dual-core BIOS execution", flush=True)
    subprocess.run(cmd, env=env, check=True)
    record = {
        "input_file": str(osup.resolve()), "input_sha256": sha256(osup),
        "qemu": str(qemu), "profile": str(profile),
        "firmware_elf": str(firmware), "firmware_shared": False,
        "exesx_experimental_m4_boot": True, "results": str(results),
        "note": "Boot probe only; LCD and main menu are not established",
    }
    (results / "recovery.json").write_text(json.dumps(record, indent=2) + "\n")
    print("\nBoot logs:", results, flush=True)
    return results


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("osup", type=Path, help="locally owned OSUP.BIN or OSUPD.bin")
    p.add_argument("--workdir", type=Path, default=Path("exesx-recovery"))
    p.add_argument("--mode", choices=["release", "source", "local"],
                   default="release")
    p.add_argument("--qemu", type=Path, help="override executable path")
    p.add_argument("--profile", type=Path, help="override INI hardware profile")
    p.add_argument("--seconds", type=float, default=2.0)
    p.add_argument("--force", action="store_true", help="refresh or rebuild")
    args = p.parse_args()
    if args.seconds <= 0 or args.seconds > 120:
        p.error("--seconds must be in (0, 120]")
    if not args.osup.is_file():
        p.error("updater binary not found: " + str(args.osup))
    try:
        recover(args.osup, args.workdir.resolve(), args.mode, args.qemu,
                args.profile, args.seconds, args.force)
    except (OSError, ValueError, subprocess.CalledProcessError) as err:
        p.exit(1, f"EXeSX recovery failed: {err}\n")


if __name__ == "__main__":
    main()
