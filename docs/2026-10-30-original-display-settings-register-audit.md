# DY357 original DISPLAY SETTINGS: source-grounded register audit (2026-10-30)

## Live original-ROM observation

Using owner-private original OSUP and the **actual Linux QEMU from CI**,
single-threaded TCG, read-only QMP framebuffer, original electrical M4 key
contacts, sparse reconstructed eMMC and disposable SD (`snapshot=on`),
the guest reached **TEST MENU → MANUAL CHECK → DISPLAY MENU → SETTINGS**.
Its real 864×480 LCD painted eleven entries, including BACKLIGHT PWM,
BACKLIGHT EN, BACKLIGHT DUTY and BACKLIGHT BRIGHTNESS.

The original `BACKLIGHT DUTY` handler `0x6004FD64` appeared in the
owner-private execution trace (twice), but a long-held ENTER returned
to the parent menu before an independent duty-setting screenshot. GPIO
readbacks before and after the resulting transient operation matched:
GPIOF `0x400F00C0 = 0x00040010`, GPIOB `0x4100F040 = 0`, and
GPIOC `0x400F0000 = 0x00090000`. This does **not** show that PWM duty
is correct or that the target backlight changed brightness. Later
shorter-event verification is required.

## What QEMU actually models

The source `hw/arm/exesx-imx7ulp.inc` implements RGPIO PDOR,
PSOR/PCOR/PTOR, PDIR voltage synthesis and PDDR; these operations allow
firmware GPIO writes/readback for digital enables. The read-only LCD
framebuffer export captures original RGB565 RAMWR pixels. The actual
`hw/arm/exesx-lcd.inc` parser supports DCS `0x34/35` TE,
`0x36` MADCTL, `0x2A/2B` address windows, `0x2C` RAMWR
and `0x3A` COLMOD. Its default branch treats unrecognized
vendor-panel commands as **inert**. The TE source is a synthetic
**fixed 60 Hz** 1 ms pulse.

| Original SETTINGS label | Original A7 routine / path | Emulator outcome |
|---|---|---|
| COLOR MODE | `FUN_60015640`, panel `0x38/39` data | No verified vendor-mode effect |
| FRAME FREQUENCY | Password `FUN_6004752C(0)`, then `FUN_6004ECF8` | Protected; fixed TE, no real frequency adjustment |
| INVERSION | `FUN_6004EF20`, `FUN_600166B4` | Firmware settings modified; vendor inversion effect absent |
| BACK PORCH | `FUN_6004F104`, `FUN_600166C4` | No programmable panel porch timing |
| FRONT PORCH | `FUN_6004F2B4`, `FUN_600166D0` | No programmable panel porch timing |
| BACKLIGHT PWM | `FUN_6004F76C`, `FUN_600166F4` | No electrically timed PWM oscillator |
| BACKLIGHT EN | `FUN_6004FB2C`, GPIOF bit 4 and GPIOB bit 11 | GPIO set/clear/readback modeled; panel brightness gating not proven |
| BACKLIGHT DUTY | `FUN_6004FD64`, `FUN_60016890` | Panel parameter write modeled as bus transaction, duty effect absent |
| BACKLIGHT BRIGHTNESS | `FUN_6004FEF4`, `FUN_60016068` | Digital GPIO modeled; no calibrated luminance |
| BRIGHTNESS TABLE | `FUN_6001573C`, `FUN_600162B0`, `FUN_60016068` | Not a complete electrical backlight model |
| BOOSTER FREQUENCY | `FUN_6004F470`, `FUN_6001678C` | Vendor analog pump not modeled |

A screenshot of the SETTINGS menu is **not** proof of a measured frame
rate, PWM period/duty, power gating, inversion or optical brightness.
Never label these tests PASS from a rendered heading alone.

## CI scope

The owner-private CI adds **DISPLAY SETTINGS MENU visual coverage**:
genuine submenu title, all 11 black-ink caption rows, monochrome LCD,
two equal consecutive native frames, and a screenshot artifact.
The result explicitly includes `hardware_controls_verified=false`.
Existing six green full-display regressions (two factory ARM patterns,
CHIDORI, R-CHIDORI, FRAME, W-B GRADATION) remain the hardware
framebuffer acceptance baseline, not a complete set of eleven pattern
checks.

To reach real hardware parity, first trace and document the controller's
vendor command payloads (D/C and 0xB0000000 writes); then implement
panel-specific PWM/duty, inversion and porch state behind an opt-in
device-model feature. Test original guest UP/DOWN transitions and
negative controls, with read-only register tracing and separate
source-framebuffer versus optical-output evidence. Do not invent
panel register meanings or synthesize success.
