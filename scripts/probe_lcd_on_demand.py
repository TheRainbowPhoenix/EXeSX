#!/usr/bin/env python3
"""Two host-requested LCD snapshots after real ARM pixel MMIO; no ROM needed."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile
import time

from probe_lcd_screenshot import make_elf


def run(qemu, profile):
    with tempfile.TemporaryDirectory() as work:
        base = Path(work)
        elf = base / "lcd-real-arm.elf"
        ini = base / "profile.ini"
        request = base / "lcd-request.txt"
        elf.write_bytes(make_elf())
        ini.write_text(profile.read_text(encoding="utf-8") +
                       "\n[synthetic-lcd]\nkind=exesx-lcd\nbase=0xb0000000\nsize=0x1000\n")
        env = os.environ.copy()
        env.update(EXESX_MEMORY_PROFILE=str(ini),
                   EXESX_EXPERIMENTAL_LCD="1",
                   EXESX_LCD_CAPTURE_REQUEST_FILE=str(request.resolve().as_posix()))
        if (qemu.resolve().parent / "lib").is_dir():
            env["LD_LIBRARY_PATH"] = (
                str(qemu.resolve().parent / "lib") + os.pathsep +
                env.get("LD_LIBRARY_PATH", ""))
        cmd = [str(qemu.resolve()), "-machine", "exesx", "-m", "64M",
               "-accel", "tcg", "-display", "none", "-serial", "none",
               "-monitor", "none", "-no-reboot",
               "-device", f"loader,file={elf},cpu-num=0"]
        with subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL,
                              stderr=subprocess.PIPE) as qemu_proc:
            try:
                for index in (1, 2):
                    image = base / f"requested-{index}.ppm"
                    staging = base / "staging.txt"
                    staging.write_text(image.resolve().as_posix() + "\n", encoding="utf-8")
                    os.replace(staging, request)
                    deadline = time.monotonic() + (18 if os.name == "nt" else 5)
                    while time.monotonic() < deadline:
                        if image.exists():
                            data = image.read_bytes()
                            if len(data) == 1244175:
                                break
                        if qemu_proc.poll() is not None:
                            raise AssertionError("QEMU exited before requested LCD capture")
                        time.sleep(.05)
                    else:
                        raise AssertionError("QEMU did not complete on-demand screenshot; request_exists={} image_exists={} size={} qemu_exit={}".format(request.exists(), image.exists(), image.stat().st_size if image.exists() else None, qemu_proc.poll()))
                    if not data.startswith(b"P6\n864 480\n255\n"):
                        raise AssertionError("Invalid P6 screenshot format")
                    if data[15:27] != bytes([255,0,0,0,255,0,0,0,255,255,0,0]):
                        raise AssertionError(f"Native ARM LCD pixel path wrong: {data[15:27].hex()}")
                    if request.exists():
                        raise AssertionError("QEMU did not consume screenshot request")
            finally:
                qemu_proc.terminate()
                try:
                    qemu_proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    qemu_proc.kill()
                    qemu_proc.wait()
    print("PASS: two separate on-demand captures, exact genuine ARM MMIO pixels, no continuous PPM writes")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--qemu", type=Path, default=Path("build/qemu-system-arm"))
    p.add_argument("--profile", type=Path, default=Path("profiles/imx7ulp-early-boot.ini"))
    a = p.parse_args()
    run(a.qemu, a.profile)
