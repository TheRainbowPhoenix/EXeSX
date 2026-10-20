# i.MX7ULP MU v1 channel-bit reversal — verified hardware-driver cross-reference

**Date:** 2026-10-20. **Scope:** real i.MX7ULP register semantics and a testable emulator correction. OSUP, private firmware, snapshots and raw logs stay out of Git.

## Authoritative source: Linux i.MX7ULP mailbox driver

The Linux kernel's own `drivers/mailbox/imx-mailbox.c` selects an explicit `imx_mu_cfg_imx7ulp` profile: TX registers `+0x20`, RR `+0x40`, SR `+0x60`, CR `+0x64`. It uses **MU v1** (not the unrelated v2 register order).

The same file defines these **v1** macros, with the `3 - channel` mapping:

```c
#define IMX_MU_xSR_GIPn(type, x) (type & IMX_MU_V2 ? BIT(x) : BIT(28 + (3 - (x))))
#define IMX_MU_xSR_RFn(type, x)  (type & IMX_MU_V2 ? BIT(x) : BIT(24 + (3 - (x))))
#define IMX_MU_xSR_TEn(type, x)  (type & IMX_MU_V2 ? BIT(x) : BIT(20 + (3 - (x))))
#define IMX_MU_xCR_GIEn(type, x) (type & IMX_MU_V2 ? BIT(x) : BIT(28 + (3 - (x))))
#define IMX_MU_xCR_RIEn(type, x) (type & IMX_MU_V2 ? BIT(x) : BIT(24 + (3 - (x))))
#define IMX_MU_xCR_GIRn(type, x) (type & IMX_MU_V2 ? BIT(x) : BIT(16 + (3 - (x))))
```

- Linux driver source: https://github.com/torvalds/linux/blob/master/drivers/mailbox/imx-mailbox.c
- NXP MU SDK: https://mcuxpresso.nxp.com/api_doc/dev/1095/group__mu.html
- Upstream Linux i.MX7ULP MU v1 binding: https://kernel.googlesource.com/pub/scm/linux/kernel/git/kishon/linux-phy/+/f74fd13f4585e418a3e630a82468be58bf1d98c1/Documentation/devicetree/bindings/mailbox/fsl,mu.txt

**The EXeSX model was wrong.** It stored channel `n` as nibble bit `1<<n` for transmit-empty and receive-full status, whereas the i.MX7ULP requires `1<<(3-n)`. The RX registers themselves still use offset `+0x40+4*n` and the TX registers `+0x20+4*n`; only the flag order changes. This caused earlier diagnostics to mislabel the target channels; it also made the actual firmware ISR miss the flags for its intended channel.

| MU channel | Correct status-nibble mask | RX full SR bit | RX interrupt enable CR bit |
| --- | --- | --- | --- |
| 0 | `0x8` | `0x08000000` | `0x08000000` |
| 1 | `0x4` | `0x04000000` | `0x04000000` |
| 2 | `0x2` | `0x02000000` | `0x02000000` |
| 3 | `0x1` | `0x01000000` | `0x01000000` |

The private original firmware is SHA256-validated to this user's DY357 OSUP: `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`. Its registered M4 MU ISR at `0x1FFD5712` handles masks **8,4,2** in its normal loop. The *correct* interpretation is that it handles MU channels **0,1,2** and omits channel **3** (potentially a special path). Our old text that says it skips channel 0 is factually wrong. The ISR's `CR |= 0x01000000` enables receive interrupt for **channel 3**, not channel 0.

The older captured status `SR=0x04F00000 CR=0xFF000000` was a status *manufactured by the incorrectly indexed emulator*, not a valid hardware-derived ch2 RF2. Under the real MU v1 field definition it is **channel 1**. The later `SR=0x05F00000 CR=0xFB000000` represents **channels 1 and 3 full**, with only channel 3 still interrupt-enabled. Our claim that it was a genuine hardware channel-0 storm is **retracted**.

## Code correction and regression

