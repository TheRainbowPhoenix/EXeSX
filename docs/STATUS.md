# EXeSX measured bring-up status — 2026-10-21

**No genuine Casio OS entry, LCD pixels or text have been verified.** All real firmware experiments used the original locally SHA-verified proprietary OSUP. No firmware, private traces, snapshots or user credentials are in GitHub.

## Confirmed functional advances

- Cortex-A7 BIOS executes and releases M4 firmware. The i.MX7ULP MU v1 channel-bit ordering was corrected against Linux's actual imx7ulp mailbox driver: experimental M4 IRQ22 storm fell from 78,665 to 2 entries, and rejected TR2 sends from 5 to 0 in bounded runs. Off-chip I²C 0x4B and 0x40 chips remain unidentified; their optional register mirrors are **diagnostic inventions**.
- SNVS high-power `HPCOMR`/ `HPCR` now have a manufacturer-defined command subset. The real security lifecycle is **NOT modeled**; writes requesting software security-violation pulses are rejected unless `EXESX_SNVS_DIAGNOSTIC_SECURITY_PULSES=1` is explicitly set for a private research-only run.
- A bounded, snapshot-safe **32.768-kHz relative SNVS HP RTC** is now available at `HPRTCMR` `0x41070024`/`HPRTCLR` `0x41070028`, gated by `RTC_EN`. This removed the observed M4 BusFault at 0x41070024 in a subsequent real OSUP run. No host calendar/secure clock is emulated. [RTC investigation](2026-10-21-snvs-rtc-m4-followup.md).
- The earlier A7 Data Abort was at USDHC0 `0x40370024`, **not a corrupt IRQ return to 0x20002028**. Clock-ready-only USDHC0, DMA1 TCD/register storage, DMAMUX1 packed 8/16/32-bit register access, and LPSPI2 CR startup controls passed native ARM tests. No SD card, DMA transfer or SPI message is simulated. [A7 MMIO ladder](2026-10-21-a7-usdhc-dma-bringup.md).
- A second A7 Data Abort, `0x403800C0`, was identified as **USDHC1.VEND_SPEC**. Merged [PR #14](https://github.com/TheRainbowPhoenix/EXeSX/pull/14) models only vendor SDCLK-on bit8, SYS_CTRL reset/clock controls, host stable/no-card status and MIX_CTRL storage. It accepts an observed firmware write of 0xF to reserved SYS_CTRL low bits as RAZ/WI. Real OSUP advances beyond this controller setup, with native CI all green. [USDHC1 study](2026-10-21-usdhc1-mmdc-lowpower.md).

## Current root cause — missing M4 GPIOB7 input suppresses A7 startup

**The MMDC suspend is a *consequence*, not the first missing condition.** Native execution with private original OSUP and a dual-core watchpoint confirms that M4 firmware `0x1FFD7782` reads real hardware **GPIOB.PDIR pin 7 at `0x4100F050`** and writes **`0xFFFFFFFF`** (high input) or **0** (low input) to A7 shared startup permission at `0x2F029284`. Current GPIO model only loops back outputs, and original M4 found `GPIOB.PDIR=0, PDDR=0x00068C04` (pin7 input), therefore it repeatedly writes **zero**.

A7 MainTask checks the shared permission using `0x60010C80 → 0x6001D47C`; the real `r0=0` triggers shutdown at **`0x6004A1B4`**, through `0x600117A0 → 0x601E7144 → 0x601CD48C` and finally SRAM DDR `MAPSR.LPMD`/WFI. Thus **MMDC.MAPSR DFAR `0x40AB0404`** was reached because firmware intentionally shut down. [Instruction-level investigation and references](2026-10-21-gpiob7-boot-permission.md).

The **opt-in** `EXESX_GPIOB_INPUT_MASK=0x80` supplies a controlled GPIOB pin7 voltage for research while leaving all default inputs low and respecting output direction. The exact physical Casio board signal, polarity, and LLWU wake event are still unverified. A private diagnostic *A7 register-only* r0=1 test proved the second startup check returns 1 and A7 takes its normal startup branch `0x6004A1BC`, then a **different Data Abort**; no OS or LCD yet. A native build/true dual-core input differential is required before merging the GPIO patch.

**Next:** compare clean original-OSUP execution with GPIOB7 low/high using the new M4/A7 dual-core breakpoint probe. Diagnose the new A7 fault and investigate pin/LLWU wiring only from guest code or physical board evidence; **do not fake MMDC LPACK, security state, a card, or IRQ wakeup**.

Other observed facts: `MainTask` runs and semaphore31 cycles; the kernel optional idle callback is intentionally null; DMA1 `CR.ACTIVE` is **bit31** and reads at 0x601CBC34 do not alone demonstrate a hang. Both the original M4 IPC `0xEEEEEEEE` marker and lack of guest display remain unresolved.

**Authoritative references:** [manufacturer/upstream hardware reference catalog](HARDWARE_REFERENCES.md). 
