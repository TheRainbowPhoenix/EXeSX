# 2026-10-27 — DY357 original factory FFT, touch preset and MANUAL CHECK audit

**Experiment:** `experiment/dy357-m4-inputs-0804-20261023`, unmodified owner-private OSUP, native GitHub CI QEMU, physical M4 keyboard contacts, source-reconstructed synthetic eMMC and disposable SD, both `snapshot=on`. A menu is counted as reached only when the actual original LCD changes after a confirmed highlighted row; framebuffer observation does not fabricate guest input or a factory verdict.

**Privacy:** private OSUP/ELF/decompilation, guest traces and LCD screenshots are local only. The original DEVELOPER MENU exposes WLAN SSID/password/network parameters: **do not publish its raw screenshot**. Local contact sheet has network fields masked.

## Original FFT and TOUCH PANEL PRESET outcomes

* FFT row 7: native `PLEASE TOUCH`/then `PLEASE WAIT 0.5sec.`/`*** RECORDING ***` observed. Critically, the *pre-contact* framebuffer already contained `PLEASE WAIT`, so a physical pen press was **not proven to cause the transition**. No PCM/FFT computation or original OK verdict verified.
* TOUCH PANEL PRESET row 11: original border/X screen appeared. Physical host raw electrode pen held mid-screen; cross remained unchanged; original OK was **not** observed.
* With opt-in BU21029 at I2C2 address 0x40, physical contact caused a PTB3 pen-IRQ transition; genuine original M4 did program PORTB.PCR3 in focused trace, **but no 14-byte I2C RX_REQUEST or consumed report** was observed in these bounded trials.
* A separate live unchanged-ROM *read-only* M4 GDB/NVIC snapshot during a held physical pen saw `NVIC.ISER1 = 0x0F008030` (**IRQ57 enable bit25 set**), `GPIOB.PDIR = 0xC0` (**PTB3 low**), `PORTB.PCR3 = 0` (**disarmed**), `PORTB.ISFR = 0`, `NVIC.ISPR1 = 0` at that instant. This local snapshot does **not** imply IRQ never occurred. The concrete blocker is normal firmware touch interrupt arming/worker state, not globally disabled NVIC.
* The ROHM BU21029 standby-pen detection was corrected so pen closure can physically assert INT before automatic scan; scan-complete semantics remain for autoscan. Original A7 `0x180C(0)` IPC → M4 `FUN_1FFDC76A` → actual `PORTB.PCR3=0x00080000` arming, original 14-byte RX, M4 event queue and A7 type `0x6000` are **still not verified end-to-end**. Never insert A7 touch records, IRQ pending bits or E2 OK manually.

Linux CI [40509633517](https://github.com/TheRainbowPhoenix/EXeSX/actions/runs/40509633517) and Windows CI [40509633456](https://github.com/TheRainbowPhoenix/EXeSX/actions/runs/40509633456) both pass real synthetic ARM hardware regressions for the standby-pen model at commit `0e6a5f9a`; this is not an original firmware E2/PRESET pass.

## All 14 MANUAL CHECK top-level rows — guarded, non-destructive

Eleven safe rows were selected from the real LCD and ENTER sent through the original M4 physical key matrix. Six opened a distinct second-level menu, five showed only their highlighted parent row within ~5 seconds (inconclusive). Rows 12-14 were deliberately not entered.

| Row | Original label | Actual LCD observation |
| ---: | --- | --- |
| 1 | DISPLAY MENU | Opened: DISPLAY TEST; SETTINGS; IMAGE DISPLAY CHECK from SD; JPEG DATA DISPLAY; BMP DATA DISPLAY; MAG DATA DISPLAY; MESSAGE CHECK |
| 2 | MEMORY MENU | Opened: INSIDE SRAM TEST; SECURE RAM TEST; SDRAM TEST; ROM SUM CHECK; BUS TEST; MEMORY BUS TEST; BUS TEST(STRONG); MEMORY BUS TEST(STRONG); VIRTUAL MEMORY TEST |
| 3 | eMMC MENU | Opened: DISPLAY INFORMATION; DISPLAY CID DUMP; identifiers not opened |
| 4 | INPUT MENU | No separate LCD within window — inconclusive |
| 5 | SD CARD MENU | Opened: FORMAT, WRITE, READ, WRITE LOOP, READ LOOP, READ LOOP(Display OFF), DETECT TEST(PTB14), INFORMATION, FILE COPY TEST, MEDIA FULL TEST, MOUNT TEST, AUTO TEST. **None executed**, especially FORMAT/WRITE |
| 6 | AUDIO MENU | No separate LCD within window — inconclusive |
| 7 | USB MENU | No separate LCD within window — inconclusive; BACK failed to return within window |
| 8 | WIRELESS MENU | Original WLAN CHECK MENU opened: COMMUNICATION, BATTERY LIFE, POWER SAVE MODE, FIRMWARE, MAC ADDRESS. MAC ADDRESS not opened |
| 9 | SYSTEM MENU | No separate LCD within window — inconclusive |
| 10 | DEVELOPER MENU | Opened: WLAN SSID SETTING, WLAN PASSWORD SETTING, WLAN IPERF IP ADDRESS SETTING, WLAN AUTO TEST, AES DECRYPTION ON FILE SYSTEM, EXECUTE SECURE ADDIN. Settings are sensitive, locally redacted |
| 11 | OTHERS MENU | No separate LCD within window — inconclusive |
| 12 | FLASH UTILITIES | Not entered: potentially destructive |
| 13 | SERVICE MENU | Not entered: safety not classified |
| 14 | FULL RESET (CONFIG & DICS) | Not entered: destructive reset |

An unchanged parent screenshot is not a factory NG. For rows 4, 6, 7, 9 and 11, next trace original selected handler PCs/return and any unimplemented MMIO/IPC before attributing failure to a peripheral.

## Repository housekeeping

Previous draft PR [#36](https://github.com/TheRainbowPhoenix/EXeSX/pull/36) was **closed**, not merged. Its divergent branch is retained to avoid losing historical work. [PR #41](https://github.com/TheRainbowPhoenix/EXeSX/pull/41) remains the active **draft** on this experiment branch; do not merge incomplete touch emulation to `main` yet. Neither original screenshots nor private guest dumps should be uploaded into public GitHub.

## Next touch acceptance sequence

1. At FFT touch prompt and PRESET X screen, monitor unmodified A7 `FUN_6001EC84(0/1)` and M4 `0x180C` lifecycle; confirm `PORTB.PCR3=0x80000` persists while touch is expected.
2. Confirm live PTB3 voltage, original NVIC IRQ57 handler execution, PORTB.ISFR set/clear, I2C2 original 14-byte reads with source raw ADC samples, genuine M4 event producer, and actual A7 `0x6000` touch record.
3. Only then evaluate FFT start causality and PRESET cross erasure / genuine LCD verdict. No fake IRQs, IPC acknowledgments or framebuffer erasure.
