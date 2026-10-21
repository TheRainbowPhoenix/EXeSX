# SNVS high-power RTC and real M4 timer-path unlock — 2026-10-21

## Source and reproducibility

The original, locally uploaded Casio XD-SX9850/DY357 updater has SHA256 `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`. Only privately extracted ARM ELF images were executed in native EXeSX/QEMU 10.1.0. **No firmware, binaries, raw traces, snapshots or user credentials are committed.**

Prior SNVS command-register bring-up used NXP documented `HPCOMR` and `HPCR` controls. `EXESX_SNVS_DIAGNOSTIC_SECURITY_PULSES=1` remains a **research-only bypass of an unmodeled software-security-violation effect**. It does not authenticate or repair security state. Both earlier I²C mirrors are still synthetic peripheral replies.

## Real newly exposed M4 fault

With [PR #12 A7 peripheral startup support](2026-10-21-a7-usdhc-dma-bringup.md), real firmware runs for four seconds without an observed A7 Data Abort, while M4 reaches a precise BusFault on **`0x41070024`**, the SNVS HP real-time-counter MSB (`HPRTCMR`).

- M4 instruction near **`0x1FFD4D46`** reads SNVS `HPRTCMR` at `0x41070024`; adjacent `HPRTCLR` lives at `0x41070028`.
- The code samples high/low/high/low, compares both pairs, and retries if they disagree, then derives elapsed time. This is a counter-consistency loop, not evidence of another security violation.
- [NXP i.MX7ULP PERI_SNVS.h](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/periph/PERI_SNVS.h) names the two registers and `HPCR.RTC_EN` bit 0. SNVS HP RTC nominal reference tick frequency is 32.768 kHz, with the counter's documented fractional format. Consult the [i.MX7ULP Reference and Security Manuals](https://www.nxp.com/products/i.MX7ULP) for exact silicon lifecycle and high-power/low-power handoff behavior.

## New bounded virtual-time emulation

The existing `hw/arm/exesx-imx7ulp-snvs.inc` model is extended to expose only those two read-only RTC registers. The emulator increments an **initially-zero 32.768-kHz synthetic counter** based on `QEMU_CLOCK_VIRTUAL` while `HPCR.RTC_EN` is set; the count freezes when disabled and resumes on re-enable. The epoch and frozen-count words live in reserved **VMState-serialized private fields** of the existing MMIO register array, restoring with QMP snapshots.

This is *relative elapsed time only*: there is no calendar date, host wall-clock injection, RTC alarm/IRQ, tamper state, battery retention, secure time sync, or physical hardware equivalence. Unknown SNVS registers continue to fault. Writes to the RTC counter are not emulated; security command acceptance still requires explicit diagnostic opt-in.

A firmware-free `scripts/probe_snvs_hp_rtc.py` runs real ARM instructions to enable RTC, read the high/low pair, execute a bounded delay loop, read again, disable, delay again, and verify the count **advanced only while enabled**. Included in GitHub native CI and packaged diagnostics.

## Completed native and original-OSUP validation

The native GitHub Actions [RTC run 39565779140](https://github.com/TheRainbowPhoenix/EXeSX/actions/runs/39565779140) passed the real ARM RTC count/freeze test and all existing synthetic peripheral regressions. [PR #13](https://github.com/TheRainbowPhoenix/EXeSX/pull/13) was merged. A separate native original-OSUP run with synthetic off-chip I²C mirrors and **explicitly diagnostic** SNVS security pulses found **no M4 BusFault in 2.5 or 5 seconds** after the earlier 0x41070024 fault. This is not a real secured clock or OS boot.

The newly exposed A7 Data Abort, DFAR **`0x403800C0`**, belongs to USDHC1 `VEND_SPEC`. Merged PR #14 models the observed clock/reset register path, and the subsequent original-OSUP run reaches **MMDC0.MAPSR at `0x40AB0404`**. The [confirmed copied low-power routine](2026-10-21-usdhc1-mmdc-lowpower.md) requests MMDC low-power mode, waits for LPACK, then reaches an A7 WFI loop. That deliberately chosen suspend path is now the important next research question, not the SNVS RTC itself.

## Next experiment / evidence boundaries

After passing synthetic native CI, compare the locally supplied firmware on the previous and newly compiled QEMU for identical windows and environment settings. Specifically observe M4 BusFault (`BFAR/CFSR`), MCU timer read consistency, any new M4 interrupt, A7 Abort data fault (`DFAR`), and **actual OS code/entry** rather than inferring boot from an idle-loop sample. Name the next missing peripheral/register precisely if another fault emerges.

All real-firmware tests must retain clear distinction between an opt-in bypass of security commands and actual SNVS silicon behavior. The hardware references are indexed at [HARDWARE_REFERENCES.md](HARDWARE_REFERENCES.md).
