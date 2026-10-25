# Original DY357 factory-menu auto-drive: real LCD captures and exact blocker (2026-10-25)

**No private ROM, extracted ELF, raw QMP trace, media or LCD screenshot is checked into the public repository.** Source original owner OSUP SHA-256: d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0.

## Real guest test, not synthesized pixels or firmware key return

Using the successful native Linux QEMU build at main commit ad51e58b1291215b0a737fec6685359a4e80351d, with source-derived synthetic eMMC and optional disposable SD mounted snapshot-on, the no-debugger Python auto-driver drove physical matrix contacts 0x9C+0x90 from reset, released after original M4-to-A7 CA05 handshake, waited for original A7 version-dialog event-wait 0x600108A8, then closed/released original electrical 0x93, 0x93, 0x94 individually (60ms holds, 25ms gaps). No CPU/PC override, RAM IPC patch, emulated glyph injection or fabricated RTOS event was used.

**Original A7 execution milestones from the successful menu pass:**

| Original PC | Observed host time | Meaning |
| --- | ---: | --- |
| 0x60010868 | 13.014s | Actual A7 version-dialog handler |
| 0x600108A8 | 13.074s | Keyboard-event wait |
| 0x60010910 | 13.351s | First key check |
| 0x60010928 | 13.351s | Third key check |
| 0x60010930 | 13.351s | Correct final-key path |
| 0x6003A878 | 13.351s | Authentic factory TEST MENU entry |
| 0x60006240 | 13.351s | Synchronous service 0x400B |
| 0x60006268 | **not observed** | Required post-service return |
| 0x60057668 | **not observed** | Menu glyph painter |

Actual emulated 864x480 LCD PPM snapshots were requested by a one-shot host capture request and converted losslessly to PNG. The first screenshot captured **before** any second-stage menu keys, after the version dialog had actually painted. The second screenshot captured **after** the original menu-entry PC. Both contain the same authentic original BIOS/OS version-information popup on a white background; pixel data are **identical** (PPM SHA256 c3a539130372499fe3fda848fe70bf86444c0b04041734f7fc5fbd88ca4ae573). Each image has 408,674 white pixels, 6,046 black pixels, no other colors. Screen text identifies model DY357 and BIOS/OS version details. These are private owner screenshots distributed in the conversation, not committed to this public repo.

**Crucial: the test-menu function is entered but the visible test menu is NOT painted.** Reaching 0x6003A878 is not equivalent to painting the menu. The LCD still displays the version popup because service 0x400B has not returned to the original caller in the observed time window.

A distinct private no-debugger/real-firmware QMP control on a previously verified binary, also after original fresh-boot menu entry, read shared IPC at 0x2F028000 as handshake 0xEEEEEEEE and pending request word **0x0001400B** at 0x2F02800C. The native A7 painter and post-IPC return remained absent. This corroborates a stalled original M4/A7 synchronous service, **not a proven emulator crash or invalid keycode**. The private QEMU run exited only because the bounded auto-driver terminated it, not from a spontaneous process fault.

## Implementation / validation status

- scripts/auto_driver.py: Windows/Linux standard-library-only, accepts private OSUP for local media preparation or precomputed private ELF/eMMC. Uses two independent cold boots, exact guest PC milestones, adjustable stage timing/retries, safe non-destructive SD image snapshots, real PPM→PNG screenshots and structured checkpoint/pixel diagnostics.
- hw/arm/exesx-lcd.inc / hw/arm/exesx.c: on-demand EXESX_LCD_CAPTURE_REQUEST_FILE request, without continuous 864x480 PPM writes that slow original guest timing. Preserves prior periodic capture without opt-in.
- scripts/probe_lcd_on_demand.py: synthetic ARM performs real GPIO/LCD RGB565 MMIO; two independent on-demand requests passed on Linux native QEMU (864x480 exact pixels).
- tests/test_factory_auto_driver.py: unit checks for exact executed-PC parsing, complete raw screen validation, lossless PNG, and atomic host screenshot requests. Windows unit tests passed prior to the additional on-demand Windows probe; CI build outcome must be consulted separately.
- The first automated popup capture triggered at dialog **entry** was blank because original firmware had not painted text yet; the correct request waits at least ~0.6 *host* seconds after original event-wait. A later authentic screenshot under this timing confirmed actual popup pixels. This timing is experimental, not a QEMU virtual-clock invariant.

**Next exact device-protocol task:** trace original M4 handler/completion for service 0x400B(2), original event object7 consumer and actual MU completion envelope. A real hardware/firmware response, not a hardcoded success, must cause A7 to resume at 0x60006268 and then 0x60057668 before claiming visible TEST MENU or running menu-selected SD diagnostics. The auto-driver does not run destructive FORMAT/WRITE tests; those require a separate disposable-card selector test after menu paint is proven.
