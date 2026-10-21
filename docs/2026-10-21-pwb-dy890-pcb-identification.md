# Candidate Casio board PWB-DY890-1: chip identification from user PCB photos

**Evidence date:** 2026-10-21 (photos themselves show 2024 dates).
**Board marking visible:** `PWB-DY890-1 / RJA542224-001V02`.

> **Board/model identity is NOT established.** These photos were provided as a possible EX-word SX-family board. Our privately analyzed OSUP identifies a different firmware target (DY357). Do **not** silently replace DY357 motherboard identifiers with DY890 or assume every peripheral, memory size, or GPIO wiring matches. Do not publish original photos, QR codes, device identifiers, MACs or assembly labels; this report records only nonsensitive part markings and public datasheets.

## Component identification table

| Seen marking | Identification and manufacturer documentation | Confidence | EXeSX relevance |
| --- | --- | --- | --- |
| `MCIMX7U5DVP07SD`, **`2N54W`**, `CTAH2145A` | NXP i.MX7ULP Cortex-A7 + M4 application processor, **silicon revision B2**. [NXP part/B2 datasheet](https://www.nxp.com/docs/en/data-sheet/IMX7ULPCECB2.pdf), [NXP PCN 202009014I](https://www.nxp.com/pcn/202009014I) explicitly links mask set 2N54W to B2. | High for pictured board | Prioritize **IMX7ULPRMB2** and the **2N54W errata** instead of B1-only assumptions, especially MU/clock/DDR/boot nuances. Whether the DY357 target uses the same mask is **unverified**. |
| `ESMT M54D1G3232A`, `-2.5...` | ESMT **1-Gbit LPDDR2-S4B SDRAM, 32-bit data bus, 8 banks, 134-ball BGA**. [Original manufacturer datasheet](https://www.esmt.com.tw/upload/pdf/ESMT/datasheets/M54D1G3232A.pdf). | High | **128 MiB volatile LPDDR2**, **not eMMC** and **not flash**. It may justify a separately tested **128 MiB DRAM configuration** for this *board revision*, but do not change QEMU's memory map unconditionally without checking the actual DY357 board and firmware mapping. |
| `BU26154` with smaller date/lot characters | [ROHM BU26154MUV](https://www.rohm.com/products/audio-video/audio-converters/audio-codecs/bu26154muv-product): **24-bit audio CODEC, speaker/headphone amps and four-wire resistive touch-panel ADC/interface**, intended in part for electronic dictionaries. Datasheet I²C SAD-selected 7-bit address **0x1A or 0x1B** (`0011010`/`0011011`), or 3-wire mode. [Full datasheet](https://www.infinite-electronic.kr/datasheet/67-BU26154MUV-E2.pdf). | High for chip function; bus selection/wiring not confirmed | **Major new touch/audio candidate.** This can explain a resistive touchscreen without a separate digital touch controller. **Not the unknown I²C 0x4B device**; address 0x1A/1B differs. The board must be traced before assigning an EXeSX bus or simulating touch events. |
| `ATWINC1510-MR210PB` | [Microchip ATWINC1510 / ATWINC15x0 module](https://www.microchip.com/en-us/product/ATWINC1510-IC) — 2.4-GHz 802.11 b/g/n Wi-Fi network coprocessor, **SPI host** plus GPIO/IRQ/WAKE/RESET. [Microchip developer guide](https://developerhelp.microchip.com/xwiki/bin/view/products/wireless-connectivity/Embedded-Wi-Fi/winc1500-overview/). | High | Strong candidate for future LPSPI host-device and IRQ emulation. Module's own embedded flash is for Wi-Fi firmware, **not proof of the missing system eMMC**. No claim Wi-Fi must initialize before UI boot. |
| `BD70527`, smaller `223 H45` | **Unknown.** This marking does not unambiguously identify a publicly verified device/datasheet from current research. | Low | Do not call it the board PMIC or assign an I²C address until a clear photo/full part name or continuity and vendor documentation confirm it. |
| `N2006`, smaller `06 02` | **Unknown** from the presently legible package marking. | Low | Not a proven touch, PMIC, charger, storage or USB chip. No fake driver or I²C address assignment. |
| **Unidentified square BGA** adjacent to processor/DRAM | Surface text is faint in user photo; function **not established**. | Unidentified | **Top priority to re-photograph** as a candidate for NAND/eMMC/other system storage. The actual A7 firmware uses USDHC1 MMC CMD0/CMD1/2/3/9/7/6; package identity, wiring, capacity and contents still unknown. |
| **Visible microSD-format slot** | Mechanical slot on board photo. | High for connector, unverified bus | Might be another storage interface. Slot presence does **not** establish which USDHC host is connected or that CMD1 is aimed at this connector instead of soldered eMMC. |

## What this changes in our emulator research

1. The **2N54W mask unlocks B2 documentation**: NXP states that B2 added DDR performance and boot-stability fixes. For this photographed PCB, use [B2 datasheet](https://www.nxp.com/docs/en/data-sheet/IMX7ULPCECB2.pdf), [mask revision notice](https://www.nxp.com/pcn/202009014I), [B2 reference manual/errata index](https://www.nxp.com/products/i.MX7ULP). The actual DY357 board mask is still unconfirmed.
2. **The 128-MiB LPDDR2 is not persistent storage.** Keep DRAM sizing and DDR initialization separate from USDHC1 eMMC protocol/state/content. The ROM's no-card CMD1 timeout test stays valid for empty eMMC.
3. **Audio + touch are likely related to ROHM BU26154**, not necessarily a 0x4B touchscreen controller. Its datasheet describes XP/XN/YP/YN four-wire touch electrodes. Before changing QEMU, XRef actual firmware reads/writes of I²C 0x1A/0x1B and inspect controller routing and IRQ pin. Do not ascribe its touch ADC to the unknown M4 0x4B device.
4. The photographed Wi-Fi module is an **SPI peripheral**, not a stand-alone OS flash chip. Its SPI bus/IRQ may become a later blocker but is not currently proven so.
5. **The actual eMMC remains unidentified.** Request a close, sharp, glare-free angled-light photo of the **third large BGA with faint text next to the SoC and LPDDR2**, plus both sides of the PCB if possible, and a photo of the model designation on the device itself. No desoldering/probing required for identification.

## Address warning: 0x4B

Some **other** ROHM PMICs can use a 7-bit I²C address `0x4B` ([ROHM PMIC FAQ](https://www.rohm.co.kr/products/faq-search/faqId/2453); e.g. BD71850 I²C addressing, [BD71850 datasheet](https://fscdn.rohm.com/en/products/databook/datasheet/ic/power/switching_regulator_system/bd71850mwv-e.pdf)). This is **not evidence that such a PMIC is installed here**, and does **not identify the unverified `BD70527` marking**. Do not implement BD71850 register maps against the M4's 0x4B traffic on this basis alone.

## Working verification checklist

- `PWB-DY890-1` board identity vs privately analyzed `DY357` firmware/model: **unverified**.
- 2N54W and 128 MiB LPDDR2: **verified for pictured board**.
- BU26154 touch+audio and I²C 0x1A/0x1B option: **datasheet-verified**, actual interface mode unverified.
- ATWINC1510 Wi-Fi on SPI: **datasheet-verified**, host port selection unverified.
- Unknown BGA = eMMC: **hypothesis, not confirmation**.
- Existing EXeSX USDHC1 CMD0/CMD1 first-boot trace remains **firmware-verified**; device chip/content and eMMC image not proven.

All chip IDs above are package identifiers or board manufacturing marks, **not** user-identifying radio IDs, QR labels, or serial numbers.
