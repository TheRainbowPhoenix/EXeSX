# 2026-10-30: original DY357 DISPLAY/WLAN physical-key live sweep (partial)

**Evidence boundary:** these observations were made with the owner-private,
unchanged A7/M4 `OSUP.BIN` (SHA-256
`d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`),
the locally downloaded Linux QEMU CI binary from
`1f0e63e5572f22ef82e6c0902c53723013dd72a5`,
`-accel tcg,thread=single`, real M4 physical contact-file input, original
LCD exported read-only through QMP, and source-derived eMMC/disposable SD
both using `snapshot=on`. No firmware, ELFs, pixel dumps, traces or disks
are committed here. The later branch-only archival changes do not establish
that every new QEMU build has been rerun through these menu tests.

**Already confirmed by separate [CI run 41041899931](https://github.com/TheRainbowPhoenix/EXeSX/actions/runs/41041899931):**
original ARM PATTERN AUTO CHECK passed exact framebuffer goldens. The
public synthetic QEMU tests are not original-ROM peripheral verdicts.

## Actual LCD observations

| Route | Verified guest LCD | Status |
|---|---|---|
| TEST MENU → MANUAL CHECK | Real 14-row MANUAL MENU | **ENTERED** |
| MANUAL → DISPLAY MENU | Real seven-row DISPLAY MENU | **ENTERED** |
| DISPLAY → DISPLAY TEST | Original 11-row DISPLAY TEST MENU | **ENTERED** |
| DISPLAY TEST → COLOR BAR 1 (row 2) | Original stable 864×480 eight-color pattern, PPM SHA-256 `5a046dd6d3080c97c0c2bff76f130d4dbae59e6aa5eb741df4eaaf`; two consecutive full-color frames identical | **PASS: framebuffer pattern**, not a monitor's optical/electrical test |
| DISPLAY TEST → remaining 10 entries | Not completed in controlled live sweep; firmware source enumerates the entries | **UNTESTED**, do not claim pass |
| DISPLAY → SETTINGS | 11 setting names identified in original A7 source, but the live SETTINGS menu and individual controls **were not reached** in this sweep | **UNTESTED** |
| MANUAL → WIRELESS (row 8) | Real five-row WLAN CHECK MENU | **ENTERED** |
| WLAN CHECK → FIRMWARE (row 4) | Real FIRMWARE MENU, options UPDATE and VERSION CHECK | **ENTERED** |
| FIRMWARE → VERSION CHECK (row 2) | Real `VERSION CHECK TEST` screen, still `NOW READING...` after passive observation; no version, OK, or NG | **BLOCKED / INCOMPLETE** |
| WLAN CHECK → COMMUNICATION / BATTERY LIFE / POWER SAVE / MAC ADDRESS | Source-identified menu entries, not all entered in this live sweep | **UNTESTED** |

The version check was a **disconnected WINC negative control**: FIFO/DMA
flags were enabled, but no Python ATWINC1510 TCP SPI-slave backend was
attached. Do not claim the implemented backend or a simulated WINC radio
failed this test, only that the owner original firmware did not complete a
version read in this configuration. Prior original-ROM factory WIFI AUTO
TEST was shown to require a separate **USB fixture**, not the direct
ATWINC1510 WLAN CHECK route.

## Exact planned safe coverage (not completed)

- **DISPLAY MENU**: DISPLAY TEST, SETTINGS, IMAGE DISPLAY CHECK from SD,
  JPEG DATA DISPLAY, BMP DATA DISPLAY, MAG DATA DISPLAY, MESSAGE CHECK.
  File/image checks need matching files and explicit error-path expectations.
- **DISPLAY TEST MENU**: 8 COLORS AUTO, COLOR BAR 1, COLOR BAR 2,
  CHIDORI, R-CHIDORI, FRAME, W-B GRADATION, MENU 1, MENU 2, MENU 3,
  PATTERN AUTO. For each, verify the selected LCD row, genuine handler
  transition, stable read-only framebuffer capture and return to the
  original menu. Auto tests require multiple original key events and
  frame-by-frame verification, not one static screenshot.
- **DISPLAY SETTINGS MENU**: COLOR MODE, FRAME FREQUENCY, INVERSION,
  BACK PORCH, FRONT PORCH, BACKLIGHT PWM, BACKLIGHT EN, BACKLIGHT DUTY,
  BACKLIGHT BRIGHTNESS, BRIGHTNESS TABLE, BOOSTER FREQUENCY. These are
  hardware **controls**, not independently judged PASS/NG tests; enumerate
  them read-only before any controlled snapshot-only mutation. FRAME
  FREQUENCY invokes the original separate protected-operation key gate.
- **WLAN CHECK MENU**: COMMUNICATION → RSSI, BATTERY LIFE, POWER SAVE MODE,
  FIRMWARE → VERSION CHECK, MAC ADDRESS → GET MAC ADDRESS. Skip
  FIRMWARE UPDATE, AP/password changes and high-load connect/stress tests
  until the original WINC SPI/HIF + IRQ, real asynchronous callbacks,
  negative-control tests and an isolated fixture are proven.

## Critical harness findings / safety

1. Even after the correct factory startup, M4 physical key contact timing
   is not deterministic: some `0x94` ENTER contacts are missed; some
   `0x90/0x91` selections skip or wrap rows. A header or full-image
   hash change **from a highlight redraw** is not submenu-entry evidence.
   Require the original LCD *title region* to change and stabilize;
   verify the inverse-highlighted target before every ENTER.
2. Individual DISPLAY PATTERN handlers `FUN_6004e010` wait for physical
   code `0x95` to return, not the assumption that code `0x92` exits
   every screen. Auto-pattern handlers `FUN_6004df58` and
   `FUN_6004df98` require successive original key events.
3. The read-only WLAN firmware VERSION CHECK screen did **not** exit on
   the first `0x95` contact within the bounded test; that is not an
   original test verdict.
4. Keep **original ARM PATTERN regression** unchanged and green. **Do
   not add the 11-pattern, SETTINGS or WLAN suite as CI acceptance tests
   until each golden/error path is locally reproduced**. Failed cold
   boots should be reported separately from test failures.
5. Two historical non-authentic scripts were moved to
   `scripts/_trash_doNotUse/`: `force_factory_menu_experimental.py`
   (guest PC redirection) and `probe_synthetic_factory_menu.py`
   (injected event records). Authentic physical-key tools remain active.
