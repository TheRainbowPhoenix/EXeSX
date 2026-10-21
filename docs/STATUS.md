# EXeSX measured bring-up status — 2026-10-21

**No genuine Casio OS entry, LCD pixels or text have been verified.** All real firmware experiments used the original locally SHA-verified proprietary OSUP. No firmware, private traces, snapshots or user credentials are in GitHub.

## Confirmed functional advances

- Cortex-A7 BIOS executes and releases M4 firmware. The i.MX7ULP MU v1 channel-bit ordering was corrected against Linux's actual imx7ulp mailbox driver: experimental M4 IRQ22 storm fell from 78,665 to 2 entries, and rejected TR2 sends from 5 to 0 in bounded runs. Off-chip I²C 0x4B and 0x40 chips remain unidentified; their optional register mirrors are **diagnostic inventions**.
- SNVS high-power `HPCOMR`/ `HPCR` now have a manufacturer-defined command subset. The real security lifecycle is **NOT modeled**; writes requesting software security-violation pulses are rejected unless `EXESX_SNVS_DIAGNOSTIC_SECURITY_PULSES=1` is explicitly set for a private research-only run.
- A bounded, snapshot-safe **32.768-kHz relative SNVS HP RTC** is now available at `HPRTCMR` `0x41070024`/`HPRTCLR` `0x41070028`, gated by `RTC_EN`. This removed the observed M4 BusFault at 0x41070024 in a subsequent real OSUP run. No host calendar/secure clock is emulated. [RTC investigation](2026-10-21-snvs-rtc-m4-followup.md).
- The earlier A7 Data Abort was at USDHC0 `0x40370024`, **not a corrupt IRQ return to 0x20002028**. Clock-ready-only USDHC0, DMA1 TCD/register storage, DMAMUX1 packed 8/16/32-bit register access, and LPSPI2 CR startup controls passed native ARM tests. No SD card, DMA transfer or SPI message is simulated. [A7 MMIO ladder](2026-10-21-a7-usdhc-dma-bringup.md).
- A second A7 Data Abort, `0x403800C0`, was identified as **USDHC1.VEND_SPEC**. Merged [PR #14](https://github.com/TheRainbowPhoenix/EXeSX/pull/14) models only vendor SDCLK-on bit8, SYS_CTRL reset/clock controls, host stable/no-card status and MIX_CTRL storage. It accepts an observed firmware write of 0xF to reserved SYS_CTRL low bits as RAZ/WI. Real OSUP advances beyond this controller setup, with native CI all green. [USDHC1 study](2026-10-21-usdhc1-mmdc-lowpower.md).

## Current concrete roadblock — deliberate A7 DDR suspend entry

The next A7 Data Abort is **DFAR `0x40AB0404`**, a read of NXP **MMDC0.MAPSR**, the DDR power-saving control/status register. The private A7 firmware has copied a routine into internal RAM `0x2F02B000`; its disassembly explicitly requests `MAPSR.LPMD` bit20, polls `MAPSR.LPACK` bit24, then executes **`WFI` in a loop**. This is a *deliberate low-power/suspend path*, not proven OS startup.

**Do not force a fake MMDC LPACK and call it a boot.** It would merely send this code to WFI. Determine the real reason the firmware selects suspend, which PMC/SMC/LLWU/GIC wake event is missing, and whether the main OS should already have entered a different path. [Precise disassembly and NXP sources](2026-10-21-usdhc1-mmdc-lowpower.md).

Other observed facts: `MainTask` runs and semaphore31 cycles; the kernel optional idle callback is intentionally null; DMA1 `CR.ACTIVE` is **bit31** and reads at 0x601CBC34 do not alone demonstrate a hang. Both the original M4 IPC `0xEEEEEEEE` marker and lack of guest display remain unresolved.

**Authoritative references:** [manufacturer/upstream hardware reference catalog](HARDWARE_REFERENCES.md). 
