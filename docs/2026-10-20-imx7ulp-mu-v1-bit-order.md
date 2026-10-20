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

## Required before claiming an unlock

Build/test the corrected QEMU in CI, then run a clean firmware comparison with `EXESX_EXPERIMENTAL_MU_IRQ=0/1`, both diagnostic I²C mirrors, tracking MU TR2 busy attempts, **correctly decoded RF/RIE channels**, IRQ22 rate and A7 progress/OS entry. A smaller number of interrupts is not proof of a boot. Do not force an IRQ clear, fake an RR read, or claim display text. The original private firmware and emulator file layout must match checksum checks.

