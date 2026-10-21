# EXeSX hardware and kernel reference library

Source catalog for the QEMU 10.1.0 Casio XD-SX9850/DY357 Cortex-A7 + Cortex-M4 research emulator. Sources below are independent of the proprietary firmware, and **do not prove Casio's external I2C chip identities**. Do not commit OSUP, extracted ELFs, snapshots or private debugger traces.

## Highest priority: i.MX7ULP-specific manufacturer material

| Document | Why we need it | Caveat |
| --- | --- | --- |
| [NXP i.MX7ULP official documentation index](https://www.nxp.com/products/i.MX7ULP) | **Reference Manual IMX7ULPRM, B2 revision IMX7ULPRMB2, Security Reference Manual IMX7ULPSRM, data sheets and silicon mask errata** | Full RM/SRM downloads can require an NXP account; Casio board silicon revision unknown. |
| [NXP MCIMX7U5_cm4_COMMON.h](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/MCIMX7U5/MCIMX7U5_cm4_COMMON.h) | Verified peripheral addresses and M4 IRQs, including SNVS at 0x41070000 | Header documents placement, not state-machine semantics. |
| [NXP PERI_SNVS.h](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/periph/PERI_SNVS.h) | **Essential SNVS register layout:** HPCOMR at +0x04; HPCR at +0x08; LP_SWR bit4; SW_SV bit8; SW_LPSV bit10; HPCR RTC_EN bit0 | Command bits are security-sensitive; do not treat them as ordinary writable RAM. |
| [NXP SNVS HP SDK driver, published through RTEMS](https://docs.rtems.org/doxygen/main/fsl__snvs__hp_8h_source.html) | Concrete driver conventions for ResetLP, RTC StartTimer and SetSoftwareSecurityViolation | Cross-check target SoC, since RTEMS may reference other NXP devices. |
| [NXP silicon mask errata and revision documents](https://www.nxp.com/products/i.MX7ULP) | Lists 1N54W and 2N54W errata and B1/B2 comparison | Don't apply revision-specific workaround without identifying Casio's revision. |

## Crucial A7/M4 communication and boot sources

| Document | Porting relevance |
| --- | --- |
| [Linux i.MX mailbox driver](https://github.com/torvalds/linux/blob/master/drivers/mailbox/imx-mailbox.c) | **Critical proved MU fix:** channel 0 uses top bit of TE/RF/GIP nibble in MU v1, not lowest bit; peer RR reads release transmit slots. |
| [NXP MCUXpresso MU API](https://mcuxpresso.nxp.com/api_doc/dev/1095/group__mu.html) | MUA/MUB send, receive, status flags, interrupts and GP doorbells. |
| [NXP RPMsg-Lite Linux/M4 example](https://mcuxpresso.nxp.com/mcuxsdk/latest/html/examples/multicore_examples/rpmsg_lite_pingpong_rtos_linux/remote/readme.html) | Useful dual-core startup and shared-memory synchronization example, **not evidence Casio uses RPMsg**. |

## Reverse engineering the firmware's RTOS

| Reference | Use / limits |
| --- | --- |
| [eForce uC3 example project](https://github.com/shun0847/uC3) | µITRON tasks, semaphores, ISR, scheduler and API nomenclature. AArch64/i.MX8 example; not a proven Casio ARMv7 binary match. |
| [Older eForce uNet3s i.MX25 SDK](https://github.com/DerEchteJoghurt/uNet3s_iMX25_ewarm_eva) | Historic ARM9 µITRON/API conventions, not an exact ABI or port. |
| [EXeSX A7 firmware-verified Ghidra name table](../reverse/a7_kernel_named_sites.tsv) | Actual real-firmware addresses and evidence confidence. |

## A7 USDHC0, DMA1, DMAMUX1 and LPSPI2 references

- [Linux i.MX7ULP device tree](https://github.com/torvalds/linux/blob/master/arch/arm/boot/dts/nxp/imx/imx7ulp.dtsi) — maps USDHC0 0x40370000, A7 eDMA1 0x40080000 and DMAMUX1 0x40210000 with 32 channels
- [Linux Freescale eDMA binding](https://kernel.googlesource.com/pub/scm/linux/kernel/git/torvalds/linux/+/7c16f0a4ed1ce7b0dd1c01fc012e5bde89fe7748/Documentation/devicetree/bindings/dma/fsl,edma.yaml) — DMA1 0x2000 byte and DMAMUX1 0x1000 byte windows
- [NXP MCIMX7U5 peripheral base addresses](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/MCIMX7U5/MCIMX7U5_cm4_COMMON.h) — independent confirmation of DMA1, DMAMUX1, USDHC0 and LPSPI2
- [NXP USDHC SDK API](https://mcuxpresso.nxp.com/api_doc/dev/1581/group__usdhc.html) — `PRES_STATE.SDSTB` (stable clock) is distinct from `CINST` (actual card inserted)
- [Live A7 USDHC→DMA1→DMAMUX1→LPSPI2 study](2026-10-21-a7-usdhc-dma-bringup.md) — private-firmware addresses, exact instructions, model limits and next tests; no proprietary firmware uploaded

## SNVS high-power real-time counter and DMA status

- [NXP PERI_SNVS.h](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/periph/PERI_SNVS.h) — HP RTC counter MSB/LSB offsets `+0x24/+0x28` and control register `HPCR.RTC_EN`
- [NXP PERI_DMA.h](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/periph/PERI_DMA.h) — A7 DMA1 `CR.ACTIVE` bit **31**, eDMA TCD control/state
- [Private M4 SNVS RTC follow-up](2026-10-21-snvs-rtc-m4-followup.md) — exact 0x41070024 bus read, virtual elapsed-time emulation and limitations

## A7 USDHC1 and MMDC0 power-management references

- [NXP i.MX7ULP PERI_USDHC.h](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/periph/PERI_USDHC.h) — USDHC1 `VEND_SPEC.FRC_SDCLK_ON` bit8 and `SYS_CTRL.RSTA` bit24, plus `PRES_STATE.SDSTB` (host clock only)
- [NXP i.MX7ULP PERI_MMDC.h](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/periph/PERI_MMDC.h) — MMDC0 `MAPSR +0x404`, `PSD` bit0, `LPMD` request bit20, `LPACK` acknowledgment bit24
- [Firmware-confirmed USDHC1/MMDC suspend investigation](2026-10-21-usdhc1-mmdc-lowpower.md) — A7 copied internal-RAM low-power routine requests DDR self-refresh and ends in `WFI`; do not force unverified wakeup

## M4 GPIOB7 startup permission and independent wakeup references

- [NXP PERI_GPIO.h](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/periph/PERI_GPIO.h) — GPIOB `PDIR` at +0x10 (input voltages), `PDDR` +0x14 (input/output direction)
- [NXP i.MX7ULP MCIMX7U5 CMSIS base addresses](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/MCIMX7U5/MCIMX7U5_cm4_COMMON.h) — GPIOB base `0x4100F040`
- [NXP MCUXpresso EVK power-mode switch demo](https://docs.mcuxpresso.nxp.com/mcuxsdk/26.09.00-pvw1/html/examples/_boards/evkmcimx7ulp/demo_apps/power_mode_switch/example_board_readme.html) — **explicitly separate** A7 boot, wake, shutdown and reboot commands and M4-managed power states; only an architectural example, **not** Casio's proven protocol
- [NXP i.MX7ULP low-power boot discussion](https://community.nxp.com/t5/i-MX-Processors/i-MX7ULP-in-low-power-boot/m-p/1166065/highlight/true) — dual-boot A7 can remain VLLS while M4 coordinates wake; Casio board assumptions require independent evidence
- [NXP A7/M4 power-mode timing case](https://community.nxp.com/t5/i-MX-Processors/A7-M4-timing-issue-using-power-mode-switch-example/td-p/1065463) — GPIO/LPTMR wake in demo use cases, **not a confirmed GPIOB7 Casio wakeup**
- [Original-OSUP M4 GPIOB7→A7 shared permission investigation](2026-10-21-gpiob7-boot-permission.md) — exact Thumb, ARM and cross-core watchpoint traces; MMDC low-power is a consequence of the gate being false

## First SD/eMMC command-transaction references

- [NXP i.MX7ULP PERI_USDHC.h](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/periph/PERI_USDHC.h) — `CMD_ARG` +0x08, `CMD_XFR_TYP` +0x0C, `INT_STATUS` +0x30 W1C, `INT_STATUS_EN` +0x34, `INT_SIGNAL_EN` +0x38, `WTMK_LVL` +0x44; no card response may be invented
- [Linux i.MX7ULP USDHC/eSDHC driver](https://github.com/torvalds/linux/blob/master/drivers/mmc/host/sdhci-esdhc-imx.c) — SDHCI command/interrupt, reset, watermarks and i.MX-specific quirks (requires port validation)
- [QEMU SDHCI controller implementation](https://gitlab.com/qemu-project/qemu/-/blob/master/hw/sd/sdhci.c) — possible reusable *actual* USDHC-compatible command/card engine, but verify i.MX7ULP-specific register differences, IRQ wiring, backing-card semantics, and licensing
- [USDHC1 first CMD0/zero-argument boundary](2026-10-21-usdhc1-irq-control.md) — firmware-verified CTRL/interrupt/W1C progression
- [USDHC1 WTMK watermark disassembly](2026-10-21-usdhc1-watermarks-after-bootgate.md) — firmware write 0x08200820 before first command

## Verified MMC/eMMC startup and next emulator implementation sources

- [NXP i.MX7ULP USDHC register definitions — PERI_USDHC.h](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/periph/PERI_USDHC.h) — `PROT_CTRL`, `CMD_ARG`, `CMD_XFR_TYP`, `CMDRSP0-3`, `INT_STATUS.CC/CTOE`, `SYS_CTRL` and clock/status fields
- [NXP MCUXpresso USDHC driver](https://mcuxpresso.nxp.com/api_doc/dev/1581/group__usdhc.html) — command/no-response/48-bit/136-bit response types, response error handling and real transfers
- [QEMU upstream SDHCI controller](https://github.com/qemu/qemu/blob/master/hw/sd/sdhci.c) — reusable command/response/data-controller implementation; i.MX7ULP-specific MMIO and IRQ differences remain unresolved
- [QEMU SD card and TYPE_EMMC device API](https://qemu.googlesource.com/qemu/+/25fef09ce17ac1ae22638a0b57d97c2bd5cd7d83/include/hw/sd/sd.h) — **separate eMMC device exists**; use a backed image and real device protocol, not arbitrary 0xff/0x00 sectors or invented OCR
- [Linux i.MX eSDHC driver](https://github.com/torvalds/linux/blob/master/drivers/mmc/host/sdhci-esdhc-imx.c) — host reset/clock/CMD response/bus power differences relevant to adapting QEMU SDHCI
- [Linux MMC core host definitions](https://github.com/torvalds/linux/blob/master/include/linux/mmc/mmc.h) — standard MMC CMD0/CMD1/CMD2/CMD3/CMD9/CMD7/CMD6 command IDs and OCR/CID/CSD semantics
- [JEDEC eMMC 5.1 standard, JESD84-B51](https://www.jedec.org/standards-documents/docs/jesd84-b51) — normative eMMC protocol source where accessible; do not assume Casio uses exactly v5.1 without hardware evidence
- [Original Casio A7 MMC identification disassembly](2026-10-21-usdhc1-cmd0-no-media.md) — first CMD0 and CMD1 with live arguments; full software sequence includes CMD2/3/9/7 and CMD6
- [Native and original-ROM confirmed empty-eMMC-slot timeout behavior](2026-10-21-usdhc1-no-media-timeout.md) — 65 CMD1 retries then CMD7 with absent card, no invented OCR or OS boot

These records confirm the **firmware speaks an MMC/eMMC-class protocol**; they do **not** identify the physical Casio storage package, capacity, CSD contents, partition geometry, or any actual SD/eMMC image.

## Current investigation reports

- [Real firmware MU v1 correction](2026-10-20-imx7ulp-mu-v1-bit-order.md) — 78,665 to 2 IRQ22 entries with MU interrupt enabled, still no proven OS entry.
- [SNVS command investigation](2026-10-21-snvs-hp-investigation.md) — bounded SNVS HP model with no fabricated secure state.
- [Current EXeSX status](STATUS.md).

## Evidence labels used in EXeSX research

- **Silicon fact** — NXP register headers/SDK or an explicit i.MX7ULP upstream driver.
- **Firmware fact** — actual locally supplied checksum-validated Casio firmware PC/disassembly/trace.
- **Emulator result** — native QEMU guest ARM instruction test or real private OSUP differential.
- **Hypothesis** — stated as such until matched by relevant runtime and external documentation.

For SNVS, a synthetic register response, guest PC advance, or reduced fault count **does not establish successful secure-boot or OS startup**.