`hw/arm/exesx-imx7ulp-mu.inc` now maps status-bit masks through `exesx_mu_v1_mask(chan)` for TX nonempty/empty and RR-full lifecycle. It retains distinct VMState-backed TE/RF/GIP nibbles and the existing peer handoff; it does **not** auto-acknowledge, drain any MU receive channel, or install missing handlers. GIP/GIR are represented directly by their physical register bits and do not need remapping.

`scripts/probe_imx7ulp.py` now expects **`0x08f00000`** for MU TR0→peer RR0 full, instead of the buggy model's `0x01f00000`. `scripts/probe_mu_v1_channels.py` sends and receives through **all four** MU channels and tests GIR/GIP/W1C bit positions with actual ARM guest instructions, not a Python-only simulated bus. `scripts/probe_mu_irq.py` now exposes both raw nibble masks and decoded physical channel numbers. Tests deliberately check the historical raw capture as evidence of the old emulator bug.

The **manufacturer-supported low-level protocol** is: transmitter waits for TE, writes TRn; receiver tests RF, reads RRn to release RF and set peer TE; enabled RF causes the receiver IRQ; GIP doorbell flags are W1C. The higher-level meaning of Casio command words 0..6, startup completion, semaphores and OS boot sequencing is **proprietary firmware behavior**, not specified by the MU block manual.

## Measured corrected native build: real firmware unlock

