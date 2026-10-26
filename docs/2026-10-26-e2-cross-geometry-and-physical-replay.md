# Original A7 E2 cross: exact coverage requirement and physical replay

Source basis: owner-private XD-SX9850.0.c, functions FUN_6005c618
and FUN_6005c6bc. No proprietary decomp, OSUP, disk, screen or logs committed.

## How the test works

It is a full framebuffer coverage test, NOT a sequence of button taps.
A7 draws eight black bands then waits for real event records via
FUN_60047504. A touch record must have type 0x6000 and state 1, 2,
4, 8, 16, 32, 64 or 128. The touch path uses FUN_601b2060 to draw
between successive reported coordinates. When event 0x12, 0x1a, or 0x11
ends the check, A7 tests whether any framebuffer pixel remains zero:
a missing touch event, premature exit or incomplete coverage gives NG.

The eight FUN_6005c618 source calls represent these LCD-pixel bands:

| Region | Endpoints | Perpendicular width |
| --- | --- | --- |
| Left | (2,2) to (2,477) | 27 pixels toward right |
| Right | (835,2) to (835,477) | 27 toward right |
| Top | (2,2) to (861,2) | 21 downward |
| Bottom | (2,457) to (861,457) | 21 downward |
| X arm 1 | (2,2) to (835,457) | 27 toward right |
| X arm 2 | (2,2) to (835,457) | 21 downward |
| X arm 3 | (2,477) to (835,2) | 27 toward right |
| X arm 4 | (2,457) to (835,2) | 21 downward |

There is no special stroke order required by this original code.
The test demands complete coverage, then an exit key, not an arbitrary
single contact or a success flag.

## Reproduction driver

scripts/drive_e2_cross.py interpolates all eight original bands into
raw physical BU21029 contact updates, including release gaps, and can
wait for owner-private factory runner log text confirming LCD selection
of row 13 and real ENTER. The interpolation/step rate and raw electrode
axis swap/flip are configurable; the ROM's actual calibration from raw
12-bit readings to LCD pixels is NOT yet measured.

    python scripts/drive_e2_cross.py --touch-file /private/touch.txt \
      --wait-log /private/factory-runner.log --offset-step 8

Only host electrode samples are written, atomically, to the private
touch-input file. No guest RAM, A7 input records, IPC replies or factory
result flags are manufactured.

On the original owner-OSUP run, the genuine factory menu was reached and
E2 row13 highlighted before ENTER. A test replay sent **1,649 raw
physical samples across 36 continuous strokes**, using swapped axes to
compensate the older local QEMU image. The original LCD still displayed
NG and showed no independently verified erased cross pixels. That is a
NEGATIVE end-to-end test: a correct gesture pattern alone does not
prove delivery of A7 touch type 0x6000 records.

Original M4 FUN_1ffdba48 derives its output param2 from the first
16-bit device report word and output param1 from the second. The new
emulator version serializes raw Y then X (the older local binary had
X then Y). A synthetic ARM probe checks these byte positions, but
full calibrated touch-event delivery must be traced with unchanged ROM.

## Remaining hardware test

Observe whether original M4 0x40 I2C2 14-byte reads, PTB3 active-low
pen IRQ, and original IPC input worker proceed during E2. Independently
check A7 FUN_60047504 for actual type 0x6000 records. Only report an
E2 PASS when the ORIGINAL LCD genuinely reports OK, not when the
firmware-free device register test passes.
