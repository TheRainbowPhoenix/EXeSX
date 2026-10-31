# DY357 LCD/backlight verification: native ARM PASS, original settings still incomplete

**Date:** 2026-10-30. **Branch:** `experiment/dy357-wlan-host-20261029`.

## Verified on the QEMU build containing LCD DCS-state changes

The native Linux GitHub Actions run **41105153892**, job `native-qemu`,
passed the original-arm MMIO regression tests:

- Original SoC GPIOF/Port F bit 4 at `0x400F00C0`: output-high
  PDIR `0x10`, output-low PDIR `0x00` (EN2).
- Original SoC GPIOB/Port B bit 11 at `0x4100F040`: output-high
  PDIR `0x800`, output-low PDIR `0x00` (EN3).
- LCD DCS `SLPOUT`, `DISPON`, `INVON`, `IDMON`, standard
  brightness `0x51` with value `0x80` and raw vendor `B2`
  data: read-only diagnostic values matched the original ARM-written data.
- Normal 864×480 RGB565 orientation, window clipping and pixel order
  remain unchanged.

The tests execute ARM instructions with `-machine exesx`, **not**
Python register mocks. The corresponding public scripts are
`scripts/probe_lcd_backlight_enable.py` and
`scripts/probe_lcd_landscape.py`. They run in
`.github/workflows/qemu.yml`.

**The outcomes above verify digital register behavior, not physical PWM,
luminance, booster oscillator or panel optical response.**

## Private original-ROM test outcomes

A local original-A7/M4 boot with source-derived eMMC and disposable SD,
both opened `snapshot=on`, did reach the original factory TEST MENU,
MANUAL MENU, DISPLAY MENU and the eleven-item DISPLAY SETTINGS MENU.
The original A7 `FUN_6004FD64` duty handler has also been observed in
an earlier run. However, a subsequent attempt to interact with the DUTY
handler was not confirmed by an independent handler-state screenshot or
measured register change.

The latest bounded original-ROM attempts failed due to factory-key
acceptance (one boot) or physical-key navigation that skipped/wrapped
highlight rows (subsequent attempts). These must not be reported as DUTY
or PWM hardware failures or successes. **No original-ROM PWM/brightness
hardware PASS has been obtained.**

## Firmware-derived contract

From the owner-private decompilation (no proprietary source committed):

| Control | Original routine | What the guest issues | Hardware-level evidence |
|---|---|---|---|
| BACKLIGHT EN | `FUN_6004FB2C` / `FUN_60015468/7C/90/A4` | GPIOF bit 4 and GPIOB bit 11 set/clear | **PASS** digital model via real ARM |
| BACKLIGHT DUTY | `FUN_6004FD64` → `FUN_60016890(duty)` | 16-bit LCD data-port write, duty bound `0..255` | **NOT VERIFIED** waveform or live data register |
| BACKLIGHT PWM FREQ | `FUN_6004F76C` → `FUN_600166F4` | Frequency divisor maintained in firmware RAM; current decompilation path also sends a literal `1` to LCD data port | **NOT VERIFIED** actual programmable PWM frequency |
| BRIGHTNESS | `FUN_6004FEF4` → `FUN_60016068` | Brightness levels `0..5`, panel-bus writes and GPIO enable transitions | **PARTIAL** GPIO only |
| INVERSION / PORCH / BOOSTER | Various `FUN_6004E...` and `FUN_6001678C` | Vendor settings and panel transfer | **NOT VERIFIED** analog/scan timing |

A host read-only DCS status export at `0xB1100000` records the
implemented standard DCS state and raw `B2` parameters. Other
vendor-specific panel control semantics are not established. The current
TE model is a fixed approximate 60 Hz pulse, **not** a calibrated timing
generator. A framebuffer screenshot cannot measure panel brightness.

## Required before marking all backlight settings PASS

1. Resolve the actual panel-controller identity and vendor register map
   from owner hardware or original bus captures.
2. Capture original A7 LCD command/data traffic plus GPIO readback
   **after** genuine M4 row-verified entry into each settings handler.
3. Implement the documented vendor PWM duty, frequency, inversion,
   porch and pump semantics with real negative/transition tests. Keep
   vendor effects separate from raw RGB565 GRAM contents.
4. Add to CI only independently verified original-firmware outcomes;
   never synthesize an `OK` screen or call a painted menu a PWM PASS.

The separate current private E2E suite remains flaky at cold-boot
matrix-key acceptance and deep-menu navigation; these are not LCD
hardware verdicts.
