# EXeSX status — 2026-10-20

**Native ARM firmware executes on Cortex-A7 and Cortex-M4, but NO OS boot, UI text or LCD pixels have been produced.**

A7 CPU startup, real M4 release from copied BIOS firmware, LPI2C2 command generation, ADC0/ADC1 control registers, and an initial DMA0 control subset work in the experimental native emulator. Genuine external peripherals at 7-bit I²C 0x4B and 0x40 remain **unidentified**. The default bus correctly NACKs missing slaves.

Opt-in synthetic 8-bit register mirrors at 0x4B and 0x40 can bypass NACK and permit the M4 to reach ADC/DMA0 configuration. They do **not** produce a valid A7/M4 initialization: the IPC word at 0x2F028000 is still 0xEEEEEEEE, while A7 PC is sampled at 0x60179A7C (error/holding loop) and M4 PC at 0x1FFDA0A0 (ISB after WFI) during both-mirror cold runs. Do not interpret that WFI sample alone as proof of an IRQ bug.

Current measured evidence: [real differential experiment](2026-10-20-validated-native-differential.md). Protocol callsites: [M4 static I2C XRefs](M4_I2C_STATIC_XREFS.md). Full knowledge: [consolidated handover](ALL_IMPORTANT_KNOWLEDGE.txt). Firmware stays local and out of GitHub.

Next: trace the writer and interpretation of IPC error marker, validate M4 interrupt dependencies and DMA control requirements; then model specific real off-chip device semantics, OS entry, storage, LCDIF and guest text.
