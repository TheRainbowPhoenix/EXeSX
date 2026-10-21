# SNVS high-power early-boot fault and bounded model — 2026-10-21

> **Later corrected diagnosis:** The apparent A7 IRQ return PC `0x20002028` did not cause the subsequent Data Abort. The actual A7 DFAR was **USDHC0 `0x40370024`**; this has been modeled and tested alongside the next DMA1/DMAMUX1/LPSPI2 startup registers. See [verified A7 fault ladder](2026-10-21-a7-usdhc-dma-bringup.md). A still later *M4* fault accesses SNVS high-power RTC `HPRTCMR` at `0x41070024`; see [RTC investigation](2026-10-21-snvs-rtc-m4-followup.md).

**Status:** controlled emulation experiment. Genuine Casio XD-SX9850 firmware binary provided privately; its updater SHA256 is d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0. No ROM, ELF, snapshots or private execution logs are checked into GitHub.

## Silicon-verified register identity

NXP [MCIMX7U5_cm4_COMMON.h](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/MCIMX7U5/MCIMX7U5_cm4_COMMON.h) maps SNVS at 0x41070000. The [NXP SNVS definitions](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/periph/PERI_SNVS.h) define:

| MMIO | Register | Important fields |
| --- | --- | --- |
| 0x41070004 | SNVS.HPCOMR, high-power command | LP_SWR bit4, SW_SV bit8, SW_LPSV bit10, LP_SWR_DIS bit5 |
| 0x41070008 | SNVS.HPCR, high-power control | RTC_EN bit0 |
| 0x41070014 | SNVS.HPSR, high-power status | Security-state information **not implemented** |

