#!/usr/bin/env python3
"""Actual ARM writes to original DY357 PWM UI RAM drive the opt-in panel shadow.

This is an approximate compatibility observer, not proof of the unknown
physical vendor PWM register. Each case is an independent native QEMU boot.
"""
import argparse
from pathlib import Path
from probe_lcd_pwm_diagnostic import one_boot

SETTINGS = ((0x40, 0x1239), (0xc0, 0x1239), (0xc0, 0x2000))


def run(qemu, profile):
    result = {}
    for duty, divisor in SETTINGS:
        words, rgb565 = one_boot(qemu, profile, duty,
                                 shadow_divisor=divisor)
        assert words[0] == 0x3144434c, "LCD device not attached"
        assert words[15] == 0x50574d32, "live owner-firmware PWM shadow absent"
        assert words[12] == divisor, ("divisor", words[12], divisor)
        assert words[14] == duty, ("duty", words[14], duty)
        period = (divisor * 1000000000 + 8000000) // 16000000
        width = (period * duty + 127) // 255
        assert words[8] == period, ("period", words[8], period)
        assert words[9] == width, ("high pulse", words[9], width)
        assert words[13] == 16000000 // divisor, "frequency mismatch"
        result[(duty, divisor)] = (words, rgb565)
        print("original PWM shadow: duty=%d/255 divisor=%d period=%d ns "
              "HIGH=%d ns nominalHz=%d" %
              (duty, divisor, words[8], words[9], words[13]),
              flush=True)
    a, b, c = (result[s] for s in SETTINGS)
    assert b[0][9] > a[0][9] * 2, "different firmware duties ignored"
    assert c[0][8] > b[0][8], "different firmware divisors ignored"
    assert a[1] == b[1] == c[1], "PWM should not corrupt RGB565 GRAM"
    print("PASS ARM original firmware variable A/B: distinct duty, "
          "distinct frequency, unchanged LCD GRAM", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--qemu", type=Path, required=True)
    p.add_argument("--profile", type=Path, required=True)
    args = p.parse_args()
    run(args.qemu, args.profile)
