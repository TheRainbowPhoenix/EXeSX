# DY357 M4 keyboard interrupt/event producer: original-code map and Ghidra renames

**23 October 2026**. Evidence derives from the owner's unchanged,
checksum-valid original `OSUP.BIN`, relocated original Thumb disassembly
at `0x1FFD0000`, a **75-second cold-boot QEMU hardware watchpoint**
and the original firmware running from a persisted, private VM snapshot.
No proprietary executable, raw instruction bytes, snapshot, framebuffer,
or full trace is published. All proposed labels preserve original addresses.

## Root cause identified: the producer is PCTLA IRQ56, not LPTMR0

The original Cortex-M4 keyboard task begins at **`0x1FFD7B08`**.
At **`0x1FFD7B1A`** it calls the real RTOS event-flag wait,
`0x1FFD6BAC`, with `R0=10` (event object ID10), `R1=7`
(mask bits 0..2), `R2=1`, and `R3=&stack_event_bits`.
When bit **0x1** is received the original M4 at
`0x1FFD7B2E` calls `0x1FFD7FB0`, which calls
`0x1FFD8634` to scan the **9×8 original GPIO matrix**.
It does not scan continuously or when only an A7 timeout arrives.

In the original M4 at **`0x1FFD7D2E`**, the external
interrupt callback runs `0x1FFDB5F4`, `0x1FFDB622`,
and **`0x1FFD247A(0x48)`** to clear vector 72 pending.
The latter function converts vector-number minus 16 into
NVIC ICPR word/bit, confirming **external IRQ56**.
The NXP i.MX7ULP Reference Manual Table 3-1 identifies vector
**72/IRQ56 as PCTLA (Port A pin interrupt)**, and vector
**73/IRQ57 as PCTLB**.
The callback then reads original M4 state global `0x1FFEA034`:
- nonzero: tailcalls original scan `0x1FFD7FB0` directly;
- zero: sets `R0=10`, `R1=1`, tailcalls original
  **`0x1FFD53BA` (RTOS SetEventFlags)**. This is the
  **precise event-bit-0 producer** waking the keyboard worker.

A **separate callback `0x1FFD7D5A`** sets event bit
`0x4` for object10, not keyboard scan; a separate software
timer callback near `0x1FFD7FA0` sets **bit 0x2**.
A recurring LPTMR0 interrupt alone is therefore
**insufficient** to schedule a matrix scan, although it
is required for other M4 work. Do not equate event-bit2
or A7 `status=5` timeout notifications with keyboard events.

### Cold-boot / resumed-QEMU evidence

An original unchanged OSUP cold-boot **write watchpoint**
on real M4 `0x1FFF4F08` (event object10 flags) stopped
only for early zero initialization (M4 PCs
`0x1FFE377E`, `0x1FFD3DDE`, `0x1FFD447C`).
The original keyboard worker entered `0x1FFD7B08`
and waited at `0x1FFD7B1A` with bitmask 7.
**No nonzero bit0 post was observed in 75 seconds**.
The original A7 then repeatedly got `0x0804=1` until
board input voltages changed, and subsequently received
only event **status5/type0/subtype0** in the version-dialog
queue, not key-down **type2/subtype1**.

A separately saved original-firmware `version-event-wait`
checkpoint had original M4 flags object10 at
`0x1FFF4F00`, flags word `0x1FFF4F08=0`,
and M4 NVIC ISER1 `0xE000E104=0x0F000010`
(IRQ56 and IRQ57 **enabled**).
The corresponding NVIC pending register
`0xE000E204=0`; no PCTLA IRQ was pending.
At this checkpoint, GPIOA pins are driven or externally
pulled high where expected, but all **PORTA.PCR[0..31]
IRQC fields at 0x4103F000..0x4103F07C are zero**,
so changing column inputs does **not** necessarily
produce a configured PORTA pin interrupt yet.
By contrast PORTB PCR registers contain nonzero IRQC
configuration, including PTB6 IRQC=0x8.
This is a vital independent observation: merely
connecting NVIC IRQ56 does not establish why original
firmware left PORTA pin interrupts disabled in the
checkpoint. Investigate M4 input mode/arming code and
actual PCTLA configuration before claiming real keys.

The output of an actual Cortex-M4 GDB snapshot showed
original VTOR `0xE000ED08=0x1FFD0000`, vector72
entry `[0x1FFD0120]=0x1FFED6D1` (generated
vector trampoline), and vector73 entry
`[0x1FFD0124]=0x1FFED6F9`.
Do **not** assume a generated trampoline has a
one-to-one handler until its runtime handler table
is inspected.

## Suggested Ghidra renames

`Confirmed` means original decomp/Thumb instruction
semantics with explicit calls or a live execution
checkpoint. `Likely` denotes narrower inferred role,
not necessarily an original developer symbol.
For original M4 use the binary loaded at
`0x1FFD0000`; A7 labels require its separate load.

