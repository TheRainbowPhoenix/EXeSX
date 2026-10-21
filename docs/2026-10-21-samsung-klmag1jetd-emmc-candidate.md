# Candidate Samsung KLMAG1JETD-B041 eMMC on photographed PWB-DY890-1

**Evidence date:** 2026-10-21. **Status: strong part-family identification hypothesis, exact physical marking and wiring unverified.**

The user inspected the faint printing on the third large BGA of a *candidate* EX-word mainboard labelled `PWB-DY890-1 / RJA542224-001V02`. The middle line **appears to start `KLMAG1J`**. Samsung's documented part `KLMAG1JETD-B041` matches that prefix, physical package class, and the MMC/eMMC command sequence reverse-engineered independently in EXeSX. The complete remaining letters and suffix are **not yet readable**. Crucially the reverse-engineered private firmware refers to DY357, and the photographed PCB is DY890: **the two board models are not proved electrically identical**.

We have *not* photographed an established CID, traced USDHC1 CLK/CMD/DAT pins, imaged the eMMC, or read an actual card response. This report is therefore a **test-device profile** and research roadmap, not a declaration that a confirmed Samsung eMMC is installed on the target Casio device.

## Exact candidate device from published Samsung datasheet

Sources: [Samsung KLMAG1JETD-B041 family datasheet, Rev. 1.21 (July 2017), 28 pages](https://manuals.plus/m/73f47e95f7f148c9d063bbf1cc3073bbe86781cc4deea903952521fb7725c585) and [Samsung product-specification page archive](https://manuals.plus/m/c541cfe15445324325e0add977ef2fee7a43eda5f5ded9c75c3a6fe22d4fdd6). **Link to external documentation only; do not commit the datasheet or private photos.**

| Item | Samsung's KLMAG1JETD-B041 published specification | Modeling implication |
| --- | --- | --- |
| Technology | Managed NAND with integrated eMMC controller; **eMMC 5.1** | Use MMC (not raw NAND or SD-only) protocol and card state machine. |
| Nominal capacity | **16 GB** | Nominal marketing capacity; not a byte-exact backing-image size. |
| User data area | **15,634,268,160 bytes**, Samsung Table 18 | Exactly **30,535,680 512-byte sectors**, `SEC_COUNT=0x01D1F000` for the *reference part* if unmodified. Do not round to 16 GiB. |
| Boot area | Two **4 MiB** boot partitions | Separate eMMC hardware partitions; do not silently concatenate them with the user data area. |
| Replay-protected area | **4 MiB RPMB** | Distinct authenticated/replay-protected partition. Do not implement arbitrary user-data reads as RPMB or forge key authentication. |
| CID manufacturer | Samsung **MID=0x15** | Manufacturer byte only; don't invent OEM/application ID, real serial number, or revision. |
| CID product name (PNM) | Family datasheet 16 GB value `0x414A54443452`, ASCII `AJTD4R` | A candidate device-identification signature; validate against a real `mmc extcsd read`/`mmc cid read` if accessible. Never assume that marking alone proves it. |
| EXT_CSD revision | `EXT_CSD_REV=8` for eMMC 5.1 | 512-byte EXT_CSD support is necessary, not just CMD1 OCR. |
| Package | 153-ball FBGA, approximately **11.5 × 13 × 0.8 mm** | Supports package-size plausibility, not electrical continuity proof. |
| VCC/VCCQ | Flash 2.7–3.6 V; interface 1.7–1.95 V **or** 2.7–3.6 V | Supports voltage negotiation context; actual board rails unmeasured. |
| MMC OCR | Samsung documents 1.7–1.95 and 2.7–3.6 V windows; sector-addressing mode; bit31 signals power-up ready | Casio BIOS issues CMD1 with **argument `0x40FF8000`**. An attached *real modeled* card should negotiate these bits with correct readiness timing; no-card mode must never set OCR_BUSY. |
| User storage contents | **Not supplied** | A blank/synthetic eMMC could validate protocol progression but **cannot be asserted to contain Casio's OS, filesystem or user dictionary data**. |

**Capacity calculation:** `15,634,268,160 / 512 = 30,535,680 = 0x01D1F000` sectors. Samsung's Table 18 describes a *factory-standard user-area density*, not a measured dump or immutable property if hardware partitions have been reconfigured. Production EXT_CSD may differ.

**Note on the product name:** Samsung's Rev. 1.21 Product Name table prints 6-byte PNM `0x414A54443452` for KLMAG1JETD-B041; byte order/word layout when reading USDHC `CMDRSP` registers must be handled according to MMC R2 response alignment. Do not substitute this value for a complete 128-bit CID.

## Why this directly relates to the EXeSX boot blocker

Original SHA-validated DY357 firmware already reached USDHC1 (`0x40380000`) without patching firmware or CPU register values (after the explicitly diagnostic GPIOB7 input option enabled the normal startup branch). A real native-QEMU trace showed:

```text
USDHC1 CMD0 ARG=0x00000000 XFR=0x00000000
USDHC1 CMD1 ARG=0x40ff8000 XFR=0x01020000
```

With no physical medium or virtual card, a separate no-media emulation test observed **65 CMD1 requests**, then CMD7 as firmware fell through its initialization/error path. The BIOS code also contains CMD2/CMD3/CMD9/CMD7 and CMD6. The MMC CMD1 sequence is **consistent with Samsung's eMMC 5.1**, but not unique to this manufacturer or model. See [real firmware CMD0/1 disassembly](2026-10-21-usdhc1-cmd0-no-media.md) and [real no-media experiment](2026-10-21-usdhc1-no-media-timeout.md).

## Recommended next emulator milestone: real virtual eMMC card

1. **Keep current no-media mode unchanged and passing.** Do not use Samsung's theoretical OCR or a made-up eMMC response unless a virtual card device is explicitly attached to USDHC1.
2. Add a separate **opt-in 16 GB Samsung-compatible test eMMC** with a suitable sparse/block backend sized from Table 18, independent 4 MiB boot0/boot1 and RPMB metadata. Prefer QEMU's actual [TYPE_EMMC card implementation](https://github.com/qemu/qemu/blob/master/include/hw/sd/sd.h) over a fake table of success values.
3. Wire USDHC1 request/response path to a real card model: CMD0 → CMD1 with power-up delay/OCR; CMD2 R2 CID; CMD3 RCA; CMD9 R2 CSD; CMD7 select; CMD6 switch and EXT_CSD; **then** data reads (`CMD17/18`), transfer completion and DMA/IRQ under measured conditions. Verify any host-controller register remapping against NXP [PERI_USDHC.h](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/periph/PERI_USDHC.h) and [Linux i.MX SDHCI host driver](https://github.com/torvalds/linux/blob/master/drivers/mmc/host/sdhci-esdhc-imx.c).
4. Run firmware **twice**: absent medium should still return CTOE/no-card and never produce OCR; attached synthetic device should enumerate, expose capacity and enter the next *actual* BIOS branch. Only declare storage read success if a backend truly supplies the requested block.
5. Avoid treating the updater `OSUP.BIN` as a sector-for-sector eMMC backup. It is a firmware update container and may lack boot partitions, filesystem, user area and Casio device-specific data.
6. If hardware becomes accessible, obtain a **non-destructive read-only dump** of the chip identity (CID, CSD, EXT_CSD), and only then, where authorized and practical, separate read-only partition images. Do not write to physical eMMC, modify permanent write-protect, or attempt RPMB provisioning just for identification.

The following remain **unverified**: full BGA top marking (last letters and suffix), PCB trace routing to USDHC1 vs USDHC0, its exact capacity/configuration after factory partitioning, chip serial/revision, and whether photographed DY890 memory is present on target DY357. The candidate part information should not alter default QEMU board RAM or flash behavior until verified.

## Source links

- [Samsung product-family datasheet Rev. 1.21, including OCR/CID/CSD/EXT_CSD](https://manuals.plus/m/73f47e95f7f148c9d063bbf1cc3073bbe86781cc4deea903952521fb7725c585)
- [Samsung KLMAG1JETD-B041 original product overview archive](https://manuals.plus/m/c541cfe15445324325e0add977ef2fee7a43eda5f5ded9c75c3a6fe22d4fdd6)
- [Samsung eMMC user-density and boot partition information (original datasheet)](https://www.pilover.com/wp-content/uploads/2020/05/KLMAG1JETD-B041.pdf)
- [NXP i.MX7ULP USDHC registers](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/periph/PERI_USDHC.h)
- [QEMU 10.1 host/card code: SDHCI](https://github.com/qemu/qemu/blob/v10.1.0/hw/sd/sdhci.c), [SD/eMMC card](https://github.com/qemu/qemu/blob/v10.1.0/hw/sd/sd.c), [API](https://github.com/qemu/qemu/blob/v10.1.0/include/hw/sd/sd.h)
- [Linux MMC/eMMC command definitions](https://github.com/torvalds/linux/blob/master/include/linux/mmc/mmc.h)

The Samsung part is a **high-quality hardware lead**, not yet a hardware-backed proof of a bootable eMMC attached to the same controller.
