# DY357 WLAN: firmware entry points, candidate device, and pass criteria

This is an **in-progress hardware investigation**, not proof that the original WLAN test passes.

**Owner-confirmed card identity:** DY357 uses the same Microchip ATWINC1510 as DY890. The original DY357 A7 WLAN driver's accesses to LPSPI2 are independently confirmed by the supplied decompilation; individual board PCS/IRQ/RESET pins still need tracing.

**New detailed source analysis:** [WLAN reply/USB fixture contract](WLAN_PROTOCOL_AND_USB_FIXTURE.md). This identifies original factory USB commands 1–6, separate WLAN HIF callbacks, real 32-bit packed LPSPI2 and DMA requirements, and the potential `\\data0\\sys_bin\\ota.bin` update image.


## What the original owner A7 code actually calls

From the owner-local `XD-SX9850.0.c` decompilation (the proprietary file is **not** committed):

| Original A7 routine | What it does |
|---|---|
| `FUN_60059404` | TEST MENU row 8, prints `##### WIFI AUTO TEST #####`; calls the communication setup and loops until completion/error |
| `FUN_600597A0` | Calls `FUN_601770D8`, `FUN_60177124(1)`, `FUN_60177130(30000)` |
| `FUN_60059808` | Polls a communication event, checks the external connection, reads a 6-byte header; error strings include `TIMEOUT!` and `CHACK USB CABLE!` |
| `FUN_60177130` | Calls `FUN_60077848` (communication-open path), which waits for a connection and can return timeout/connection errors |
| `FUN_60068DDC` | Separate WLAN CHECK MENU: COMMUNICATION, BATTERY LIFE, POWER SAVE MODE, FIRMWARE, MAC ADDRESS |
| `FUN_601CDD80` | Wi-Fi RSSI submenu: calls `FUN_601CFB14` and the original AP connection/readout routines |
| `FUN_601CFB14` | General WLAN service initialization path, not the direct factory AUTO routine |
| `Task_WLAN_WlanTask` | Native WLAN task; the OS also creates `Task_WiFiSocketTask` |

**Important:** the factory `WIFI AUTO TEST` has an external communication/cable dependency in addition to any Wi-Fi chip. A successful SPI chip-ID or synthetic packet is not the same test.

## Additional original LPSPI2 source fingerprint

The owner's original A7 decompilation includes `FUN_1FFEA5E4`, a bootloader function which checks `s_lpspiHandle[2]` and calls `FUN_1FFEA5A8(0x40290000, handle)`. Its retained NXP SDK assert string names `fsl_lpspi.c`. This **does ground LPSPI2 as a real programmed controller** in this ROM family; it **does not** show that the WLAN task attaches to this bus or which chip select is wired to the radio. We still need guest execution and MMIO reads/writes while original WLAN CHECK runs.

## What is known about the candidate module

The user confirms the same **ATWINC1510** module family is used by **DY357 and DY890**. Physical CS/IRQ/RESET routing still needs measurement. The original WLAN software directly programs LPSPI2 at `0x40290000`. Neither an A7-to-LPSPI2 bus address nor CS/IRQ/RESET wiring for DY357 has been observed yet.

Official Microchip WINC15x0 documentation:

- [ATWINC1510 product and datasheet](https://www.microchip.com/en-us/product/ATwinc1510)
- [Microchip host interface](https://developerhelp.microchip.com/xwiki/bin/view/products/wireless-connectivity/Embedded-Wi-Fi/winc1500-overview/)
- [WINC15x0 SPI slave interface](https://onlinedocs.microchip.com/oxy/GUID-9BEF11ED-F448-4EB7-8CC1-E0B7C40FDE76-en-US-1/GUID-2FABC4E6-33A0-4AF5-8B8C-3BDA9BE601AB.html)
- [WINC command/response protocol](https://onlinedocs.microchip.com/oxy/GUID-440F7CB9-F849-446D-A9AB-3749711C7849-en-US-5/GUID-A4231B36-9E09-46A3-9301-6E950FDDDEC3.html)

The candidate is 2.4 GHz 802.11 b/g/n; signals are SPI_SSN, MOSI, MISO, SCK plus IRQ_N, RESET_N, WAKE, CHIP_EN. SPI instructions include internal register read/write (`0xC4/0xC3`), single-word read/write (`0xCA/0xC9`), DMA read/write (`0xC2/0xC1`) and extended DMA (`0xC8/0xC7`). The response contains a command-copy nibble and error/status byte. Authentication, firmware/HIF messages, network sockets and 802.11 radio behavior are separate layers.

## Work on this branch

1. Add opt-in `EXESX_EXPERIMENTAL_LPSPI2_FIFO=1` for the actual LPSPI2 host MMIO offsets at `0x40290000`. PIO register semantics, W1C flags, RX watermark, FIFO empty and reset are modeled for 8-bit frames. Default CR-only mode is unchanged. There is **no WINC card attached** yet.
2. Add `EXESX_DIAGNOSTIC_LPSPI2_LOOPBACK=1` only for a **negative/synthetic device-control**. A real 8-bit ARM guest checks it. Without it, the disconnected MISO returns the pulled-up byte `0xFF`; this is an electrical simplification, not a silicon reply.
3. Add opt-in original guest trace `EXESX_TRACE_WLAN_A7=1` in the factory GUI worker to watch the authentic WLAN auto and service entry paths without injecting data or altering A7/M4 registers.
4. Keep private original firmware and MMIO logs local.

## Current opt-in QEMU and Python transport (2026-10-29)

The following code is now committed on this **draft** branch:

- Native LPSPI2 PIO packed 32-bit words and the high-lane terminal partial word, original `PCS2` chip select and `TCR.BYSW` byte swapping on **both** TX and RX, FIFO status, reset and no-slave controls. `EXESX_EXPERIMENTAL_LPSPI2_FIFO=1`.
- Bounded paired eDMA1 linear RAM-to-`TDR` and `RDR`-to-RAM transfers, real TCD `DONE`/interrupt only on actual transfer and GIC grouped IRQ W1C. `EXESX_EXPERIMENTAL_LPSPI2_DMA=1`.
- Localhost TCP SPI bridge, with original QEMU-determined `PCS` and byte stream. `EXESX_WINC1510_TCP_PORT=<port>`.
- `scripts/winc1510_spi_backend.py` models SPI chip ID, selected WINC internal registers, command response/acknowledgements, DMA-accessible memory, optional private 1MiB flash image and chip-select boundaries. `--hif-mailbox` additionally implements the original outbound buffer request (`0x1078`/`0x150400`) and guest-originated HIF request parsing (`0x106c`), plus callback-ready buffer registers (`0x1084`/`0x1070`). It **does not synthesize successful AP association or sockets**.
- The published Microchip `nmspi.c` byte ordering is used: command addresses travel in big-endian order, but the four register *data* bytes are little-endian. The initial synthetic model had this wrong; the branch now tests the corrected MISO behavior using the **original firmware's** BYSW-enabled TCR and little-endian TDR values.
- Public real-ARM hardware tests: `scripts/probe_wlan_lpspi.py`, `scripts/probe_wlan_packed.py`, `scripts/probe_winc1510_tcp.py`, and `scripts/probe_winc1510_dma.py`; Python HIF mailbox fixtures in `tests/test_winc1510_spi_backend.py`.

Example of the separate localhost process:

```sh
python3 scripts/winc1510_spi_backend.py --port 50991 --hif-mailbox
```

In the QEMU environment, set `EXESX_EXPERIMENTAL_LPSPI2_FIFO=1`, `EXESX_EXPERIMENTAL_LPSPI2_DMA=1`, and `EXESX_WINC1510_TCP_PORT=50991` **before launching QEMU**. Use `-accel tcg,thread=single` and your private ROM/media. The server never connects to an AP or Internet automatically. A broken/missing server must not be interpreted as a chip reply.

**Still missing before original WLAN OK:** source-derived actual WINC IRQ_N and RESET/WAKE GPIO routing; WINC firmware/HIF operation and asynchronous response scheduling; original A7 **scatter/gather eDMA1 TCD chains** (FUN_601c2740 queues multiple descriptors and may reprogram TCR between 512-byte blocks); Wi-Fi association, DHCP, sockets; and the **separate** USB factory test fixture described in [WLAN_PROTOCOL_AND_USB_FIXTURE.md](WLAN_PROTOCOL_AND_USB_FIXTURE.md). Linear synthetic DMA passing does not establish real large-transfer completion or genuine WLAN menus.

## Original-ROM single-threaded factory WLAN test (local negative control)

A new bounded original-OSUP run on the owner-private emulator, with `-accel tcg,thread=single` and source-derived eMMC plus a disposable SD card both opened snapshot-protected, reached the authentic factory menu and sent only M4 physical key contacts:

- The A7 accepted the `0x93,0x93,0x94` entry sequence at original PC `0x60010930`; `0x400B(2)` returned and the authentic menu painter executed.
- Real physical DOWN navigation visibly selected row 8, **WLAN AUTO TEST**, with the full-width inverse bar.
- Real physical ENTER opened the original heading `##### WIFI AUTO TEST #####` in the genuine LCD. A read-only 864x480 pixel screenshot was captured locally.
- During the bounded observation, the screen had the heading only. **No original OK, Wi-Fi association, WLAN firmware reply, link status, MAC query, or passing factory result** was observed.
- The native QEMU build used for this run predates the new LPSPI2 PIO code; the comparison is a **baseline**, not a claim that the new opt-in SPI host already fixes WLAN. The private screenshot and runtime logs remain outside Git.

This confirms real guest dispatch to the factory test and provides a negative baseline for future original-OSUP experiments. It does **not** establish DY357 radio wiring or an external USB fixture.

## Required evidence before calling the original WLAN test PASS

- Confirm whether DY357 actually uses ATWINC1510, and trace which original guest SPI controller, chip select, IRQ and reset GPIO it touches. Do not infer DY357 wiring from the different DY890 photograph.
- Decode real original guest command bytes. Only then attach a WINC slave to the observed bus and implement its register/DMA/HIF/interrupt protocol, including tested error paths.
- Establish the expected external fixture/cable and AP/SSID behavior of `FUN_60059404` versus separate RSSI/association checks. A simulated card-ID response is insufficient.
- Run QEMU `tcg,thread=single` with unchanged OSUP. Drive the real menu with M4 physical keys. Observe a genuine original WLAN result handler and visible `OK` on the original LCD, capture the screenshot read-only and confirm negative-control failure without the card.
- Do not forge WLAN packets, AP authentication, RSSI, MAC address, IPC events, SRAM flags or factory verdict to force success.

**Current end-to-end WLAN factory verdict: NOT VERIFIED.**
