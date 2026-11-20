# DY357 LCD: Himax HX5298/HI5298 candidate and 0x53 dimming audit (2026-11-20)

## Evidence and identification confidence

**Status: candidate, not chip-ID confirmation.** A user comparison across Himax manuals reports that the unnamed **HX5298** controller is closest in its vendor-register behavior to **HX8399-C**, while some registers resemble **HX8398-A** or **HX8399-A**. The spelling **HI5298** has also been proposed; neither the full part name nor the HX/HI distinction is verified by a package marking, a panel label, an ID read, or a publicly checked HX5298/HI5298 datasheet. Treat these as research leads, **not** an authenticated controller identity.

The existing original-DY357 BIOS memory-value trace *does* establish:

- Command/data GPIOA16 and 16-bit writes to `0xB0000000`.
- A vendor-unlock command `B9 FF 52 98`, register bank selection `BD 00/01/00`, and vendor commands `B1/B2/B4/DF/E0`.
- MIPI DCS operations `35` (TEON), `3A 55` (RGB565), `36 60` (MADCTL), `44` (TE scanline), `2A/2B` (address windows), and `2C` (RAMWR).
- An initial 800x480 window and a subsequent 864x480 drawing window. Those do not independently establish the panel's native glass resolution.

These findings make a Himax-register comparison useful, but a shared DCS command or `B9` unlock mechanism cannot establish a manufacturer. HX8399-C is a **register-semantic reference**, not an electrically interchangeable part: its published display specification is for a different resolution and interface configuration than the observed DY357 parallel command/data bus.

Cross-check **each** original `B1/B2/B4/BD/DF/E0` command's length, bank selection, argument semantics, and value against the proposed HX5298 documentation, annotating discrepancies with HX8398-A/HX8399-A. Do not copy confidential manual contents or firmware command payloads into the repository.

