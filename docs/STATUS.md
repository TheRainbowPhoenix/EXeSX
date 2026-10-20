# EXeSX status — 2026-10-20

**A7 BIOS and Cortex-M4 execute, but no proven Casio OS entry, guest LCD output or on-screen text.** Proprietary firmware stays local; the emulator is experimental.

## What really works

- A7 boots its BIOS; BIOS loads/releases M4 Thumb code; dual-core diagnostics show M4 interaction with LPI2C2 7-bit slaves 0x4B and 0x40, ADC0/1 and DMA0 startup registers. External I2C chips remain unidentified; opt-in register mirrors at 0x4B/0x40 are artificial.
- M4 firmware checks GPIO input codes 0x9C and 0x90. One controlled PDIR bit change at M4 `0x1FFD85C6` changes the M4 IPC word at `0x2F028000` from `0xEEEEEEEE` to `0xFFFFFFFF`; A7 takes different diagnostic/alternate branch. Neither has reached OS.
- A7 kernel initializes its idle callback slot `0x62148F8C` **deliberately to zero**: caller `0x600495F0` sets config +0x40=0, and init `0x6017A564` copies it. Its idle PC `0x60179A7C` is **not evidence of an unset required callback**.
- BIOS `MainTask` TCB `0x621E88C8` runs from entry `0x60037DA8`, then repeatedly uses µITRON `wai_sem(31)`/`sig_sem(31)`. The object at `0x621EAED0` has a 16-bit current count at +0x0C. **A real continuous 0.9s trace counted 13 A7 semaphore decrement and 13 increment writes.** The kernel can resume from idle; don't misclassify a stopped-PC snapshot as a deadlock.

## New top-priority blocker: MU communication and IRQ22

- On the A7-side Messaging Unit MUB, `TR2` at **`0x40220028`** accepts one word `0`, then logs **five ignored writes** with data `1..5` (transmitter still busy; the M4 must consume MUA RR2 to free the slot).
- `EXESX_EXPERIMENTAL_MU_IRQ=1` triggers a severe **M4 NVIC IRQ22 / exception 38 storm**: in a bounded 1.5s cold run, 97,572 IRQ entries, ~97,571 MUA SR zero writes and MUA CR `0xFB000000` writes. With this optional flag disabled, no IRQ38 storm, but TR2 messages still remain unconsumed.
- The model's MU status has W1C general-purpose pending flags; zero cannot clear them. The exact live GIP/RF/TE bits at each ISR entry are **not yet resolved**, so no fabricated interrupt acknowledgment, force-clear or MMIO "success" hack is warranted.

**Investigation/reproduction:** [A7 callback, semaphore progress and MU interrupt measurements](2026-10-20-a7-callback-semaphore-mu-irq.md). Existing [GPIO/IPC differential](2026-10-20-gpio-snapshot-differential.md), [full bring-up](ALL_IMPORTANT_KNOWLEDGE.txt). Next: decode MUA/MUB pending flag lifecycle and M4 RR2 receive path; prove guest OS entry before implementing LCD text.

