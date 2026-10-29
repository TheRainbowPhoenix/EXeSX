#!/usr/bin/env python3
"""Drive the unchanged DY357 E2 touch test through physical files only.

Start the GUI/QEMU first, with EXESX_BU21029_LPI2C_BUS=2,
EXESX_BU21029_TOUCH_FILE pointing at --touch-file and
EXESX_TRACE_E2_A7=1. Navigate with original M4 keys to the genuine E2
border-and-X screen. This script checks that screen before acting.
A successful original A7 0x6005CD08 TB, not a white screen, is PASS.
"""
import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
import re
import time

WIDTH, HEIGHT = 864, 480
HEADER = b"P6\n864 480\n255\n"
CROSS_BLACK = 113969
CROSS_POINT = (200, 111)
OK_PC = re.compile(r"/000000006005cd08/")
NG_PC = re.compile(r"/000000006005cd30/")


def frame_info(path):
    raw = path.read_bytes()
    if not raw.startswith(HEADER) or len(raw) != len(HEADER) + WIDTH*HEIGHT*3:
        raise ValueError("Incomplete/non-original 864x480 P6 LCD capture")
    rgb = memoryview(raw)[len(HEADER):]
    black = sum(rgb[i] == rgb[i+1] == rgb[i+2] == 0
                for i in range(0, len(rgb), 3))
    x, y = CROSS_POINT
    off = (y*WIDTH+x)*3
    pixel = bytes(rgb[off:off+3])
    return {"black": black, "pixel": pixel,
            "sha256": hashlib.sha256(raw).hexdigest()}


def atomic_contact(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".physical.tmp")
    tmp.write_text(text + "\n", encoding="ascii")
    os.replace(tmp, path)


def wait_for(path, predicate, seconds, interval=0.20):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if path.is_file():
            try:
                state = frame_info(path)
                if predicate(state):
                    return state
            except (OSError, ValueError):
                pass  # GUI may be updating its atomic screenshot.
        time.sleep(interval)
    raise TimeoutError("Original LCD did not reach the required state")


def verdict_after_offset(trace_path, offset):
    try:
        with trace_path.open("rb") as stream:
            stream.seek(offset)
            chunk = stream.read()
    except OSError:
        return None
    # The transcript includes only guest translated-block PC addresses.
    # A host-side touch or key is never sufficient to claim a PASS.
    text = chunk.decode("utf-8", errors="replace")
    if NG_PC.search(text):
        return "NG"
    if OK_PC.search(text):
        return "OK"
    return None


def capture_native_result_frame(lcd, output, before, seconds=2):
    """Save *only* real GUI LCD pixels after the original OK branch.

    A nonblank frame is a candidate screen capture, NOT proof of readable
    OK text. The calling code must still confirm the guest-executed branch
    and a human must visually inspect the image.
    """
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            state = frame_info(lcd)
            if (state["sha256"] != before and 10 < state["black"] < 50000):
                output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(lcd, output)
                return state
        except (OSError, ValueError):
            pass
        time.sleep(.04)
    return None


def run(args):
    if args.raw_x < 0 or args.raw_y < 0 or args.raw_x > 4095 or args.raw_y > 4095:
        raise ValueError("Raw electrode coordinates must be 0..4095")
    if not args.trace.is_file():
        raise ValueError("Start QEMU with EXESX_TRACE_E2_A7=1 before E2")
    pre = wait_for(args.lcd, lambda f: f["black"] == CROSS_BLACK
                   and f["pixel"] == b"\x00\x00\x00", args.ready_timeout)
    trace_offset = args.trace.stat().st_size
    print("Original E2 border/X is painted. Black pixels:", pre["black"],
          "raw contact:", args.raw_x, args.raw_y, flush=True)
    touch_release = f"0 {args.raw_x} {args.raw_y} 800 1200"
    key_release = "0"
    result = {"method": "unchanged original ROM; real M4 GPIO contacts and BU21029",
              "original_cross_black_pixels": pre["black"],
              "original_e2_ok_branch": False, "original_e2_ng_branch": False,
              "trace_offset": trace_offset, "raw": [args.raw_x, args.raw_y]}
    try:
        atomic_contact(args.touch_file,
                       f"1 {args.raw_x} {args.raw_y} 800 1200")
        touched = wait_for(args.lcd,
                           lambda f: f["black"] == CROSS_BLACK - 1
                           and f["pixel"] == b"\xff\xff\xff",
                           args.touch_timeout)
        print("Genuine E2 pixel erased by original touch renderer.", flush=True)
        result["touch_lcd_sha256"] = touched["sha256"]
        atomic_contact(args.touch_file, touch_release)
        time.sleep(args.release_seconds)
        atomic_contact(args.key_file, "0x94")
        start = time.monotonic()
        verdict = None
        while time.monotonic() - start < args.exit_timeout:
            verdict = verdict_after_offset(args.trace, trace_offset)
            if verdict:
                break
            time.sleep(.08)
        result["verdict"] = verdict or "UNVERIFIED"
        result["original_e2_ok_branch"] = verdict == "OK"
        result["original_e2_ng_branch"] = verdict == "NG"
        # Release the physical key immediately after firmware verdict,
        # to avoid a second repeated key dismissing the result text.
        atomic_contact(args.key_file, key_release)
        print("Original E2 verdict:", result["verdict"], flush=True)
        if verdict == "OK" and args.ok_screen:
            capture = capture_native_result_frame(
                args.lcd, args.ok_screen, touched["sha256"], args.screen_timeout)
            result["post_ok_frame_captured"] = capture is not None
            if capture:
                result["post_ok_frame_sha256"] = capture["sha256"]
                print("Saved original post-OK LCD candidate:", args.ok_screen,
                      "(visually inspect text before claiming screenshot proof)",
                      flush=True)
            else:
                print("No readable post-OK frame captured; retaining original"
                      " A7-branch evidence, not fabricating an OK screenshot",
                      flush=True)
    finally:
        atomic_contact(args.touch_file, touch_release)
        atomic_contact(args.key_file, key_release)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(result, indent=2)+"\n",
                                   encoding="utf-8")
    return 0 if result["original_e2_ok_branch"] else 2


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--touch-file", type=Path, required=True)
    p.add_argument("--key-file", type=Path, required=True,
                   help="GUI's original physical M4 gui-contact.txt")
    p.add_argument("--lcd", type=Path, required=True,
                   help="GUI's read-only gui-screen.ppm")
    p.add_argument("--trace", type=Path, required=True,
                   help="GUI's original guest gui-execution-private.log")
    p.add_argument("--raw-x", type=int, default=961)
    p.add_argument("--raw-y", type=int, default=1139)
    p.add_argument("--ready-timeout", type=float, default=12)
    p.add_argument("--touch-timeout", type=float, default=12)
    p.add_argument("--release-seconds", type=float, default=3.0)
    p.add_argument("--exit-timeout", type=float, default=4.5)
    p.add_argument("--report", type=Path)
    p.add_argument("--ok-screen", type=Path,
                   help="Save original PPM result candidate after genuine OK branch;"
                        " visually inspect for readable OK, never synthesize text")
    p.add_argument("--screen-timeout", type=float, default=2.0)
    args = p.parse_args()
    if min(args.ready_timeout, args.touch_timeout, args.release_seconds,
           args.exit_timeout, args.screen_timeout) <= 0:
        p.error("Time limits must be positive")
    try:
        return run(args)
    except (OSError, ValueError, TimeoutError) as exc:
        p.exit(2, "E2 not verified: {}\n".format(exc))


if __name__ == "__main__":
    raise SystemExit(main())
