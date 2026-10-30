#!/usr/bin/env python3
"""Native ARM A/B test for opt-in diagnostic LCD PWM, not unknown DY357 vendor registers.

An actual ARM guest writes DCS 0x51 twice in separate QEMU boots.
The read-only host interface reports distinct idealized PWM pulse widths;
original raw RGB565 framebuffer content must remain identical.
"""
import argparse
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import time

from drive_factory_menu import QMP, choose_port, connect
from lcd_qmp import capture_frame
from probe_lcd_landscape import make_elf

DIVISOR = 0x1239
PERIOD_NS = (DIVISOR * 1000000000 + 8000000) // 16000000


def one_boot(qemu, profile, duty):
    with tempfile.TemporaryDirectory() as temp:
        d = Path(temp)
        elf = d / "pwm-dcs.elf"
        elf.write_bytes(make_elf(brightness=duty))
        ini = d / "profile.ini"
        ini.write_text(profile.read_text() +
                       "\n[lcd-pwm-test]\nkind=exesx-lcd\nbase=0xb0000000\nsize=0x1000\n")
        env = os.environ.copy()
        env.update(EXESX_MEMORY_PROFILE=str(ini.resolve()),
                   EXESX_EXPERIMENTAL_LCD="1",
                   EXESX_LCD_FRAMEBUFFER_EXPORT="1",
                   EXESX_EXPERIMENTAL_LCD_PWM_DIAGNOSTIC="1")
        lib = qemu.resolve().parent / "lib"
        if lib.is_dir():
            env["LD_LIBRARY_PATH"] = str(lib.resolve()) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
        port = choose_port()
        command = [str(qemu.resolve()), "-machine", "exesx", "-m", "64M",
                   "-accel", "tcg,thread=single", "-display", "none", "-serial", "none",
                   "-monitor", "none", "-no-reboot", "-S",
                   "-qmp", "tcp:127.0.0.1:%d,server=on,wait=off" % port,
                   "-device", "loader,file=%s,cpu-num=0" % elf.resolve()]
        with (d / "console.log").open("wb") as log:
            proc = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL,
                                    stdout=log, stderr=subprocess.STDOUT)
            try:
                with connect(port, proc) as sock:
                    qmp = QMP(sock)
                    qmp.execute("cont")
                    time.sleep(.4)
                    dest = d / "status.bin"
                    qmp.hmp('pmemsave 0xb1100000 64 "%s"' % dest.as_posix())
                    words = struct.unpack("<16I", dest.read_bytes())
                    framebuffer = capture_frame(qmp, d / "lcd.rgb565")
                    return words, framebuffer
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()


def run(qemu, profile):
    results = {}
    for duty in (0x40, 0xc0):
        words, frame = one_boot(qemu, profile, duty)
        assert words[0] == 0x3144434c, words
        assert words[15] == 0x50574d31, "opt-in PWM diagnostic not enabled"
        assert words[12] == DIVISOR and words[13] == 16000000 // DIVISOR, words
        assert words[8] == PERIOD_NS, words
        expected_high = (PERIOD_NS * duty + 127) // 255
        assert words[9] == expected_high, (duty, words[9], expected_high)
        assert words[11] == (duty * 10000 + 127) // 255, words
        assert words[14] == duty, words
        assert words[10] in (0, 1), words
        results[duty] = (words, frame)
        print("PWM diagnostic duty=%d/255 period=%d ns HIGH=%d ns freq=%d Hz" %
              (duty, words[8], words[9], words[13]), flush=True)
    low, high = results[0x40], results[0xc0]
    assert high[0][9] > low[0][9] * 2, "PWM high pulse does not respond to duty"
    assert high[0][8] == low[0][8], "frequency must not change with brightness"
    assert low[1] == high[1], "PWM diagnostics must not alter original RGB565 GRAM"
    print("PASS independent ARM DCS 0x51 values produce distinct virtual PWM "
          "pulse widths, same period, unchanged RGB565 framebuffer", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", required=True, type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    args = parser.parse_args()
    run(args.qemu, args.profile)
