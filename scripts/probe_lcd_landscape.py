#!/usr/bin/env python3
"""Real firmware-free ARM test for DY357 landscape MADCTL and window clipping.

Requires EXeSX QEMU; generates its own guest, with no Casio code or pixels.
Checks RGB565/window wrap plus 0x60 landscape and actual 0x40 portrait
controller mode used by FUN_601B25E4's firmware-transposed framebuffer.
"""
import argparse
import os
from pathlib import Path
import struct
import subprocess
import tempfile

W, H = 864, 480
ENTRY = 0x60000000


def make_elf(brightness=0x80, shadow_duty=None, shadow_divisor=None):
    instructions, fixups = [], []

    def op(word):
        instructions.append(word)

    def lit(reg, value):
        fixups.append((len(instructions), reg, value))
        op(0)

    def store(reg, base, offset):
        op(0xe5800000 | base << 16 | reg << 12 | offset)

    def half(reg, base):
        op(0xe1c000b0 | base << 16 | reg << 12)

    lit(4, 0x400f0000)  # GPIOA
    lit(5, 0xb0000000)  # LCD 16-bit DBI
    lit(6, 0x10000)     # D/C select GPIOA16

    def command(value):
        store(6, 4, 8)  # GPIOA.PCOR, command
        lit(1, value)
        half(1, 5)
        store(6, 4, 4)  # GPIOA.PSOR, data

    def data(value):
        lit(1, value)
        half(1, 5)

    def bounds(command_id, start, end):
        command(command_id)
        for value in (start >> 8, start & 255, end >> 8, end & 255):
            data(value)

    command(0x3a)
    data(0x55)  # RGB565
    command(0x36)
    data(0x60)  # Actual DY357 landscape orientation
    bounds(0x2a, 431, 433)
    bounds(0x2b, 239, 240)
    command(0x2c)
    for color in (0xf800, 0x07e0, 0x001f, 0xf81f, 0x07ff, 0xffe0):
        data(color)
    data(0xffff)  # Beyond 3x2 window: must NOT overwrite an adjacent pixel.

    # Regression for old X/Y transpose: x=700 would previously become
    # page y=700 and vanish from the 480-high screenshot.
    bounds(0x2a, 700, 701)
    bounds(0x2b, 100, 100)
    command(0x2c)
    data(0xf800)
    data(0x07e0)

    # Actual OSUP path: FUN_601B25E4 pre-transposes the 864x480 source,
    # then FUN_60015328(1) selects 0x40 and CASET 0..479/PASET 0..863.
    # Synthetic 2x3 portrait-window stream must appear as landscape 3x2.
    command(0x36)
    data(0x40)
    bounds(0x2a, 160, 161)
    bounds(0x2b, 304, 306)
    command(0x2c)
    for color in (0xf800, 0x07e0, 0x001f, 0xf81f, 0x07ff, 0xffe0):
        data(color)
    data(0xffff)  # Must not escape the 2x3 controller window.

    # The portrait controller row (0..863) is NOT a 480-high screenshot Y.
    bounds(0x2a, 12, 12)
    bounds(0x2b, 700, 701)
    command(0x2c)
    data(0xf800)
    data(0x07e0)

    # FUN_60015328(0) restores 0x60 for direct landscape drawing.
    command(0x36)
    data(0x60)
    bounds(0x2a, 400, 400)
    bounds(0x2b, 200, 200)
    command(0x2c)
    data(0xf800)
    # Native ARM DCS/display status and raw vendor B2 control write.
    for cmd in (0x11, 0x29, 0x21, 0x39):
        command(cmd)
    command(0x51)
    data(brightness)
    command(0xb2)
    for v in (0x10, 0x20, 0x30, 0x40, 0x50):
        data(v)
    if shadow_duty is not None or shadow_divisor is not None:
        if shadow_duty is None or shadow_divisor is None:
            raise ValueError("PWM shadow requires both duty and divisor")
        lit(0, 0x62344f3c)  # owner-original firmware PWM_FREQ variable
        lit(1, shadow_divisor)
        store(1, 0, 0)
        lit(0, 0x62413262)  # original BACKLIGHT DUTY variable
        lit(1, shadow_duty)
        half(1, 0)
    op(0xeafffffe)

    pool = len(instructions)
    for index, (pos, reg, value) in enumerate(fixups):
        offset = (pool + index - pos) * 4 - 8
        if not 0 <= offset <= 4095:
            raise ValueError("Synthetic ARM literal pool too far away")
        instructions[pos] = 0xe59f0000 | reg << 12 | offset
        instructions.append(value)

    body = struct.pack("<%dI" % len(instructions), *instructions)
    ident = b"\x7fELF\x01\x01\x01" + bytes(9)
    header = struct.pack("<16sHHIIIIIHHHHHH", ident, 2, 40, 1,
                         ENTRY, 52, 0, 0x05000000, 52, 32, 1, 0, 0, 0)
    phdr = struct.pack("<8I", 1, 0x100, ENTRY, ENTRY,
                       len(body), len(body), 5, 0x100)
    return header + phdr + bytes(0x100 - len(header) - len(phdr)) + body


