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
