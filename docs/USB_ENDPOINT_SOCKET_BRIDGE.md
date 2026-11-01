# DY357 USB ChipIdea endpoint socket bridge

The first hardware USB-device/socket bridge is implemented on the WLAN experiment branch. It is explicitly opt-in and does **not** yet prove the original Casio USB or WLAN tests passed.

## Implemented

The native i.MX7ULP ChipIdea controller is mapped at 0x40330000 (size 0x200), with GIC SPI 40. It implements core device registers: USBCMD (0x140), USBSTS (0x144), USBINTR (0x148), DEVICEADDR (0x154), ENDPTLISTADDR (0x158), PORTSC (0x184), USBMODE (0x1a4), ENDPTSETUPSTAT (0x1a8), ENDPTPRIME (0x1b0), ENDPTFLUSH (0x1b4), ENDPTSTATUS (0x1b8), ENDPTCOMPLETE (0x1bc), ENDPTCTRL0..7 (0x1c0..0x1dc).

A Python external USB host connects to a localhost socket. SETUP packets populate the original firmware's endpoint-0 queue-head SETUP area (+0x28); OUT and IN use original guest-programmed queue heads, active transfer descriptors and physical buffer pointers. Completion updates dTD residual length, USBSTS, ENDPTCOMPLETE and GIC SPI40 through USBINTR. Unprimed or stalled endpoints report NAK/STALL without writing guest RAM. The initial implementation supports 0..7 endpoints and bounded single-buffer transfers (up to 4096 bytes); not chained or multi-page dTD operation.

The model is disabled unless environment variable EXESX_EXPERIMENTAL_USB_ENDPOINTS=1. The original firmware and snapshot-protected storage stay unchanged.

## Start the Python host

Start QEMU with EXESX_EXPERIMENTAL_USB_ENDPOINTS=1 and EXESX_USB_FIXTURE_TCP_PORT=19316. Use the repository's updated imx7ulp-early-boot.ini, with tcg,thread=single. QEMU listens only on 127.0.0.1.

Then, in another terminal:

    python3 scripts/usb_endpoint_host.py --port 19316

The Python code asks the guest for actual USB descriptors, performs SET_ADDRESS and SET_CONFIGURATION, and discovers bulk IN/OUT endpoints. It does not manufacture USB descriptors. Only after real enumeration and a functioning WINC backend, use --factory-hello or --full-plan to drive the original six-byte Casio WIFI AUTO TEST fixture protocol.

Socket request: [op:u8, endpoint:u8, length:u16le, payload when applicable].
Socket reply: [status:u8, endpoint:u8, length:u16le, data for IN].
Operations: 1 SETUP(8 bytes), 2 OUT, 3 IN(requested length), 4 ATTACH, 5 DETACH, 6 BUS_RESET. Status: 0 ACK, 1 NAK, 2 STALL, 3 unsupported. Host retries NAK only within a finite timeout. No original A7 PC, SRAM, IPC or factory verdict is altered by the bridge.

## Evidence

Linux CI https://github.com/TheRainbowPhoenix/EXeSX/actions/runs/40900145277 **passed** the native real-ARM script scripts/probe_usb_endpoint_bridge.py. That verifies the guest's original ChipIdea register programming, an externally supplied EP0 SETUP reaching queue-head RAM, an EP1 OUT transaction reaching its original dTD buffer, USBSTS.UI and ENDPTCOMPLETE, plus a negative unprimed-IN test. Windows CI https://github.com/TheRainbowPhoenix/EXeSX/actions/runs/40900145291 **passed** its build and synthetic unit tests.

Neither CI run uses the owner's private ROM, so neither proves original Casio WLAN OK. No readable original WLAN OK screenshot is yet available.

## Remaining USB/WLAN TODO

The original ROM requires additional USBPHY PLL/cable-detect behavior at 0x40350000, correct physical GPIOB bit19 sensing, genuine USB device enumeration and complete endpoint/DMA semantics. Its factory WIFI AUTO TEST waits for an external USB host to send six-byte command headers. The other WLAN CHECK menus need WINC SPI/HIF firmware replies, IRQ timing, deterministic AP association, RSSI/DHCP/MAC and socket handling. A Python USB host cannot make those original tests pass without the missing emulator behavior.

## Owner firmware and regression privacy

TheRainbowPhoenix/EXeXS_test is **public**. XOR with a published passphrase such as EXeXSess does not encrypt OSUP.BIN; it would expose the original firmware to anybody with the passphrase. No owner ROM or media was added to that release. Existing scripts/ci_private_osup_regression.py uses a privately authenticated HTTPS fixture with a required SHA256 and optional bearer secret for maintainer-only workflow_dispatch, while public PRs use the synthetic tests. Original LCD captures and guest logs remain private unless the owner explicitly chooses to share them.

References: NXP i.MX7ULP USBOTG1 node (GIC SPI40), Linux ChipIdea core.c register map, owner-local A7 decompilation.
