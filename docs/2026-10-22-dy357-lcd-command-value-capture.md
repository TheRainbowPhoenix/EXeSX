# Actual original DY357 LCD command/data and RGB565 write capture

**22 October 2026** — original user-owned DY357 update, SHA-256 `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`; private A7-only prepared ELF, update-derived eMMC, pinned EXeSX QEMU with real LPIT1 IRQ enabled. Only **derived metadata** is recorded here; raw bus values, firmware, pixel traces and media stay private.

## Firmware-confirmed external display interface

A real CPU0 QEMU 10.1 memory-value capture (not merely a static search for ROM opcodes) records **924 MMIO write events** during a bounded 10-second original-BIOS run:

| Address | Accesses | Interpretation and evidence |
| --- | ---: | --- |
| `0xB0000000` | 849 | Actual **16-bit** LCD command/parameter/RGB565 port writes |
| `0x400F0008` | 38 | GPIOA **PCOR**, clearing control pin. 36 writes masked by bit16 (plus two GPIOA19 operations) |
| `0x400F0004` | 37 | GPIOA **PSOR**, setting control pin. 36 writes masked by bit16 (plus one GPIOA19 operation) |

**Critical correction to prior investigation:** those GPIO addresses were previously incorrectly referred to as `0x44F00000/04`. The original ARM code at `0x6001524C/0x60015254` constructs **`0x400F0004`**; `STR [LR,#4]` is `0x400F0008`. Actual live values confirm `PCOR bit16 → STRH command to 0xB0000000 → PSOR bit16 → STRH parameters`. This is **functional proof of a D/C-select protocol on GPIOA16**, though physical wiring is still inferred absent a board schematic. The 16-bit pixel values are **not restricted to 8 bits**; many command parameters are physically stored as halfwords but interpreted on their low 8 bits.

For the captured stream, classifying data by **GPIOA16 level** (rather than instruction address) yields **36 commands**. The ordered *selected* values provide much stronger panel-family evidence than a generic 0x2A/2B/2C match:

| Command | Original observed data | Evidence-backed interpretation |
| --- | --- | --- |
| `0xB9` | `FF 52 98` | Vendor-specific extended-register unlock; **controller not identified** |
| `0xBD` | `00`, later `01`, later `00` | Vendor register bank selection candidate |
| `0xB1`, `0xB2`, `0xB4`, `0xDF`, `0xE0` | Variable initialization bytes | Power/timing/gamma-like extension commands; exact meanings vendor-specific |
| `0x11` | one recorded 00 parameter | DCS sleep-out command; some private command-stream encoders include a placeholder, not proof a real panel requires parameter |
| **`0x35`** | **`00`** | **DCS TEON** / tearing synchronization enabled |
| **`0x3A`** | **`55`** | **RGB565** pixel format |
| **`0x44`** | **`00 00`** | TE scanline configuration command |
| `0x36` | `60` | MADCTL orientation/configuration |
| `0x2A` | `00 00 03 1F` | Initial columns **0..799** (800 pixels) |
| `0x2B` | `00 00 01 DF` | Initial rows **0..479** (480 pixels) |
| `0x38` | no parameters | DCS idle-mode off |
| `0x2C` | followed by pixel data | RAMWR frame-memory write |

