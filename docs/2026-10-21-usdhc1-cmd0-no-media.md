# First original-ROM USDHC1 SD command and the no-media boundary — 2026-10-21

## Original firmware and evidence

Original Casio DY357 updater is **local/private**; SHA256 `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`. A7 and M4 are executing real BIOS/M4 bytes; the existing I²C 0x4B/0x40 mirrors, ignored SNVS software-security pulses and GPIOB7 high (`EXESX_GPIOB_INPUT_MASK=0x80`) are opt-in diagnostic assumptions, **not claims about physical devices or security**. Firmware, dumps, account credentials and raw logs remain off GitHub.

The preceding measured A7 Data Abort was on NXP USDHC1 `CMD_ARG` **0x40380008** (`DFSR=0x1808`), instruction **`0x600178BC: str r8,[r7]`**, after [GPIO startup permission](2026-10-21-gpiob7-boot-permission.md), [watermark configuration](2026-10-21-usdhc1-watermarks-after-bootgate.md), and [W1C interrupt control](2026-10-21-usdhc1-irq-control.md). Live registers at the faulting store were `r7=0x40380008`, `r8=0`, `r4=0`, `r5=0`, `r6=0`.

### SHA-verified original A7 disassembly

```armasm
0x6001788C  push {r4,r5,r6,r7,r8,lr}    ; A7_USDHC1_SubmitCommand
0x60017890  mov r4,r0                    ; command index
0x60017894  mov r8,r1                    ; CMD_ARG
0x60017898  mov r5,r2                    ; option flags
0x6001789C  mov r6,r3                    ; transfer-type flags
0x600178A0  mov r7,#0x40000008
0x600178A4  orr r7,r7,#0x00380000       ; r7=0x40380008
0x600178A8  ldr r0,[r7,#0x28]          ; INT_STATUS +0x30
0x600178AC  str r0,[r7,#0x28]          ; W1C pending
0x600178B0  bl 0x600174BC              ; controller setup
0x600178B8  str r0,[r7,#0x2C]          ; INT_STATUS_EN (+0x34)
0x600178BC  str r8,[r7]                ; CMD_ARG +0x08, argument ZERO
...
0x600178D8  orr r0,r0,r4,lsl #24       ; command index at [29:24]
0x600178DC  orr r0,r6,r0               ; response/data flags
0x600178E0  str r0,[r7,#4]             ; CMD_XFR_TYP +0x0C
0x600178EC  ldr r0,[r7,#0x28]          ; INT_STATUS +0x30
0x600178F0  tst r0,#1                  ; CMD complete
```

For the captured initial call, the original inputs `r4=r5=r6=r8=0` yield **CMD0, argument 0, no response expected and no data**. Thus the next missing feature was not simply a register mirror: the firmware is actively entering SD/eMMC command submission. The exact physical medium type and contents remain unknown.

## First native real-OSUP run: intervening PROT_CTRL was missing