def verify(ppm):
    raw = ppm.read_bytes()
    header = f"P6\n{W} {H}\n255\n".encode()
    if not raw.startswith(header) or len(raw) != len(header) + W * H * 3:
        raise AssertionError("LCD PPM screenshot missing or wrong size")
    pix = memoryview(raw)[len(header):]

    def pixel(x, y):
        start = 3 * (y * W + x)
        return tuple(pix[start:start + 3])

    colors = {
        (431, 239): (255, 0, 0),
        (432, 239): (0, 255, 0),
        (433, 239): (0, 0, 255),
        (431, 240): (255, 0, 255),
        (432, 240): (0, 255, 255),
        (433, 240): (255, 255, 0),
        (700, 100): (255, 0, 0),
        (701, 100): (0, 255, 0),
        # Portrait 480x864 window written in row-major controller order
        # must be transposed on presentation to normal 864x480 LCD.
        (304, 160): (255, 0, 0),
        (304, 161): (0, 255, 0),
        (305, 160): (0, 0, 255),
        (305, 161): (255, 0, 255),
        (306, 160): (0, 255, 255),
        (306, 161): (255, 255, 0),
        (700, 12): (255, 0, 0),
        (701, 12): (0, 255, 0),
        (400, 200): (255, 0, 0),
        (307, 160): (0, 0, 0),
        (304, 162): (0, 0, 0),
        (702, 12): (0, 0, 0),
        (430, 239): (0, 0, 0),
        (434, 239): (0, 0, 0),
        (432, 238): (0, 0, 0),
        (432, 241): (0, 0, 0),
        (702, 100): (0, 0, 0),
        (0, 0): (0, 0, 0),
    }
    for xy, expected in colors.items():
        actual = pixel(*xy)
        if actual != expected:
            raise AssertionError(f"LCD pixel {xy}: {actual}, expected {expected}")
    print("PASS original DY357 MADCTL 0x60 landscape plus 0x40 "
          "pre-transposed 480x864 window, clipping, pixel order and "
          "restored 0x60")


def run(qemu, profile):
    with tempfile.TemporaryDirectory() as d:
        folder = Path(d)
        elf = folder / "lcd-landscape-synthetic.elf"
        ppm = folder / "lcd-landscape-synthetic.ppm"
        ini = folder / "lcd-profile.ini"
        elf.write_bytes(make_elf())
        ini.write_text(profile.read_text() +
                       "\n[lcd-landscape-probe]\nkind=exesx-lcd\n"
                       "base=0xb0000000\nsize=0x1000\n")
        env = os.environ.copy()
        env["EXESX_MEMORY_PROFILE"] = str(ini.resolve())
        env["EXESX_EXPERIMENTAL_LCD"] = "1"
        env["EXESX_LCD_FRAMEBUFFER_EXPORT"] = "1"
        library = qemu.resolve().parent / "lib"
        if library.is_dir():
            env["LD_LIBRARY_PATH"] = str(library) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
        # QMP pmemsave reads the genuine RGB565 frame synchronously,
        # independent of Windows guest-virtual-time screenshot timers.
        from drive_factory_menu import QMP, choose_port, connect
        from lcd_qmp import capture_frame
        import time
        port = choose_port()
        cmd = [str(qemu.resolve()), "-machine", "exesx", "-m", "64M",
               "-accel", "tcg", "-display", "none", "-serial", "none",
               "-monitor", "none", "-no-reboot",
               "-S", "-qmp", f"tcp:127.0.0.1:{port},server=on,wait=off",
               "-device", f"loader,file={elf.resolve()},cpu-num=0"]
        with (folder / "console-private.log").open("wb") as console:
            proc = subprocess.Popen(cmd, env=env, stdin=subprocess.DEVNULL,
                                    stdout=console, stderr=subprocess.STDOUT)
            try:
                with connect(port, proc) as sock:
                    qmp = QMP(sock)
                    qmp.execute("cont")
                    time.sleep(.5)
                    capture_frame(qmp, folder / "lcd-rgb565.raw", ppm)
                    state = folder / "lcd-dcs-state.bin"
                    qmp.hmp('pmemsave 0xb1100000 64 "{}"'.format(state.as_posix()))
                    words = struct.unpack("<16I", state.read_bytes())
                verify(ppm)
                assert words[0] == 0x3144434c, "DCS diagnostic window signature"
                assert words[1] & 0x3f == 0x3d, "display, sleep, inversion, idle state"
                assert words[2] == 0x000560b2, "vendor parameter length and MADCTL"
                assert words[3] & 255 == 0x80, "DCS brightness parameter"
                assert words[4] == 0x40302010, "vendor B2 bytes 0..3"
                assert words[5] & 255 == 0x50, "vendor B2 byte 4"
                assert words[6] == 0, "default path must not byte-swap"
                print("PASS ARM DCS state: display/inversion/idle/brightness and vendor B2 raw data")
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path,
                        default=Path("build/qemu-system-arm"))
    parser.add_argument("--profile", type=Path,
                        default=Path("profiles/imx7ulp-early-boot.ini"))
    args = parser.parse_args()
    run(args.qemu, args.profile)
