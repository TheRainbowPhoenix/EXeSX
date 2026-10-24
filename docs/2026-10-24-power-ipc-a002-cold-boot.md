# Cold-start IPC power-service and M4 interrupt differential — 24 October 2026

The owner's unchanged `OSUP.BIN` was executed with the GitHub Actions
native QEMU build in local fresh-backing QCOW2 cold boots. All logs below
remain private; no proprietary firmware or memory dumps are committed.

## Correct original firmware classification

Original A7 decomp `XD-SX9850.0.c` shows:

- `FUN_60008CBC(setting)` calls `FUN_601782C8(2,0xA002,&setting,1)`.
- `Power_SendSettingCommandA002(setting)` also calls the synchronous
  IPC service `0xA002`. It then reads the power-state shared value.
- `FUN_60009284()` sends service `0xA004` with one argument `2`.
- `FUN_600065FC(argument)` sends service `0xB000`.

Thus **A002 is a power-setting service, NOT a storage command.**
The prior `0xA002` slot observation must not be described as a USDHC
device hang.

## Original A7 live software-breakpoint evidence

The real `0x601782C8` synchronous IPC entry was intercepted with
read-only RSP `Z0` breakpoints in an unmodified original firmware run:

| Approx. host time | R0 (service target) | R1 (service ID) | Source |
| --- | --- | --- | --- |
| 1.25 s | 2 | `0xB000` | `FUN_600065FC` |
| 1.52 s | 2 | `0xA004` | `FUN_60009284` |

At the second call, original shared slot `0x2F02800C` contained
`0x0001B000`. After 22 host seconds with GDB tracepoints attached,
no further entry breakpoint at `0x601782C8` or A7 event wait
`0x600108A8` occurred, and that slot still contained `0x0001B000`.
**Do not infer the current A7 service call from a single stale
shared-slot word: it must be matched with A7 R1 and observed completion.**
GDB breakpoints materially alter host/virtual-time pacing.

By contrast, independent no-GDB QMP samples during a 6-second run
show `0x0001A002` in the same slot with status transition
`0x04020800` to `0x040208FF`. We have not yet established the
semantic meaning of the low `0xFF` byte, so it is not a proven
error or completion code.

## Mailbox + exception differential (no debugger)

Unmodified original firmware, independent 6-second QMP samples,
same QEMU build and emulated eMMC. MU mailbox tracing recorded:

| Configuration | M4 TX accepted | A7 RX consumed | QEMU invalid Cortex-M exception-return warnings |
| --- | ---: | ---: | ---: |
| Previous LPTMR IRQ model, uncalibrated 1 MHz clocks | 307 | 307 | 25,394 |
| LPTMR1 PCS=01 selected 1kHz; A7 TPM6 32kHz; M4 TPM0 48MHz diagnostic | 314 | 314 | 6,433 |
| LPTMR IRQ disabled | 1 | 1 | 20 |

The large `M profile return from interrupt with misaligned PC is
UNPREDICTABLE on v7M` volume is real QEMU diagnostic output. It is
correlated with the active interrupt model, but its precise causal
relationship to the power IPC service and original M4 exception return
must be proven before modifying QEMU interrupt semantics.

The actual low-power timer PCS=01/PSR=0x05 selects a 1 kHz low-power
oscillator and the firmware uses a compare value of 4; this is
hardware-grounded. A7 TPM6 and M4 TPM0 rates remain experimental.

**Result: neither the sampled power slot nor the version dialog
was cleared/reached in these bounded tests. The authentic keys are
already known to reach the BIOS factory-menu entry from a saved
version-event-wait snapshot, but current cold boot still does not
create that snapshot.**

Next: trace M4 IRQ exception entry/return and the service worker for
A7 `0xB000` and `0xA004`; measure genuine completion of each command
before tracing subsequent `0xA002`. Do not force a reply or patch
original ROM.
