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

Sources: [official NXP PERI_USDHC.h](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/periph/PERI_USDHC.h), [Linux i.MX7ULP host-controller device tree](https://github.com/torvalds/linux/blob/master/arch/arm/boot/dts/nxp/imx/imx7ulp.dtsi), [GPIOB7-to-A7 gate study](2026-10-21-gpiob7-boot-permission.md), and [hardware reference catalog](HARDWARE_REFERENCES.md).
