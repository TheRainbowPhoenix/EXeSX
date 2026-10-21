# A7 USDHC1 controller startup and MMDC suspend trampoline — 2026-10-21

**Real local-firmware evidence only:** private Casio OSUP SHA256 `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`. The real firmware and private RAM/code dumps are NOT in Git. Native EXeSX/QEMU 10.1.0; A7 and M4 run with opt-in synthetic I²C 0x4B/0x40 mirrors, experimental MU IRQ, and **research-only** SNVS security-command pulse bypass. This does NOT represent real physical security state or a genuine OS boot.

## First newly reached A7 fault — USDHC1

With SNVS high-power RTC from merged [PR #13](https://github.com/TheRainbowPhoenix/EXeSX/pull/13), M4 no longer BusFaults on `0x41070024`. A7 then took a precise Data Abort (`DFSR=0x8, DFAR=0x403800C0`) at ARM `0x60017118: ldr r2,[r0,#0x9c]`, where `r0=0x40380024`. NXP [MCIMX7U5_cm4_COMMON.h](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/MCIMX7U5/MCIMX7U5_cm4_COMMON.h) identifies 0x40380000 as **USDHC1**; the [official USDHC register definitions](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/periph/PERI_USDHC.h) identify +0xC0 as `VEND_SPEC` and its bit8 `FRC_SDCLK_ON`.

The actual A7 initialization code:
- At `0x60017118`, reads `USDHC1.VEND_SPEC`; tests `FRC_SDCLK_ON`, and clears that bit if set.
- At `0x60017134`, accesses `SYS_CTRL` (+0x2C), requests its `RSTA` reset bit24 and polls for `PRES_STATE.SDSTB` bit3 (+0x24).
- Another firmware helper at `0x600177D4` writes `0x0000000F` to USDHC1.SYS_CTRL. These low bits are reserved by the NXP header. The first strict model generated a new Data Abort; the corrected model treats reserved bits as **write-ignored/read-as-zero** rather than a bus transaction failure, logging a diagnostic warning.

The model in merged [PR #14](https://github.com/TheRainbowPhoenix/EXeSX/pull/14) handles the documented clock/reset controls, the no-card host clock-stable status, and MIX_CTRL register storage. It neither asserts `CINST` (card present) nor services a command/data transfer. The native CI [run 39566903001](https://github.com/TheRainbowPhoenix/EXeSX/actions/runs/39566903001) **passed**, including the synthetic real-ARM test of exact reserved low SYS_CTRL bits. The private firmware now advances past USDHC1 VEND_SPEC/SYS_CTRL without that abort.

## Next precise fault — MMDC0 MAPSR (DDR power saving)

Independent cold native runs, 2 and 5 seconds, from checksum-verified original OSUP with CI artifact source `b86d90cb4627e1d0eedea6b8872cc0da3b9b44c8` showed:
- A7 **Data Abort at DFAR `0x40AB0404`**, `DFSR=0x8`; M4 had no observed BusFault.
- No verified A7 OS entry at `0x60400000` or known trampoline `0x605E3AD0`; no guest LCD pixels or text.
- The A7 has copied a power-management routine into internal RAM near `0x2F02B000` before trying to enter DDR low power.

NXP [MCIMX7U5_cm4_COMMON.h](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/MCIMX7U5/MCIMX7U5_cm4_COMMON.h) names **MMDC0** at `0x40AB0000`. NXP [PERI_MMDC.h](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/periph/PERI_MMDC.h) defines offset **`+0x404` `MAPSR`**, the DDR core power-saving control/status register: `PSD` bit0 (power-saving disabled), `LPMD` bit20 (low-power mode request), `LPACK` bit24 (low-power acknowledgment), plus power saving timer and other status fields.

**Real copied A7 ARM code, verified in guest internal RAM:**

```armasm
0x2F02B118  ldr r0, [pc, #0x158]       ; internal RAM literal pool
0x2F02B120  ldr r1, [pc, #0x154]       ; r1 = 0x40AB0404
0x2F02B124  ldr r2, [r1]               ; FIRST A7 Data Abort: MMDC0.MAPSR
...
0x2F02B1B0  ldr r3, [r1]
0x2F02B1B4  orr r3, r3, #1             ; MAPSR.PSD
0x2F02B1B8  str r3, [r1]
0x2F02B1BC  ldr r3, [r1]
0x2F02B1C0  orr r3, r3, #0x00100000    ; MAPSR.LPMD request
0x2F02B1C4  str r3, [r1]
0x2F02B1C8  ldr r3, [r1]
0x2F02B1CC  tst r3, #0x01000000       ; MAPSR.LPACK
0x2F02B1D0  beq 0x2F02B1C8          ; poll until DDR low-power acknowledged
...
0x2F02B264  dsb sy
0x2F02B268  wfi                     ; A7 waits for interrupt
0x2F02B26C  isb sy
0x2F02B270  b 0x2F02B264
```

A7 firmware at `0x601CD2D4` branches to the copied RAM trampoline (`0x2F02B0B8`) after preparing low-power hardware (including LPIT). This is **explicit suspend/low-power control flow**, *not* an OS-entry trampoline.

**Verified caller and classification:** The A7 BIOS reaches `0x601CD5E8: b 0x601CD2D4` after shutdown/power-management cleanup, including LPIT register writes. At `0x601CD2D4: ldr pc,[pc,#-4]`, the literal `0x2F02B0B8` jumps into the copied internal-RAM suspend routine. These are *intentional control-flow instructions*, not an IRQ return/address-corruption artifact. SHA-guarded Ghidra instruction-site names are `A7_PM_EnterSRAMSuspendAfterShutdown` and `A7_PM_JumpToSRAMSuspendTrampoline` in [the A7 kernel symbol table](../reverse/a7_kernel_named_sites.tsv). The precise upstream call chain/condition which selects this shutdown path remains unverified.

**Important: do not add an unconditional MMDC LPACK=1 as a supposed boot fix.** That would only advance this A7 path into an actual `WFI` sleep loop without establishing what wakeup interrupt or initialization state the system expects. Correct next experiment is trace the caller that elects suspend, inspect the clock/PM state and wakeup source (`PMC/SMC/LLWU/GIC`), and determine whether that path is normal idle or a missing wakeup trigger. A later proper MMDC emulation should model self-refresh request/ack only in a justified state, with a separate explicitly diagnostic override if necessary.

## Source hierarchy

- NXP [PERI_USDHC.h](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/periph/PERI_USDHC.h) and [PERI_MMDC.h](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/periph/PERI_MMDC.h) are authoritative register layouts, not proof of Casio board wiring.
- NXP [i.MX7ULP reference/security documentation](https://www.nxp.com/products/i.MX7ULP) for actual low-power/DDR lifecycle; silicon-mask revision still unknown.
- [Hardware reference catalog](HARDWARE_REFERENCES.md), [SNVS HP RTC follow-up](2026-10-21-snvs-rtc-m4-followup.md), [A7 peripherals study](2026-10-21-a7-usdhc-dma-bringup.md).

No account password or proprietary artifacts were needed or used for this analysis.
