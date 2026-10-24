#!/usr/bin/env python3
"""Summarize the raw EXeSX experimental P6 LCD GRAM screenshot without firmware.

This is a pixel summary, NOT OCR and NOT a claim that the guest OS booted.
The PPM file and any previews remain private.
"""
import argparse
from collections import Counter
import json
from pathlib import Path


def summarize(source):
    raw = Path(source).read_bytes()
    fields = raw.split(b"\n", 3)
    if len(fields) != 4 or fields[0] != b"P6" or fields[2] != b"255":
        raise ValueError("Unsupported PPM: expected EXeSX P6 RGB888 header")
    dims = fields[1].split()
    if len(dims) != 2:
        raise ValueError("Invalid PPM dimensions")
    width, height = map(int, dims)
    if width < 1 or height < 1 or width > 4096 or height > 4096:
        raise ValueError("Invalid LCD dimensions")
    pix = fields[3]
    if len(pix) != width * height * 3:
        raise ValueError("Incomplete/oversized PPM RGB data")
    counts = Counter()
    minx = width
    miny = height
    maxx = maxy = -1
    for pixel in range(width * height):
        pos = 3 * pixel
        rgb = (pix[pos], pix[pos + 1], pix[pos + 2])
        counts[rgb] += 1
        if rgb != (255, 255, 255):
            y, x = divmod(pixel, width)
            minx = min(minx, x)
            miny = min(miny, y)
            maxx = max(maxx, x)
            maxy = max(maxy, y)
    other = width * height - counts[(255, 255, 255)]
    return {
        "width": width, "height": height,
        "white_pixels": counts[(255, 255, 255)],
        "nonwhite_pixels": other,
        "black_pixels": counts[(0, 0, 0)],
        "distinct_colors": len(counts),
        "nonwhite_bbox_xyxy": [minx, miny, maxx + 1, maxy + 1] if other else None,
        "note": "Raw experimental LCD GRAM pixels only; not OCR, guest OS entry, or physical panel orientation",
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("ppm", type=Path)
    args = ap.parse_args()
    print(json.dumps(summarize(args.ppm), indent=2))


if __name__ == "__main__":
    main()
