# Online cross-references: EXeSX firmware is using i.MX7ULP peripherals

This report contrasts **public source identifications** with **observed real-BIOS execution**. Private OSUP.BIN / firmware ELF / memory snapshots are never published.

## Primary exact source matches

| Firmware address | Device / register | Strong public source |
| --- | --- | --- |
| 0x4102603c | PCC0 RGPIO2P0 peripheral clock control | [NXP SDK fsl_clock.h](https://github.com/zephyrproject-rtos/hal_nxp/blob/a8b437ef366ff9a6f9bee3377dc189c4d2623f5b/mcux/mcux-sdk-ng/devices/i.MX/i.MX7ULP/MCIMX7U5/drivers/fsl_clock.h) |
| 0x410260fc | PCC0 PCTLA clock control | same fsl_clock.h |
| 0x41026100 | PCC0 PCTLB clock control | same fsl_clock.h |
| 0x4100f004 | GPIO PTA Port Set Output (PSOR), offset 4 | [NXP PERI_GPIO.h](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/d0112c674564adbc10418148001d13b5541ed532/i.MX7ULP/periph/PERI_GPIO.h); [NXP i.MX7ULP DTS](https://github.com/nxp-imx/uboot-imx/blob/bb41975aeb4cbd153b49c9fd62da1d64cd65968d/arch/arm/dts/imx7ulp.dtsi) |
| 0x4100f014 | GPIO PTA Port Data Direction (PDDR), offset 0x14 | same GPIO SDK header |
| 0x4103d010 | PCTLA PCR4 pin-control register, offset 0x10 | NXP DTS (pinmux area 0x4103d000); NXP [IAR low-power assembly](https://github.com/nxp-mcuxpresso/mcuxsdk-examples/blob/3151bc057b8924db54c7395d39b213c05ab94dc3/_boards/evkmcimx7ulp/iar/lpm_asm.s) |
| 0x410a3c08 | TSTMRB timestamp timer low register | [NXP MCIMX7U5_cm4_COMMON.h](https://github.com/zephyrproject-rtos/hal_nxp/blob/a8b437ef366ff9a6f9bee3377dc189c4d2623f5b/mcux/mcux-sdk-ng/devices/i.MX/i.MX7ULP/MCIMX7U5/MCIMX7U5_cm4_COMMON.h); [PERI_TSTMR.h](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/d0112c674564adbc10418148001d13b5541ed532/i.MX7ULP/periph/PERI_TSTMR.h) |
| 0x403f0040 | PCC2 FlexBus clock gate | NXP fsl_clock.h (`kCLOCK_Flexbus`) |
| 0x403f003c | PCC2 RGPIO2P1 clock gate | NXP fsl_clock.h (`kCLOCK_Rgpio2p1`) |
| 0x40b300a8 | PCC3 LCDIF clock register (anticipated; **not yet reached**) | NXP fsl_clock.h (`kCLOCK_Lcdif`) |

The public [i.MX7ULP U-Boot board configuration](https://git.ti.com/cgit/ti-u-boot/ti-u-boot/tree/include/configs/mx7ulp_com.h?id=6e2af641e4bfed24d3edd8519dd40ec397361b4e) sets external DRAM `PHYS_SDRAM=0x60000000`, consistent with our BIOS/OS mapping. The real firmware has zero-initialization regions at `0x61080000` and `0x67100000` that are probably DRAM subregions, but their precise memory attributes and actual chip/package remain unverified.

## Very relevant IAR code match

NXP's public **IAR Embedded Workbench assembly** `_boards/evkmcimx7ulp/iar/lpm_asm.s` executes the following during `LPM_Resume`: writes `0x40000000` to PCC0 + `0x3c` (RGPIO2P0), + `0xfc` (PCTLA) and + `0x100` (PCTLB), programs IOMUXC0 at `0x4103d000`, and restores GPIO PTA at `0x4100f000` using `PDOR` / `PDDR`. This independently validates the address/device identifications and provides a much more useful peripheral trace context than generic decimal code searches.

It does **not** imply the Casio firmware copied NXP's example, or that NXP's low-power flow is identical to the Casio BIOS.

## Why the supplied STM32 linker-script hit is not device evidence

The [BattBox_DM430 STM32F777BIT7wp.ld](https://github.com/i2t-repo/BattBox_DM430/blob/d76fda537a2fc64b3a3c4d291bc04e7056a2c60a/STM32F777BIT7wp.ld) does indeed use `EXT_SDRAM2 ORIGIN=0x61080000`, but sets `LENGTH=0x00000000` and also describes `0x60000000` as a separate SDRAM buffer. The embedded target is STM32F405-family according to the script itself. These addresses are broadly used for external memory across ARM SoCs. They are **not** proof of a shared chip or board; the NXP PCC/PCTL/GPIO exact matches are decisive by comparison.

Exact GitHub code searches for `0x67100000` produced no useful i.MX7ULP device-register match. That is unsurprising for a guest DDR layout rather than a fixed peripheral.

## Real hardware-constrained emulation now in EXeSX

`hw/arm/exesx-imx7ulp.inc` implements a small modular set of memory-mapped models, enabled by `profiles/imx7ulp-early-boot.ini`:

- PCC0/PCC1/PCC2/PCC3: only register offsets enumerated by the NXP SDK; CGC bit30 writable, INUSE bit29 and PR bit31 read-only. This does **not** create actual gated peripheral clocks or assert interrupts.
- GPIO PTA: PDOR, PSOR (write-one-to-set), PCOR (write-one-to-clear), PTOR (write-one-to-toggle), PDIR (output-pin loopback without external wiring), PDDR.
- PCTLA: the first 32 PCR[n] words, preserving written values. Pin electrical state and interrupts are not modeled.
- TSTMRB: 64-bit monotonic 1 MHz timestamp from QEMU virtual clock; this allows actual firmware busy-wait delays to complete. It is **not** a verified crystal oscillator model.

All mutable register banks are serialized in EXeSX VMState, preserving snapshot-fuzzer rollback. Peripheral implementations are a distinct included source file: changes recompile the EXeSX machine object only; changing which known models are enabled via profile is immediate without recompilation.

## Measured staged BIOS execution

With first experimental memory backing and no devices, the first Data Abort after initialization was `0x4102603c`. After confirming PCC0 clock registers, the fault progressed through `0x4100f004` (PSOR), `0x4103d010` (PCR4), `0x4100f014` (PDDR) and `0x410a3c08` (TSTMRB). A constant-zero fake timestamp trapped the guest in an unproductive busy loop; the actual 1-MHz virtual timer model let execution advance. Once TSTMRB was modeled, the next fault occurred on **PCC2 FlexBus** `0x403f0040`. After mapping that register, the next fault was **PCC2 RGPIO2P1** `0x403f003c`. Both offsets are SDK-confirmed.

A synthetic ARM guest, independent of proprietary firmware, has **passed** checking PCC0/PCC2 CGC readback (including read-only PR bit), GPIO set/clear/direction, PCTLA PCR4 and live TSTMRB low/high counter reads.

**Next milestones:** identify further faults with the expanded SDK-whitelisted PCC gates, then implement actual FlexBus transactions, DDR/MMDC and I/O when exercised. A genuine OS/eForce μITRON scheduler, M4 communication and LCD framebuffer are still not running.
