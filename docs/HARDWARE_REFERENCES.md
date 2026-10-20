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
