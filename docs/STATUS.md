# EXeSX status — 2026-10-20

**Experimental native QEMU executes the locally supplied Casio Cortex-A7 BIOS and copied Cortex-M4 firmware. No genuine OS execution, LCD pixels or user-visible text has been demonstrated.**

## What has been reached
- A7 real ARMv7 startup and M4 handoff, M4 Thumb code execution, LPI2C2 register traffic to unknown 7-bit I²C addresses 0x4B and 0x40.
- NXP ADC0/ADC1 startup control and DMA0 early-register access after optional **diagnostic** register mirrors are enabled. Default unconnected slave response is NACK.
- A7/M4 mailbox word at 0x2F028000 is observed at 0xEEEEEEEE and A7 PC at 0x60179A7C. The M4 sampled at 0x1FFDA0A0 (ISB after WFI) in a bounded run; that idle instruction alone does not establish an IRQ blocker.

## Newly localized IPC / GPIO decision
Verified real-QEMU memory tracing shows A7 initializes the mailbox at PC **0x601B9DE8**; M4 itself writes the 0xEEEEEEEE marker at PC **0x1FFD5B60**. The responsible M4 branch at **0x1FFD5B54–0x1FFD5B68** calls **0x1FFD7F08**, a routine that tests two mapped GPIO input codes (0x9C and 0x90), with 120 actual M4 PDIR reads at **0x4100F010** in the bounded trace. The emulator's GPIO PDIR currently loops back configured outputs but has **no modeled external inputs**. A new **verified real-firmware snapshot-backed differential** changes only one PDIR read at M4 `0x1FFD85C6`: raising input **bit 19** for code `0x9C` or **bit 23** for code `0x90` makes the M4's real store use `0xFFFFFFFF` at `0x1FFD5B68`, instead of `0xEEEEEEEE` at `0x1FFD5B60`. The A7's actual `BNE` at `0x601786D4` then jumps to `0x601786E0`, skipping the special error handler, rather than falling into `0x601786D8`. **After further execution the A7 still reaches the same holding loop `0x60179A7C`.** Physical GPIO polarity and real OS boot remain unverified.

See [snapshot GPIO differential results](2026-10-20-gpio-snapshot-differential.md), [real CPU-specific IPC/GPIO evidence](2026-10-20-ipc-gpio-input-scan.md) and [earlier cold-run comparison](2026-10-20-validated-native-differential.md). Static XRefs: [M4 I2C callsites](M4_I2C_STATIC_XREFS.md). Complete project handover: [ALL_IMPORTANT_KNOWLEDGE.txt](ALL_IMPORTANT_KNOWLEDGE.txt).

**Next:** Determine what blocks A7 after the alternate `0xFFFFFFFF` IPC branch (e.g. callback/interrupt/OS entry dependencies) and independently establish actual physical GPIO wiring/polarity. Next prove real OS entry and guest LCD framebuffer. Keep all proprietary ROMs and traces private.
