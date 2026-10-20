# EXeSX dual-core boot — LPI2C2 `0x4B` blocker and recovery

Updated 2026-10-20. All firmware-derived information is from the user's own **locally supplied and executed** OSUP.BIN; none of the firmware, ELF, or RAM snapshots is committed to this public repo. Chip identifications are labeled separately from observation.

## Progress measured with real firmware (QEMU A7 + M4)

The firmware does now reach the dual-core M4 handoff through `SIM0_DGO_GP7`, with M4 reset `MSP=0x20001C00` and Thumb `PC=0x1FFE19E5`. QEMU's M4 executes copied private firmware, and the A7/M4 shared IPC word at physical `0x2F028000` becomes **`0xEEEEEEEE`** in the observed test. This was not created by a host-side override. It establishes that the old A7 semaphore/shared-memory handshake was surpassed.

The latest native build source commit used for this local trace was `205ff703be4403a6fd61e0913f365ab357cd6ae2` (before the diagnostic I2C changes).

- A7 PC when sampled: `0x60179A7C`. The disassembly confirms this is a literal self-loop `b 0x60179A7C` in the BIOS's idle routine, not a proven eForce μITRON scheduler.
- M4 PC when sampled: `0x1FFD4D18`. This is part of a 64-bit free-running clock sampling routine, with other loops used for delays. Being observed in a timer helper does not by itself mean the M4 has HardFaulted.
- M4 LPI2C2 base: `0x41035000`. Multiple `MTDR` starts address the same missing 7-bit I²C slave `0x4B`. The emulator deliberately NACKs it.

### Exact observed transaction

The first repeated MTDR command sequence logged by QEMU is:

| MTDR word | Interpretation |
|---|---|
| `0x0496` | START with SLA+W, 7-bit address `0x4B` |
| `0x0014` | TX data byte 0x14 |
| `0x0062` | TX data byte 0x62 |
| `0x0496` | retry START write (after missing-slave NACK) |
| `0x0014` | retry first pointer byte |
| `0x0497` | START with SLA+R, 7-bit address `0x4B` |

If bytes 0x14/0x62 represent a little-endian 16-bit register pointer, that is **0x6214**. The most recent log includes 1,014 MTDR words, with `0x0496` seen 338 times and `0x0497` seen 169 times. Those counts are for this bounded test, not the hardware's normal polling frequency.

**A plausible candidate:** Microchip maXTouch touchscreen controllers commonly accept 7-bit `0x4A` or `0x4B` and use a 16-bit little-endian address pointer. This is an unusually good *protocol-level* match to the sequence; it still does **not** prove the Casio XD-SX9850 contains a Microchip chip. The address and pointer layout are not unique. A maXTouch identity normally appears in its Information Block at register zero; this firmware starts by reading nonzero 0x6214. That limits confidence in a maXTouch identification.

## Primary public sources and authoritative definitions

- [NXP MCIMX7U5 PERI_LPI2C.h](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/periph/PERI_LPI2C.h): LPI2C register layout, MTDR command/data fields, NDF, RX FIFO flags and MRDR.
- [NXP MCIMX7U5_cm4_COMMON.h](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/MCIMX7U5/MCIMX7U5_cm4_COMMON.h): M4-domain LPI2C2 peripheral base at 0x41035000.
- [Microchip application note AN2428 (MXTAN0213), Interfacing with maXTouch Touchscreen Controllers](https://ww1.microchip.com/downloads/aemDocuments/documents/OTH/ApplicationNotes/ApplicationNotes/MXTAN0213_Interfacing_with_maXTouch_Touchscreen_Controllers_00002428A.pdf): section 3.1 gives addresses 0x4A/0x4B; section 3.2 specifies low-byte-first 16-bit register addressing; section 3.4 describes write-pointer then repeated-start read.
- [Microchip maXTouch product information](https://www.microchip.com/en-us/products/sensors-touch/maxtouch-touchscreen-controllers): family background, not Casio-specific board evidence.
- [NXP i.MX7ULP Linux device tree](https://github.com/nxp-imx/uboot-imx/blob/master/arch/arm/dts/imx7ulp.dtsi): reference memory/peripheral definitions. Board-specific touch wiring is not established.

These links are public documentation only; exact physical touch-controller vendor, part number and panel wiring remain **unconfirmed**.

## Reproduce from OSUP.BIN or OSUPD.bin after losing your machine/environment

Download the standalone repository script, then execute (Python 3.10+, Linux x86_64):

~~~sh
curl -fL https://raw.githubusercontent.com/TheRainbowPhoenix/EXeSX/main/scripts/recover_exesx.py -o recover_exesx.py
python3 recover_exesx.py /path/to/OSUPD.bin --workdir "$HOME/exesx-recovery" --seconds 3
~~~

The recovery script downloads the current `dev-native` release, checks SHA256SUMS, rejects unsafe archive entries, extracts your own update with the repository's strict checksum validator, and starts the real A7+M4 machine. The source ROM never leaves your host; file mode 0600 is used for the extracted ELF. Outputs are stored under `exesx-recovery/results/latest/`.

For a full source rebuild instead of a prebuilt Linux emulator: `python3 recover_exesx.py /path/to/OSUPD.bin --mode source`. This requires QEMU build dependencies, git, Meson/Ninja and network access. If you are inside a checked-out EXeSX repository and have already compiled QEMU, use `--mode local`.

## Controlled protocol research

By default the LPI2C bus has **no connected chip** and returns NACK. It never responds with invented identity bytes. For differential firmware experiments, the LPI2C2 model additionally supports *opt-in diagnostic* environment variable:

~~~sh
EXESX_I2C4B_REPLY_HEX=00000000 EXESX_EXPERIMENTAL_M4_BOOT=1 \
  python3 scripts/run_firmware.py private/a7-firmware.elf \
    --qemu build/qemu-system-arm --profile profiles/imx7ulp-early-boot.ini \
    --results private/lpi2c4b-probe --seconds 2
~~~

This synthetic one-address-only probe is **NOT** a maXTouch chip model. It accepts only 0x4B on LPI2C2 and supplies the specified bytes to reads. Its firmware path may diverge; behavior is evidence about what the firmware tests, not evidence of correct touchscreen operation. Every ACK is tagged `DIAGNOSTIC` in QEMU logs.

Run `python3 scripts/analyze_lpi2c_trace.py private/lpi2c4b-probe/qemu-instructions.log` to decode MTDR commands, readbacks, and NACK frequencies. If the firmware proceeds, compare instruction traces against the no-slave baseline, identify what bytes/CRC/IRQ lines it validates, and only then write a chip-specific model. Do not call a fake ACK or host mock frame an emulator boot.

## Still outstanding

Guest LCD framebuffer, panel timing, touchscreen hardware inputs, storage, authentic I²C response semantics, and the eForce μITRON scheduler have not been validated. The correct next significant objective is to identify the missing 0x4B peripheral (ideally PCB photos/part markings), implement its real register protocol, connect M4 interrupts if the software demands them, and obtain a guest-produced framebuffer.
