# Empty MMC/eMMC slot: truthful command timeout instead of silent spin

**Date:** 2026-10-21. **Media backing:** none. All proprietary Casio firmware, original-ROM dumps, console logs, guest RAM, snapshot states and user credentials remain off GitHub.

## Real first storage-protocol blocker

Previous merged [CMD0/PROT_CTRL PR #18](https://github.com/TheRainbowPhoenix/EXeSX/pull/18) passed native [CI 39591495132](https://github.com/TheRainbowPhoenix/EXeSX/actions/runs/39591495132), including actual ARM checks of `PROT_CTRL=0x8820` → `0x20`, `CMD_ARG`, `CMD_XFR_TYP`, host-only no-response CMD0 completion, W1C, and no fabricated CMD8 response.

A **private original-ROM A7/M4 cold run on that same corrected native QEMU** (SHA-validated DY357 OSUP) emitted exactly:

```text
EXeSX USDHC1 CMD0 ARG=0x00000000 XFR=0x00000000 response=0 no-media
EXeSX USDHC1 CMD1 ARG=0x40ff8000 XFR=0x01020000 response=2 no-media
```

At an independent monitor stop around 1.5s the *actual* A7 registers were `PC=0x600178FC`, `r4=1`, `r8=0x40FF8000`, `r7=0x40380008`: firmware was looping over USDHC1 `INT_STATUS`, with **`INT_STATUS=0`** (no completion/error). `CMD_ARG=0x40FF8000` and `CMD_XFR_TYP=0x01020000` were retained; importantly **there was no longer an A7 Data Abort**. This is an incomplete *no-card timeout*, rather than an undocumented MMIO register. No guest OS entered.

The original firmware's next logic at `0x600179FC` reads `CMDRSP0` (+0x10) and tests **OCR busy/ready bit31**, which requires an actual MMC/eMMC CMD1 response. With no installed card, the correct behavior is **command timeout and no fabricated OCR/ready bit**, not infinite waiting or success.

## Conservative model and test

[NXP PERI_USDHC.h](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/periph/PERI_USDHC.h) names `INT_STATUS.CTOE` (bit16) and `CMDRSP[0..3]` (host response registers +0x10..1c). The [MCUXpresso USDHC driver](https://mcuxpresso.nxp.com/api_doc/dev/1581/group__usdhc.html) distinguishes command-complete from command timeout and card response type. [Linux i.MX eSDHC](https://github.com/torvalds/linux/blob/master/drivers/mmc/host/sdhci-esdhc-imx.c) is another driver cross-check.

The no-media model now:
- Stores the command deadline as two 32-bit words plus an armed bit in **guest-invisible, VMState-backed existing regfile positions**.
- Uses `QEMU_CLOCK_VIRTUAL` for a **provisional 1ms elapsed-time timeout** on response-required commands against an empty slot, evaluated when firmware polls `INT_STATUS`. This is not an actual programmable USDHC SDCLK timeout calculation, and cannot wake an interrupt-only driver; it's a bounded, explicitly approximate polling subset.
- After the deadline, reports `INT_STATUS.CTOE` if the firmware enabled that status source. W1C of CTOE clears it.
- Provides `CMDRSP[0..3]` as zero (no card attached, thus no valid card response or ready bit).
- Retains CMD0 host-side no-response completion. No media data, card-insertion, valid OCR, DMA completion, IRQ, or false secure state is produced.

`scripts/probe_usdhc1_no_media.py` executes actual guest ARM: CMD1/arg `0x40FF8000`, immediate no-completion read, bounded guest instruction delay, timeout status `0x10000`, zero response, W1C clear, unchanged argument/transfer type, host clock-stable bit with card-present clear. Included in native GitHub CI.

**Important limitation:** The physical emulator currently has no eMMC/SD drive. **This is not a complete, timing-accurate USDHC or a successful eMMC boot.** An image-backed real eMMC device and host command/response/DMA implementation will be required if Casio depends on the storage contents. The separate [QEMU TYPE_EMMC card model](https://qemu.googlesource.com/qemu/+/25fef09ce17ac1ae22638a0b57d97c2bd5cd7d83/include/hw/sd/sd.h) and [QEMU SDHCI controller](https://github.com/qemu/qemu/blob/master/hw/sd/sdhci.c) are possible implementation foundations after checking their i.MX7ULP-specific register mapping and correct backing image.

## Required original-OSUP differential

Run the *same private ROM* with unchanged I²C and SNVS diagnostic flags and GPIOB7 input high, and verify: the old A7 `PC=0x600178FC` CMD1 poll terminates with CTOE rather than a bus abort or invented ready bit; capture the next A7 branch and whether the firmware retries, returns a no-media error, or reaches alternate boot code. If a new MMIO fault emerges, identify and log it precisely. **No UI or verified Casio OS entry is claimed.**

See the [master hardware reference library](HARDWARE_REFERENCES.md) and [CMD0/eMMC disassembly](2026-10-21-usdhc1-cmd0-no-media.md).
