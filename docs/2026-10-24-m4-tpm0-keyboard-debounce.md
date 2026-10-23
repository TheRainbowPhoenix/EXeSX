# Original XD-SX9850 Cortex-M4 decomp: TPM0 keyboard-debounce interrupt

**24 October 2026 — Source-verified, then implementation under test.**
Based on owner-uploaded `XD-SX9850-M4.bin.c` and
`XD-SX9850-M4.bin`, independently checked against original
`OSUP.BIN`. Do not upload or commit those proprietary binaries,
decompiler output, source-derived guest disk, or private VM snapshots.

## Binary provenance: no guessed M4 image

The supplied M4 binary is **85,872 bytes**, SHA256
`25f95e3a5cfe2a898b2110d874075e6da5b288c706c03bc5a051a1f8c8e54fb0`.
Every byte matches the original attached `OSUP.BIN`
at file offset **`0x001ED8A0`**, loaded at
**`0x1FFD0000`**. Raw initial SP is `0x20001C00`,
Thumb reset PC `0x1FFE19E5`. The supplied
C decomp SHA256 is
`63cdb036efebe7f4f4ca91f228b3684babcb85ec1c260a0fe27425ad61706292`.
These match checks matter when naming any original instruction
address; they do **not** validate an arbitrary other model's M4 ROM.

## Actual original hardware ISR chain (resolved from raw Thumb instructions)

The raw Thumb code around `0x1FFDB710` installs
three distinct callbacks with `FUN_1FFD219C`
using original vector **`0x36`, `0x38`,
`0x39`**. The first is the TPM0 vector:
`DAT_1FFDB844 = 0x1FFDB68D` (Thumb handler pointer,
function address `0x1FFDB68C`).
The original lookup addresses:
`DAT_1FFDB830 = 0x41030010` (TPM0.SC),
`DAT_1FFDB834 = 0x410A8010` (TPM2.SC),
`DAT_1FFDB838 = 0x410A9010` (TPM3.SC).
Vector `0x36` = 54 = external Cortex-M4
**NVIC IRQ38**, not IRQ56 (which is PCTLA).

At function `0x1FFDB68C` the original ARM Thumb
handler:

1. Reads **TPM0.SC `0x41030010`** and tests
   its overflow flag **TOF / bit7**.
2. If the flag is set, executes **`BL 0x1FFD7D5A`**
   (`M4_PostKeyboardEventBit2`).
3. Writes TPM0.SC **OR `0x80`** to
   acknowledge sticky TOF (write-one-to-clear).
4. Returns from the native IRQ callback.

The original `FUN_1FFDB7C2(0)` prepares TPM0;
`FUN_1FFDB6D4(0)` writes its `SC.CMOD=1`
configuration, resets `CNT` and sets **`MOD=0x5DC`**.
The start function then sets SC bits `0x48`:
clock mode `0x08` and overflow interrupt enable
`0x40`; it also enables the original NVIC vector
via `FUN_1FFD23AA`. The original
`FUN_1FFDB7FA(0)` stops the timer and clears
its counter. *The clock-source period used by
real Casio hardware remains unmeasured.*

Critically, `M4_PostKeyboardEventBit2`
(`0x1FFD7D5A`) calls
**`FUN_1FFD53BA(10, 4)`**, posting event
object 10, bitmask 4, when the key worker uses
the RTOS flag path. The callback may also
directly execute `M4_KeyboardEventBit2_StateMachine`
depending on a global dispatch condition.
That explains why Port A IRQ56 and event
mask1 alone previously woke an initial scan
but **failed to complete debounce** after
M4 keyboard state became 2.

## What the supplied Ghidra C proves about a complete key press

`M4_KeyboardEventBit2_StateMachine`
at **`0x1FFD8088`** uses original state block
`DAT_1FFD860C` (pointing to original
`0x1FFEA320`):

- **State 2**: decrements a debounce counter,
  samples the *already selected* GPIO column
  via `FUN_1FFD8564`. While pressed, when
  the counter reaches zero, queues an event with
  **`FUN_1FFD8200(1, current_key)`**,
  transitions to state **1**, refreshes timing
  constants, and signals original RTOS
  **`FUN_1FFD53BA(2, 4)`**.
- **State 3**: waits for the contact to be
  released, may queue `FUN_1FFD8200(3,...)`
  and clear the key context; if contact is
  held it may instead queue `FUN_1FFD8200(2,...)`
  before returning to state 1.
