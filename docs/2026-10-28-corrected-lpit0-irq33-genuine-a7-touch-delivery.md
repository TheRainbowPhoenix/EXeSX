# 2026-10-28 — Corrected LPIT0 IRQ33 and original M4→A7 touchscreen delivery

**Verdict:** the owner-private, unchanged original ROM reaches TEST MENU and TOUCH PANEL PRESET with corrected LPIT0 IRQ wiring; the original M4 performs **complete 14-byte BU21029 reads**, and the original A7 executes its **type `0x6000` touch-event rendering path** in response to a physical emulated pen contact. This is an authentic touchscreen input delivery **PASS**, but **TOUCH PANEL PRESET/E2 coverage and factory `OK` remain unverified**.

## LPIT0 exception-number correction

The original M4 calls `FUN_1FFD23AA(0x31)`. The routine expects an ARM *exception vector number* and subtracts `0x10` for the system exception slots. Vector 49 (`0x31`) means external NVIC **IRQ33**, not external IRQ49. Earlier source connected LPIT0 to IRQ49 and erroneously verified pending `ISPR1` bit17 while original M4 enabled bit1.

The source now routes M4 LPIT0 `0x4102D000` to `qdev_get_gpio_in(m4,33)`, with 12MHz counter timing for the original firmware's channel-1 `TVAL=12000` ~1ms interval. The real-ARM synthetic test `scripts/probe_m4_lpit0_irq.py` confirms:

| Bridge | Guest MIER | Real LPIT0 MSR channel 1 | M4 NVIC.ISPR1 |
|---|---|---|---|
| Off | Unmasked | expired | 0 |
| On | Masked | expired | 0 |
| On | Unmasked | expired | `0x00000002` |

**CI:** [Linux 40606439589](https://github.com/TheRainbowPhoenix/EXeSX/actions/runs/40606439589) and [Windows 40606439748](https://github.com/TheRainbowPhoenix/EXeSX/actions/runs/40606439748), both passing on build `60e7120993ae8e8eb7c4036873c497af28e0de7b`.

## Unchanged original ROM: end-to-end evidence

Guest boot: exact Linux CI-built binary; `tcg,thread=multi`; original M4 startup keyboard chord and the source-verified physical `93,93,94` factory entry. `0x400B` returned; original menu painter ran. Selected row 11 **TOUCH PANEL PRESET** through repeated physically pressed M4 keys with framebuffer-confirmed highlights. Both original source-derived synthetic eMMC and disposable SD used `snapshot=on`. Analog ADC0/1 were explicitly simulated as raw `0x7000`; these are not real battery readings. Opt-in BU21029 was at M4 LPI2C2 slave address `0x40`.

After confirming the original border-and-X screen (864x480), host physically supplied `down=1, X=2048, Y=2048, Z1=800, Z2=1200` via the modeled electrical contact file for six seconds, followed by pen release. No M4/A7 RAM, CPU registers, RTOS flags, pending IRQ bits, MU messages, or framebuffer pixels were fabricated or altered.

Bounded original execution trace counts split at the host physical-pen contact:

| Event | Before pen contact | After pen contact |
|---|---:|---:|
| M4 original LPIT0 ISR entry `0x1FFD69F2` | 79 | 1,180 |
| M4 original touch RTOS callback `0x1FFDBFB4` | 0 | 5,649 |
| M4 original coordinate acquisition `0x1FFDBA48` | 0 | 5,615 |
| Original BU21029 `RX_REQUEST count=14` | 0 | **1,621** |
| Original 14-byte report fully consumed | 0 | **1,621** |
| A7 accepted-touch branch `0x6005C904` | 0 | **entered** |
| Original A7 drawing function `0x601B2060` | 0 | **463** translation-block executions |

The original A7 disassembly at `FUN_6005C6BC` is definitive for event type: `0x6005C88C` calls its native event queue, `0x6005C8B4` compares the returned type with `0x6000`, `0x6005C8B8` skips touch rendering on mismatch, and `0x6005C954` invokes the genuine framebuffer renderer. The trace enters the touch branch then calls that renderer. This establishes genuine original M4-to-A7 touch delivery, **not merely I2C activity**. Repeated firmware execution under a held pen is normal and not a count of unique screen coordinates.

The original LCD changed **exactly one pixel** at coordinate `(477,236)` after the raw stationary pen contact, from white to black. Original black target pixels increased from `113,969` to `113,970`. Releasing the pen did not erase the target pattern. The complete TOUCH PANEL PRESET and E2 tests **have not passed**; future replay must accurately invert the raw→screen calibration, draw continuous line coverage, avoid missed samples/double draw, and observe the original factory `OK` verdict.

## Scope and confidentiality

Private owner-provided OSUP, A7/M4 decompilations, media images, PNG screenshots and full diagnostic execution logs remain **local**, not in this public repository. This document contains only abstracted, sanitized original source-derived function addresses and validation facts. Historical branch PR #41 remains draft until additional factory tests pass.
