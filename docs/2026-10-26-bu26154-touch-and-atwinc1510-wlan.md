# 2026-10-26 — ROHM BU26154 touch prototype and ATWINC1510 WLAN investigation

## Source-backed board evidence (do not conflate DY890 and DY357)

The photographed `PWB-DY890-1` board contains ROHM `BU26154` (audio codec plus four-wire resistive-touch ADC) and Microchip `ATWINC1510-MR210PB` (SPI Wi-Fi coprocessor). The original private OSUP fingerprint is DY357, which has **not** been electrically proven to use the identical motherboard/pin routing. The photo, module MAC/serial, user ROM, private disk images and traces must remain outside the public repository.

- ROHM: https://www.rohm.com/products/audio-video/audio-converters/audio-codecs/bu26154muv-product
- ROHM datasheet register/protocol text: https://htmlapp.alldatasheet.com/html-pdf/873342/ROHM/BU26154MUV/2199/21/BU26154MUV.html (I2C two-wire), /7344/70/ (TCHCTRL), /7449/71/ (ADCR1/2).
- Microchip: https://developerhelp.microchip.com/xwiki/bin/view/products/wireless-connectivity/Embedded-Wi-Fi/winc1500-overview/
- ATWINC15x0 SPI host interface: https://onlinedocs.microchip.com/oxy/GUID-9BEF11ED-F448-4EB7-8CC1-E0B7C40FDE76-en-US-1/GUID-2FABC4E6-33A0-4AF5-8B8C-3BDA9BE601AB.html

## Opt-in touch peripheral (M4 LPI2C controller)

`hw/arm/exesx-imx7ulp-lpi2c.inc` adds **ROHM BU26154-specific** two-wire transactions, NOT a `0x4B` maXTouch surrogate. Default is **absent/no ACK**. Opt in with `EXESX_BU26154_LPI2C_BUS=0`, `1`, `2` or `3`, corresponding to M4 LPI2C0..3; this is a wiring *hypothesis* the researcher must choose, not an established DY357 bus. The documented ROHM 7-bit I2C address is **0x1A** (8-bit bus address `0x34/0x35`). A write of one 8-bit register pointer and repeated-start read is supported; sequential registers increment by **two**.

Implemented touch subset:
- Touch control read at `0x60`, write at `0x61`; reset value `0x78` with TCHEN disabled.
- Read X/Y **12-bit ADC** upper 8 bits from `0x62`, lower four bits from `0x64`, only after real guest enables TCHEN and selects X/Y conversion mode in bits 5:4.
- Optional raw electrode host input file via `EXESX_BU26154_TOUCH_FILE=/private/raw-touch.txt`; ASCII `down x y`, e.g. `1 291 2748` for a contact, `0 291 2748` for release. X/Y are **raw 0..4095 ADC samples**, not 864x480 LCD pixels or guessed touchscreen calibration. Default missing file yields disconnected ADC zero. Read from guest virtual MMIO/I2C, not write guest memory or fake IPC.
- Unsupported codec/pressure registers warn via `LOG_UNIMP`; no audio codec output, touch analog settling, pen IRQ, interrupt GPIO, timer, resistance/pressure measurement or factory-test pass is invented. All guest-visible state lives in existing VMState-backed register storage.

The firmware-free ARM regression `scripts/probe_bu26154_touch.py` checks: no-device NACK, explicit port binding, disconnected/released zero, complete X/Y ADC split, disable behavior, and unrelated I2C `0x4B` still NACK. Linux and Windows CI run it with the real emulator. **A passing synthetic probe cannot demonstrate that the original DY357 factory touchscreen test has passed.**

## WLAN identification and next required host-controller work

The photographed ATWINC1510 supports 2.4 GHz 802.11b/g/n with **SPI_SSN, MOSI, MISO, SCK, IRQ_N, RESET_N, WAKE, CHIP_EN**. Its controller protocol has nontrivial register transactions/DMA FIFOs/interrupts: even a correct ID response cannot substitute for real SPI transfer completion and firmware/network-stack semantics. The existing EXeSX `LPSPI2` (`0x40290000`) model only handles `CR+0x10` startup, **not** TDR/RDR transfers, CLK/CS, FIFO, IRQ, SDIO or WLAN firmware.