Native [run 39590649690](https://github.com/TheRainbowPhoenix/EXeSX/actions/runs/39590649690) passed the first 28-word real-ARM CMD0/CMD8 regression. Downloaded that exact native artifact, checked the SHA256 manifest, and ran the original local OSUP **without modifying any firmware bytes**, with existing explicitly diagnostic I²C/SNVS settings and GPIOB7 input high. A7 progressed beyond `CMD_ARG +0x08` but then took a *new precise Data Abort* **DFSR `0x1808`, DFAR `0x40380028`** at original ROM **`0x600178C8: str r0,[r7,#0x20]`**. This is **USDHC1 `PROT_CTRL`**, not a card response.

The immediately preceding original instructions compute `r0=0x00008820`: the NXP [PERI_USDHC.h](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/periph/PERI_USDHC.h) `PROT_CTRL.EMODE` bits5:4 encode **little-endian mode `0x20`**; the extra `0x8800` bits are reserved and should read as zero/write-ignore. A narrowly scoped naturally aligned 32-bit PROT_CTRL register now records only the official register mask `0x7F1F03FF`. It **does not force test-card detect**, DMA requests or a peripheral interrupt.

The real-ARM regression now writes `0x8820` and checks readback `0x20` *before* sending CMD0. This new original-firmware fix must pass native CI and another ROM differential before merging.

## Stronger media identification from callsites

Original SHA-verified ARM disassembly of **`0x60017988`** shows a complete initialization command sequence through `0x6001788C`: **CMD0 → CMD1 → CMD2 → CMD3 → CMD9 → CMD7**, followed by **CMD6** through a helper at `0x60017918`. `CMD1 SEND_OP_COND` is MMC/eMMC's OCR negotiation; after CMD1 the caller reads USDHC1 `CMDRSP0` (+0x10) and checks **bit31, device power-up-ready (OCR_BUSY)** at `0x60017A00`. A standard removable SD initialization generally uses CMD8/ACMD41 instead. Thus the A7 firmware **expects an MMC/eMMC-class protocol at USDHC1**, not an arbitrarily modeled SD card. We have not established a physically mounted eMMC, CID/CSD/EXT_CSD values, or contents of its storage.

Relevant reuse options: [QEMU's SDHCI host model](https://github.com/qemu/qemu/blob/master/hw/sd/sdhci.c), [QEMU's eMMC card type](https://qemu.googlesource.com/qemu/+/25fef09ce17ac1ae22638a0b57d97c2bd5cd7d83/include/hw/sd/sd.h) (TYPE_EMMC), [NXP USDHC register reference](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/periph/PERI_USDHC.h), [MCUXpresso USDHC API](https://mcuxpresso.nxp.com/api_doc/dev/1581/group__usdhc.html), and Linux's [i.MX eSDHC host driver](https://github.com/torvalds/linux/blob/master/drivers/mmc/host/sdhci-esdhc-imx.c). A generic SDHCI controller cannot be dropped into these MMIO windows without checking i.MX7ULP's register layout, DMA, IRQ, and card attachment semantics.

## Narrow USDHC1 host-side behavior

NXP's official [i.MX7ULP PERI_USDHC.h](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/periph/PERI_USDHC.h) defines `CMD_ARG +0x08`, `CMD_XFR_TYP +0x0C`, response type `[17:16]`, data present bit21, and command index `[29:24]`. The [MCUXpresso USDHC driver](https://mcuxpresso.nxp.com/api_doc/dev/1581/group__usdhc.html) distinguishes no-response commands from card-response commands, and `INT_STATUS.CC` (bit0) from completion of data/card transfers.

This change adds only:
- Snapshot-backed CMD_ARG and last CMD_XFR_TYP register storage.
- Diagnostic log of actual command index, argument, response type, explicitly indicating **no medium attached**.
- For **CMD0, argument 0, response type none and no data**, host-side command transmission can finish with `INT_STATUS.CC` (bit0) if status reporting is enabled. This signals the *controller completed a command requiring no card response*, **not that an SD card replied, was present, or accepted CMD0**.
- Other commands (e.g. CMD8 requiring a 48-bit response) are **not granted completion or a response**. No card-insert flag, transfer-complete, DMA, RSP0..3, storage bytes, or GIC IRQ is synthesized.

Native synthetic ARM regression writes CMD0/arg0, checks host CC, clears it W1C, then issues CMD8/arg0x1AA and verifies that neither a card reply nor command completion appears. This is a bounded diagnostic/no-media stage, **not a complete USDHC host controller or proof of an operating OS**.

## Next engineering step

Re-run untouched original A7/M4 code against the exact CI-native binary with GPIOB7 high, trace USDHC1 command index and argument (from `EXeSX USDHC1 CMD` logs) and the first subsequent A7 Data Abort or command timeout, without forcing a card-ready response. If a physical card is needed, implement/attach a **real SD/eMMC backend with a verifiable card image**, considering [QEMU SDHCI controller](https://gitlab.com/qemu-project/qemu/-/blob/master/hw/sd/sdhci.c), [Linux i.MX SDHCI driver](https://github.com/torvalds/linux/blob/master/drivers/mmc/host/sdhci-esdhc-imx.c), and NXP USDHC's non-generic register differences.

If the original ROM only performs a card *probe*, a trustworthy no-card timeout path may be sufficient to continue without a storage image. Which branch is taken must be established by real code, not guessed.

See the [maintained hardware-reference index](HARDWARE_REFERENCES.md). Never upload the proprietary ROM, guest memory, generated ELF, customer identifiers or credentials.
