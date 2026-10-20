# EXeSX execution status — 2026-10-20

**Current: genuine early firmware execution on Cortex-A7 and Cortex-M4 in native QEMU; no successful Casio OS boot or screen pixels/text yet.** The machine remains experimental.

- QEMU 10.1.0 ARM TCG executes privileged Cortex-A7 CP15 initialization. The board includes RAM/aliases, GICv2, dual-core handoff, and progressively modeled i.MX7ULP peripherals.
- Locally extracted proprietary firmware (never in Git) causes the A7 to copy a BIOS-embedded M4 program into SRAM and release its Thumb reset entry via SIM0_DGO_GP7. The real M4 instructions execute.
- Current external dependency: LPI2C2 at `0x41035000` addresses a missing I²C 7-bit `0x4B` slave, writes `0x14, 0x62`, then attempts a repeated-start read. Actual chip identity and response format are unknown. NACK is the default model behavior.
- Explicit *diagnostic* artificial I²C responses `00`/`ff` advance the M4 to verified ADC0 and ADC1 writes without the prior ADC0 abort, but lead to shared IPC `0xEEEEEEEE` and the A7's **error/diagnostic holding path**, not a successful handshake.
- The OS image entry trampoline is statically identified at `0x60400000`, targeting `0x605E3AD0`; QEMU execution reaching it has **not** been demonstrated.
- No LCDIF guest framebuffer or panel has been implemented and no real guest boot menu, text, framebuffer dump, or screenshot has been verified. A host-rendered synthetic image would not count.

For detailed measurements and the full recovery sequence see:

- [Consolidated handover](ALL_IMPORTANT_KNOWLEDGE.txt)
- [M4 I²C/ADC experiments](2026-10-20-m4-i2c-adc-boot.md)
- [Dual-core recovery](dual-core-lpi2c4b-and-recovery.md)
- [Validated user's supplied firmware and immediate I²C triage](2026-10-20-supplied-artifacts-i2c-handoff.md)

CI validates the firmware-free QEMU machine and synthetic hardware regressions. A green Actions build is **not** a validated Casio firmware boot. Proprietary ROMs, resources, and guest snapshots remain local.
