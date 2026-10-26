#!/usr/bin/env python3
"""Firmware-free consistency check for original A7 E2 target geometry."""
from drive_e2_cross import BANDS, strokes, sample_lines, screen_to_raw


def main():
    assert len(BANDS) == 8
    lines = list(strokes(1))
    assert len(lines) == sum(entry[4] for entry in BANDS), len(lines)
    assert lines[0] == ((2, 2), (2, 477))
    assert lines[27] == ((835, 2), (835, 477))
    assert lines[-1] == ((2, 477), (835, 22))
    for a, b in lines:
        for x, y in (a, b):
            assert 0 <= x < 864 and 0 <= y < 480, (a, b)
    for points in sample_lines(strokes(8), sample_px=18):
        assert len(points) > 1
        for x, y in points:
            assert 0 <= x <= 4095 and 0 <= y <= 4095
    assert screen_to_raw(0, 0) == (0, 0)
    assert screen_to_raw(863, 479) == (4095, 4095)
    assert screen_to_raw(0, 479, flip_x=True) == (4095, 4095)
    assert screen_to_raw(863, 0, swap_axes=True) == (0, 4095)
    print("PASS E2 original eight-band geometry and raw touch-coordinate bounds")


if __name__ == "__main__":
    main()