- **State 0**: reset/re-arm path, and original
  PORTA wake settings restored.

The original key-message builder
`FUN_1FFD8200` uses the type-2 message
format, a subtype argument (1/2/3), and the
`FUN_1FFD82D8` keyboard queue; these are
the authentic records the A7 is supposed
to consume. No QEMU implementation should
directly synthesize such a record as a
substitute for the M4 ISR/timer.

## Ghidra-ready function and MMIO renames (source-proven)

Confidence: **confirmed** = original uploaded C
and/or raw Thumb instruction semantics;
**likely** = behavior inferred but the
original developer symbol is unknown.

| Address | Suggested symbol | Confidence |
|---|---|---|
| `0x1FFDB68C` | `M4_TPM0_Overflow_IRQHandler` | Confirmed raw Thumb branch/call/W1C |
| `0x1FFDB710` | `M4_TPM_InstallIRQHandlers` | Confirmed raw handler/vectors |
| `0x1FFDB7C2` | `M4_TPM_EnableAndStart` | Confirmed starts selected timer IRQ |
| `0x1FFDB7FA` | `M4_TPM_StopAndClear` | Confirmed |
| `0x1FFDB6D4` | `M4_TPM_ProgramMODAndResetCounter` | Confirmed |
| `0x1FFD7D5A` | `M4_PostKeyboardEventBit2` | Confirmed directly in attached decomp |
| `0x1FFD8088` | `M4_KeyboardEventBit2_StateMachine` | Confirmed directly in attached decomp |
| `0x1FFD8564` | `M4_KeyboardSampleSelectedColumn` | Confirmed from original decomp |
| `0x1FFD8200` | `M4_KeyboardBuildQueuedStateEvent` | Confirmed type2 event subtype |
| `0x1FFD82D8` | `M4_KeyboardQueueEvent` | Confirmed, queue insertion |
| `0x1FFD7E84` | `M4_KeyboardClearCurrentKeyState` | Confirmed reset of context |
| `0x1FFEA320` | `g_m4_keyboard_debounce_state` | Confirmed observed state2; runtime RAM |

Peripheral registers are **data**, not functions:

| Address | Suggested MMIO label | Evidence |
|---|---|---|
| `0x41030010` | `M4_TPM0_SC` | Original ROM literal `DAT_1FFDB830` |
| `0x41030014` | `M4_TPM0_CNT` | Original timer reset write |
| `0x41030018` | `M4_TPM0_MOD` | Original writes `0x5DC` |
| `0xE000E104` | `M4_NVIC_ISER1` | IRQ38 enable bit6 |
| `0xE000E204` | `M4_NVIC_ISPR1` | IRQ38 pending bit6 |
| `0x1FFDB844` | `m4_tpm0_irq_callback_ptr` | Original literal `0x1FFDB68D` |
| `0x1FFDB848` | `m4_tpm2_irq_callback_ptr` | Original literal `0x1FFDB6A9` |
| `0x1FFDB84C` | `m4_tpm3_irq_callback_ptr` | Original literal `0x1FFDB6BF` |

## Emulator change and validation boundaries

Existing EXeSX `hw/arm/exesx-imx7ulp-tpm.inc`
had a virtual-time counter but **no IRQ output**.
The separate opt-in
`EXESX_EXPERIMENTAL_M4_TPM0_IRQ=1`
now schedules real overflow from TPM0.SC.CMOD,
TPM0.SC.PS and TPM0.MOD, sets sticky SC.TOF,
asserts the actual M4 NVIC IRQ38 iff
SC.TOIE is enabled, and deasserts when
the original firmware clears the flag W1C.
The TPM0 timer is rearmed on private
QEMU `loadvm` from the serialized epoch/counter,
not by setting any RTOS flag manually.

`scripts/probe_m4_tpm0_irq.py` executes
**real synthetic ARM instructions** programming
`MOD=0x5DC`, `CNT=0`, `SC=0x48`
and checks TPM0.TOF and IRQ38, plus three
negative controls. The Python original-ROM
runners now expose `--tpm0-irq` independently
from `--port-irq` and `--lptmr-irq`.

**The authentic A7 type2/subtype1 key event,
three-key factory-menu entry, and menu LCD
rendering must all still be separately verified
against unchanged original Casio firmware.**
Synthetic hardware pass does not prove these
milestones. The original private firmware,
binary/decomp, and snapshots are not in GitHub.

