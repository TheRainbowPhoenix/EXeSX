# DY358 photographed motherboard cross-check — 2026-10-26

**Provenance:** user-reported markings observed on DY358 PCB photographs, compared with previously documented PWB-DY890-1 photograph. The new photographs themselves are **not** published in this repository; markings below are transcribed from the user's description, not independently verified from the pixels.

| Component | User-observed DY358 marking | Compared with previously photographed DY890 | Emulator significance |
| --- | --- | --- | --- |
| Application processor | NXP `MCIMX7U5DVP07SC`, second line transcribed `IN54W` (potentially `1N54W`) | `MCIMX7U5DVP07SD`, mask `2N54W` | **Not identical revisions.** NXP identifies separate 1N54W and 2N54W errata. Do not apply B2 assumptions from DY890 to DY358 without confirming the actual mask marking. |
| RAM | ESMT `M54D1G3232A` (speed grade `-2.5`) | Same ESMT 1-Gbit LPDDR2 part | Consistent with 128 MiB volatile RAM on both photographed boards, *not* proof of current DY357 RAM topology. |
| Wi-Fi | Microchip `ATWINC1510` module | Same ATWINC1510 SPI network coprocessor | Corroborates the component identity across two board families; **chip-select, host SPI port, IRQ GPIO and WLAN firmware protocol still need traced DY357 execution**. |
| Unidentified support IC | Marking transcribed `8070527` with manufacturing sub-marking | Earlier unclear `BD70527`-like marking | Do not assign a vendor, function, I2C address or PMIC identity from incomplete/possibly differing digits. |
| Nonvolatile storage | Samsung `KLMAG1JETD B041`, preceding label `SEC 046` | Earlier faint `KLMAG1J` prefix had been only tentative | Strong user-reported identification of **Samsung KLMAG1JETD-B041 16 GB eMMC 5.1** on **DY358**. Strengthens an eMMC capacity family hypothesis for similar boards, *not* evidence that the proprietary DY357 OS image or partitions are available. |

## Distinguish the targets

- **DY358** is the newly inspected board; **DY890** was the earlier photographed board; the unchanged private `OSUP.BIN` under test is a **DY357 firmware target**. Cross-model similarities justify focused experiments, not silent substitution of PCB-level wiring or QEMU model identity.
- NXP's official [i.MX7ULP 2N54W mask revision notice](https://www.nxp.com/pcn/202009014I) and [1N54W/2N54W errata notice](https://www.nxp.com/pcn/202411012I) confirm why the processor top-line suffix and silicon mask **matter**. The provided second-line reading `IN54W` might be `1N54W`; no definitive mask claim from a transcription alone.
- [KLMAG1JETD-B041](https://www.lcsc.com/product-detail/EMMC_span-style-background-color-ff0-Samsung-span-KLMAG1JETD-B041_C499919.html) is commercially specified as 16GB eMMC 5.1, and this new owner observation upgrades the component identification **for DY358**.
- The previous photographed ROHM BU26154 is a plausible touch/audio chip for these related boards. **This new DY358 report does not independently identify the touch IC**; however, original DY357 M4 firmware traced address `0x1A` on `LPI2C2 0x41035000`, with multiple MAPCON switches, which supports implementing ROHM digital-touch behavior experimentally there. Actual touch-panel pen GPIO/IRQ, calibration and complete E2 factory-test passage remain unverified.

**Privacy/firmware handling:** do not commit owner board photographs, Wi-Fi module MAC/QR/device identifiers, proprietary OSUP, extracted binaries, raw virtual media, private screenshots or QMP execution traces.

See [previous DY890 chip identifications](2026-10-21-pwb-dy890-pcb-identification.md) and [BU26154 touch / WLAN investigation](2026-10-26-bu26154-touch-and-atwinc1510-wlan.md).
