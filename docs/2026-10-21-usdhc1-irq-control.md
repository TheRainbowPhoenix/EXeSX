# USDHC1 INT_STATUS after M4 GPIOB7 boot permission — 2026-10-21

The original, privately SHA-verified Casio OSUP now runs with an opt-in **GPIOB7 input high** so that the actual M4 sets shared startup permission and the A7 takes normal startup. Other opt-ins (I²C 0x4B/0x40 mirrors and ignored SNVS software-security-violation commands) are **research diagnostics**, not hardware assertions. No guest OS entry or display is confirmed.

[PR #15](https://github.com/TheRainbowPhoenix/EXeSX/pull/15) corrected the externally driven GPIO input and verified original firmware independently. [PR #16](https://github.com/TheRainbowPhoenix/EXeSX/pull/16) supported the precise next A7 write `USDHC1.WTMK_LVL=0x08200820` at `0x40380044` and passed real-ARM CI.

## Next actual original-firmware fault

With PR #16 native QEMU, the original A7 chooses normal startup and the WTMK write succeeds. The next Data Abort is **DFSR=0x1008, DFAR=`0x40380030`**: i.MX7ULP USDHC1 `INT_STATUS` (host base `0x40380000`, offset `+0x30`). Nearby real A7 function `0x6001788C` reads `INT_STATUS` then writes it back to clear pending status, consistent with a **write-one-to-clear (W1C)** interrupt/error register.

NXP's official [PERI_USDHC.h](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/periph/PERI_USDHC.h) defines `INT_STATUS` at +0x30, `INT_STATUS_EN` +0x34 and `INT_SIGNAL_EN` +0x38. Documented active bit mask: `0x157F51FF`, which includes command complete (CC), transfer complete (TC), card insertion/removal, SD command/timeouts, tuning and DMA errors.

## Conservative register subset

- `INT_STATUS`: pending bits start **zero**; guest writes clear bits W1C. **No device/card exists to assert any pending event.**
- `INT_STATUS_EN` and `INT_SIGNAL_EN`: read/write only documented status-event bits, masking reserved bits as RAZ/WI; no GIC interrupt line or event generator.
- These controls live in the existing snapshot-backed USDHC1 register array.
- Not implemented: CMD_XFR_TYP command completion, actual card responses, DS_ADDR DMA, data FIFO, SD clock cycle timing, CINS/card insertion, interrupt delivery or storage contents.

The native ARM guest regression `scripts/probe_a7_early_devices.py` now tests a write of all ones to W1C status (still zero), enables all documented sources in both enable registers, reads back the exact mask, and confirms no spurious command-complete/cartridge event. A private real-ROM differential after CI is required to identify the next actual access/timeout.

## Completed native and real-firmware validation: first SD command

Native [GitHub Actions run 39577446097](https://github.com/TheRainbowPhoenix/EXeSX/actions/runs/39577446097) **SUCCESS**, including the ARM guest no-card INT_STATUS/W1C and enable-register test. Independently unpacked its exact artifact, SHA256 checked the tarball against the included manifest, and ran the real-ARM regression successfully.

Original checksum-verified Casio OSUP with opt-in GPIOB7=high, same diagnostic I²C+SNVS configuration and **no debugger register modifications**: M4 sets boot gate high, A7 passes normal startup, then gets past previously missing USDHC1 INT_STATUS at `0x40380030`. The NEXT observed A7 Data Abort was **DFSR=0x1808, DFAR=`0x40380008`**, USDHC1 `CMD_ARG` (command argument). GDB breakpoint on the original A7 instruction **`0x600178BC: str r8,[r7]`** in its command-submission function (entry `0x6001788C`) measured `r7=0x40380008`, `r8=0`, caller `r4=0,r5=0,r6=0`. The next instructions assemble `CMD_XFR_TYP` at `0x4038000C`. This is consistent with an initial **CMD0 / GO_IDLE_STATE** with **argument 0**, but confirmation of the complete CMD_XFR_TYP index field requires stepping through the later write with an actual controller model.

**This is now a *true storage-host protocol boundary*, not just missing startup status.** A complete next phase must provide a real USDHC controller state machine and an appropriate card/eMMC backing (or explicitly report no card), including CMD0, ACMD/CMD1 polling, command/response and timeout behavior. Do **not** set `INT_STATUS.CC`, card inserted, or claim media data was read simply to make the A7 continue. The existing updater OS image is not automatically a physical card image.

Sources: [official NXP PERI_USDHC.h](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/periph/PERI_USDHC.h), [Linux i.MX7ULP host-controller device tree](https://github.com/torvalds/linux/blob/master/arch/arm/boot/dts/nxp/imx/imx7ulp.dtsi), [GPIOB7-to-A7 gate study](2026-10-21-gpiob7-boot-permission.md), and [hardware reference catalog](HARDWARE_REFERENCES.md).
