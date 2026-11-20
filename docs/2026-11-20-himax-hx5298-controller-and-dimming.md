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

## Is the original DY357 ROM using 0x53 to dim?

**Not established from the accessible evidence.** The public EXeSX repository contains no owner-original `OSUP.BIN`, extracted ROM, Ghidra database, or complete private LCD bus trace. The published October trace contains a **selected** 36-command summary but does not report a `0x53` control-display transaction. That omission **must not** be interpreted as proof the ROM never uses it: the capture was bounded and did not exercise every display menu or brightness mode.

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
3. For any real `0x53` write, verify GPIOA16 was low for the command, then high for the first parameter. Examine `DD` transitions (`old ^ new & 0x08`), and correlate with `0x51` writes, `BCTRL`, `BL`, original brightness-menu execution, and an actual backlight/PWM or optical brightness change.
4. In a **private** Ghidra analysis of the original A7 image, cross-reference command-stream tables containing `0x53` and callers of `0x60015104`. Also follow `0x60015640` and the `LCD BRIGHTNESS 0` string's consumer. A literal `0x53` found elsewhere in ROM is **not** evidence of an LCD command until its dataflow reaches the command/data write path.

Do not claim hardware dimming is implemented or active unless an original-firmware code path and trace are demonstrated. Separately identify any LED driver/PWM: DCS panel-side `DD` and physical screen dimming need not be the same mechanism. No private firmware, register tables, or raw traces should be committed.
