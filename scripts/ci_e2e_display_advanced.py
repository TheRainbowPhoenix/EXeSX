#!/usr/bin/env python3
"""Private-fixture, original-ROM ARM PATTERN AUTO CHECK regression.

Only M4 electrical contact files change. LCD and A7 checkpoints are read-only.
Never put OSUP, ELF, disks, QEMU execution logs or secret URLs in CI artifacts.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from auto_driver import convert_png, profile_with_lcd
from drive_factory_menu import QMP, choose_port, connect
from factory_control_panel import original_menu_highlight
from lcd_qmp import capture_frame

HEADER = b"P6\n864 480\n255\n"
EXPECTED = {"ffffff": 55296, "ffff00": 55296, "ff00ff": 55296,
            "ff0000": 55296, "00ffff": 55296, "00ff00": 55296,
            "0000ff": 55296, "000000": 27648}
GOLDEN = "5a046dd6d3080c97c0c2bff76f130d4e05199a2d4dbae59e6aa5eb741df4eaaf"
CHECKPOINTS = {"wait": "600108a8", "first": "60010910",
               "last": "60010928", "accepted": "60010930",
               "factory": "6003a878", "ipc_call": "60006240",
               "ipc_return": "60006268", "paint": "60057668",
               "arm_auto": "60058138"}
TRACE_PC = re.compile(r"^Trace \d+:.*?/00000000([0-9a-fA-F]{8})/", re.M)


def frame(qmp, directory, name):
    raw = directory / (name + ".rgb565")
    ppm = directory / (name + ".ppm")
    capture_frame(qmp, raw, ppm)
    raw.unlink(missing_ok=True)
    pixels = ppm.read_bytes()
    if not pixels.startswith(HEADER) or len(pixels) != len(HEADER) + 864*480*3:
        raise RuntimeError("incomplete original LCD")
    rgb = pixels[len(HEADER):]
    selected = original_menu_highlight(rgb)
    # Full RGB histogram, not a synthetic success flag or a changed-frame check.
    hist = Counter(rgb[i:i+3].hex() for i in range(0, len(rgb), 3))
    result = {"sha256": hashlib.sha256(pixels).hexdigest(),
              "histogram": dict(sorted(hist.items())), "highlight_y": selected}
    return result


def actual_row(y):
    return None if y is None or y < 25 or y > 390 else round((y-25)/24.3)+1


def physical(path, value):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(value + "\n", encoding="ascii")
    os.replace(tmp, path)


def m4_idle(qmp):
    match = re.search(r":\s+0x([a-fA-F0-9]+)", qmp.hmp("xp /1wx 0x1ffea320"))
    return bool(match and int(match.group(1), 16) == 0)


def screenshot(ppm, png):
    convert_png(ppm, png)


def navigate(qmp, contact, out, target=3):
    old = frame(qmp, out, "initial-menu")
    for step in range(24):
        row = actual_row(old["highlight_y"])
        if row == target:
            time.sleep(.30)
            confirm = frame(qmp, out, "selected-row")
            if actual_row(confirm["highlight_y"]) == target:
                screenshot(out/"selected-row.ppm", out/"selected-row.png")
                return confirm
            old = confirm
            continue
        physical(contact, "0x91" if row is None or row < target else "0x90")
        changed = None
        try:
            start = time.monotonic()
            while time.monotonic() - start < 4.5:
                time.sleep(.20)
                current = frame(qmp, out, "navigation")
                if (current["highlight_y"] is not None and
                        current["highlight_y"] != old["highlight_y"]):
                    changed = current
                    break
        finally:
            physical(contact, "0")
        if changed is None:
            raise RuntimeError("physical DOWN/UP did not move visible LCD selection")
        old = changed
        start = time.monotonic()
        while time.monotonic()-start < 1.2:
            if m4_idle(qmp):
                break
            time.sleep(.04)
        time.sleep(.12)
    raise RuntimeError("ARM PATTERN row 3 selection never stabilized")


def qemu_env(profile, contact):
    env = os.environ.copy()
    env.update({
        "EXESX_MEMORY_PROFILE": str(profile), "EXESX_M4_KEY_MATRIX_FILE": str(contact),
        "EXESX_EXPERIMENTAL_M4_BOOT":"1", "EXESX_EXPERIMENTAL_MU_IRQ":"1",
        "EXESX_EXPERIMENTAL_LPIT1_IRQ":"1", "EXESX_EXPERIMENTAL_M4_LPIT0_IRQ":"1",
        "EXESX_EXPERIMENTAL_LPTMR_IRQ":"1", "EXESX_EXPERIMENTAL_LPTMR_PCS_CLOCKS":"1",
        "EXESX_EXPERIMENTAL_M4_PORT_IRQ":"1", "EXESX_EXPERIMENTAL_M4_TPM0_IRQ":"1",
        "EXESX_EXPERIMENTAL_M4_TPM0_INPUT_MHZ":"48", "EXESX_DIAGNOSTIC_A7_TPM6_KHZ":"32",
        "EXESX_EXPERIMENTAL_LCD":"1", "EXESX_LCD_FRAMEBUFFER_EXPORT":"1",
        "EXESX_EXPERIMENTAL_DMA1_M2M":"1", "EXESX_USDHC1_EMMC":"1",
        "EXESX_USDHC0_SD":"1", "EXESX_USDHC0_SD_DETECT_GPIO":"1",
        "EXESX_I2C4B_REGISTER_MIRROR":"1", "EXESX_I2C40_REGISTER_MIRROR":"1",
        "EXESX_SNVS_DIAGNOSTIC_SECURITY_PULSES":"1",
        "EXESX_GPIOA_INPUT_MASK":"0x808c6008", "EXESX_GPIOB_INPUT_MASK":"0xc8",
        "EXESX_ADC0_SAMPLE_RAW":"0x7000", "EXESX_ADC1_SAMPLE_RAW":"0x7000"})
    return env



# Header fingerprints from THREE independent untouched original-LCD menu
# captures. Only one-bit/pixel digests are included; no ROM-derived images.
HEADERS = {
    "manual-menu": "f282e75fe60f94bbdbfcede794aba81af115775432f5cb1b4c9afd8fb146afd4",
    "display-menu": "9713b41f998d654760eb741eab783f1ef3ab0b64d043792843717e110e33bc29",
    "display-test-menu": "ba98084398d39b027d663a8936b386f16a6d26743e9287c97bc16c911395be35",
}
CHIDORI_SHA = "e7b16ad2c9f0f78bd3b6d2af65e1e667fea228f4fc2b2748bdc9cfc3af55eaf3"
CHIDORI_PIXELS = {"000000": 207360, "ffffff": 207360}
FRAME_SHA = "6a73559f416f12f85796679dcb2c58176b9813a1194c3eae554a5e5555fdca51"
FRAME_PIXELS = {"000000": 412036, "ffffff": 2684}


def screen_rgb(out, name):
    frame_bytes = (out / (name + ".ppm")).read_bytes()
    if not frame_bytes.startswith(HEADER):
        raise RuntimeError("bad native LCD PPM")
    return frame_bytes[len(HEADER):]


def native_header_fingerprint(rgb):
    # Normalize the A7 painter's black or white title background, preserving
    # actual character strokes. Never compare only a full-frame hash delta.
    values = [rgb[3 * (y * 864 + x)]
              for y in range(24) for x in range(235, 655)]
    bright = sum(v > 127 for v in values) > len(values) // 2
    ink = bytes(int(v < 127 if bright else v > 127) for v in values)
    return hashlib.sha256(ink).hexdigest()


def enter_original_submenu(qmp, contact, out, title):
    target = HEADERS[title]
    for attempt_number in range(8):
        physical(contact, "0x94")
        seen = False
        try:
            start = time.monotonic()
            while time.monotonic() - start < 1.6:
                time.sleep(.12)
                frame(qmp, out, title)
                if native_header_fingerprint(screen_rgb(out, title)) == target:
                    seen = True
                    break
        finally:
            physical(contact, "0")
        if seen:
            time.sleep(.35)
            frame(qmp, out, title)
            if native_header_fingerprint(screen_rgb(out, title)) == target:
                screenshot(out / (title + ".ppm"), out / (title + ".png"))
                return
        start = time.monotonic()
        while time.monotonic() - start < 1.3 and not m4_idle(qmp):
            time.sleep(.045)
        time.sleep(.2)
    raise RuntimeError("original DISPLAY navigation failed: " + title)


def changed_two_unselected_rows(baseline, candidate):
    # The menu highlight can repaint only ONE row. Genuine display patterns
    # replace text on several OTHER rows. Check three row1-3 text stripes,
    # excluding the requested CHIDORI row4, to reject false positives.
    changed = 0
    for row in (1, 2, 3):
        y0 = 25 + (row - 1) * 24
        diff = 0
        for y in range(y0, y0 + 20):
            for x in range(20, 260):
                i = 3 * (y * 864 + x)
                diff += baseline[i:i + 3] != candidate[i:i + 3]
        changed += diff > 130
    return changed >= 2


def advanced_display_test(qmp, contact, out, output, row):
    name = "frame" if row == 6 else "chidori"
    golden = FRAME_SHA if row == 6 else CHIDORI_SHA
    pixel_golden = FRAME_PIXELS if row == 6 else CHIDORI_PIXELS
    for stage in ("manual-menu", "display-menu", "display-test-menu"):
        navigate(qmp, contact, out, 1)
        enter_original_submenu(qmp, contact, out, stage)
    navigate(qmp, contact, out, row)
    selected = "selected-" + name
    rendered = "display-" + name
    probe = name + "-probe"
    frame(qmp, out, selected)
    screenshot(out / (selected + ".ppm"), out / (selected + ".png"))
    original_menu = screen_rgb(out, selected)
    start = time.monotonic()
    while time.monotonic() - start < 1.5 and not m4_idle(qmp):
        time.sleep(.035)
    physical(contact, "0x94")
    candidate = None
    try:
        start = time.monotonic()
        while time.monotonic() - start < 9:
            time.sleep(.15)
            observed = frame(qmp, out, probe)
            if (observed["histogram"] == pixel_golden and
                    changed_two_unselected_rows(original_menu,
                                                screen_rgb(out, probe))):
                candidate = observed
                break
    finally:
        physical(contact, "0")
    if candidate is None:
        raise RuntimeError("genuine advanced display pattern never appeared")
    time.sleep(.6)
    final = frame(qmp, out, rendered)
    if final["sha256"] != golden or final["histogram"] != pixel_golden:
        raise RuntimeError("original advanced display LCD failed independent golden frame")
    screenshot(out / (rendered + ".ppm"), out / (rendered + ".png"))
    result = {"result": "PASS", "test": "DISPLAY TEST MENU -> " + name.upper(),
              "tcg": "single", "source": "original A7/M4 physical key events",
              "stable": final["sha256"] == candidate["sha256"],
              "sha256": final["sha256"], "expected_sha256": golden,
              "color_pixels": final["histogram"],
              "screenshots": ["manual-menu.png", "display-menu.png",
                              "display-test-menu.png", selected + ".png",
                              rendered + ".png"]}
    if not result["stable"]:
        raise RuntimeError("original advanced display frame was not stable")
    output.joinpath("result.json").write_text(json.dumps(result, indent=2) + "\n")
    print("PASS original DISPLAY TEST -> %s; exact LCD SHA256 %s" %
          (name.upper(), golden), flush=True)


def attempt(args, number):
    out = args.output / ("attempt-%d" % number)
    out.mkdir(parents=True, exist_ok=True)
    contact = out / "m4-physical-contact.txt"
    physical(contact, "0x9c,0x90")
    profile = profile_with_lcd(args.profile, out)
    env = qemu_env(profile.resolve(), contact.resolve())
    lib = args.qemu.parent / "lib"
    if lib.is_dir():
        env["LD_LIBRARY_PATH"] = str(lib.resolve()) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    port = choose_port()
    command = [str(args.qemu), "-machine", "exesx", "-m", "64M",
               "-accel", "tcg,thread=single", "-display", "none", "-serial", "none",
               "-monitor", "none", "-no-reboot", "-S",
               "-qmp", "tcp:127.0.0.1:%d,server=on,wait=off" % port,
               "-drive", "if=none,id=exesx-emmc,file=%s,format=raw,snapshot=on" % args.emmc,
               "-drive", "if=none,id=exesx-sd,file=%s,format=raw,snapshot=on" % args.sd,
               "-device", "loader,file=%s,cpu-num=0" % args.elf,
               "-d", "exec", "-dfilter",
               "0x60010868+0x130,0x6003a878+0x500,0x60006240+0x70,0x60057668+0x40,0x60058138+0x40",
               "-D", str(out / "private-execution.log")]
    hits = Counter()
    trace = out / "private-execution.log"
    started = time.monotonic()
    sock = None
    with (out / "private-qemu-console.log").open("wb") as console:
        proc = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL,
                                stdout=console, stderr=subprocess.STDOUT)
        try:
            sock = connect(port, proc)
            qmp = QMP(sock)
            qmp.execute("cont")
            while not trace.exists() and time.monotonic()-started < 5:
                time.sleep(.01)
            with trace.open("r", errors="replace") as stream:
                released = False
                index = 0
                down = False
                pressed = 0.0
                next_at = 0.0
                up_at = 0.0
                ack_before = 0
                buffered = ""
                while time.monotonic()-started < args.boot_timeout and proc.poll() is None:
                    now = time.monotonic()-started
                    if not released and now >= 4:
                        physical(contact, "0")
                        released = True
                    buffered += stream.read()
                    if "\n" in buffered:
                        complete, buffered = buffered.rsplit("\n", 1)
                    else:
                        complete = ""
                    for pc in TRACE_PC.findall(complete):
                        for label, addr in CHECKPOINTS.items():
                            if pc.lower() == addr:
                                hits[label] += 1
                    if released and hits["wait"] and index < 3:
                        # Advance on actual A7 acceptance; do not use blind keypress counts.
                        desired = ("first", "first", "accepted")[index]
                        if not down and now >= next_at:
                            if index == 0 or m4_idle(qmp) or now-up_at > 1.25:
                                physical(contact, ("0x93", "0x93", "0x94")[index])
                                ack_before = hits[desired]
                                pressed = now
                                down = True
                        elif down and (hits[desired] > ack_before or now-pressed > .28):
                            physical(contact, "0")
                            index += 1
                            down = False
                            up_at = now
                            next_at = now + .012
                    if hits["paint"]:
                        break
                    time.sleep(.018)
            required = ("wait", "first", "accepted", "factory", "ipc_call", "ipc_return", "paint")
            if not all(hits[name] for name in required):
                raise RuntimeError("original A7 factory checkpoints missing: " +
                                   ",".join(n for n in required if not hits[n]))
            time.sleep(1.3)
            menu = frame(qmp, out, "factory-menu")
            screenshot(out/"factory-menu.ppm", out/"factory-menu.png")
            if len(menu["histogram"]) != 2:
                raise RuntimeError("original factory menu not monochrome")
            if args.advanced_chidori or args.advanced_frame:
                advanced_display_test(qmp, contact, out, args.output,
                                      6 if args.advanced_frame else 4)
                return True
            navigate(qmp, contact, out, args.factory_row)
            start = time.monotonic()
            while time.monotonic()-start < 1.5 and not m4_idle(qmp):
                time.sleep(.035)
            physical(contact, "0x94")
            passed = None
            try:
                start = time.monotonic()
                while time.monotonic()-start < 6:
                    time.sleep(.30)
                    current = frame(qmp, out, "arm-pattern-probe")
                    if current["histogram"] == EXPECTED:
                        passed = current
                        break
            finally:
                physical(contact, "0")
            if passed is None:
                raise RuntimeError("ARM PATTERN AUTO CHECK failed expected 8-color framebuffer histogram")
            # Read again after key release; persistent original pixels, not transient bus output.
            time.sleep(.30)
            again = frame(qmp, out, "arm-pattern")
            if again["histogram"] != EXPECTED or again["sha256"] != GOLDEN:
                raise RuntimeError("ARM PATTERN differs from verified 2026-10-30 golden PPM")
            screenshot(out/"arm-pattern.ppm", out/"arm-pattern.png")
            result = {"result": "PASS", "tcg": "single", "factory_checkpoints": dict(hits),
                      "arm_pattern_row": args.factory_row, "test_name": ("ARM PATTERN MANUAL CHECK" if args.factory_row == 2 else "ARM PATTERN AUTO CHECK"), "original_lcd": "864x480 RGB565",
                      "sha256": again["sha256"], "golden_sha256": GOLDEN,
                      "color_pixels": again["histogram"], "screen_png": "arm-pattern.png"}
            (args.output / "result.json").write_text(json.dumps(result, indent=2)+"\n")
            label = "ARM PATTERN MANUAL CHECK" if args.factory_row == 2 else "ARM PATTERN AUTO CHECK"
            print("PASS original factory TEST MENU -> %s; exact LCD SHA256 %s" % (label, GOLDEN), flush=True)
            return True
        finally:
            physical(contact, "0")
            if sock:
                sock.close()
            proc.terminate()
            try:
                proc.wait(timeout=4)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()



def diagnose_failed_attempt(out, error):
    """Offline failure classification; NEVER reads/polls while QEMU runs.

    Keeping all trace analysis after the guest exits preserves the boot and
    M4 key-contact timing of the original locally and CI-proven test runner.
    Return no proprietary payloads, filesystem paths or secret URLs.
    """
    hits = Counter()
    trace = out / "private-execution.log"
    if trace.is_file():
        with trace.open("r", errors="replace") as stream:
            for line in stream:
                match = TRACE_PC.search(line)
                if match:
                    pc = match.group(1).lower()
                    for label, address in CHECKPOINTS.items():
                        if pc == address:
                            hits[label] += 1

    if not hits["wait"]:
        stage = "version-dialog-wait"
    elif not hits["accepted"]:
        stage = "physical-factory-keys"
    elif not hits["factory"]:
        stage = "factory-menu-entry"
    elif not hits["ipc_call"]:
        stage = "original-ipc-call"
    elif not hits["ipc_return"]:
        stage = "original-ipc-0x400b-return"
    elif not hits["paint"]:
        stage = "original-menu-painter"
    elif not (out / "selected-row.png").exists():
        stage = "physical-menu-navigation"
    else:
        stage = "arm-pattern-framebuffer"

    # Do not publish unexpected exception text (may contain private paths).
    known = (
        "original A7 factory checkpoints missing:",
        "original factory menu not monochrome",
        "physical DOWN/UP did not move visible LCD selection",
        "ARM PATTERN row 3 selection never stabilized",
        "ARM PATTERN AUTO CHECK failed expected 8-color framebuffer histogram",
        "ARM PATTERN differs from verified 2026-10-30 golden PPM",
        "incomplete original LCD",
    )
    message = str(error)
    reason = message[:180] if isinstance(error, RuntimeError) and message.startswith(known) else type(error).__name__
    return {"status": "FAIL", "stage": stage, "reason": reason,
            "original_checkpoints": dict(hits),
            "qemu_exited_before_checkpoints": not bool(hits),
            "private_trace_uploaded": False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for item in ("qemu", "profile", "elf", "emmc", "sd", "output"):
        p.add_argument("--" + item, type=Path, required=True)
    p.add_argument("--advanced-chidori", action="store_true",
                   help="real nested DISPLAY TEST CHIDORI checkerboard")
    p.add_argument("--advanced-frame", action="store_true",
                   help="real nested DISPLAY TEST FRAME border")
    p.add_argument("--factory-row", type=int, choices=(2, 3), default=3,
                   help="original factory display test: 2=ARM PATTERN MANUAL, 3=ARM PATTERN AUTO")
    p.add_argument("--attempts", type=int, default=4)
    p.add_argument("--boot-timeout", type=float, default=90)
    a = p.parse_args()
    for item in ("qemu", "profile", "elf", "emmc", "sd"):
        path = getattr(a, item).resolve(strict=True)
        setattr(a, item, path)
    a.output = a.output.resolve()
    a.output.mkdir(parents=True, exist_ok=True)
    for n in range(1, a.attempts+1):
        try:
            if attempt(a, n):
                return 0
        except Exception as exc:
            diagnostic = diagnose_failed_attempt(a.output / ("attempt-%d" % n), exc)
            detail = a.output / ("attempt-%d" % n) / "attempt-result.json"
            detail.write_text(json.dumps(diagnostic, indent=2) + "\n")
            print("ARM PATTERN attempt %d/%d failed at %s: %s" %
                  (n, a.attempts, diagnostic["stage"], diagnostic["reason"]), flush=True)
            if n == a.attempts:
                (a.output / "result.json").write_text(json.dumps({"result":"FAIL", "attempts":n,
                    "reason": diagnostic["reason"]})+"\n")
                return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())