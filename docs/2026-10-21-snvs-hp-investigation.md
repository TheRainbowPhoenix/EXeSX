# SNVS high-power early-boot fault and bounded model — 2026-10-21

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

See the maintained [hardware reference catalog](HARDWARE_REFERENCES.md) and the [real-firmware MU bit-order correction](2026-10-20-imx7ulp-mu-v1-bit-order.md).
