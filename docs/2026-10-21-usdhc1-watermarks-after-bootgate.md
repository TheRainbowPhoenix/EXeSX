# USDHC1 FIFO watermark after real GPIOB7 startup permission — 2026-10-21

## Verified original Casio control flow

Native EXeSX/QEMU, checksum-verified original private Casio OSUP, opt-in synthetic I²C 0x4B/0x40 mirrors, diagnostic-only SNVS security-pulse ignore and **explicit GPIOB input pin7 high** (`EXESX_GPIOB_INPUT_MASK=0x80`). All real firmware and raw logs remain private. Exact source, commands and results are described in [GPIOB7 boot-permission root cause](2026-10-21-gpiob7-boot-permission.md).

After merged [PR #15](https://github.com/TheRainbowPhoenix/EXeSX/pull/15), M4 runs its own GPIOB.PDIR path `0x1FFD7798` with `r1=0xffffffff` and writes A7 shared boot permission `0x2F029284=0xffffffff`. **No A7 debugger register or firmware patch is used.** A7 MainTask checks real permission and branches to normal startup `0x6004A1BC`, skipping intentional DDR/MMDC low-power/shutdown. This conclusively shows that the first boot blocker was the absent modeled external GPIO input, **not MMDC MAPSR or a missing WFI wake interrupt**.

## Next precise A7 Data Abort after normal startup

The A7 later executes the following real original-ROM code:

```armasm
0x600179A0  mov r6,#0x40000010
0x600179A4  orr r6,r6,#0x00380000     ; USDHC1 base+0x10
0x600179A8  mov r0,#0x08200000
0x600179AC  orr r0,r0,#0x00000820     ; r0=0x08200820
0x600179B0  str r0,[r6,#0x34]         ; USDHC1 WTMK_LVL = 0x08200820
```

Private real A7 GDB breakpoint at `0x600179B0` confirmed `r0=0x08200820`. Without a model of this register, the A7 Data Abort vector is reached with **DFSR=0x1808 and DFAR=0x40380044**. Unlike the preceding MMDC error, this is reached from the *normal startup branch*, not from shutdown.

NXP [PERI_USDHC.h](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/periph/PERI_USDHC.h) defines `WTMK_LVL +0x44`, exactly four fields:

| Field | Bits | Original Casio value |
| --- | --- | --- |
| `RD_WML` | 7:0 | 32 |
| `RD_BRST_LEN` | 12:8 | 8 |
| `WR_WML` | 23:16 | 32 |
| `WR_BRST_LEN` | 28:24 | 8 |

All reserved bits read zero. In the limited emulator, these settings are stored in the existing VMState-backed USDHC1 register array. **No SD/eMMC card, FIFO data, DMA transfers, command replies, command-complete interrupt or fake status bit is introduced**.

This is verified by the native firmware-free real-ARM test `scripts/probe_a7_early_devices.py`, which now writes the exact original value and reads it back. A new private ROM differential after CI will determine the next *real* A7/MMIO blocker and whether original firmware reaches an SD command.

## Completed native CI and original-ROM differential

Native [GitHub Actions run 39576514641](https://github.com/TheRainbowPhoenix/EXeSX/actions/runs/39576514641) **SUCCESS**. The extracted native QEMU artifact SHA256 manifest verified; independently re-ran the real guest ARM WTMK configuration test, **PASS**.

The SAME original private OSUP and diagnostic I²C/SNVS options, with `EXESX_GPIOB_INPUT_MASK=0x80` and **no debugger register injection**, confirmed M4 gate `0xFFFFFFFF`, A7 `r0=1` at `0x6004A19C`, and A7 normal startup at `0x6004A1BC`. The old A7 fault at `0x40380044` is now gone. The next precise A7 Data Abort occurred at **DFSR `0x1008`, DFAR `0x40380030`**, NXP USDHC1 **`INT_STATUS`**, a W1C interrupt/error-status register. No OS entry or LCD activity was confirmed.

Next, model only documented, observed USDHC1 interrupt status clearing and enable control without fabricating `CC` command-complete, `TC` transfer-complete, `CINS` card-insertion, or any card reply. Trace the first actual guest SD command once access reaches `CMD_XFR_TYP`. Do not claim successful storage or a boot based solely on fewer Data Aborts.

## Hardware/firmware-reference chain

- [NXP i.MX7ULP official PERI_USDHC.h](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/periph/PERI_USDHC.h): authority for offset/bit masks and burst length restrictions
- [Upstream Linux i.MX7ULP USDHC0/1 device tree](https://github.com/torvalds/linux/blob/master/arch/arm/boot/dts/nxp/imx/imx7ulp.dtsi): USDHC1 base `0x40380000`, clock sources and IRQ43
- [M4 GPIOB7 physical-input root cause](2026-10-21-gpiob7-boot-permission.md): why A7 shutdown/MMDC had previously been selected
- [Hardware reference library](HARDWARE_REFERENCES.md)

Never interpret a watermark register readback alone as proof of card initialization or booting the proprietary Casio OS.
