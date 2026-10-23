# Genuine M4 hardware key contacts: no-debugger original-firmware replay (24 October 2026)

This experiment uses the owner's unchanged private OSUP image and
previously saved real QEMU `version-event-wait` VM checkpoint.
No proprietary BIOS/M4/ELF/eMMC/VM image, raw IPC payload, or private
trace is checked into the EXeSX repository.

## Evidence that must NOT be conflated

The source-backed route is:

```text
Python physical-contact file = 0x93, release, 0x93, release, 0x94
  -> guest-selected IOMUXC0 and GPIO row/column voltage
  -> real M4 PORTA PCR.IRQC / IRQ56
  -> real M4 keyboard matrix read
  -> real TPM0 IRQ38 -> M4 debounce state machine
  -> original M4 key event: type2/subtype1, code 0x93
  -> M4 keyboard queue (SRAM)
  -> [still unverified] forwarded M4-to-A7 IPC payload / MU
  -> [still unverified] A7 version dialog accepts 0x93, 0x93, 0x94
  -> [still unverified] original BIOS factory TEST MENU 0x6003A878
```

The no-debugger test runs QEMU **without `-gdb`**. The Python
host writes only the emulated **electrical key-contact file**, uses
QMP `loadvm/cont/stop` to restore/run a private snapshot, and
reads original guest RAM/MMIO using QMP/HMP. No breakpoint, CPU
register write, shared-memory edit, RTOS event injection,
forced NVIC IRQ, or fabricated A7 event-return occurs.

In four bounded physical-contact replays using the verified Linux
QEMU compiled at commit `c753682` and original private checkpoint,
the M4 debounce state and selected physical row/column reacted to
the requested 0x93/0x94 contacts, but no usable TEST MENU
appeared. One separate **QMP-only** held-0x93 run sampled
the actual M4 keyboard event slot:

- At ~0.104 host seconds: original M4 debounce state2,
  selected row8/column7, queue empty.
- At ~0.164 host seconds: M4 state1,
  original queued first word `0x00010002`, actual keycode
  `0x0093` in the subsequent original queue field.
- At ~0.223 host seconds: queue empty again.
- At the end of the run the original A7 was sampled
  in its normal firmware housekeeping function
  `0x601B4148` rather than a proven factory menu.
- The queued record disappearing is compatible with
  the original queue being consumed, **not yet proof
  that M4 MU published its payload or A7 received it**.

A **no-key control** run measured the original A7 at
the private checkpoint resume address `0x600108A8`,
later waiting in the `0x2F02B0B0` event/IPC path, then
out of the version dialog and in regular firmware
housekeeping within approximately **0.12 seconds
of host wall time** on that specific native QEMU
machine. A different `-icount` mode changed host
time, but never established the three authentic
A7 key events. Host timing and the experimental
SoC peripheral clocks are **not hardware calibrated**.

**Do not infer full mailbox delivery from MU.SR bit changes
or a QEMU TR3 doorbell write.** Exact decoded payload must be
matched in the real M4 packet and original A7 received record,
or the version dialog must demonstrably branch to the real
factory menu using unchanged firmware.

## Exact Ghidra labels / reverse engineering map

These addresses are from the owner-supplied M4 at
`0x1FFD0000` (85,872 bytes, exact match to original OSUP
offset `0x1ED8A0`) and unchanged original A7 BIOS.

