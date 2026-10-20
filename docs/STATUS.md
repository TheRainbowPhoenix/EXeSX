# EXeSX status — 2026-10-20

**A7 BIOS and Cortex-M4 execute, but no proven Casio OS entry, guest LCD output or on-screen text.** Proprietary firmware stays local; the emulator is experimental.

## What really works

- A7 boots its BIOS; BIOS loads/releases M4 Thumb code; dual-core diagnostics show M4 interaction with LPI2C2 7-bit slaves 0x4B and 0x40, ADC0/1 and DMA0 startup registers. External I2C chips remain unidentified; opt-in register mirrors at 0x4B/0x40 are artificial.
- M4 firmware checks GPIO input codes 0x9C and 0x90. One controlled PDIR bit change at M4 `0x1FFD85C6` changes the M4 IPC word at `0x2F028000` from `0xEEEEEEEE` to `0xFFFFFFFF`; A7 takes different diagnostic/alternate branch. Neither has reached OS.
- A7 kernel initializes its idle callback slot `0x62148F8C` **deliberately to zero**: caller `0x600495F0` sets config +0x40=0, and init `0x6017A564` copies it. Its idle PC `0x60179A7C` is **not evidence of an unset required callback**.
- BIOS `MainTask` TCB `0x621E88C8` runs from entry `0x60037DA8`, then repeatedly uses µITRON `wai_sem(31)`/`sig_sem(31)`. The object at `0x621EAED0` has a 16-bit current count at +0x0C. **A real continuous 0.9s trace counted 13 A7 semaphore decrement and 13 increment writes.** The kernel can resume from idle; don't misclassify a stopped-PC snapshot as a deadlock.

## NXP-documented MU transport correction — validated with real firmware

The [specific Linux i.MX7ULP mailbox driver](https://github.com/torvalds/linux/blob/master/drivers/mailbox/imx-mailbox.c) proves MU v1 **channel 0 is nibble bit 3** (hardware mask `1<<(3-channel)`), **not bit 0**, for transmit-empty, receive-full, and interrupt-enable status. EXeSX incorrectly used `1<<channel`. The old IRQ22 channel labels, including the supposed missing channel-0 callback, were incorrect.

[Corrected 4-channel real ARM tests and real-firmware comparison](2026-10-20-imx7ulp-mu-v1-bit-order.md): with both diagnostic I²C mirrors and MU IRQ enabled, **78,665 IRQ22 entries dropped to 2** in 1.1s and **five TR2 busy rejections dropped to zero**. An actual corrected guest M4 IRQ snapshot showed RF channel 2 at the first IRQ, then no MU RF or GIP at the second entry. The Linux-based protocol fix preserves real receive acknowledgments and does not invent any hardware data.

**New observed peripheral blocker:** After DMA0 early control the real M4 hits a precise BusFault at **`0x41070004`**, NXP **SNVS.HPCOMR**. Disassembly identifies `0x1FFD4C7E: ldr r0,[r1]`. SNVS must be modeled to actual NXP documented command and reset semantics, not as arbitrary writable RAM. A7 still samples at `0x60179A7C`, IPC remains `0xEEEEEEEE`; still **no proven OS or LCD output**.

Next: build a strict SNVS HPCOMR/HPCR early-control subset backed by documented field semantics and firmware-free guest ARM tests, compare the new M4 fault/IPC afterwards. Preserve old MU captures as **historical artifacts produced with the buggy flag order**, not the correct silicon channel numbering.
