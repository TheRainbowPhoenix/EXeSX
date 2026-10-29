# WINC1510 GPIO bridge, USB host stub, and private original-ROM CI

## Implemented on experiment/dy357-wlan-host-20261029

The existing SPI host packed TCR/TDR, PCS2 and paired TX/RX eDMA path are preserved.

**GPIO bridge, opt-in and board-pin-agnostic:**

- Run the Python card: `python3 scripts/winc1510_spi_backend.py --port 19315 --hif-mailbox --gpio-status`.
- QEMU environment: `EXESX_EXPERIMENTAL_LPSPI2_FIFO=1`, `EXESX_EXPERIMENTAL_LPSPI2_DMA=1`, `EXESX_WINC1510_TCP_PORT=19315`, `EXESX_WINC1510_GPIO_PROTOCOL=1`.
- The original guest's **GPIOB PDOR and PDDR** can drive RESET_N, WAKE_N, CHIP_EN. Choose actual bit positions with `EXESX_WINC_RESET_GPIOB_PIN=N`, `EXESX_WINC_WAKE_GPIOB_PIN=N` and `EXESX_WINC_ENABLE_GPIOB_PIN=N`. A GPIO pin configured as input does not act as a fake output; unconfigured lines use safe defaults.
- `EXESX_WINC_IRQ_GPIOB_PIN=N` maps the Python card's **active-low IRQ_N** onto an actual original M4 GPIOB input pin. The original M4 PORTB/PCR interrupt logic handles edges as normally; QEMU does **not** insert any A7 event or IPC.
- A zero-clock socket status request `[0xff,0x20,0,0]` polls IRQ_N between actual SPI transfers. No CS assertion, SPI clocks, guest instruction pointer, RAM or interrupt flag is invented by this poll.
- Python resets volatile registers/HIF requests on actual RESET_N assertion or disabled CHIP_EN but retains an optional private flash. WAKE_N is carried as a level; an arbitrary WAKE toggle does not mean Wi-Fi association.
- This is a **limited GPIO electrical model** until DY357 actual WINC IRQ/RESET/WAKE GPIO pin locations have been confirmed in an original A7/M4 trace. Never guess pin numbers to make the factory menu pass.
- Original HIF callbacks still require a real command-specific device response and AP/network fixture. The Python model does not yet emulate full firmware/association/DHCP/sockets.

**Socket protocol:**

Legacy mode: request `[pcs:u8, BEGIN|END:u8, n:u16le, MOSI[n]]`, response `MISO[n]`.

When `EXESX_WINC1510_GPIO_PROTOCOL=1` and Python `--gpio-status` are both enabled, request flag bits 2/3/4 carry RESET_N/WAKE_N/CHIP_EN as *electrical levels*; response is `MISO[n] + IRQ_N_level:u8` (1 high, 0 asserted low). A special zero-clock request `FF 20 00 00` returns only IRQ_N without changing PCS. All commands use loopback TCP with explicit opt-in. Old socket protocol and default emulator behavior remain unchanged.

## First USB host fixture

`scripts/usb_factory_host.py` is a stand-alone Python *external host/fixture*, **not** a USB-device-controller replacement. With a future QEMU original USB endpoint/byte-stream socket at localhost port 19316:

```sh
python3 scripts/usb_factory_host.py --port 19316
# Once original USB gadget enumeration and the WLAN HIF work:
python3 scripts/usb_factory_host.py --port 19316 --full-plan --report private/usb-fixture.json
```

It sends original factory command `FF FF 01 00 06 00`, reads the original response and rejects errors. The full plan requests firmware WLAN initialization (command 3 subcommand 1), MAC query (command 4 subcommand 2), and sends exit (command 2) **only after successful replies**. It does not generate HIF callbacks or overwrite the original firmware result array.

**USB QEMU core bridge is not yet implemented.** The original's USB OTG controller at `0x40330000`, USBPHY at `0x40350000`, GPIOB cable sense bit 19 and endpoint interrupts need a real USB model/bridge before this host can communicate. A TCP server alone is not proof of working USB enumeration.

## CI with private original OSUP

`TheRainbowPhoenix/EXeXS_test` is **PUBLIC** and its `Test` release was empty when checked. The original `OSUP.BIN`, proprietary ELF, real-media extents and any private flash dump must **not** be uploaded there.

The original boot regression is opt-in only via maintainer-initiated GitHub Actions `workflow_dispatch`. Set GitHub Actions secrets in EXeSX:

- `EXESX_PRIVATE_OSUP_URL`: HTTPS URL to owner-controlled, **access-restricted** original OSUP.BIN; do not use a public download/release.
- `EXESX_PRIVATE_OSUP_SHA256`: exact owner firmware digest `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`.
- `EXESX_PRIVATE_ASSET_TOKEN`: optional read-only bearer token for the private URL.

The CI script `scripts/ci_private_osup_regression.py` verifies bytes and digest before boot, starts the existing safe original TEST MENU/physical-DOWN runner in **single-thread TCG**, checks the original painter plus genuine LCD selection change, then deletes the private workdir. Any missing secrets cause a **SKIP**, not a fabricated PASS. This check is *not* enabled automatically on public PRs; doing so with owner-private firmware would risk leaking it to untrusted code.

A private user-download ZIP named `EXeSX_owner_private_original_ROM_fixture_20261029.zip` can be built locally containing only user-provided OSUP/ELF/source-derived extents and reconstruction script. It is not a GitHub release asset.

## Proof status

**Passing:** firmware-free WINC Python electrical/socket unit tests and previous real ARM packed SPI / DMA / chip-ID probes (see CI). Pending updated CI results are separate.

**Not proven:** original WLAN initialization/association/MAC/RSSI/firmware/screens, USB controller enumeration/endpoint traffic, any original WLAN `OK` screenshots. Only claim success when actual original A7 code and readable LCD show it.
