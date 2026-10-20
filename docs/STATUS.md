# EXeSX status — 2026-10-21

**A7 BIOS and Cortex-M4 execute, but no proven Casio OS entry, guest LCD output or on-screen text.** Proprietary firmware stays local; the emulator is experimental.

## What really works

- A7 boots its BIOS; BIOS loads/releases M4 Thumb code; dual-core diagnostics show M4 interaction with LPI2C2 7-bit slaves 0x4B and 0x40, ADC0/1 and DMA0 startup registers. External I2C chips remain unidentified; opt-in register mirrors at 0x4B/0x40 are artificial.
- M4 firmware checks GPIO input codes 0x9C and 0x90. One controlled PDIR bit change at M4 `0x1FFD85C6` changes the M4 IPC word at `0x2F028000` from `0xEEEEEEEE` to `0xFFFFFFFF`; A7 takes different diagnostic/alternate branch. Neither has reached OS.
- A7 kernel initializes its idle callback slot `0x62148F8C` **deliberately to zero**: caller `0x600495F0` sets config +0x40=0, and init `0x6017A564` copies it. Its idle PC `0x60179A7C` is **not evidence of an unset required callback**.
- BIOS `MainTask` TCB `0x621E88C8` runs from entry `0x60037DA8`, then repeatedly uses µITRON `wai_sem(31)`/`sig_sem(31)`. The object at `0x621EAED0` has a 16-bit current count at +0x0C. **A real continuous 0.9s trace counted 13 A7 semaphore decrement and 13 increment writes.** The kernel can resume from idle; don't misclassify a stopped-PC snapshot as a deadlock.

## NXP-documented MU transport correction — validated with real firmware

The [specific Linux i.MX7ULP mailbox driver](https://github.com/torvalds/linux/blob/master/drivers/mailbox/imx-mailbox.c) proves MU v1 **channel 0 is nibble bit 3** (hardware mask `1<<(3-channel)`), **not bit 0**, for transmit-empty, receive-full, and interrupt-enable status. EXeSX incorrectly used `1<<channel`. The old IRQ22 channel labels, including the supposed missing channel-0 callback, were incorrect.

[Corrected 4-channel real ARM tests and real-firmware comparison](2026-10-20-imx7ulp-mu-v1-bit-order.md): with both diagnostic I²C mirrors and MU IRQ enabled, **78,665 IRQ22 entries dropped to 2** in 1.1s and **five TR2 busy rejections dropped to zero**. An actual corrected guest M4 IRQ snapshot showed RF channel 2 at the first IRQ, then no MU RF or GIP at the second entry. The Linux-based protocol fix preserves real receive acknowledgments and does not invent any hardware data.

## SNVS high-power initial bring-up — measured real firmware

[NXP's i.MX7ULP SNVS definitions](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/periph/PERI_SNVS.h) place HPCOMR at 0x41070004 and HPCR at 0x41070008. A strict **SNVS HP subset** now handles the M4's initial HPCOMR read, LP_SWR reset-command self-clear, and HPCR RTC_EN. Security-violation command bits **SW_SV/SW_LPSV are rejected by default**: secure lifecycle, LP state and hardware RTC are not yet emulated.

[Full SNVS investigation and independent real-OSUP comparison](2026-10-21-snvs-hp-investigation.md): Native QEMU CI passed, including synthetic ARM instruction tests. With strict SNVS, the original missing-register fault is replaced by a **deliberate fault on the later 0x500 security command**. With explicit diagnostic pulse bypass enabled, M4 completes its SNVS routine and remains free of M4 BusFaults in a 3-second cold run. This is **diagnostic code execution only**, not a valid secure state.

**Next measured blocker:** In diagnostic mode A7 returns from an IRQ to **PC 0x20002028**, then takes an **A7 Data Abort** (A7 in abort mode CPSR 0x60000197, sampled PC 0x601B40F4 after 3 seconds). The shared IPC word remains 0xEEEEEEEE and **no valid Casio OS entry, UI or LCD pixels** have been demonstrated. Need to inspect A7 saved IRQ context, MMU translation/fault registers and why that return target appears. Do not assume the SNVS model itself caused this A7 abort.

**Prioritized public hardware documents and cross-refs:** [HARDWARE_REFERENCES.md](HARDWARE_REFERENCES.md). Obtain the full NXP i.MX7ULP Security Reference Manual (account may be required) before implementing more secure-state behavior.
