# Real Casio ROM vs native QEMU eMMC: host-clock mismatch — 2026-10-21

**Scope:** Original checksum-validated private DY357 OSUP, SHA256 `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`, not uploaded. Tested the compiled native artifact from GitHub Actions [run 39628878597](https://github.com/TheRainbowPhoenix/EXeSX/actions/runs/39628878597), head `922c380ca528c2975f850cc3a91c16e99a1b1468` (QEMU 10.1.0). Original A7 and M4 firmware bytes unchanged. GPIOB7 high, 0x4B/0x40 I²C mirrors, MU IRQ and ignored SNVS security-violation pulses are explicitly diagnostic, not physical-board facts.

## Opt-in real eMMC capability actually verified

PR #20 embeds the **real upstream** `TYPE_IMX_USDHC` i.MX controller and `TYPE_EMMC` card on USDHC1 `0x40380000`, with GIC SPI 43, behind `EXESX_USDHC1_EMMC=1` and a named backing drive `exesx-emmc`. It *does not* replace the default no-media profile. Its native CI guest ARM test generated a **sparse, synthetic** Samsung KLMAG1JETD-B041-size backing image: 4 MiB boot0 + 4 MiB boot1 + 15,634,268,160 bytes user area (total 15,642,656,768 bytes, including reserved boot areas). It confirmed MMC CMD0/1/2/3/9/7, CMD17 actually reading an injected user-sector marker, and CMD8/EXT_CSD exposing **30,535,680 user sectors**. The same CI also passed the original no-media timeout and existing ARM smoke tests. These are **synthetic guest tests, not original Casio firmware progress**. Upstream card's CID/revision differs from a hardware Samsung chip; RPMB and physical Casio storage data are absent.

## Controlled original-ROM comparison on exactly this build

The artifact was downloaded separately and its tarball verified against packaged `SHA256SUMS`. The original OSUP was re-extracted with `prepare_osup.py`; source SHA256 and BIOS/OS load bases checked. Both conditions used the same native QEMU, profile, original firmware, and explicitly diagnostic I²C/SNVS/GPIO flags.

| Condition | Bounded original-firmware result |
| --- | --- |
| **Default:** `EXESX_USDHC1_EMMC` absent (stub/no-card) | Existing USDHC1 no-media controller progresses through **CMD0, 65 CMD1 polls and CMD7** in ~2.4 s, as independently established. Extended instruction logs still had **zero addresses in the 0x60400000 OS section**, and also surfaced unrelated later A7 MMIO Data Aborts at `0x40210020` and `0x4008001B`. |
| **Real device:** `EXESX_USDHC1_EMMC=1`, sparse reference-size eMMC image provided | The test guest had already passed genuine eMMC commands and data reads in CI. However, the **original Casio ROM** did **not** reach MMC CMD0 within 4.5 s. Its last newly translated A7 instructions were `0x60017140`/`0x60017144`, which wait on `USDHC1.PRES_STATE.SDSTB` bit 3. No original-OS instruction PCs were recorded and no new A7 MMIO Data Abort was reported during this bounded run. |

Physical `xp` MMIO reads in the original-firmware opt-in run, while it had reached the SDCLK initialization path:

```text
0x40380024  USDHC1.PRES_STATE = 0x01FF0000  (SDSTB bit3 CLEAR)
0x4038002C  USDHC1.SYS_CTRL  = 0x00000000
0x403800C0  USDHC1.VEND_SPEC = 0x00000000
```

**Exact original A7 clock/setup code from independent firmware disassembly:**

```armasm
0x60017134  ldr r2, [r0,#8]   ; r0 = 0x40380024, SYS_CTRL
0x60017138  orr r2, r2,#0x01000000  ; RSTA host reset bit24
0x6001713C  str r2,[r0,#8]
0x60017140  ldr r2,[r0]      ; PRES_STATE
0x60017144  tst r2,#8       ; SDSTB: host clock stable
              beq 0x60017140
```

The ROM requests reset, then immediately polls SD clock stable, and QEMU's upstream host leaves `SYS_CTRL=0`, `SDSTB=0` on that path. Unlike the synthetic ARM smoke test, this Casio path **does not first write `SYS_CTRL=0xF` to enable QEMU's conventional SDHCI clock bits**. This is the currently demonstrated *opt-in real-firmware blocker*, earlier than the MMC card identification/flash contents.

## Relevant independent QEMU fixes discovered

A contemporaneous upstream QEMU development series (v3, **4 October 2026**) covers closely analogous issues on i.MX uSDHC, albeit in the context of a different i.MX SoC and U-Boot. Apply/port only with source version and i.MX7ULP-specific behavior checked:

- [**QEMU v3 06/10: Honor i.MX uSDHC vendor clock gates**](https://mid.mail-archive.com/qemu-devel@nongnu.org/msg1231901.html) — explains that i.MX software may enable `VEND_SPEC.IPGEN/HCKEN/PEREN/CKEN` instead of conventional SDHCI clock registers. It fixes reporting `PRES_STATE.SDSTB` and translating vendor clock gates to the command engine. **Not itself evidence the Casio code wrote all four vendor gates; the observed Casio `VEND_SPEC` was zero.**
- [**QEMU v3 07/10: Preserve i.MX uSDHC interrupt-status enables across RSTA**](https://mid.mail-archive.com/qemu-devel@nongnu.org/msg1231900.html) — fixes a second reset/interrupt enable mismatch that can cause command polling timeouts. The author explicitly calls this a compatibility accommodation, not behavior mandated by hardware manual.
- [NXP i.MX7ULP USDHC peripheral register definitions](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/periph/PERI_USDHC.h), notably `SYS_CTRL.RSTA`, `PRES_STATE.SDSTB` and `VEND_SPEC`.
- [QEMU 10.1.0's actual USDHC implementation](https://github.com/qemu/qemu/blob/v10.1.0/hw/sd/sdhci.c) — `usdhc_read` derives SDSTB from `s->clkcon & SDHC_CLOCK_INT_STABLE`, and `usdhc_write` handles the i.MX vendor register.

**Next exact task:** inspect the Casio `RSTA`/clock-tree sequence and reconcile it with QEMU's i.MX7ULP USDHC reset clock semantics **before** changing default clock-ready behavior. A faithful initial fix must regress (a) the exact Casio `RSTA → poll SDSTB` ARM instruction sequence, (b) upstream normal clock and vendor clock paths, (c) no-media mode unmodified, then rerun this original OSUP and find the *next* genuine command/data/fault. **Do not force `SDSTB=1` globally** without a documented gate/reset transition or prove the card has real Casio data.

The synthetic 16 GB backing is deliberately **not a Casio eMMC dump**. Boot still unverified, no LCD/text. All source firmware, private images/logs, photos, device identifiers and account credentials remain outside the repository.