Compiled source from GitHub Actions run [39505114951](https://github.com/TheRainbowPhoenix/EXeSX/actions/runs/39505114951), **CI success**. Downloaded native artifact `exesx-qemu-native-c40d531c75084b880f4343e867f906b9a2f422e6`, verified the extracted tarball SHA256 **`a96f0ab4ba673a8b1b47ce0baf1374f8b13e921f9175a291fde90ca0d04d0edc`** against the included `SHA256SUMS`. Native build source stamp `c40d531c75084b880f4343e867f906b9a2f422e6` is GitHub's PR merge/test ref. The original baseline QEMU source stamp was `aa5f55b0d4513d2f2847903a9aae16c5d4993f7e`. Same real SHA-validated original OSUP, extracted locally via `prepare_osup.py`.

**Cold boot comparison** (separate QEMU processes, ~1.1 seconds wall-clock per sample), both artificial I²C register mirrors at `0x4B` and `0x40` enabled, and actual A7/M4 ROM execution:

| Native model | Experimental MU IRQ | M4 IRQ22 entries logged | Rejected TR2 writes | A7 sampled PC | Shared IPC `0x2F028000` |
| --- | --- | ---: | ---: | --- | --- |
| Before corrected mapping | 0 | 0 | 5 | `0x60179A7C` | `0xEEEEEEEE` |
| Before corrected mapping | 1 | **78,665** | **5** | `0x60179A7C` | `0xEEEEEEEE` |
| **Corrected NXP MU v1 mapping** | 0 | 0 | **0** | `0x60179A7C` | `0xEEEEEEEE` |
| **Corrected NXP MU v1 mapping** | 1 | **2** | **0** | `0x60179A7C` | `0xEEEEEEEE` |

The count is a bounded log measurement, not a cycle-exact comparison; the reduction is nevertheless several orders of magnitude. A MU receiver message initially posted on TR2 is now consumed, permitting a second TR2 word `0x00000001`; the old model logged five ignored attempts for `1..5`. M4 actual SR/CR snapshot probe `scripts/probe_mu_irq.py --entries 2` on the corrected QEMU printed first entry **MUA SR `0x02F00000`, CR `0xFF000000`, RF channel [2]**, then second entry **MUA SR `0x00F00000`, CR `0xFF000000`, no currently asserted MU receive or GIP flags**. Thus the remaining second latched NVIC entry is not an ongoing level IRQ storm. Snapshot rollback of M4 PC and both MU states passed. The ARM regression `scripts/probe_mu_v1_channels.py` reports PASS for all four channels and GIP clear.

**The genuine boot is NOT solved.** The A7 remains in kernel idle and the diagnostic M4→A7 IPC word remains `0xEEEEEEEE`. With experimental MU IRQ delivery enabled, the newly unblocked M4 advances through an early DMA0 write `0x41008000=0x90` and then hits a **new and precise** Cortex-M4 fault at `0x41070004`. Native QEMU reports **CFSR `0x00008200` (PRECISERR/BFARVALID), HFSR `0x40000000`, BFAR `0x41070004`**; a private GDB breakpoint on the actual M4 HardFault entry `0x1FFE14E2` confirmed the registers. Thumb disassembly localizes the exact bus read to **`0x1FFD4C7E: ldr r0,[r1]`**, with `r1=0x41070004`, inside a function starting at `0x1FFD4C64`.

NXP's own `MCIMX7U5_cm4_COMMON.h` maps **`SNVS_BASE=0x41070000`**. Official `PERI_SNVS.h` names offset `+0x4` **`SNVS_HPCOMR`** (High-Power Command Register), and `+0x8` **`SNVS_HPCR`**. The faulting code first reads HPCOMR, sets bit `0x10` (**LP_SWR**, low-power-section software reset request), reads until self-cleared, then writes HPCR=1 and sets `0x500` in HPCOMR. It will require a careful bounded SNVS model, not an arbitrary successful read or security-state forgery. Official source:

- https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/MCIMX7U5/MCIMX7U5_cm4_COMMON.h
- https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/periph/PERI_SNVS.h

### Interpreting the next M4 SNVS routine safely

The SHA-matched M4 function `0x1FFD4C64` is now called `M4_SNVS_HPCOMR_CommandSequence` in the private ELF/Ghidra symbol map. Its observed instructions:

```text
0x1FFD4C7E  ldr  r0, [r1]        ; r1 = SNVS_BASE+0x04, read HPCOMR; faults now
0x1FFD4C80  orr  r0, r0, #0x10   ; NXP HPCOMR.LP_SWR low-power reset command
0x1FFD4C84  str  r0, [r1]
0x1FFD4C86  ldr  r0, [r1]        ; polls LP_SWR deassertion
0x1FFD4C8C  movs r0, #1
0x1FFD4C8E  str  r0, [r1, #4]    ; SNVS.HPCR RTC_EN
0x1FFD4C90  ldr  r0, [r1]
0x1FFD4C92  orr  r0, r0, #0x500  ; SW_SV and SW_LPSV command bits
0x1FFD4C96  str  r0, [r1]
```

NXP `PERI_SNVS.h` identifies `LP_SWR (bit4)` as a reset request, `SW_SV (bit8)` as a software security violation, and `SW_LPSV (bit10)` as an LP software security violation. `SNVS_HP_SetSoftwareSecurityViolation()` is documented in the NXP SDK. Therefore a naive SNVS RW register mirror or an always-zero security-status result **would be speculative and could conceal a real boot-security dependency**. We have not determined which silicon lifecycle mode Casio expects. NXP additionally documents SNVS state-machine compatibility concerns on certain i.MX7ULP revisions, but **no specific revision or erratum has been linked to this ROM**.

A future isolated opt-in SNVS test must prove, in guest ARM instructions, the command/self-clearing behavior, status/lock protections, and precise fault behavior for unsupported offsets. It must not force a trusted security state, fabricate an RTC or change real OSUP bytes. The current default M4 BusFault is useful evidence.

This **new peripheral blocker** only became visible after correcting the MU channel flags. Do not conflate the SNVS BusFault with the prior MU IRQ storm. Model only real observed SNVS offsets/command self-clear semantics with firmware-free ARM tests before adding anything to the default machine.

## Required before claiming an unlock

CI and the first real cold-run comparison are now complete (see above). For further study run another clean firmware comparison with `EXESX_EXPERIMENTAL_MU_IRQ=0/1`, both diagnostic I²C mirrors, tracking MU TR2 busy attempts, **correctly decoded RF/RIE channels**, IRQ22 rate and A7 progress/OS entry. A smaller number of interrupts is not proof of a boot. Do not force an IRQ clear, fake an RR read, or claim display text. The original private firmware and emulator file layout must match checksum checks.

