# EXeSX measured status — 2026-10-21

**No Casio OS entry, LCD pixels, or on-screen text have been verified.** All native runs use the original privately supplied SHA-verified OSUP; firmware, snapshots and credentials are excluded from public GitHub.

## Verified milestones

- Native Cortex-A7 BIOS and Cortex-M4 firmware execute in QEMU 10.1.0 with custom i.MX7ULP MMIO and GPIO/ADC/DMA/MU support. Off-chip I²C 0x4B/0x40 devices remain unidentified; only **opt-in synthetic mirrors** can bypass their NACKs.
- The i.MX7ULP **MU v1 status-bit numbering bug** was corrected using the explicit upstream Linux i.MX7ULP mailbox driver. M4 IRQ22 storms fell from 78,665 to 2 in bounded real firmware, and five busy A7 TR2 sends fell to zero. [Full MU evidence](2026-10-20-imx7ulp-mu-v1-bit-order.md).
- M4 SNVS high-power command registers `HPCOMR` and `HPCR` now have a strict documented subset. **Software security-violation commands remain rejected by default**, or can be ignored **only with explicit research-mode opt-in**. Neither setting models a valid SNVS security lifecycle. [SNVS HP investigation](2026-10-21-snvs-hp-investigation.md).
- **Corrected A7 Abort diagnosis:** the earlier IRQ-return-to-0x20002028 theory was wrong. The fault was at **USDHC0 PRES_STATE 0x40370024** (A7 instruction 0x60034F18), polling the stable-host-clock bit. Bounded early models for USDHC0, A7 DMA1/TCD storage, DMAMUX1 byte/word access, and LPSPI2 control now permit a real 4-second run without A7 Data Abort. **There is no simulated SD card, DMA transfer, or SPI device.** [A7 peripheral ladder](2026-10-21-a7-usdhc-dma-bringup.md).
- **New M4 fault:** SNVS HP RTC MSB read at **0x41070024**, code around 0x1FFD4D46 (paired with LSB at 0x41070028), after A7 peripheral progress. An evidence-based **32.768-kHz QEMU virtual-time RTC high/low read subset** is under native test. No wall clock, calendar, secure time, tamper, wake or alarm is fabricated. [M4 HP RTC follow-up](2026-10-21-snvs-rtc-m4-followup.md).
- The repeatedly sampled A7 DMA1 CR read at **0x601CBC34** tests **bit 31, DMA_CR.ACTIVE**, a documented engine-active status. In the early-control-only model, no channel runs and the flag stays clear. That loop alone is not a proven deadlock.

## Next verification

Run the patched HP RTC against the same private OSUP with diagnostic I²C and explicitly diagnostic SNVS pulses; compare M4 fault register/PC, A7 DFSR/DFAR, actual OS entry `0x60400000`, and next unsupported MMIO access. Keep all unsupported peripheral operations explicit; do not insert fictitious card data, DMA completions, security states, or UI success.

**Primary external references:** [manufacturer and upstream hardware reference index](HARDWARE_REFERENCES.md).
