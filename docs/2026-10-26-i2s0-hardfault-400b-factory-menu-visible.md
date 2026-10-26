# 2026-10-26: genuine factory TEST MENU visible — M4 SAI0 bus fault fixed

## Root cause from the original firmware

During synchronous factory IPC 0x400B(2), the original Cortex-M4 HardFaulted inside its SAI/audio initialization, before releasing RTOS event object 10. Hardware fault registers:

- CFSR 0x00008200 — precise data bus fault with BFAR valid.
- HFSR 0x40000000 — escalated HardFault.
- BFAR **0x41037008** — attempted access to **I2S0/SAI0 TCSR (+0x08)**.

NXP's i.MX7ULP headers identify I2S0 base 0x41037000 and I2S1 base 0x410AA000. EXeSX had omitted both from its M4 peripheral map. The M4 recovery path emitted mode 0xCAFC, failed to signal event object 10, and left the original A7 waiting indefinitely for 0x400B.

Public references:
- [NXP MCIMX7U5_cm4_COMMON.h](https://github.com/zephyrproject-rtos/hal_nxp/blob/50f039d54381e6445336f502a1b01973e84861bf/mcux/mcux-sdk-ng/devices/i.MX/i.MX7ULP/MCIMX7U5/MCIMX7U5_cm4_COMMON.h)
- [NXP PERI_I2S.h](https://github.com/zephyrproject-rtos/hal_nxp/blob/50f039d54381e6445336f502a1b01973e84861bf/mcux/mcux-sdk-ng/devices/i.MX/i.MX7ULP/periph/PERI_I2S.h)

## Source fix

Implemented a strict I2S control/register MMIO model in hw/arm/exesx-imx7ulp-i2s.inc; routed it through exesx-imx7ulp.inc; registered both SAI0/SAI1 windows in profiles/imx7ulp-early-boot.ini; and copied the module through scripts/integrate_qemu.py. NXP-documented registers only: TCSR/TCR1-5/TDR/TFR/TMR and RCSR/RCR1-5/RDR/RFR/RMR. Basic CSR software/fifo-reset auto-clear and W1C status behavior; reserved offsets and unsupported writes still cause bus errors. This is **not** a fabricated RTOS event, mailbox acknowledgment, ROM patch or forced CPU PC. No speaker waveform, DMA audio transfer or external sound device is claimed.

A no-proprietary-firmware, real-ARM-MMIO regression (scripts/probe_i2s_sai.py) verifies SAI0 and SAI1 configuration read/write, reset behavior, reserved hole rejection and the intentionally unmapped control. Correct FIFO-reset bit is 0x02000000 (bit 25).

## Verified original OSUP cold boot (Linux native QEMU)

The unchanged user-provided original OSUP.BIN SHA256 d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0, private extracted ELF, owner-derived synthetic eMMC and disposable 2 GiB SD (snapshot-on) were used. Firmware and private disk/trace/image data were **not uploaded to GitHub**.

Physical row-gated matrix inputs: hold 0x9C+0x90 at boot; release; after the real A7 event wait at 0x600108A8 send 0x93, 0x93, 0x94 with 60 ms press and 25 ms release.

An authentic no-debugger native ARM translated-block trace showed the original firmware actually executed:

| Original A7 PC | Outcome |
| --- | --- |
| 0x60010868 — version-dialog code | PASS |
| 0x600108A8 — event wait | PASS |
| 0x60010930 — final key accepted | PASS |
| 0x6003A878 — factory-menu entry | PASS |
| 0x60006240 — IPC 0x400B invoke | PASS |
| **0x60006268 — IPC 0x400B returned** | **PASS** |
| **0x60057668 — genuine menu painter** | **PASS** |

Two independent successful cold boots reached entry and painter. Other cold boots missed startup timing, so retry remains useful.

The existing auto_driver.py then captured **two actual 864x480 LCD RGB frames** after separate cold boots. The first is the original version dialog (6046 black pixels / 408674 white); the second shows the **actual 16-item TEST MENU** (26099 black / 388621 white). Original PPM SHA256 differs: popup c3a539130372499fe3fda848fe70bf86444c0b04041734f7fc5fbd88ca4ae573; true menu cf12b3a9fbeaabe20b7fa986322336efdcdf5a74d8f358e6902730e1bd3eb893.

Visible menu items include MANUAL CHECK, ARM PATTERN MANUAL CHECK, ARM PATTERN AUTO CHECK, FFT TEST, WLAN AUTO TEST, LCD UNIT CHECK, VERSION and OS UPDATE.

The same genuine-M4 physical input and read-only QMP headless_factory_menu_checks.py performed ten non-destructive checkpoints, including a single original **DOWN key 0x91** after painter; the LCD framebuffer **changed** after DOWN. No SD FORMAT, WRITE, OS UPDATE, factory data destruction or blind confirmation key was performed.

Linux native QEMU [CI 40315315547](https://github.com/TheRainbowPhoenix/EXeSX/actions/runs/40315315547) and Windows [CI 40315315477](https://github.com/TheRainbowPhoenix/EXeSX/actions/runs/40315315477) both passed the SAI implementation and synthetic MMIO tests. Successful experimental guest trace uses compiled native source commit ed1579c609e34e804f1c37e72a349b2c809f85b2. A later follow-up refines headless test status reporting only (no peripheral changes).

## Reproduce on Windows

Download the latest successful Windows Actions artifact including BOTH QEMU binary and revised profiles/imx7ulp-early-boot.ini. Extract all files, then launch, using PowerShell:

    py -3 .\scripts\headless_factory_menu_checks.py "C:\Casio\OSUP.BIN" --qemu ".\qemu-system-arm.exe" --seconds 100 --retries 3 --post-menu-seconds 8

Alternatively use the floating factory_control_panel.py and click AUTO TEST MENU to see and navigate the real emulated LCD.

**This fixes the original M4 HardFault and makes the visible factory menu available.** Actual factory functions beyond one safe DOWN navigation are not yet validated.