The observed initialization **supports a nominal 800×480 viewport**, not the earlier casual comparison with small ST7789 modules. **Do not claim the exact chip is ST7789**: the `B9 FF 52 98` vendor unlock sequence and unusually long extended initialization must be matched to a verified controller-specific datasheet. DCS/8080 bus semantics are documented in the [Sitronix ST7789V datasheet, 8080 parallel bus and D/CX](https://docs.espressif.com/projects/esp-dev-kits/zh-cn/latest/_static/esp32-s3-lcd-ev-board/datasheets/2.4_320x240/ST7789V_SPEC_V1.0.pdf); that is a *protocol reference*, not proof of this physical controller.

A **later** original direct drawing routine at `0x60015268` (following an initial setup `0x60015248`) programs `0x2A` parameters `00 00 03 035F` and `0x2B` parameters `00 00 01 01DF`, where the last parameter was transmitted as an actual **16-bit** `STRH`. Decoding only the low 8 bits of DCS window parameter bytes yields 0..**863** columns (864 pixels) and 0..479 rows; this differs from the 800-wide init window. It could reflect a padded framebuffer stride, a wider internal memory window, or a caller issue. **No authoritative panel width can be inferred from the latter call alone.** Preserve both raw halfword facts and their low8 DCS interpretation.

## Actual captured pixels, not an invented screen

The last command is a real `RAMWR 0x2C`. In the capture with GPIOA controls, the next **640** observed 16-bit pixel words were all `0xFFFF`, i.e. white in RGB565. An earlier *value-only* capture sampled **715** white pixels from the same drawing routine without the GPIO control events; the differing length reflects a **bounded run**, not a fixed-size DMA transfer. The private display trace contains **no rendered glyphs/text** and far fewer than the 384,000 pixels in an 800×480 full frame. White fill is consistent with an initial screen clear, **not proof of a complete white framebuffer**. Do not redistribute raw capture, pixel buffer or a guessed reconstructed screen.

The original BIOS later waits for **GPIOF13 HIGH then LOW** at `0x601B4144..0x601B4158`, after the separate opt-in LPIT1 interrupt already restored timer callbacks. This display init positively sends **TEON `0x35`** and **TESL `0x44`**, so an external LCD TE output to PTF13 is now a **much stronger hypothesis**. It is still unverified that the PCB connects those pins or that the real controller generates the assumed pulse period. Do not force a GPIO edge or fake an interrupt to claim boot progress.

## LCD diagnostic/test menus in original BIOS

The literal test strings found in the original firmware are genuinely referenced by code:

- `DISPLAY TEST MENU`: ASCII around `0x60164C68`, pointer `0x60067494`
- `DISPLAY TEST`: text at `0x60164BE4`, pointer `0x60067478`
- `MAINPANEL CHECK`: text at `0x60161EE8`, pointer `0x6005D6BC`
- `DISPLAY INFORMATION`: text at `0x60164F10`, pointer `0x60067BC8`
- `LCD BRIGHTNESS 0`: text at `0x60164194`, pointer `0x60069FE0`

The actual original **display-test menu** code is at `0x600673D4..0x60067470`, not simply a collection of strings. ARM BL instructions call text/selection helpers `0x60057550`, `0x600575B4`, `0x60057734`, `0x6005762C`, `0x60057668`, `0x60057720`, `0x60057650`. It branches on selection values **29, 30 and 31**; for two of them, the menu invokes `0x6004E6F0` with **R0=3 or R0=2** respectively. The *meanings* of those dispatcher mode numbers are not yet identified, and no display-test menu has been reached on the running original ROM. We should not force PC to the menu or invent button presses without an authenticated input device model.

## Reproducible private capture

A new **opt-in** `values=1` flag on `plugins/memtrace.c` uses QEMU 10.1's `qemu_plugin_mem_get_value()` to log successful write values; it is disabled by default, limited by existing `max=N` and filter ranges. This log contains original proprietary device/pixel bytes and must stay private. The file can be captured from a privately launched original ROM with:

```bash
# Additional existing -machine/-drive/-device/firmware arguments omitted
qemu-system-arm ... -plugin build/exesx-memtrace.so,virtual_only=1,values=1,max=2048,range=0xb0000000:0xb0000004,range=0x400f0004:0x400f000c \
  -d plugin,guest_errors,unimp -D private/lcd-value.log

python3 scripts/decode_lcd_bus_trace.py private/lcd-value.log \
  --json private/lcd-metadata.json
```

The decoder defaults to **GPIOA16 hardware D/C classification** when captured, and uses a known-original-ROM-PC fallback for older address-only traces; it publishes only *metadata* (commands, counts, windows, sampled RGB565 histogram) and **never the raw parameters or pixel stream**. Unit tests use fabricated command/pixel values, not firmware. The private value-aware probe captured and confirmed each actual GPIO and LCD write, but the private original trace and compiled local experimental plugin are not part of this repository.

**Remaining implementation work:** trace the input/output mux of GPIOA16 and GPIOF13, identify exact panel/vendor from further command tables or accessible physical markings, and construct an **opt-in real display command/GRAM device** with TE timing derived from identified controller. A real GUI rendering test requires enough pixels beyond the initial partial white fill and a known screen stride/panel size. No actual Casio OS boot or rendered LCD text has been established.