| Address | Proposed label | Grounding |
| --- | --- | --- |
| `0x1FFD8990` | `m4_keyboard_event_slot_pointer_literal` | Original ROM holds `0x1FFEA34C` |
| `0x1FFEA34C` | `m4_keyboard_event_slot_20bytes` | Original firmware QMP observed type2/subtype1/code 0x93; runtime SRAM |
| `0x1FFD8984` | `m4_keyboard_scan_state_pointer_literal` | Original M4 ROM points at `0x1FFEA320` |
| `0x1FFEA320` | `g_m4_keyboard_debounce_state` | Original real M4 state0/1/2/3 observed |
| `0x1FFEA334` | `m4_selected_key_column_row` | Original chosen column7/row8 packed into 32 bits |
| `0x1FFD8200` | `M4_KeyboardBuildTypedEvent` | Confirmed decomp sets type2, subtype argument, keycode |
| `0x1FFD82D8` | `M4_KeyboardQueueTypedEvent` | Confirmed decomp copies 20-byte type2/subtype1 to original queue |
| `0x1FFD838A` | `M4_KeyboardReadAndRemoveQueuedEvent` | Source-confirmed copies queued record and clears slot when requested; runtime caller undetermined |
| `0x1FFD874A` | `M4_KeyboardDispatchToInterprocessorService` | Decompiled conditional path invokes `FUN_1FFDE672(2,record)` or service 5; dynamic routing not yet confirmed |
| `0x1FFDE672` | `M4_BuildAndPostIPCEnvelope` | Source-confirmed builds 0x28-byte envelope and passes to `0x1FFDE74A` |
| `0x1FFDE74A` | `M4_QueueIPCEnvelope` | Source-confirmed enqueue / signal; MU delivery not yet proven |
| `0x1FFE0CCE` | `M4_NotifyIPCQueue` | Likely: called after original IPC envelope queued, precise peripheral handoff to verify |
| `0x41022020..2C` | `M4_MUA_TR0_3` | Real M4 MU transmit MMIO registers |
| `0x40220040..4C` | `A7_MUB_RR0_3` | Real A7 MU receive MMIO registers |
| `0x41022060 / 0x40220060` | `M4_MUA_SR / A7_MUB_SR` | Status registers only; not keyboard payload |
| `0x60009FB0` | `A7_BIOS_ReceiveEvent` | Confirmed source-decompiled blocking A7 event read |
| `0x600108A8` | `A7_BIOS_VersionDialogEventWait` | Confirmed original version dialog loop |
| `0x600108CC` | `A7_BIOS_CopiedEventTypeCheck` | Source-decompiled type/subtype check |
| `0x60010910` | `A7_BIOS_CheckFirstTwo0x93Keys` | Original code checks pressed code 0x93 |
| `0x60010928` | `A7_BIOS_CheckFinal0x94Key` | Original code checks pressed code 0x94 |
| `0x60010974` | `A7_BIOS_NormalDialogExit` | Source-decompiled timeout and special-key exit |
| `0x6003A878` | `A7_BIOS_FactoryTestMenu` | Original function previously reached with SYNTHETIC event responses only |

## Emulator/model improvement

The matrix input source previously polled
`EXESX_M4_KEY_MATRIX_FILE` at most once every
**20 ms of guest virtual time**; the M4 PORT interrupt
input sampler had the same interval. This was too
coarse for short physical transitions and contributed
unnecessary latency while the BIOS timed out.
On this experiment branch, opt-in *physical key*
input now refreshes at **1 ms of guest virtual
time**, while no-key PORT sampling retains the
previous 20 ms path. Genuine original guest
PCR.IRQC, TPM0 interrupts, row IOMUX, and RTOS
event publication are still required.
**This is contact signal delivery, not a synthetic
keyboard firmware event.** Its hardware timing is
experimental, not measured against a physical unit.

`scripts/drive_physical_menu_qmp.py` is a
replayable, Windows/Linux QMP-only harness.
It copies the original private QCOW2 before
loading, logs the input transitions, and samples
the original queue and MU status into
`physical-keys-results-private.json`.
Optional `--trace` emits a large PRIVATE
read-only QEMU execution/MMIO log, but adds
substantial host overhead and must not be
used to calibrate real keypress timing.
The report contains independent booleans for
M4 queue event, confirmed MU payload,
confirmed A7 key-down, and genuine factory
menu; the latter three stay false until a
stronger original-firmware observation proves
them. Neither snapshot nor source ROM is
uploaded to GitHub.

Example from the Windows ZIP, after saving
the actual owner-private version dialog checkpoint:

```powershell
py -3 .\scripts\drive_physical_menu_qmp.py `
  --qemu .\qemu-system-arm.exe `
  --output-dir .\private\factory-menu `
  --hold 0.12 --gap 0.06 --seconds 2 `
  --overwrite
```

### Next exact blocker

Find original M4 queue consumer and trace
`FUN_1FFD874A` → `FUN_1FFDE672` →
`FUN_1FFDE74A` → real MUA.TR writes alongside
actual A7 `FUN_60009FB0` returned records.
Separately compare the A7 timeout-event virtual-time
source to the genuine M4 debounce cadence and test
a checkpoint before the BIOS expires. Do not
extend firmware timeout by altering the ROM,
and do not claim a visible factory menu until
the unchanged A7 branches into `0x6003A878`
and the LCD draws its native UI.
