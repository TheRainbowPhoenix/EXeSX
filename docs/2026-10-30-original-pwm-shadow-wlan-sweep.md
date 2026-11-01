# 2026-10-30 — DY357 opt-in PWM compatibility and honest display/WLAN sweep

## Changes

The opt-in panel compatibility mode
`EXESX_EXPERIMENTAL_LCD_ORIGINAL_PWM_SHADOW=1`
reads the **unchanged original firmware's numeric settings** at
physical A7 RAM addresses `0x62344f3c` (frequency divisor, 32-bit)
and `0x62413262` (duty, 16-bit). Only valid values are accepted:
divisor 160..160000, duty 0..255. There is **no guest RAM mutation**.

QEMU's previously tested PWM diagnostic uses the original UI's
approximate model `f = 16,000,000 / divisor`, with a high pulse
`period * duty / 255`. Its read-only status window is at
`0xb1100000`, and marker `PWM2` confirms that actual A7 RAM
values were sampled. The default mode and original framebuffer
are unchanged. This is **functional approximation**, not a claim
that a hidden vendor-panel PWM command or actual optical hardware
was identified. The original frequency menu's identified helper
writes constant `1` over the LCD bus, not its changing divisor.

The separate `scripts/ci_e2e_display_advanced.py` MENU 1
regression is updated to enable the experimentally confirmed
transposed RGB565 byte order only on MENU 1. All other original
display tests continue to use the original color interpretation.

## Verifiable native test results

Linux native CI commit `76c192a352e69b0a4c4c9995a6a7db53f97efb35`,
Actions run `41127362308`, passed both:

- real ARM DCS 0x51 brightness A/B: distinct diagnostic PWM
  high times and byte-identical RGB565 framebuffer;
- real ARM writes to the exact **original firmware RAM addresses**:
  three separate QEMU boots with the following read-only output:

| Duty | Divisor | Nominal Hz | Period ns | High ns |
| --- | --- | ---: | ---: | ---: |
| 64/255 | 4665 | 3429 | 291563 | 73177 |
| 192/255 | 4665 | 3429 | 291563 | 219530 |
| 192/255 | 8192 | 1953 | 512000 | 385506 |

All three cases have **identical original RGB565 GRAM bytes**.
A separate local rerun against the exact CI-built native binary
also passed these assertions, with original QEMU diagnostic status
marker `0x50574d32` and raw framebuffer SHA-256
`63c5e6fc5da74419172bae49de0dac986fb1d9c8f7e71bb7f5caaa18d96d2c17`.
The stimuli here are **synthetic ARM writes to original addresses**,
NOT physical-key interactions with original BACKLIGHT DUTY/FREQ menus.

Local *unchanged owner original firmware* boot on the same
`76c192a...` Linux binary also passed factory ARM PATTERN
AUTO CHECK on attempt 2 with exact original LCD PPM SHA-256
`5a046dd6d3080c97c0c2bff76f130d4e05199a2d4dbae59e6aa5eb741df4eaaf`.
Proprietary ROM, eMMC, SD, runtime logs and screenshots remain
outside GitHub source.

## Real WLAN backend / original-ROM menu sweep

A native WINC1510 localhost TCP register/HIF backend was started
with `--gpio-status --hif-mailbox`, and QEMU configured with
`EXESX_WINC1510_TCP_PORT`,
`EXESX_WINC1510_GPIO_PROTOCOL=1`,
`EXESX_EXPERIMENTAL_LPSPI2_FIFO=1` and
`EXESX_EXPERIMENTAL_LPSPI2_DMA=1`.
The physical M4 keyboard successfully entered genuine
`TEST MENU -> MANUAL CHECK -> WIRELESS -> WLAN CHECK MENU ->
FIRMWARE MENU`. Separate native read-only LCD captures prove
both WLAN CHECK and FIRMWARE menus were painted with the TCP
backend running. **No successful radio HIF callback, version,
MAC, RSSI or communication verdict was demonstrated.**

The next physical-key sequence appeared to select VERSION
CHECK but ultimately displayed POWER SAVE MENU, so it was
rejected as a misnavigation. A further bounded, shorter-key
retry did not reliably enter MANUAL CHECK after factory
startup. The original BACKLIGHT DUTY menu also was not
reached in that bounded deep-navigation attempt. The
frontend did not fabricate a test verdict.

## Completed versus missing original-ROM display coverage

Native CI previously passed factory ARM AUTO/MANUAL, CHIDORI,
R-CHIDORI, FRAME, W-B GRADATION, plus an 11-row
DISPLAY SETTINGS **menu visual** check. An earlier MENU 1
test used the *incorrect* pre-byte-swap golden and failed;
its corrected golden now requires separate CI confirmation.
COLOR BAR 1 passed in prior local original-ROM tests.

Not yet independently verified from the original firmware:
8 COLORS AUTO, COLOR BAR 2, MENU 2, MENU 3, PATTERN AUTO,
the actual BACKLIGHT DUTY/FREQ menu driven transitions,
panel optical luminance/real PWM pin, other vendor timing
controls, and WLAN network/firmware/MAC/RSSI results.

### Safety and proof

Never upload proprietary OSUP/ELF, raw storage, execution logs,
private Wi-Fi SSIDs/passwords, or guest HIF payloads to public
GitHub. Keep visual screenshots as owner-only artifacts.
A screenshot of a menu being painted is **not** an OK
hardware verdict. All new test assertions must differentiate
original-ROM code paths from synthetic ARM probes, support
failure evidence, and avoid forging original 'PASS' screens.