## Unchanged owner-ROM QEMU runtime confirmation — TPM0 really fixes state2

The **native QEMU artifact built from commit `28c70c9` passed
Linux CI**, including the exact original ARM TPM0 overflow and
three disabled/negative variants. An owner-private **original
OSUP checkpoint**, saved before this change at A7 BIOS
`0x600108A8`, was resumed without any guest code/data
patches using `EXESX_EXPERIMENTAL_M4_TPM0_IRQ=1`.

The initial original M4 state was 2, debounce
remaining count 4, `TPM0.SC=0x4C`,
`TPM0.CNT=0x514`, `TPM0.MOD=0x5DC`.
With the corrected QEMU, real original M4 thread2
executed:

`0x1FFDB68C` TPM0 IRQ handler →
`0x1FFD7D5A` original event-bit2 producer →
`0x1FFD7B28` original task wait return →
`0x1FFD7B42` original bit2 dispatch →
`0x1FFD8088` state2 debounce handler →
`0x1FFD809E` GPIO column resampling.

**The original M4 debounce counter decremented from 4 to 3**
and the genuine firmware subsequently returned to
**state 0** with timer halted
(`TPM0.SC=0x0`, `TPM0.MOD=0xFFFF`).
No debugger fake event or forced PC was used.
This directly validates the missing timer IRQ root cause.

The subsequent three Python-driven key-contact attempts
with different holds/releases also translated the original
M4 `FUN_1FFD8200` keyboard event-builder path,
but the original A7 did **not** hit the
`0x93,0x93,0x94` diagnostic checks or
`0x6003A878` factory menu; it exited normally
at `0x60010974`. These tests **do not establish a
genuine accepted A7 key-down event**.

### Newly found second contact-model defect: the row IOMUX

A focused one-shot original-M4 breakpoint at
`FUN_1FFD8200` then `FUN_1FFD82D8`
caught a genuine **type2/subtype1** event, but with
keycode **`0xC5`**, not host-requested `0x93`.
This is real original-ROM execution, not a fabricated
event; it identifies a *wrong-row* contact.

The decomp of `FUN_1FFD8412` explains it:
the original M4 does **not** select a keyboard row
only by GPIO.PCOR/PDOR/PDDR. It writes
the row's **IOMUXC0** selector too:
`DAT_1FFD89A0 = 0x4103D000` and
`DAT_1FFD899C = 0x00020100`.
Selecting row N writes `0x20100` to
`IOMUXC0[pin + (bankB ? 32 : 0)]`;
deselecting writes **0**. Rows can retain low
GPIO PDOR/PDDR values after being de-muxed,
but must be **electrically disconnected** from
keyboard columns. Our first version modeled the
GPIO output without testing this mux, allowing
a pressed A31 column to register on row1,
producing the wrong logical `0xC5`.

The corrected opt-in physical key-contact model
now checks **all three original conditions**:
GPIO.PDDR output, GPIO.PDOR low, **IOMUXC0
row selector == 0x20100**. It reads serialized
guest MMIO state, not a host-only last-selected-row
variable (which would break `loadvm`).
The synthetic ARM matrix regression programs
the IOMUX mux as the actual M4 does before
sampling and zeroes it between rows.
**Rebuilt-original-ROM acceptance of `0x93` /
`0x94` is still pending.**

Additional precise Ghidra symbols:

| Address | Proposed label | Source evidence |
|---|---|---|
| `0x1FFD8412` | `M4_KeyboardSetRowIOMUXAndGPIO` | Original decomp writes mux then PCOR/PDDR |
| `0x1FFD8470` | `M4_KeyboardConfigureAllRows` | Original 9-row mux setup |
| `0x1FFD8998` | `m4_keyboard_row_table_literal` | Original points to `0x1FFD0DA8` |
| `0x1FFD899C` | `m4_keyboard_active_iomux_value_literal` | Original `0x20100` |
| `0x1FFD89A0` | `m4_iomuxc0_base_literal` | Original `0x4103D000` |
| `0x4103D054` | `M4_IOMUXC0_PTA21` | Original row8 (logical key 0x93) |
| `0x4103D044` | `M4_IOMUXC0_PTA17` | Original row6 (logical key 0x94) |