The successful original factory-menu sweep reached `WIFI AUTO TEST` but produced **no result** in a 12-second bounded run. That *does not prove* LPSPI2 is the actual host; check the original A7 trace for LPSPI controller instance/CS and GPIO toggles in this exact test, then add ATWINC15x0 as a separate SPI slave with actual transaction framing. Do not claim Wi-Fi authentication, scan or RF support simply by returning success bytes. Firmware strings alone are not proof of bus wiring.

## Safety and status

No touch or Wi-Fi chip responses are enabled by default on DY357. Do not upload photos, MAC addresses, private OSUP, extracted A7/M4 binary, original screenshots or execution traces to the public repository. Preserve observed factory `NG` touch outcomes rather than fabricating a pass. This initial change is an opt-in, hardware-specific **digital-subset implementation** with synthetic tests; complete original firmware integration and WLAN behavior remain outstanding.

## Real unchanged DY357 original OSUP: negative E2 touch differential

After the native Linux QEMU compiled the new BU26154 model, the owner-derived unchanged original A7/M4 firmware was cold-booted twice with `EXESX_BU26154_LPI2C_BUS=2`, the explicit synthetic ADC source `0x1230/0x4560`, and eMMC+disposable SD both `snapshot=on`. The real `0x9C+0x90` chord and `0x93,0x93,0x94` accepted guest keyboard contacts led to original `0x400B` return and factory-menu painter. Genuine DOWN navigation with LCD-highlight verification selected **row 13 E2 PATTERN CHECK**, then original ENTER. Host QMP framebuffer sampling was disabled until the real painter executed; no guest RAM/IPC writes or forced jumps.

- **No-contact control:** `EXESX_BU26154_TOUCH_FILE` contained `0 2048 2048`. The original factory E2 touch cross displayed. No complete touch interaction was observed.
- **Contact differential:** a separate fresh cold boot with the raw file `1 2048 2048`, remaining pressed through E2 entry, displayed the real factory `NG` / `Retry 'TOUCH PANEL CROSS TEST'` failure. This is a **negative integration test** of the candidate bus and unscheduled touch ADC: the factory test does **not** pass by supplying an arbitrary BU26154 register sample.
- Both were authentic guest execution and LCD captures from native QEMU, but **did not trace an original guest transaction to the opt-in address 0x1A**. They do not demonstrate whether DY357 uses BU26154, what bus is wired, whether the touch ADC is enabled, or which GPIO/interrupt indicates pen state. Missing physical pen IRQ/analog timing remain explicit.

The original private screenshots, OSUP, traces, raw touch inputs and virtual media are *not* published. Avoid manufacturing touch hits or overriding the negative NG outcome. Next decisive experiment: record STOP-aware I2C or SPI accesses and original firmware touch subroutine PC during the E2 target, correlate any address 0x1A traffic and pen IRQ. Only then wire the correct input path and test actual per-target touch coordinates (not an always-pressed static center sample).

## WLAN logging addition

`hw/arm/exesx-imx7ulp-lpspi.inc` now emits a `LOG_UNIMP` warning when LPSPI2 CR.MEN is newly enabled: register enable alone has **no SPI clock, TX/RX FIFO, chip-select, or IRQ engine**, and there is no verified ATWINC attachment. Existing strict unsupported register accesses still bus-fault. This diagnostic must **not** be interpreted as evidence that the pictured ATWINC1510 is on LPSPI2.

## Original WLAN AUTO TEST, post-menu MMIO diagnostics

A separate unchanged-OSUP cold-boot run (private), using the actual row-gated chord and visually verified menu row **8**, reached original factory-menu painter and entered **WIFI AUTO TEST**. The LCD showed its heading but no completion/result during a 13-second bounded observation. **This does not establish a passing WLAN test.**

To avoid boot timing distortion, the host QMP debugger enabled only `exec,unimp` logging **after** the original menu painter was observed. The focused log captured repeated genuine DMA1 framebuffer memory-to-memory copies but **no new LPSPI/ATWINC unsupported-MMIO warning** in that run. That negative trace is *not* proof that the ATWINC chip or a different SPI controller is inactive: it does not identify a WLAN command caller, mapped bus, or GPIO transaction. Next, add targeted A7/M4 driver call tracing and actual SPI/CS/MISO observation in a post-menu snapshot before choosing a WLAN host controller.

Original WLAN LCD screenshot, guest log, raw firmware and storage remain local.
