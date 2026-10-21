# EXeSX measured bring-up status — 2026-10-21

**No genuine Casio OS entry, LCD pixels or text have been verified.** All real firmware experiments used the original locally SHA-verified proprietary OSUP. No firmware, private traces, snapshots or user credentials are in GitHub.

## Confirmed functional advances

- Cortex-A7 BIOS executes and releases M4 firmware. The i.MX7ULP MU v1 channel-bit ordering was corrected against Linux's actual imx7ulp mailbox driver: experimental M4 IRQ22 storm fell from 78,665 to 2 entries, and rejected TR2 sends from 5 to 0 in bounded runs. Off-chip I²C 0x4B and 0x40 chips remain unidentified; their optional register mirrors are **diagnostic inventions**.
- SNVS high-power `HPCOMR`/ `HPCR` now have a manufacturer-defined command subset. The real security lifecycle is **NOT modeled**; writes requesting software security-violation pulses are rejected unless `EXESX_SNVS_DIAGNOSTIC_SECURITY_PULSES=1` is explicitly set for a private research-only run.
- A bounded, snapshot-safe **32.768-kHz relative SNVS HP RTC** is now available at `HPRTCMR` `0x41070024`/`HPRTCLR` `0x41070028`, gated by `RTC_EN`. This removed the observed M4 BusFault at 0x41070024 in a subsequent real OSUP run. No host calendar/secure clock is emulated. [RTC investigation](2026-10-21-snvs-rtc-m4-followup.md).
- The earlier A7 Data Abort was at USDHC0 `0x40370024`, **not a corrupt IRQ return to 0x20002028**. Clock-ready-only USDHC0, DMA1 TCD/register storage, DMAMUX1 packed 8/16/32-bit register access, and LPSPI2 CR startup controls passed native ARM tests. No SD card, DMA transfer or SPI message is simulated. [A7 MMIO ladder](2026-10-21-a7-usdhc-dma-bringup.md).
- A second A7 Data Abort, `0x403800C0`, was identified as **USDHC1.VEND_SPEC**. Merged [PR #14](https://github.com/TheRainbowPhoenix/EXeSX/pull/14) models only vendor SDCLK-on bit8, SYS_CTRL reset/clock controls, host stable/no-card status and MIX_CTRL storage. It accepts an observed firmware write of 0xF to reserved SYS_CTRL low bits as RAZ/WI. Real OSUP advances beyond this controller setup, with native CI all green. [USDHC1 study](2026-10-21-usdhc1-mmdc-lowpower.md).

## Why the earlier MMDC0 shutdown occurred — resolved experimentally

The firmware shutdown path was deliberate: original M4 at `0x1FFD7782` reads **GPIOB.PDIR bit7**, then stores either `0xFFFFFFFF` (input high) or zero (input low) into A7 startup permission `0x2F029284`. The original A7 MainTask checks it at `0x6004A19C` and calls shutdown/DDR MMDC MAPSR self-refresh/WFI when zero. Our model had no externally driven GPIO inputs. [PR #15](https://github.com/TheRainbowPhoenix/EXeSX/pull/15) added `EXESX_GPIOB_INPUT_MASK=0x80`, strictly opt-in and respecting pin direction.

Two genuine cold original-ROM runs verified the branch without changing CPU registers or firmware: **GPIOB7 low → M4 writes zero → A7 shutdown; GPIOB7 high → M4 writes `0xFFFFFFFF` → A7 normal startup `0x6004A1BC`**. The physical Casio pin's wiring and default voltage remain unconfirmed. [Proof and named methods](2026-10-21-gpiob7-boot-permission.md).

## Current blocking subsystem — USDHC1 MMC/eMMC initialization

Progress along the normal startup path is source-verified, synthetic-ARM tested and original-ROM rechecked:

- [PR #16](https://github.com/TheRainbowPhoenix/EXeSX/pull/16): USDHC1 `WTMK_LVL=0x08200820` FIFO watermark and burst controls
- [PR #17](https://github.com/TheRainbowPhoenix/EXeSX/pull/17): `INT_STATUS` write-one-to-clear and documented interrupt-enable registers, with no invented card events
- [PR #18](https://github.com/TheRainbowPhoenix/EXeSX/pull/18): `PROT_CTRL`, `CMD_ARG`, `CMD_XFR_TYP`; no-response CMD0 host completion only, without pretending a card replied
- [PR #19](https://github.com/TheRainbowPhoenix/EXeSX/pull/19): bounded, QEMU-virtual-time **no-media `CMD1` timeout**, zero `CMDRSP0..3` rather than inventing a valid OCR; explicitly an approximate polling controller model

The original A7 BIOS at `0x60017988` tries **CMD0 → CMD1 → CMD2 → CMD3 → CMD9 → CMD7**, with subsequent MMC CMD6/SWITCH logic. This is characteristic of an **MMC/eMMC-class storage interface** (not a proven physical chip marking). With an empty slot the real firmware emitted, over a 2-second native run, **one CMD0, 65 CMD1 (OCR argument `0x40FF8000`), then one CMD7** as initialization/recovery proceeded. **No new MMIO Data Abort appeared in that bounded trace**, but A7 was not executing the OS section at `0x60400000`. See the [instruction-level MMC disassembly](2026-10-21-usdhc1-cmd0-no-media.md) and [verified no-media test](2026-10-21-usdhc1-no-media-timeout.md).

**Next indispensable component:** an actual **USDHC1↔MMC/eMMC** controller/card protocol integration, with accurate OCR/CID/CSD/EXT_CSD, card commands, block reads and backing medium. QEMU supplies [a TYPE_EMMC device](https://qemu.googlesource.com/qemu/+/25fef09ce17ac1ae22638a0b57d97c2bd5cd7d83/include/hw/sd/sd.h) and [an SDHCI host model](https://github.com/qemu/qemu/blob/master/hw/sd/sdhci.c), but register/IRQ/DMA differences with i.MX7ULP must be resolved before reuse. The private OSUP firmware update is **not** an established sector-for-sector eMMC image; physical chip and contents are still unknown. Do not fabricate card-ready bits or storage sectors.

The synthetic off-chip I²C mirrors, GPIO input voltage and SNVS security-command bypass are research-only; **none establishes the real Casio hardware state**. The shared M4/A7 IPC marker `0xEEEEEEEE` and the display/LCD still require validation. **No successful Casio OS entry or text output has been proven.**

**Official manufacturer and upstream references:** [HARDWARE_REFERENCES.md](HARDWARE_REFERENCES.md).
