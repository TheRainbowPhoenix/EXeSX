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

## Verified native interrupt and original-ROM integration boundary

The independent firmware-free M4 pen-interrupt experiment used a real guest ARM write of `0x00080000` to `PORTB.PCR3 0x4104000C`, matching the original M4, then changed **only** the host-supplied contact-file voltage from released to pressed. It examined actual M4 CPU2 NVIC memory through GDB after the virtual timer ran:

| Control | PORTB.ISFR | M4 NVIC ISPR1 bit25 (external IRQ57) |
| --- | --- | --- |
| Port IRQ bridge disabled | 0 | 0 |
| PCR3 IRQC disabled | 0 | 0 |
| Bridge and IRQC=8; physical press | `0x00000008` | `0x02000000` |

This is genuine QEMU PORTB/NVIC pending behavior without A7 event fabrication. The project now adds this assertion to `scripts/probe_bu21029_touch.py` using the actual M4 GDB thread, not an A7 CPU read of the Cortex-M SCB.

**End-to-end not yet passing:** Separate original unchanged owner OSUP cold-boot experiments with the opt-in BU21029 attachment encountered a pre-menu startup stall in their bounded windows, both with a continuously pressed raw contact and with a released contact. A matched control using the **same new QEMU binary**, but without BU21029 attachment, reached real `0x400B` completion, menu painter, DOWN navigation, and the genuine E2 cross-check screen. The attempted press-then-stroke replay was **not started**, because E2 was not reached with BU21029 attached. Thus no original A7 `0x6000` event or passing E2 test has been established, and the model should remain opt-in.

ROHM STATUS bits are AUTO (6), PDM (5), BUSY (3), ACTIVE (2), CALIB_DONE (1), TOUCH (0). The model now avoids permanently setting BUSY: its first conversion expires after 2ms of guest virtual time; CF=5 calibration latches CALIB_DONE. Analog conversion timing is a simplification, not full silicon emulation. The next decisive original-ROM experiment is to find why the original M4 init/task may block with the live I2C 0x40 device, compare STOP-aware transfers and IRQ57 state against the diagnostic mirror control, then validate original M4 touch event publication to the A7. Do not invent any RTOS flag or E2 success indicator.

## Why the previously working factory menu regressed in local testing

A genuine original-ROM M4 CPU state probe during pending `0x400B` captured HardFault CFSR **`0x00008200`**, BFAR **`0x41037008`**, HFSR `0x40000000`, M4 state bit2 set. This is the **original I2S0.TCSR bus-fault signature**, not a new touchscreen exception. The root cause is that the private runner selected an **October 25 diagnostic memory profile** that omitted both I2S0 `0x41037000+0x100` and I2S1 `0x410AA000+0x100`, even though the current repository `profiles/imx7ulp-early-boot.ini` and QEMU model contain them. **QEMU does not auto-create a register window omitted by `EXESX_MEMORY_PROFILE`.**

With those two windows added to the private diagnostic profile, a real unchanged-OSUP cold boot using the **same `f2ecb2c` native QEMU with BU21029 opt-in OFF** passed all milestones: version popup, original three menu keys, TEST MENU, `0x400B` invocation and authentic return, menu painter, all DOWN navigation to visibly confirmed E2 row13, and real ENTER into E2. LCD frames were read asynchronously. The E2 cross ended in **NG** as expected with no pen input. This constitutes a reliable menu/display restoration, **not** a passed touch check.

The fix in `scripts/auto_driver.py:profile_with_lcd` now backfills the real I2S0/I2S1 windows into owner-provided stale profiles with explicit console messages, preserving their other mappings. `scripts/probe_factory_profile_backfill.py` makes this a Linux/Windows regression test (including idempotence and LCD export), preventing another false diagnosis as an emulator regression.

**Separate performance issue:** The opt-in BU21029 GPIO model originally called `g_getenv` on *every* high-frequency PDIR poll and reread the host touch file for *every* PDIR or I2C data read. Current source now parses the immutable bus parameter once via GLib atomic once-init and polls host touch samples no more often than every **5ms guest virtual time**, caching coherent contact/X/Y/Z values per EXeSX machine. Actual original-ROM contact-enabled factory E2 completion still requires a dedicated end-to-end test; no A7 `0x6000` events were manufactured. These changes are grounded as performance/reliability fixes, not proofs of E2 success.

The private I2S-fault GDB dump, screen pixels, OSUP, original media and traces stay off GitHub.
