# 2026-10-26: strict M4 MMIO diagnostics after the I2S0 HardFault fix

## Original-firmware evidence and current baseline

The owner-supplied `OSUP.BIN` locally hashes to SHA256 `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`. **Do not commit or publish** the firmware, extracted M4/ARM binary, synthetic installed eMMC/SD, private QMP memory samples or emulator guest traces.

The original `0x400B(2)` M4 hardware setup at `0x1FFE49B8` references the following documented peripheral windows:

| Peripheral | Base | Modeling status |
| --- | --- | --- |
| I2S0/SAI0 | `0x41037000` | TCSR read `+0x08` previously caused precise BusFault (BFAR `0x41037008`); mapped by the existing I2S0 fix |
| DMA0 | `0x41008000` | Early controls and TCD storage, **no general M4 DMA execution** |
| DMAMUX0 | `0x41020000` | Channel configuration, **no peripheral DMA requests** |
| IOMUXC0 | `0x4103D000` | Documented early pin mux/config offsets modeled |

SAI1 also maps at `0x410AA000`. These are the setup path's directly identified MMIO windows; the table **does not prove all downstream factory functions or sound transfers are modeled**.

The prior fix and successful original-ROM cold boot are documented in [I2S0 HardFault → factory menu visible](2026-10-26-i2s0-hardfault-400b-factory-menu-visible.md). It is essential **not** to clear original M4 state bit2, fake an event10 post, fabricate an IPC completion, or force a menu PC.

## This follow-up

- Every failed MMIO read/write in a recognized, partially implemented i.MX7ULP peripheral now logs **peripheral kind, exact physical address, width, operation and BUS FAULT** in the `guest_errors` or `unimp` QEMU log. It still returns `MEMTX_ERROR` to the CPU; this is intentionally a real bus fault, not a register fallback.
- On I2S0/I2S1, enabling the TX/RX state logs that clock/FIFO/DMA/IRQ effects are **not implemented**, without inventing audio frame progress. TX FIFO writes log that the sample was dropped; RX FIFO reads return an empty value with an explicit no-source warning rather than echoing stale data.
- Enabling a DMAMUX0 channel logs that peripheral DMA requests are not implemented. Existing channel configuration readback is unchanged.
- The firmware-free, **real ARM guest** SAI test now checks both banks' configuration and reset as before, exercises dropped TX/empty RX accesses, verifies the negative unmapped/reserved-offset controls, and asserts the new MMIO/functional warning messages.

For an actionable local log, start native QEMU with `-d unimp,guest_errors -D /private/path/exesx-mmio.log`; be aware that these logs may contain private execution details and must stay off GitHub.

**Verification boundary:** the independent original-ROM factory-menu proof predates these additional warnings. Synthetic CI testing checks semantics and diagnostics without redistributing the owner's firmware. New original-ROM end-to-end observations should be reported separately from synthetic results.
