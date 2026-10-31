# WINC1510 implementation audit, remaining work and screenshot evidence

This is an audit of code **already committed** to draft PR #42, not a claim that original WLAN test results are passing. Owner confirms DY357 and DY890 use ATWINC1510.

## Implemented and synthetically tested

| Stage | Implementation | Positive test | Limitation |
|---|---|---|---|
| i.MX7ULP SPI host | `hw/arm/exesx-imx7ulp-lpspi.inc`: TCR packed frames, TDR/RDR, PCS selection/continuity, BYSW and FIFO/status | `scripts/probe_wlan_packed.py` | Opt-in, no real timing, only modeled controller subset |
| A7 eDMA | Paired DMA1 TX/RX TCD with DMAMUX sources 26/25, DONE, INT and W1C | `scripts/probe_winc1510_dma.py` | Descriptor constraints, major/scatter chains, IRQ details need original OS validation |
| Python bridge | Localhost TCP `EXESX_WINC1510_TCP_PORT`; PCS/BEGIN/END/MOSI -> MISO | `scripts/probe_winc1510_tcp.py` | Socket exchanges are synchronous and no independent IRQ event path is exposed |
| WINC SPI commands | `scripts/winc1510_spi_backend.py`: `C1/C2/C3/C4/C7/C8/C9/CA/C5/C6/CF`, optional CRC, chip ID and register data | `tests/test_winc1510_spi_backend.py` | Only observed/documented subset |
| WINC flash | Optional owner-private `--flash`, up to 1 MiB; read-mapped image | Python tests and range guards | No APS3S CPU execution, flash program/erase lifecycle incomplete |
| HIF mailbox | Registers `1070/1078/1084/108c/106c/150400`, HIF request DMA parser | Python HIF mailbox test | Requests are **recorded**, not automatically fulfilled |
| Manual device callback | `queue_hif_callback(group,opcode,payload)` makes device RAM/status available to host polling | Python callback test | No physical IRQ_N GPIO assertion/wakeup, association engine or configured fixture |
| Factory USB messages | `scripts/decode_dy357_factory_wifi.py` read-only six-byte parser | `tests/test_decode_dy357_factory_wifi.py` | Does not create a USB controller or feed original device endpoints |

Latest complete baseline before this document: both Linux/Windows CI green at `2ad2c82`. Subsequent DMA channel-order correction is pending full CI check.

## Exact TODO before an original WLAN CHECK 'OK' screenshot

1. Run unchanged original OSUP with `EXESX_EXPERIMENTAL_LPSPI2_FIFO=1`, `EXESX_EXPERIMENTAL_LPSPI2_DMA=1`, `EXESX_WINC1510_TCP_PORT=...`, and original M4 boot/menu contacts. Collect read-only SPI and A7 WLAN traces. Check that the firmware sees the WINC chip ID and finishes the complete ROM initialization sequence. A synthetic chip-ID test is insufficient.
2. Compare original guest's selected PCS, packed TX/RX DMA descriptors, bit/byte ordering, `DER`, FIFO flags and eDMA1 interrupt group with the current model. The DMA descriptor discovery has just been corrected to allow RX-channel numbers below TX-channel numbers. Verify real firmware works and add that ordering to real-ARM regression coverage.
3. Implement WINC device IRQ_N / RESET_N / WAKE / CHIP_EN as QEMU GPIO lines. Python device notifications must be delivered **through those lines**; not by writing original SRAM, RTOS flags or A7 queues.
4. Implement genuine HIF firmware command processing for WINC initialization and firmware/MAC/version queries. Use the original request opcodes as the contract. Preserve error and timeout responses when unconfigured.
5. Add a **deterministic, explicitly configured test AP fixture** for connect/disconnect, SSID/channel, RSSI and DHCP. Only signal an association callback after a modeled state transition; do not return a universal success byte.
6. Add socket command handling and optional host TCP backend with isolation and negative controls for unavailable peers, refused sockets and timeouts.
7. Verify each original WLAN CHECK submenu's result with read-only original LCD screenshots: init/communication, firmware version, MAC, RSSI/AP, power-save and socket tests. Record exact original A7 result branch when available. **No screenshot named OK unless original framebuffer visibly says OK.**
8. Verify absent-card, wrong-PCSes, backend-disconnected, no-AP and missing-network-peer negatives.

**Current original WLAN CHECK screenshots:** no authentic `OK` captured. The prior original WLAN AUTO TEST heading screenshot confirms only menu entry, not success. A passing chip-ID/DMA synthetic QEMU probe is not a factory result.

## Why USB is a separate next phase

The original row-8 `WIFI AUTO TEST` opens a USB-style fixture link and waits for a six-byte command header (commands 1-6), while the WLAN CHECK submenu speaks directly through SPI/HIF. Therefore **the WINC simulator is not yet complete**, and there are still WLAN tasks before moving solely to USB.

A future rapidly iterable USB design can use the same pattern:

```text
Original guest USB controller + USBPHY/cable GPIO
    -> QEMU modeled enumeration/endpoint FIFO/IRQ/DMA
    -> localhost TCP socket (length-delimited endpoint packets)
    -> Python external test fixture (factory commands 1..6)
```

The Python fixture can be written and tested without recompiling QEMU for every reply change, **once** the one-time device-controller socket bridge is installed. Until the USB controller produces genuine guest enumeration and endpoint interrupts, a stand-alone Python socket server is not sufficient for the original test.

Original USB clues: GPIOB.PDIR bit19 `0x4100f050`; USBPHY register `0x40350808`; OTG `0x40330000`; USB misc `0x40330200`; native link state `0x625ee030`. The read-only frame decoder in `scripts/decode_dy357_factory_wifi.py` is reusable by a future Python USB fixture.

## Privacy/evidence controls

Keep original OSUP, media, private Wi-Fi flash image, MAC/SSID/credentials, runtime traces and screenshots local. Synthetic test images do not prove guest OK. Preserve `tcg,thread=single` and snapshot-protected media.
