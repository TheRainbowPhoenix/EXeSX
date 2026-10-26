# 2026-10-26 — Original DY357 E2 touchscreen: BU21029 and PTB3 pen detect

## Proven by owner-provided decomp (private sources, not committed)

The A7 `XD-SX9850.0.c` E2 handler `FUN_6005c6bc` waits for firmware input records with event type `0x6000` and coordinates. These events are an output of the original firmware's input pipeline: the emulator **must not inject them directly**.

The original M4 `XD-SX9850-M4.bin.c` supports a *separate* touchscreen controller:
- `FUN_1ffdb910`: `LPI2C_SendStartAddress(0x80)` to I²C slave **0x40** (write), one-byte register-address command encoding.
- `FUN_1ffdb974`: one-byte register select, STOP, restart at **0x81** (read) for status.
- `FUN_1ffdb9bc(0x84)`: controller conversion/scan command.
- `FUN_1ffdba12`: starts I²C **0x81**, requests **14 bytes**, swaps each of seven 16-bit values.
- `FUN_1ffdbdbc` and `FUN_1ffdbcde`: physical pen state sampled repeatedly at GPIOB.PDIR **0x4100F050 bit3** (low = contact).
- `FUN_1ffdff08`: arms **PORTB.PCR3** at `0x4104000C` with `0x00080000` (IRQC=8 low-level interrupt) and acknowledges PORTB.ISFR at `0x410400A0` with bit3 `0x8`.

These separate address and report fingerprints match the documented **ROHM BU21029MUV** 4-wire resistive touch controller. The BU26154 device at address 0x1A is an audio CODEC with a separate ADC block, and the existing diagnostic I2C 0x40 register mirror is **not** a BU21029 device implementation.

Public references: [ROHM BU21029 datasheet](https://www.furutaka-netsel.co.jp/pdf/rohm/jp/bu21029muv-j.pdf), [Linux BU21029 controller driver](https://codebrowser.dev/linux/linux/drivers/input/touchscreen/bu21029_ts.c.html), [original board candidate differences](2026-10-26-dy358-pcb-crosscheck.md).

## New opt-in emulation

- `hw/arm/exesx-imx7ulp-touch.inc` reads private host `EXESX_BU21029_TOUCH_FILE` contents: `down x y [z1 z2]` as **12-bit raw electrode ADC values (0..4095)**. Example `1 291 2748 800 1200`; `0 291 2748` = release. Never treat this as screen pixel coordinates or fabricate calibrated positions.
- Only when `EXESX_BU21029_LPI2C_BUS=2` (expected M4 LPI2C2 base 0x41035000) does the peripheral attach at I2C 0x40, override the old register mirror, and drive **PTB3 active low** on touch. Default disabled to preserve absence/NACK.
- `hw/arm/exesx-imx7ulp-lpi2c.inc` acknowledges the real I2C read/write addresses, stores command and control registers in serialized device state, returns original 14-byte big-endian raw sample structure (X, Y, Z1, Z2 plus absent secondary contact) on conversion commands. It logs unsupported reads/writes rather than inventing downstream behavior.
- Existing `hw/arm/exesx-imx7ulp-port.inc` performs the actual PCR3/ISFR + IRQ57 behavior based on PTB3 physical voltages, polled each **1ms guest virtual time** with an active host touch file. The original M4 must still recognize and publish the event via its RTOS / IPC implementation.
- No direct A7 input records, RTOS flags, IPC completions, or forced factory check pass.

**Verification boundary:** the firmware-free synthetic real-ARM I2C/GPIO regression must show no-device NACK, controller status and read protocol, raw byte positions, contact/release GPIO levels and genuine PORTB.ISFR flag. *A passing register probe alone does not prove the original E2 factory test passes.* An original-ROM run must separately display real touch response, pass all requested crosses/contacts, and report a genuine E2 success.

**Caution:** BU21029 hardware timing, pressure equations, GPIO IRQ persistence, calibration/second-finger handling and full register mode bits need original-ROM observation. The unimplemented aspects must be logged. No original OSUP firmware, decompiler source, MAC identifier, screenshot, firmware-derived media or private logs belong in GitHub.