| Address | Suggested rename / comment | Confidence and basis |
|---|---|---|
| `0x1FFD7B08` | `M4_KeyboardEventWorker` | Confirmed: RTOS task entry |
| `0x1FFD7B1A` | `M4_KeyboardEventWait_CallSite` | Confirmed: R0=10/R1=7, calls wait |
| `0x1FFD6BAC` | `M4_RTOS_WaitEventFlags` | Confirmed: accepts event object/mask |
| `0x1FFD7B28` | `M4_KeyboardEventBitsReturned` | Confirmed: reads saved bitfield |
| `0x1FFD7B2E` | `M4_KeyboardBit0Dispatch_CallSite` | Confirmed: invokes scan |
| `0x1FFD7FB0` | `M4_KeyboardScanIfEnabled` | Confirmed: M4-state gating |
| `0x1FFD7FCA` | `M4_KeyboardFullScan_CallSite` | Confirmed: BL target 0x1FFD8634 |
| `0x1FFD8634` | `M4_ScanKeyboardMatrix9x8` | Confirmed: original row/column scan |
| `0x1FFD8412` | `M4_KeyboardDriveRow` | Likely: entry in row-drive helper |
| `0x1FFD8564` | `M4_KeyboardScanColumn` | Likely: input-column helper |
| `0x1FFD85C6` | `M4_KeyboardSampleColumn` | Likely: PDIR sampling |
| `0x1FFD8610` | `M4_KeyboardDebounce` | Likely: repeated stability check |
| `0x1FFD7D2E` | `M4_PCTLA_KeyWakeIRQ_Handler` | Confirmed: NVIC vector72 cleared then sets flag bit0; exact registration via trampoline still to verify |
| `0x1FFD247A` | `M4_NVIC_ClearPendingVector` | Confirmed: NVIC ICPR bit of (R0-16) |
| `0x1FFD53BA` | `M4_RTOS_SetEventFlags` | Confirmed: R0 object ID10/R1 flag1 |
| `0x1FFD7D5A` | `M4_KeyboardAuxBit2Notify` | Confirmed: event object10 mask 0x4, actual IRQ source undetermined |
| `0x1FFD7FA0` | `M4_KeyboardTimerBit1Callback` | Likely: object10 mask0x2 callback, static |
| `0x1FFD7D6E` | `M4_KeyboardInitialize` | Likely: sets state, creates original RTOS timer |
| `0x1FFD655E` | `M4_RTOS_CreateTimer` | Likely: called with callback 0x1FFD7FA1 |
| `0x1FFF4F00` | `m4_rtos_keyboard_event10_object` | Confirmed in *this* cold-boot VM; runtime allocated, not a constant ROM address |
| `0x1FFF4F08` | `m4_rtos_keyboard_event10_flags` | Confirmed in *this* VM, write-watchpoint address |
| `0x1FFEA034` | `g_m4_keyboard_direct_scan_mode` | Likely: zero selects posted event rather than direct scanner |
| `0x1FFEA320` | `g_m4_keyboard_scan_state` | Likely: gate read by scan helper |
| `0x60010868` | `A7_BIOS_VersionDialog_KeyGate` | Confirmed: real original decomp |
| `0x60009FB0` | `A7_BIOS_ReceiveEvent` | Confirmed: blocking RTOS event read |
| `0x600108CC` | `A7_BIOS_CopiedKeyEventCheck` | Confirmed: original debugger event stack |
| `0x6003A878` | `A7_BIOS_FactoryTestMenu` | Confirmed: original factory menu entry, synthetic debugger branch only so far |

**Port / NVIC MMIO labels** (peripheral addresses, do not mark as
functions):

| MMIO address | Label | Meaning |
|---|---|---|
| `0x4100F010` | `M4_GPIOA_PDIR` | A pin sample; A31/A23 keyboard columns |
| `0x4100F050` | `M4_GPIOB_PDIR` | B pin sample; B6 keyboard column |
| `0x4103F000` | `M4_PORTA_PCR0` | 32 PCR register slots through +0x7c |
| `0x4103F05C` | `M4_PORTA_PCR23` | Logical key 0x94 column A23 control |
| `0x4103F07C` | `M4_PORTA_PCR31` | Logical key 0x93 column A31 control |
| `0x4103F0A0` | `M4_PORTA_ISFR` | Sticky interrupt pin bitmap |
| `0x41040000` | `M4_PORTB_PCR0` | Original B pin controls |
| `0x410400A0` | `M4_PORTB_ISFR` | Original B interrupt flags |
| `0xE000E104` | `M4_NVIC_ISER1` | IRQs 32–63 enable; bit24 = PCTLA56 |
| `0xE000E204` | `M4_NVIC_ISPR1` | IRQs 32–63 pending |
| `0x1FFD0120` | `M4_Vector72_PCTLA_HandlerPtr` | Runtime vector to 0x1FFED6D1 |
| `0x1FFD0124` | `M4_Vector73_PCTLB_HandlerPtr` | Runtime vector to 0x1FFED6F9 |

## Emulator experiment and remaining validation

Research-only **`EXESX_EXPERIMENTAL_M4_PORT_IRQ=1`**
adds a virtual-time host-input sampler to M4 PORTA/B.
It uses *original guest-written* PCR.IRQC (disabled,
low, rising/falling/either, high), drives PCR.ISF and
ISFR sticky status only for a matching electrical
condition, and connects those flags to the real
M4 NVIC IRQ56/57. W1C synchronizes PCR.ISF and ISFR;
no firmware RAM/RTOS flag/IPC response is written.
External contact is still driven through
`EXESX_M4_KEY_MATRIX_FILE` and GPIO direction
via `--matrix-keys --port-irq --lptmr-irq`.

`scripts/probe_m4_port_irq.py` runs synthetic ARM instructions
to configure PCR23 and switches external PTA23 voltage during
execution, checking PORT.ISFR and M4 NVIC IRQ56 and
two negative controls (disabled bridge/disabled IRQC).
Only when both Windows and Linux CI pass may the new
QEMU hardware bridge be considered tested. **No genuine
A7 keyboard event or usable TEST MENU is claimed yet.**
The actual ROM currently leaves PORTA PCR.IRQC disabled
at the saved checkpoint, so the remaining question is
*which original M4 mode/initialization should arm the
PCTLA pin IRQ*, and/or whether another GPIO pin needs
to be stimulated to dispatch the scan.
