# EXeSX October 20 handover: supplied SX9850 artifacts and I²C next step

**Status:** A7 and M4 execute real locally supplied firmware; there is **no verified OS boot, text, LCD framebuffer, or guest-generated screenshot**. `docs/STATUS.md` predates the actual M4/ADC investigation; prefer `docs/ALL_IMPORTANT_KNOWLEDGE.txt` and `docs/2026-10-20-m4-i2c-adc-boot.md` for current measured progress.

## Attached materials checked (private, never committed)

- `OSUP(1).BIN`: **30,670,850 bytes**, SHA256 `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`. The independent attached `extract_roms(1).py` validates its container and component checksums. Internal model `DY357`, ARMv7-A little-endian.
- Validated BIOS payload: `0x60000000`, **2,447,360 bytes**, SHA256 `eb7dafa1b544bbb8d79081866af280e6c0f88197de9f635c6887f8486155da66`.
- Validated OS payload: `0x60400000`, **8,923,136 bytes**, SHA256 `f7a34a4a604691eb4de44b9c9e586a91c410b7caee844f9d32740927948775ea`. The OS's entry trampoline points to `0x605E3AD0`; this is a **static code address**, not evidence that QEMU booted the OS.
- The embedded M4 code recorded by the supplied `XD-SX-notes` is BIOS source `0x600AD6A0` for `0x14F70` bytes. Independently checked first vector words at the corresponding offset: MSP `0x20001C00`, Thumb reset `0x1FFE19E5`; resulting local copied-region SHA256 `25f95e3a5cfe2a898b2110d874075e6da5b288c706c03bc5a051a1f8c8e54fb0`. The A7 copy/release routine is labeled `0x60178608` in the notes.
- `XD-SX-notes(3).zip`: twelve address-anchored research Markdown notes on boot, M4, RTOS, display gaps, memory and update paths. These are **static research notes**, not boot/test logs.
- `exword-sx-analysis-kit(2).zip`: Ghidra scripts, annotations, types, BSim signatures, and reverse-engineering documentation. Useful for inspecting the private image; none of these reference files is needed to run the QEMU machine. Do not confuse Ghidra's recovered call graph with guest execution.
- `extract_roms(1).py` is an alternative, more expansive Ghidra/ELF extraction workflow that expects a `captures/all-models/results.json` download manifest. The repository's existing `scripts/prepare_osup.py` already accepts a **direct** OSUP filename and is the supported local QEMU path. Do not introduce a second required ROM extraction path.

The proprietary OSUP, extracted A7/M4 images, Ghidra memory captures and VM snapshots must **not** be added to the public GitHub repository or Actions artifacts.

## Where execution stops

`EXESX_EXPERIMENTAL_M4_BOOT=1` starts the real M4 image in QEMU using the A7 handoff. The M4 issues LPI2C2 `MTDR` commands at controller `0x41035000`: `0x0496` (SLA+write `0x4B`), data `0x14`, `0x62`, then `0x0497` (SLA+read `0x4B`). The two data bytes **may** form register pointer `0x6214` (little-endian). The unknown, unmodeled external slave is correctly NACKed.

The `EXESX_I2C4B_REPLY_HEX` environment variable is a controlled *artificial* response—not a touchscreen implementation. Earlier 00/FF differential experiments reached real M4 ADC0/ADC1 initialization and cleared the prior ADC0 Data Abort; the A7 then saw `0xEEEEEEEE` at shared `0x2F028000` and entered a diagnostic/error branch followed by a holding loop `0x60179A7C`. See the main handover for the tested QEMU build/run and confidence limits. **No value has yet shown a successful M4 initialization handshake.**

The 0x4B + two-byte pointer shape fits a *possible* Microchip maXTouch variant, but hardware identity is **unconfirmed**, especially because the apparent pointer is not the usual information-block address zero. Board marking, real I²C capture, or validation of an actual information block is required.

## Immediate reproducible next experiment

Build or obtain the trusted firmware-free native QEMU release per `scripts/recover_exesx.py`. From a checkout with the native build:

```sh
python3 scripts/prepare_osup.py "/private/path/OSUP(1).BIN" -o private/a7-firmware.elf

EXESX_EXPERIMENTAL_M4_BOOT=1 python3 scripts/run_firmware.py \
  private/a7-firmware.elf --qemu build/qemu-system-arm \
  --profile profiles/imx7ulp-early-boot.ini \
  --seconds 2 --results private/m4-i2c-4b

python3 scripts/analyze_lpi2c_trace.py \
  private/m4-i2c-4b/qemu-instructions.log

python3 scripts/i2c_boot_triage.py \
  private/m4-i2c-4b/qemu-instructions.log \
  --json private/m4-i2c-4b/i2c-intentions.json

python3 scripts/compare_i2c_boot.py private/a7-firmware.elf \
  --qemu build/qemu-system-arm --profile profiles/imx7ulp-early-boot.ini \
  --cases none,00,ff --seconds 0.8
```

`i2c_boot_triage.py` reports attempted repeated-START read pointers and *requested* RECEIVE_DATA byte counts, grouped by bus and 7-bit target. This is important because the prior log parser only counted raw commands. **An attempted receive length or pointer is not proof the bus got ACKed.** The next reverse-engineering step is to align these intentions and any NACKs with the M4 return/status checks; recover the required response framing/interrupt events, then add a bounded, verifiable device model. Distinguish the A7 `0xEEEEEEEE` error path from any genuine successful IPC response.

After a successful M4/A7 handoff, **separate milestones** remain: demonstrate the OS entry actually executing, RTOS scheduling, storage, an LCDIF framebuffer written by the *guest*, and finally rendering text or UI from guest pixels. A host overlay or static extracted Casio image is not a boot screenshot.

## Source basis

- Repository measured execution: `docs/2026-10-20-m4-i2c-adc-boot.md`, `docs/dual-core-lpi2c4b-and-recovery.md` and [issue #1](https://github.com/TheRainbowPhoenix/EXeSX/issues/1).
- User-provided private source artifact: checksum-validated `OSUP(1).BIN`, `extract_roms(1).py`, `XD-SX-notes(3).zip`, `exword-sx-analysis-kit(2).zip`. The ZIPs and binary are **not reproduced here**.
- Reference protocol research: [NXP PERI_LPI2C.h](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/periph/PERI_LPI2C.h) and [Microchip maXTouch I²C note](https://ww1.microchip.com/downloads/en/Appnotes/MXTAN0213_Interfacing_with_maXTouch_Touchscreen_Controllers_00002428A.pdf).