NXP [SNVS HP driver code](https://docs.rtems.org/doxygen/main/fsl__snvs__hp_8h_source.html) issues a write-one pulse for ResetLP and a separate command for software security violation. LP_SWR is a *command*, not persistent storage. NXP's full [i.MX7ULP reference/security manuals](https://www.nxp.com/products/i.MX7ULP) may require login.

## Exact M4 caller

With the previous, now-corrected MU v1 model and explicit diagnostic I²C mirrors, the M4 reaches a **precise BusFault on a read from 0x41070004**. CFSR 0x00008200 and BFAR 0x41070004; instruction 0x1FFD4C7E in M4 function 0x1FFD4C64, named `M4_SNVS_HPCOMR_CommandSequence`.

```armasm
0x1FFD4C7E  ldr r0,[r1]           ; HPCOMR
0x1FFD4C80  orr r0,r0,#0x10      ; LP_SWR command
0x1FFD4C84  str r0,[r1]
0x1FFD4C86  ldr r0,[r1]           ; waits until bit 4 clears
0x1FFD4C8E  str r0,[r1,#4]        ; HPCR = 1 (RTC_EN)
0x1FFD4C90  ldr r0,[r1]
0x1FFD4C92  orr r0,r0,#0x500     ; software security violation command bits
0x1FFD4C96  str r0,[r1]
```

The same function has an earlier conditional branch that skips LP_SWR when its argument is zero. The observed fault is on the first HPCOMR read in a nonzero-argument invocation.

## Implementation scope and intentional limits

The new kind `imx7ulp-snvs` is registered at 0x41070000 with a 0xC00-byte MMIO window. **Only +0x04 and +0x08 are modeled; all other reads/writes fault.** Accesses must be naturally aligned 32-bit words.

- HPCOMR: stores only explicitly documented persistent control bits; LP_SWR is treated as a non-sticky reset command. Because **no SNVS LP state exists** in this model, the pulse is logged rather than claiming an LP-domain reset was simulated. The command reads back zero, allowing the M4 to leave its documented polling loop.
- HPCR: implements only documented bit0 RTC_EN storage/readback, **not an actual 64-bit RTC, monotonic counter or clock synchronization**.
- Software security-violation commands SW_SV and SW_LPSV are **rejected by default** as unsupported. If the user expressly sets `EXESX_SNVS_DIAGNOSTIC_SECURITY_PULSES=1`, their write pulses can be ignored to *explore subsequent code*; a conspicuous log warning states that no secure state or authenticated status exists. No trusted/secure state is fabricated.
- Writes of undocumented bits, accesses to unmapped offsets and non-word accesses return an MMIO error. The C handler uses the existing QEMU VMState-backed regfile, preserving any stored control values in snapshots.

The synthetic regression `scripts/probe_snvs_hp.py` runs ARM firmware inside actual native QEMU, checking LP_SWR command clear, HPCR RTC_EN, LP_SWR_DIS persistence, and opt-in diagnostic command pulse behavior. It never requires proprietary firmware and is integrated in native CI.

**Do not call this security-correct emulation** or claim that the Casio OS booted. Private real-ROM differential results, guest M4 PC/fault changes and any next peripheral blocker should be recorded separately after compiling this patch.

## Completed CI and real-firmware comparison

**Native GitHub Actions build/test:** [run 39517192643](https://github.com/TheRainbowPhoenix/EXeSX/actions/runs/39517192643) **SUCCESS**, including synthetic ARM guest tests for both strict and diagnostic SNVS command behavior and all earlier MU tests. For independent real-ROM validation, extracted the compiled QEMU binary from the compiler artifact of run 39516973986. That artifact is the same source code as the CI-success run, apart from the subsequent GitHub Actions command typo fix. The source firmware was re-extracted locally and SHA256-validated. All firmware, private machine logs, snapshots and binary artifacts stayed off GitHub.

Both independent QEMU cold processes used the same user OSUP, existing synthetic I2C register mirrors for 7-bit 0x4B/0x40, experimental MU IRQ delivery, and the new SNVS profile at 0x41070000.

| Observation | Strict SNVS (security pulses rejected) | Research-only security-pulse ignore |
| --- | --- | --- |
| M4 initial HPCOMR read | **Succeeds** | **Succeeds** |
| LP_SWR reset command | Issued, command clears | Issued, command clears |
| HPCOMR/HPCR readback at end | 0 / 1 | 0 / 1 |
| Write of 0x500 (SW_SV, SW_LPSV) | **Rejected: precise M4 BusFault** | **Diagnostic-only pulse ignored with warning** |
| M4 CFSR/HFSR/BFAR after 1s | 0x00008200 / 0x40000000 / 0x41070004 | **0 / 0 / 0** |
| Sample M4 PC after 1s | 0x1FFD4D1E, fault context | 0x1FFDA0A0, M4 kernel idle/WFI area |
| Sample A7 PC after 1s | 0x60179A7C, kernel idle | 0x601B82A8, A7 exception-handler context |
| Shared A7/M4 IPC | 0xEEEEEEEE | 0xEEEEEEEE |

At **3 seconds** in diagnostic mode, the M4 remains near 0x1FFDA0A0 without an observed M4 BusFault; the A7 is in **Abort mode** (CPSR 0x60000197), with sampled PC 0x601B40F4. The QEMU interrupt trace includes the line **"Exception return from AArch32 irq to sys PC 0x20002028"** immediately followed by **"Taking exception 4 [Data Abort] on CPU 0"**. That is a newly exposed **A7-side interrupt-return/translation problem**. It is **not proven** to be an SNVS issue; it may involve the interrupt context, memory mappings, or another incomplete guest peripheral. We have not measured a working OS entry at 0x60400000 or on-screen text. Do not call A7 Abort-mode execution successful boot progress.

**What is actually unlocked:** the original missing-peripheral SNVS HPCOMR BusFault is resolved, and normal M4 code reaches and requests the next documented command. The policy deliberately leaves real security state unimplemented, while a separate opt-in diagnostic run isolates the *next* CPU failure without patching the ROM.

### Next test

1. Find what guest A7 instruction or saved IRQ stack frame produces return PC 0x20002028; inspect IRQ stack, translation status (DFSR/DFAR), and whether the failing fetch/address is mapped. Use CPU-specific debug breakpoints rather than assuming the M4 idle loop implies success.
2. Obtain the **i.MX7ULP Security Reference Manual** (NXP login may be required) before modeling software violation effects or the SNVS state machine. Identify the Casio silicon mask revision first if errata are relevant.
3. Preserve the default strict SNVS and only use diagnostic security bypass in private experiments; do not fake secure status or accept unsupported register offsets.
4. Prove OS entry and actual LCD framebuffer updates independently.

See the maintained [hardware reference catalog](HARDWARE_REFERENCES.md) and the [real-firmware MU bit-order correction](2026-10-20-imx7ulp-mu-v1-bit-order.md).
