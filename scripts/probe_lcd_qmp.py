#!/usr/bin/env python3
"""QMP framebuffer export regression: actual ARM LCD writes, two host samples.

Cross-platform. No OSUP, no periodic guest timers, no proprietary pixels.
"""
import argparse
import os
from pathlib import Path
import tempfile
import time

from drive_factory_menu import QMP, choose_port, connect
from lcd_qmp import capture_frame, FRAME_BYTES
from probe_lcd_screenshot import make_elf
import subprocess

def run(qemu, profile):
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        elf = root / "synthetic.elf"
        ini = root / "lcd-profile.ini"
        elf.write_bytes(make_elf())
        ini.write_text(profile.read_text(encoding="utf-8") +
                       "\n[synthetic-lcd]\nkind=exesx-lcd\nbase=0xb0000000\nsize=0x1000\n")
        env = os.environ.copy()
        env.update(EXESX_MEMORY_PROFILE=str(ini.resolve()),
                   EXESX_EXPERIMENTAL_LCD="1",
                   EXESX_LCD_FRAMEBUFFER_EXPORT="1")
        lib = qemu.resolve().parent / "lib"
        if lib.is_dir():
            env["LD_LIBRARY_PATH"] = str(lib) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
        port = choose_port()
        cmd = [str(qemu.resolve()), "-machine", "exesx", "-m", "64M",
               "-accel", "tcg", "-display", "none", "-serial", "none",
               "-monitor", "none", "-no-reboot",
               "-device", "loader,file={},cpu-num=0".format(elf.resolve()),
               "-S", "-qmp", "tcp:127.0.0.1:{},server=on,wait=off".format(port)]
        # Windows anonymous stderr pipes are small; QEMU machine-init
        # diagnostics can fill an unread pipe and deadlock QMP after greeting.
        # Use a host-private file so the QMP thread can always make progress.
        with (root / "qemu-console-private.log").open("wb") as diag, subprocess.Popen(
                cmd, env=env, stdout=diag, stderr=subprocess.STDOUT) as proc:
            try:
                with connect(port, proc) as sock:
                    qmp = QMP(sock)
                    qmp.execute("cont")
                    time.sleep(.4)
                    for i in (1, 2):
                        raw = capture_frame(qmp, root / "rgb565-{}.raw".format(i),
                                            root / "screen-{}.ppm".format(i))
                        assert len(raw) == FRAME_BYTES
                        # Original ARM code writes red, green, blue, red
                        assert raw[:8] == bytes.fromhex("00f8e0071f0000f8"), raw[:8].hex()
                        ppm = (root / "screen-{}.ppm".format(i)).read_bytes()
                        assert ppm.startswith(b"P6\n864 480\n255\n")
                        assert ppm[15:27] == bytes((255,0,0,0,255,0,0,0,255,255,0,0))
            finally:
                proc.terminate()
                try: proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
    print("PASS native ARM RGB565 LCD export: two QMP pmemsave readbacks and exact pixels")

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--qemu", type=Path, required=True)
    p.add_argument("--profile", type=Path, required=True)
    a = p.parse_args()
    run(a.qemu, a.profile)
