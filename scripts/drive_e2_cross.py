#!/usr/bin/env python3
"""Send actual original E2 cross geometry via BU21029 physical electrodes.

Source: original A7 FUN_6005c6bc -> eight FUN_6005c618 calls.
E2 checks framebuffer coverage after an exit key; it does NOT require a
specific touch order. This driver DOES NOT write guest RAM, fabricate A7
0x6000 events, or force a passing check. Raw ADC calibration is experimental.
"""
import argparse
import json
import math
import os
from pathlib import Path
import time

# x0,y0,x1,y1, width, offset axis; original 864x480 LCD pixel coordinates.
BANDS = (
    (2, 2, 2, 477, 27, "x"),
    (835, 2, 835, 477, 27, "x"),
    (2, 2, 861, 2, 21, "y"),
    (2, 457, 861, 457, 21, "y"),
    (2, 2, 835, 457, 27, "x"),
    (2, 2, 835, 457, 21, "y"),
    (2, 477, 835, 2, 27, "x"),
    (2, 457, 835, 2, 21, "y"),
)


def strokes(offset_step=8):
    for x0, y0, x1, y1, width, axis in BANDS:
        offsets = list(range(0, width, offset_step))
        if offsets[-1] != width - 1:
            offsets.append(width - 1)
        for i in offsets:
            dx, dy = (i, 0) if axis == "x" else (0, i)
            yield ((x0+dx, y0+dy), (x1+dx, y1+dy))


def screen_to_raw(x, y, flip_x=False, flip_y=False, swap_axes=False):
    # Only a configurable linear hypothesis until actual ROM calibration
    # is measured; 864x480 display != 4096x4096 ADC electrode coordinates.
    sx = max(0.0, min(1.0, x / 863.0))
    sy = max(0.0, min(1.0, y / 479.0))
    if flip_x:
        sx = 1.0 - sx
    if flip_y:
        sy = 1.0 - sy
    if swap_axes:
        sx, sy = sy, sx
    return round(sx * 4095), round(sy * 4095)


def sample_lines(lines, sample_px=18, **mapping):
    for a, b in lines:
        count = max(1, math.ceil(math.dist(a, b) / sample_px))
        yield [screen_to_raw(round(a[0] + (b[0]-a[0]) * i / count),
                             round(a[1] + (b[1]-a[1]) * i / count),
                             **mapping) for i in range(count+1)]


def write_contact(file, down, x, y, z1, z2):
    tmp = file.with_name(file.name + ".next")
    tmp.write_text(f"{int(down)} {x} {y} {z1} {z2}\n", encoding="ascii")
    os.replace(tmp, file)  # physical sample update, atomic for guest poll


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--touch-file", type=Path, required=True)
    p.add_argument("--wait-log", type=Path,
                   help="Owner-private factory driver log; wait for LCD-verified row13 ENTER")
    p.add_argument("--offset-step", type=int, default=8)
    p.add_argument("--point-step", type=float, default=18)
    p.add_argument("--period-ms", type=float, default=12)
    p.add_argument("--release-ms", type=float, default=50)
    p.add_argument("--z1", type=int, default=800)
    p.add_argument("--z2", type=int, default=1200)
    p.add_argument("--flip-x", action="store_true")
    p.add_argument("--flip-y", action="store_true")
    p.add_argument("--swap-axes", action="store_true")
    p.add_argument("--max-wait", type=float, default=210)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    if (args.offset_step < 1 or args.point_step <= 0 or
            args.period_ms < 5 or args.release_ms < 5):
        p.error("Invalid sample spacing/timing")
    mapping = dict(flip_x=args.flip_x, flip_y=args.flip_y,
                   swap_axes=args.swap_axes)
    paths = list(sample_lines(strokes(args.offset_step),
                              args.point_step, **mapping))
    samples = sum(len(points) for points in paths)
    print(json.dumps({
        "original_E2_bands": len(BANDS), "strokes": len(paths),
        "raw_samples": samples,
        "estimated_seconds": round(
            samples * args.period_ms / 1000 +
            2 * len(paths) * args.release_ms / 1000, 1),
        "mapping": mapping,
    }), flush=True)
    if args.dry_run:
        return
    touch = args.touch_file.resolve()
    if not touch.parent.is_dir():
        p.error("Touch-file parent directory must already exist")
    write_contact(touch, 0, 0, 0, args.z1, args.z2)
    if args.wait_log:
        deadline = time.monotonic() + args.max_wait
        while time.monotonic() < deadline:
            if (args.wait_log.exists() and
                "ENTER confirmed menu row 13" in
                    args.wait_log.read_text(errors="replace")):
                break
            time.sleep(.02)
        else:
            raise RuntimeError("E2 ENTER was never confirmed from original LCD")
        print("E2 ENTER observed; beginning physical contact replay", flush=True)
    sent = 0
    try:
        for points in paths:
            x, y = points[0]
            write_contact(touch, 0, x, y, args.z1, args.z2)
            time.sleep(args.release_ms / 1000)
            for x, y in points:
                write_contact(touch, 1, x, y, args.z1, args.z2)
                sent += 1
                time.sleep(args.period_ms / 1000)
            write_contact(touch, 0, x, y, args.z1, args.z2)
            time.sleep(args.release_ms / 1000)
    finally:
        write_contact(touch, 0, 0, 0, args.z1, args.z2)
    print(f"Finished {sent} physical samples; pen released", flush=True)


if __name__ == "__main__":
    main()