References: [original DY357 LCD capture](2026-10-22-dy357-lcd-command-value-capture.md), [Himax HX8399-C datasheet reference](https://dl.espressif.com/AE/esp-iot-solution/HX8399-C_DS_temporary_v00.06_150714.pdf).

## DCS 0x53: write_control_display, not a brightness byte

The HX8399-C control-display definition and standard DCS-style register descriptions agree on these first parameter bits:

| Mask | Name | Meaning |
| --- | --- | --- |
| `0x20` (bit 5) | `BCTRL` | Enables brightness control using the brightness register. |
| `0x08` (bit 3) | `DD` | Enables display dimming / gradual transitions in supported configurations. |
| `0x04` (bit 2) | `BL` | Backlight control enable. |

**Important:** setting or clearing `0x53` bit 3 controls *dimming behavior*; it does **not**, by itself, prove that the firmware reduced brightness. Under the HX8399-C description, `DD=1` applies a dimming transition when brightness-control state changes; `0x51` (write_display_brightness) or a separate backlight/PWM path may be involved in real level changes. A `0x53` value of `0x28` has `BCTRL=1`, `DD=1`, and `BL=0` by these bit definitions, so inferring emitted light from bit 3 alone would be incorrect.

References: [Linux MIPI DCS command definitions](https://github.com/torvalds/linux/blob/master/include/video/mipi_display.h) and the HX8399-C manual above.

## Already demonstrated: factory LCD test exercises the display

The [original-firmware guarded factory menu sweep](2026-10-26-original-factory-menu-test-sweep.md) records actual original A7 firmware entering **TEST MENU item 12, LCD UNIT CHECK**, with visible RGB gradient/test fields followed by white. It also records original LCD color bars for ARM PATTERN MANUAL/AUTO CHECK (items 2/3). These are positive observations of *original firmware exercising LCD drawing*. The newer ARM PATTERN AUTO CHECK run additionally captures real DCS `0x53` and `0x51` commands; the earlier LCD UNIT CHECK sweep itself was not instrumented for dimming. This evidence is stronger than synthetic guest tests for deciding whether display drawing is used, but cannot answer whether `DD` is exercised.

**Current emulator limitation:** `hw/arm/exesx-lcd.inc` accepts and remembers a command byte but `exesx_lcd_parameter()` handles only selected DCS commands (including `0x35`, `0x36`, `0x3a`, `0x2a`, `0x2b`, and `0x2c`). The default handler ignores unknown commands' parameter bytes, including **`0x53` and `0x51`**. Therefore even if owner-original firmware sends `0x53` during LCD UNIT CHECK, the current QEMU presentation will **not** dim in response to it. Trace the writes first; do not implement brightness visuals as proof that they happened.

Build CI's synthetic LCD screenshot and MADCTL tests passing does **not** constitute an original-ROM LCD UNIT CHECK rerun. A direct re-test needs a local owner-held `OSUP.BIN` / extracted original ROM, its private media setup, and safe original factory-menu navigation. These assets are excluded from the public repository; no runtime claim should be made without them.

## Is the original DY357 ROM using 0x53 to dim?

**Measured answer: yes, the unchanged original ROM uses `0x53` and `0x51` during ARM PATTERN AUTO CHECK, but `DD` bit 3 was CLEAR in that tested path.** The release fixture contains the SHA-verified original `OSUP.BIN`, extracted A7 ELF, sparse eMMC data and an original-firmware six-attempt factory-menu regression. This fixture was executed on GitHub Actions using the matching native EXeSX QEMU build and the opt-in **control-only** plugin.

- [Original-ROM CI run 44827804708](https://github.com/TheRainbowPhoenix/EXeSX/actions/runs/44827804708): original factory ARM PATTERN AUTO CHECK **PASS on attempt 1**; screenshot matches reference golden image. The sole observed `0x53` command was emitted at original PC `0x6001514C`, first parameter at `0x600151F8`: **BCTRL=1, DD=0, BL=1**. The original CPU also emitted two `0x51` brightness commands at **`0x60016158`** and **`0x60016258`** (first parameters at `0x60016168`, `0x60016268`). Trace summary: **cmd53=1, params53=1, DD transitions=0, cmd51=2, params51=2**.
- [Synthetic tracer calibration run 44827534996](https://github.com/TheRainbowPhoenix/EXeSX/actions/runs/44827534996): synthetic ARM sent deliberate `0x53` (DD=1) and `0x51` commands; both were recorded correctly and LCD screenshot test passed. **QEMU plugin logging `-d plugin` was required**; earlier uncalibrated empty traces must not be considered evidence of non-use.

The `0x53` PC is the **generic LCD command emitter**, not the established top-level brightness-menu caller. `0x51` writes are original display-brightness commands, but the tracer redacts their parameter values: it does not prove that two different brightness levels were selected. The run covers the TEST MENU's **ARM PATTERN AUTO CHECK (item 3)**, **not** LCD UNIT CHECK (item 12) or a user-initiated brightness-setting transition. No `DD=1` or `DD` toggle was measured in this bounded path. Therefore there is **no verified hardware dimming activation** from this test.

Useful existing reverse-engineering anchors:

| Original firmware address | Why inspect |
| --- | --- |
| `0x60015104` | BIOS command-stream interpreter: trace input tables and callers, including banked commands. |
| `0x60015640` | Frequently called display state/on-off routine: check whether brightness or dimming calls pass through it. |
| `0x60015328` | MADCTL helper; identifies the display-command writing family. |
| `0x600153D0` | B2 vendor-configuration helper; compare register-bank semantics. |
| `0x60164194` / pointer `0x60069FE0` | `LCD BRIGHTNESS 0` diagnostic string and reference; xref containing menu code, **not evidence of a 0x53 write**. |

### Reproducible owner-private check

1. Run the **unchanged original ROM** under native QEMU with the existing opt-in memtrace plugin, capturing writes to `0xB0000000:0xB0000004` **and** GPIOA PSOR/PCOR `0x400F0004:0x400F000C`. Enable `values=1`, use sufficient `max` (or focused capture around a safe original brightness-test action), and retain the raw log locally.
2. Run `python3 scripts/decode_lcd_bus_trace.py private/lcd-value.log --json private/lcd-metadata.json`. The decoder's `control_display_0x53` summary contains **counts and bit-state metadata only**, never raw command parameters. Zero observed commands means `not observed in this trace`, not `unused by the ROM`.
3. For any real `0x53` write, verify GPIOA16 was low for the command, then high for the first parameter. Examine `DD` transitions (`(old ^ new) & 0x08`), and correlate with `0x51` writes, `BCTRL`, `BL`, original brightness-menu execution, and an actual backlight/PWM or optical brightness change.
4. In a **private** Ghidra analysis of the original A7 image, cross-reference command-stream tables containing `0x53` and callers of `0x60015104`. Also follow `0x60015640` and the `LCD BRIGHTNESS 0` string's consumer. A literal `0x53` found elsewhere in ROM is **not** evidence of an LCD command until its dataflow reaches the command/data write path.

Do not claim hardware dimming is implemented or active unless an original-firmware code path and trace are demonstrated. Separately identify any LED driver/PWM: DCS panel-side `DD` and physical screen dimming need not be the same mechanism. No private firmware, register tables, or raw traces should be committed.
