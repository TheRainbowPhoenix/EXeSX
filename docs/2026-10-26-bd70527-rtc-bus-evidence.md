# 2026-10-26 — BD70527 PCB marking, original RTC I²C address 0x4B

## Hardware / source evidence

Owner-provided PCB marking: **BD70527 103 H23** (previously read as an uncertain "8070527"). The user linked public Linux **ROHM BD70528** drivers, not a confirmed BD70527 datasheet:

- [ROHM BD70528 RTC driver](https://github.com/EOS-team/EOS/blob/40c8096ed6603bf0a2e256d4d594a56048765c4c/src/RROS/drivers/rtc/rtc-bd70528.c#L4)
- [Coccinelle extraction of BD70528 RTC structures](https://github.com/jajajasalu2/cocci-lkmp-c-files/blob/5da943aabe1589e393a131121dbf8e7a84b3cf2a/linux/5521.c#L10)
- [Upstream Linux BD70528 MFD driver / register definitions](https://kernel.googlesource.com/pub/scm/linux/kernel/git/kishon/linux-phy/+/f74fd13f4585e418a3e630a82468be58bf1d98c1/drivers/mfd/rohm-bd70528.c)

**Decisive original M4 firmware evidence:** the owner-provided private `XD-SX9850-M4.bin.c` decomp (not published) calls `LPI2C_SendStartAddress(0x96)` / `0x97`, the 8-bit write/read forms of 7-bit slave **0x4B**, inside:

- `FUN_1ffd6f4c` — address-pointer byte write, then one-byte register read.
- `FUN_1ffd6f7e` — two-byte register write.
- `FUN_1ffd73cc` — starts at register **0x2D**, performs a **9-byte burst read**, then unpacks BCD calendar fields.
- `FUN_1ffd748a` — writes register **0x2F** followed by **seven BCD calendar bytes**.

This is an unusually strong match to the *public BD70528* RTC map:

| Register | Public BD70528 definition | Original DY357 M4 access |
| --- | --- | --- |
| `0x2D` | RTC_COUNT_H | Start of 9-byte burst |
| `0x2E` | RTC_COUNT_L | Second byte |
| `0x2F` | RTC_SEC | Start of seven-byte write |
| `0x30` | RTC_MINUTE | Read/write as BCD |
| `0x31` | RTC_HOUR | Read/write as BCD with 12/24h handling |
| `0x32` | RTC_WEEK | Read/write |
| `0x33` | RTC_DAY | Read/write |
| `0x34` | RTC_MONTH | Read/write |
| `0x35` | RTC_YEAR | End of nine-byte read / seven-byte write |

The public BD70528 device-tree binding independently uses `pmic@4b` (`reg=<0x4b>`) and describes buck regulators, LDOs, RTC, interrupt controller, GPIO, clocks and charger. **The matching address and RTC accesses make a ROHM BD7052x-family power/RTC controller on the Casio board very likely**, not just a visual guess. But there is *no verified BD70527 datasheet* in these references: **do not assume BD70527 is register-for-register identical to BD70528**, assign BD70528's OTP/charger/control bits, or synthesize power/RTC IRQ.

## Emulation boundary

EXeSX currently has `EXESX_I2C4B_REGISTER_MIRROR=1`, a diagnostic LPI2C byte-storage device at 0x4B. This is **not** a real BD70527 model: there is no battery-backed clock progression, RTC freeze/latch semantics, BCD validation, alarm or regulator power rails. Keep register-mirror behavior for cold-boot control until actual 0x4B read/write traces and the BD70527 differences are established. Add an opt-in RTC subdevice only after confirming its transfer semantics; do not counterfeit power-good or charger readings to make firmware tests pass.

## Original touchscreen test status on CI commit a737e6d

The GitHub Actions Linux and Windows smoke suites both **pass** at `a737e6d`, including the BU21029 synthetic ARM I2C/PTB3/IRQ57 checks. Separately, a real original owner-OSUP snapshot-on eMMC/SD test used the Linux artifact built for that commit with `EXESX_BU21029_LPI2C_BUS=2`, raw touch file `0 2048 2048 800 1200`, original key chord and original ROM. It remained in **boot** after four cold-boot attempts over a **110-second** bounded run; no original factory painter or E2 pass was observed. A separate same-binary controller-*disabled* control reached the A7 version popup, menu-key acceptance, `0x400B` invocation, but did **not** reach `0x400B` return/menu painter during its own 110-second run. Thus **do not ascribe the entire boot failure uniquely to BU21029**: this QEMU build still exhibits cold-boot/IPC timing variability without the new device.

Touch improvements being tested separately: the BU21029 firmware reads CFR3 (register 0x0B) before a read-modify-write. Its documented **power-on CFR3 value is 0x72**, not the old emulator's zero. The model now distinguishes untouched register defaults from guest-written zero using a VMState-backed written-bitmap; the synthetic ARM probe verifies both. The physical PTB3 interrupt path remains real, but the A7 factory E2 screen does **not** yet report OK. No guest event/IPC injection or forged test success is permitted.

Proprietary ROM binaries, local QMP traces, media images, synthetic installed eMMC, raw touch contact streams and LCD captures stay private.
