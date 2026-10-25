#!/usr/bin/env python3
"""Autodrive genuine DY357 factory-menu keys, capture LCD, check startup faults.

Works with Linux and Windows native EXeSX QEMU artifacts; Python stdlib only.
The two cold boots intentionally separate the popup screenshot from the menu
key sequence, so taking the first image cannot perturb key pulse timing.
Only physical GPIO/IOMUX contact files are changed; no ROM/IPC/CPU injection.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import time
import zlib

# Also support importlib-based unit tests from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from drive_factory_menu import QMP, connect, choose_port
from lcd_qmp import capture_frame

BOOT = "0x9c,0x90"
KEYS = ("0x93", "0x93", "0x94")
PC = {
    "version_dialog": 0x60010868,
    "event_wait": 0x600108a8,
    "first_check": 0x60010910,
    "third_check": 0x60010928,
    "third_key_success": 0x60010930,
    "factory_menu": 0x6003a878,
    "service_400b": 0x60006240,
    "service_return": 0x60006268,
    "menu_painter": 0x60057668,
}
FILTER = ("0x60048e08+0x40,0x60010868+0x140,0x6003a878+0x500,"
          "0x60006240+0x50,0x60057668+0x30")


def milestone_addresses(text):
    """Only executed TBs count, not raw string/disassembly mentions."""
    return {int(match, 16) for match in re.findall(
        r"^Trace \d+:.*?/00000000([0-9a-fA-F]{8})/", text, re.M)}


def ppm_stats(path):
    """Validate complete P6 RGB data; calculate real pixel statistics."""
    data = Path(path).read_bytes()
    header = re.match(rb"P6\s+([0-9]+)\s+([0-9]+)\s+255\s", data)
    if not header:
        raise ValueError("not a P6 8-bit RGB image")
    width, height = (int(v) for v in header.groups())
    if width != 864 or height != 480:
        raise ValueError("unexpected LCD size")
    raw = data[header.end():]
    if len(raw) != width * height * 3:
        raise ValueError("partial LCD screenshot")
    blacks = sum(raw[i:i+3] == b"\x00\x00\x00" for i in range(0, len(raw), 3))
    whites = sum(raw[i:i+3] == b"\xff\xff\xff" for i in range(0, len(raw), 3))
    return {"width": width, "height": height, "black_pixels": blacks,
            "white_pixels": whites, "other_pixels": width * height - blacks - whites,
            "sha256": hashlib.sha256(data).hexdigest()}


def convert_png(ppm, png):
    data = Path(ppm).read_bytes()
    header = re.match(rb"P6\s+([0-9]+)\s+([0-9]+)\s+255\s", data)
    if header is None:
        raise ValueError("not a P6 screenshot")
    width, height = map(int, header.groups())
    rgb = data[header.end():]
    stride = 3 * width
    scanlines = b"".join(b"\x00" + rgb[i:i+stride]
                         for i in range(0, len(rgb), stride))
    def chunk(kind, payload):
        return (struct.pack(">I", len(payload)) + kind + payload +
                struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff))
    png_data = (b"\x89PNG\r\n\x1a\n" +
                chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
                chunk(b"IDAT", zlib.compress(scanlines)) +
                chunk(b"IEND", b""))
    Path(png).write_bytes(png_data)


def request_capture(request, destination):
    """Atomic request: the emulator never reads a half-written pathname."""
    destination.unlink(missing_ok=True)
    staging = request.with_name(request.name + ".tmp")
    staging.write_text(destination.resolve().as_posix() + "\n", encoding="utf-8")
    os.replace(staging, request)


def optional_qemu_path(explicit):
    if explicit:
        return explicit.resolve()
    root = Path(__file__).resolve().parent.parent
    for name in ("qemu-system-arm.exe", "qemu-system-arm"):
        path = root / name
        if path.is_file():
            return path
    raise FileNotFoundError("Use --qemu PATH (or run from extracted Windows artifact)")


def prepare_media(args, output):
    if args.elf or args.emmc:
        if not args.elf or not args.emmc:
            raise ValueError("--elf and --emmc must both be provided")
        return args.elf.resolve(), args.emmc.resolve()
    if args.osup is None:
        raise ValueError("Provide your private OSUP.BIN or both --elf and --emmc")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from run_osup import prepare
    elf, emmc, _ = prepare(args.osup.resolve(), output / "private-firmware")
    return elf.resolve(), emmc.resolve()


def profile_with_lcd(path, output):
    text = path.read_text(encoding="utf-8")
    if "[diagnostic-flexbus-lcd]" not in text and "base=0xb0000000" not in text.lower():
        text += ("\n[diagnostic-flexbus-lcd]\nkind=exesx-lcd\n"
                 "base=0xb0000000\nsize=0x1000\n")
    destination = output / "local-profile-private.ini"
    destination.write_text(text, encoding="utf-8")
    return destination


def wait_for_image(path):
    try:
        return ppm_stats(path) if path.is_file() else None
    except (OSError, ValueError):
        return None  # QEMU may still be completing the file write.


def run_phase(args, phase, qemu, elf, emmc, profile, output):
    stage = output / phase
    stage.mkdir(parents=True, exist_ok=True)
    contacts = stage / "contacts-private.txt"
    capture_request = stage / "capture-request-private.txt"
    raw_frame = stage / "lcd-rgb565-private.raw"
    contacts.write_text(BOOT + "\n", encoding="ascii")
    capture_request.unlink(missing_ok=True)
    screenshot = output / ("version-dialog.ppm" if phase == "popup"
                           else "factory-test-menu.ppm")
    env = os.environ.copy()
    env.update({
        "EXESX_MEMORY_PROFILE": str(profile.resolve()),
        "EXESX_EXPERIMENTAL_M4_BOOT": "1",
        "EXESX_EXPERIMENTAL_MU_IRQ": "1",
        "EXESX_EXPERIMENTAL_LPIT1_IRQ": "1",
        "EXESX_EXPERIMENTAL_LPTMR_IRQ": "1",
        "EXESX_EXPERIMENTAL_LPTMR_PCS_CLOCKS": "1",
        "EXESX_EXPERIMENTAL_M4_PORT_IRQ": "1",
        "EXESX_EXPERIMENTAL_M4_TPM0_IRQ": "1",
        "EXESX_EXPERIMENTAL_M4_TPM0_INPUT_MHZ": str(args.tpm0_mhz),
        "EXESX_DIAGNOSTIC_A7_TPM6_KHZ": str(args.a7_tpm6_khz),
        "EXESX_EXPERIMENTAL_LCD": "1",
        "EXESX_LCD_FRAMEBUFFER_EXPORT": "1",
        "EXESX_EXPERIMENTAL_DMA1_M2M": "1",
        "EXESX_USDHC1_EMMC": "1",
        "EXESX_USDHC0_SD": "1" if args.sd else "0",
        "EXESX_USDHC0_SD_DETECT_GPIO": "1" if args.sd else "0",
        "EXESX_I2C4B_REGISTER_MIRROR": "1",
        "EXESX_I2C40_REGISTER_MIRROR": "1",
        "EXESX_SNVS_DIAGNOSTIC_SECURITY_PULSES": "1",
        "EXESX_GPIOA_INPUT_MASK": "0x808c6008",
        "EXESX_GPIOB_INPUT_MASK": "0xc8",
        "EXESX_M4_KEY_MATRIX_FILE": str(contacts.resolve()),
    })
    lib = qemu.parent / "lib"
    if lib.is_dir():
        env["LD_LIBRARY_PATH"] = str(lib) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    trace = stage / "execution-private.log"
    console = stage / "qemu-console-private.log"
    qmp_port = choose_port()
    command = [
        str(qemu), "-machine", "exesx", "-m", "64M",
        "-accel", "tcg", "-display", "none", "-serial", "none",
        "-monitor", "none", "-no-reboot",
        "-S", "-qmp", "tcp:127.0.0.1:{},server=on,wait=off".format(qmp_port),
        "-drive", "if=none,id=exesx-emmc,file={},format=raw,snapshot=on".format(emmc),
        "-device", "loader,file={},cpu-num=0".format(elf),
        "-d", "exec" + (",guest_errors" if args.guest_errors else ""),
        "-dfilter", FILTER, "-D", str(trace),
    ]
    if args.sd:
        command.extend(["-drive", "if=none,id=exesx-sd,file={},format=raw,snapshot=on".format(args.sd.resolve())])
    if args.sd and args.sd.stat().st_size < 2 * 1024**3:
        raise ValueError("Disposable SD must be >=2GiB")
    report = {"phase": phase, "checkpoints_seconds": {},
              "physical_contacts": [], "screenshot": None,
              "reason": None, "qemu_exit_code": None}
    first_seen = set()
    qmp_sock = None
    qmp = None
    sent = False
    capture_issued = False
    image_ready = False
    released = False
    menu_at = None
    t0 = time.monotonic()
    print("START", phase, flush=True)
    with console.open("wb") as log:
        process = subprocess.Popen(command, env=env, stdout=log,
                                   stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        try:
            qmp_sock = connect(qmp_port, process)
            qmp = QMP(qmp_sock)
            qmp.execute("cont")
            deadline = t0 + args.seconds
            while not trace.exists() and time.monotonic() < t0 + 8 and process.poll() is None:
                time.sleep(.02)
            if not trace.exists():
                report["reason"] = "trace not created"
                return report
            with trace.open("r", encoding="utf-8", errors="replace") as stream:
                pending = ""
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        report["reason"] = "QEMU exited before phase completed"
                        break
                    elapsed = time.monotonic() - t0
                    if not released and elapsed >= args.release_at:
                        contacts.write_text("0\n", encoding="ascii")
                        report["physical_contacts"].append(["release_boot", round(elapsed, 3)])
                        released = True
                    latest = stream.read()
                    if latest:
                        pending = (pending[-200:] + latest)[-40000:]
                        found = milestone_addresses(pending)
                        for label, pc in PC.items():
                            if label not in first_seen and pc in found:
                                first_seen.add(label)
                                report["checkpoints_seconds"][label] = round(elapsed, 3)
                                print(phase, label, round(elapsed, 2), flush=True)
                                if label == "factory_menu":
                                    menu_at = time.monotonic()
                    if (phase == "popup" and "event_wait" in first_seen and
                            elapsed - report["checkpoints_seconds"]["event_wait"] >= args.popup_settle_seconds and
                            not capture_issued):
                        # The original dialog PC precedes its actual glyph painting.
                        # Capture after this verified settle window or the PPM is blank.
                        capture_frame(qmp, raw_frame, screenshot)
                        capture_issued = True
                    if capture_issued and not image_ready:
                        image = wait_for_image(screenshot)
                        if image:
                            image_ready = True
                            report["screenshot"] = image
                    if phase == "popup" and image_ready and "event_wait" in first_seen:
                        report["reason"] = "popup screenshot captured before menu key presses"
                        break
                    if phase == "menu" and "event_wait" in first_seen and not sent:
                        sent = True
                        for key in KEYS:
                            contacts.write_text(key + "\n", encoding="ascii")
                            report["physical_contacts"].append(["press", key,
                                                                 round(time.monotonic()-t0, 3)])
                            time.sleep(args.hold)
                            contacts.write_text("0\n", encoding="ascii")
                            report["physical_contacts"].append(["release", key,
                                                                 round(time.monotonic()-t0, 3)])
                            time.sleep(args.gap)
                    if phase == "menu" and menu_at is not None:
                        if time.monotonic() - menu_at >= args.post_menu_seconds and not capture_issued:
                            capture_frame(qmp, raw_frame, screenshot)
                            capture_issued = True
                        if image_ready:
                            report["reason"] = "factory-menu framebuffer captured"
                            break
                    time.sleep(.02)
                else:
                    report["reason"] = "bounded timeout"
        finally:
            if qmp_sock is not None:
                qmp_sock.close()
            contacts.write_text("0\n", encoding="ascii")
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            report["qemu_exit_code"] = process.returncode
    if report["screenshot"] is not None:
        try:
            convert_png(screenshot, screenshot.with_suffix(".png"))
        except (OSError, ValueError) as exc:
            report["png_error"] = str(exc)
    # Never confuse a C terminate on purpose with a guest crash.
    report["terminated_by_driver"] = True
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("osup", nargs="?", type=Path, help="Private original OSUP.BIN; auto-prepare locally")
    p.add_argument("--qemu", type=Path)
    p.add_argument("--elf", type=Path)
    p.add_argument("--emmc", type=Path)
    p.add_argument("--profile", type=Path)
    p.add_argument("--sd", type=Path, help="Disposable raw SD image; snapshot-on, never write host disk")
    p.add_argument("--output-dir", type=Path, default=Path("private/factory-auto"))
    p.add_argument("--seconds", type=float, default=50,
                   help="Maximum wall seconds PER cold boot pass")
    p.add_argument("--release-at", type=float, default=1.2)
    p.add_argument("--hold", type=float, default=.060)
    p.add_argument("--gap", type=float, default=.025)
    p.add_argument("--post-menu-seconds", type=float, default=4)
    p.add_argument("--popup-settle-seconds", type=float, default=.6,
                   help="Host seconds after original A7 event wait to allow real dialog glyphs to paint")
    p.add_argument("--tpm0-mhz", type=int, default=48)
    p.add_argument("--a7-tpm6-khz", type=int, default=32)
    p.add_argument("--guest-errors", action="store_true",
                   help="Extra private QEMU MMIO/exception diagnostics; potentially very large")
    p.add_argument("--menu-only", action="store_true", help="Skip separate popup-only cold boot")
    p.add_argument("--attempts", type=int, default=3,
                   help="Fresh-boot retries per phase (timing-sensitive original firmware)")
    args = p.parse_args(argv)
    if args.attempts <= 0:
        p.error("--attempts must be positive")
    if args.seconds <= 0 or args.hold <= 0 or args.gap < 0 or args.release_at < 0 or args.post_menu_seconds < 0 or args.popup_settle_seconds < 0:
        p.error("invalid timing")
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    qemu = optional_qemu_path(args.qemu)
    if not qemu.is_file():
        p.error("missing QEMU binary: " + str(qemu))
    profile = args.profile or Path(__file__).resolve().parent.parent / "profiles" / "imx7ulp-early-boot.ini"
    if not profile.is_file():
        p.error("missing memory profile; specify --profile")
    elf, emmc = prepare_media(args, out)
    for name, path in (("ELF", elf), ("eMMC", emmc)):
        if not path.is_file():
            p.error("missing private " + name + " file " + str(path))
    local_profile = profile_with_lcd(profile, out)
    summary = {"emulation": "owner-private firmware, real physical key contacts",
               "boot_chord": BOOT, "menu_keys": list(KEYS), "phases": {},
               "screenshots_validated": False, "menu_entry_confirmed": False,
               "menu_paint_confirmed": False, "service_400b_return_confirmed": False,
               "read_only_menu_smoke": "no destructive SD actions executed"}
    for phase in (("menu",) if args.menu_only else ("popup", "menu")):
        tries = []
        for index in range(args.attempts):
            result = run_phase(args, phase, qemu, elf, emmc, local_profile, out)
            result["attempt"] = index + 1
            tries.append(result)
            achieved = (result.get("screenshot") is not None and
                        (phase == "popup" or
                         "factory_menu" in result.get("checkpoints_seconds", {})))
            if achieved:
                break
            print("RETRY", phase, index + 1, "reason:", result.get("reason"), flush=True)
        summary["phases"][phase] = tries[-1]
        summary["phases"][phase]["attempt_history"] = [
            {"attempt": t["attempt"], "reason": t.get("reason"),
             "checkpoints": list(t.get("checkpoints_seconds", {}))}
            for t in tries
        ]
    checkpoints = summary["phases"].get("menu", {}).get("checkpoints_seconds", {})
    summary["menu_entry_confirmed"] = "factory_menu" in checkpoints
    summary["menu_paint_confirmed"] = "menu_painter" in checkpoints
    summary["service_400b_return_confirmed"] = "service_return" in checkpoints
    images = [data.get("screenshot") for data in summary["phases"].values()]
    summary["screenshots_validated"] = (len(images) == 2 and
                                        all(x is not None for x in images))
    summary["screen_changed_after_menu"] = (
        summary["screenshots_validated"] and
        images[0]["sha256"] != images[1]["sha256"])
    summary["visible_menu_proven"] = (
        summary["menu_entry_confirmed"] and
        summary["menu_paint_confirmed"] and
        summary["screen_changed_after_menu"])
    summary["assessment"] = (
        "menu paint executed" if summary["menu_paint_confirmed"] else
        "menu entered but painter not observed; check 0x400B(2) completion" if summary["menu_entry_confirmed"] else
        "factory entry not reached; inspect private execution trace")
    (out / "summary-private.json").write_text(json.dumps(summary, indent=2) + "\n")
    print("MENU ENTRY:", summary["menu_entry_confirmed"],
          "MENU PAINT:", summary["menu_paint_confirmed"],
          "VISIBLE MENU:", summary["visible_menu_proven"],
          "TWO SCREENSHOTS:", summary["screenshots_validated"], flush=True)
    print("Private results:", out, flush=True)
    required_captures = (summary["phases"]["menu"].get("screenshot") is not None
                         if args.menu_only else summary["screenshots_validated"])
    if not summary["menu_entry_confirmed"] or not required_captures:
        return 2
    # Successful original menu-PC execution is NOT successful visible rendering.
    # Use a distinct exit status for an uncompleted IPC/paint/screen transition.
    return 0 if summary["visible_menu_proven"] else 3


if __name__ == "__main__":
    sys.exit(main())
