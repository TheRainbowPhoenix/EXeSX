# i.MX7ULP USDHC1 clock and FIFO watermark review — 21 October 2026

## Sources and scope
- NXP [i.MX7ULP PERI_USDHC.h](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/periph/PERI_USDHC.h): `PRES_STATE.SDSTB` bit3 reports stable clock; `SYS_CTRL.RSTA` bit24 is software reset; `SYS_CTRL.DVS` and `SDCLKFS` select divisors; `VEND_SPEC.FRC_SDCLK_ON` bit8 forces card clock when set and returns control to hardware when clear; `WTMK_LVL.RD_WML` is RX FIFO level measured in words.
- NXP [USDHC SDK API](https://mcuxpresso.nxp.com/api_doc/dev/721/group__usdhc.html): distinct APIs for SD card clock, force-clock, and reset. NXP [i.MX Linux reference](https://www.nxp.com/docs/en/reference-manual/IMX_REFERENCE_MANUAL.pdf) explains received FIFO watermark and host DMA request.
- [QEMU 10.1.0 SDHCI](https://github.com/qemu/qemu/blob/v10.1.0/hw/sd/sdhci.c): `usdhc_write` ignores `USDHC_WTMK_LVL`; generic `sdhci_read_block_from_card` raises RBUFRDY once for whole buffered block, while `sdhci_read_dataport` advances actual read offset.

## Clock model conclusion
The i.MX7ULP fields and split clock-source/card-output controls are documented. However, neither NXP register header nor tested driver sources establish the exact clock-tree/PCC2 state or SDSTB settling interval for the DY357 board: **no reliable numerical delay or automatic PCC2 power-up constant can be inferred**. We retained the opt-in `imx7ulp-input-clock` model from PR #21, rather than inventing timing or forcing SDSTB unconditionally; the root clock is independently testable on/off. Static ARM tests and private original-OSUP prior differential already proved the RSTA→SDSTB path progressed through eMMC CMD0–CMD8.

## WTMK_LVL and BRR extension
The opt-in i.MX7ULP device now stores and reads documented WTMK_LVL fields and resets them. The existing genuine 512-byte card FIFO data is never fabricated. After each configured RD_WML-word tranche, firmware W1C of BRR can acknowledge and re-arm ready only while `DATA_AVAILABLE` and unread bytes remain in the *actual* buffered card block. The unmodified QEMU device and default EXeSX no-media path are untouched. New state is VMState version 2, backward-compatible with version 1 loads.

The expanded synthetic ARM eMMC regression writes original `0x08200820`, checks register readback, consumes 32-word batches and W1C-acks BRR for CMD17 and CMD8/EXT_CSD. It verifies fresh BRR after the first three boundaries and no false ready event after the final 512-byte block. Existing CMD1 OCR, CID/CSD, user sector marker, SEC_COUNT and no-media tests remain.

**Validation boundary:** CI is guest ARM and synthetic media, not genuine Casio OSUP, and dynamic PCC2 clock-tree connection is still not modeled. Do not claim original firmware success until an independent native private original ROM run reproduces it.


## CI and private original-firmware result
Native QEMU 10.1.0 guest-ARM CI [run 39675448940](https://github.com/TheRainbowPhoenix/EXeSX/actions/runs/39675448940) passed compile, CMD17 synthetic sector, CMD8 real EXT_CSD in 32-word batches with W1C and repeated BRR, root-clock-disabled regression and no-media timeout. Other native regressions also passed.

A separate **5-second private original DY357 firmware execution** used the same SHA-verified OSUP-derived A7/M4 ELF, the same sparse Samsung-reference-size test eMMC and existing opt-in diagnostic board environment as the earlier clock-fix differential. Firmware and traces remain local and uncommitted.

Measured at native QEMU monitor stop: A7 **PC `0x601b82b8`** (BIOS region) rather than previously stalled **`0x60018784`**; USDHC1 command register `CMD_XFR_TYP=0x11220010` = **CMD17** (SINGLE_BLOCK_READ), `PRES_STATE=0x01ff0008`, `SYS_CTRL=0x008d0200`, `INT_STATUS=0x00000003` (CC+TC). Log contains original BIOS addresses beyond `0x60018784` and no new Invalid read/write MMIO entries in the bounded capture. This independently validates progress through EXT_CSD and into a later genuine card-sector read, **not OS boot**. The synthetic eMMC has no Casio sectors. No execution at OS section `0x60400000` or framebuffer/text has been demonstrated.

**What remains unknown:** significance of BIOS poll/control at `0x601b82b8`, later data content expectations, exact SCG1/PCC2 clock gate wiring, real hardware reset timing, Samsung CID/EXT_CSD match, and physical eMMC sectors. No change to the actual proprietary ROM.
