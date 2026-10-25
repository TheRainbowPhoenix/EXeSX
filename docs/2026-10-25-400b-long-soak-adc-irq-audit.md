# Original TEST MENU 0x400B(2): 105-second LCD-free soak and M4 ADC audit (2026-10-25)

**Private owner firmware stays private.** Original OSUP SHA256 `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`; experiment used unchanged OSUP-derived A7/M4 guest, original row-gated physical 0x9C+0x90 at cold boot and 0x93,0x93,0x94 after native A7 0x600108A8 event wait. Emulator baseline: successful Linux QEMU from original commit `046058cd15332486ec2c3742de60b2abfb412b23`, original source-derived synthetic eMMC and disposable SD with `snapshot=on`.

## Does leaving the guest running or disabling LCD capture finish 0x400B?

In a **180.12-second** read-only headless replay, the first two cold boots did not reach the dialog and the third reached authentic **0x6003A878** at host time **75.45 s**. The headless GUI worker had its LCD frame acquisition replaced with an absolute no-op for this entire experiment: **zero QMP frame dumps, zero framebuffer mmap reads, zero PNG/PPM image writes**. The only guest interactions were original electrical key contacts plus sparse read-only QMP samples of the IPC word.

The following original shared-memory observations all continued to show `request=0x0001400B`, `argument=2`, and `status=0x04010800` at `0x2F02800C/10/08`:

| Host time | Time after genuine 0x6003A878 menu code entry |
| --- | --- |
| 95.67 s | 20.22 s |
| 115.69 s | 40.24 s |
| 135.70 s | 60.25 s |
| 155.73 s | 80.28 s |
| 175.76 s | **100.31 s** |

The run ended at **104.67 s after menu code entry** without seeing original A7 `0x60006268` (synchronous IPC return) or `0x60057668` (genuine TEST MENU painter); the original A7/M4 QEMU subprocess remained alive. **Slow screenshot conversion is therefore not sufficient to explain the pending service.** A longer timeout does *not* imply the OS would never complete it on better hardware emulation; this specific configuration failed to complete in 105 post-entry seconds.

## Single-CPU-thread and invasive tracing controls

A separate read-only **142.02-second** `-accel tcg,thread=single` run, also zero LCD frames, reached the original A7 version dialog and initial `0x93` checker but **not** the final accepted `0x94` path or menu function. That is a timing/scheduling negative control, **not** evidence for or against 0x400B completion: the synchronous menu service was never submitted.

A separate zero-LCD 160-second multi-thread run adding broad M4 executed-TB filtering slowed and changed startup enough that all three bounded cold-boot attempts missed the original A7 dialog. It cannot prove anything about event-7 behavior *after* 0x400B. Consider enabling costly M4 tracing only from an owner-private genuine post-menu checkpoint or through an even more targeted trace switch. Do not compare exact host seconds across these runs as if they were calibrated guest CPU cycles.

## New original-M4 callback and ADC-IRQ investigation

The **original unchanged M4 ARM Thumb disassembly** was locally decoded from source-proven OSUP offsets, with no original ROM bytes uploaded. In the **successful multi-thread no-LCD replay**, original M4 execution *after* A7 entered `0x6003A878` included `0x1FFE4740` (original `FUN_1FFD537E(7,0x01000000)` RTOS event posting), `0x1FFE4748`, `0x1FFE474E`, and the MU callback `0x1FFE4776`. This is **positive evidence of MU-side callback/event posting**, not evidence the later application-level service response was dequeued/completed. The original A7 `0x60006268` was absent.

The firmware also contains an **original ADC service path** `0x1FFD8E76` that accepts a choice of ADC channel bank. It waits indefinitely on original RTOS object **8 for ADC0** or **7 for ADC1** (via `0x1FFD6320`) and then accesses controller registers at `0x41041000` (ADC0) or **`0x410AD000` (ADC1)**. Its original callers include `0x1FFD93DE` and `0x1FFD9404`. The current emulator source `hw/arm/exesx-imx7ulp-adc.inc` admits it has **no analog source / no conversion result FIFO**; `0x300` reads always return zero and the SW-trigger path at `0x34` only logs. It currently cannot emulate a genuine completed analog conversion and its end-to-end IRQ. That is a **concrete gap worth probing**, but original ADC1's event7 wait is **not yet causally proven to be the awaited `0x400B(2)` handler**. A distinct event-object-7 post does not prove ADC completion.

**Do not solve this by forging a shared `0x400B` reply, forcing A7 PC, posting RTOS event7, or creating ungrounded analog result bits.** Instrument whether ADC1 SW triggers, FIFO/IRQ enable, original consumer `0x1FFD8E76`, and M4 RTOS event wake occur in the same run *after* the exact `0x400B` request. Only then implement a correctly gated, opt-in, hardware-source-backed ADC conversion/IRQ model with real synthetic ARM regression and disabled control.

## Reproducible headless options on new main

In the next successful Windows GitHub Actions artifact, the new CLI flags route through the same read-only headless worker:

~~~powershell
py -3 .\scripts\headless_factory_menu_checks.py "C:\Casio\OSUP.BIN" `
  --qemu ".\qemu-system-arm.exe" --seconds 260 --post-menu-seconds 150 `
  --retries 3 --retry-after 35 --no-screenshots `
  --tcg-thread multi
~~~

For a separate scheduling differential: change **only** `--tcg-thread multi` to `single`. To emit more M4 event7/ADC service executed-TB records into a **private** trace, use `--trace-m4-400b`; enabling this from reset was measurably intrusive and may prevent dialog entry in a bounded run.

A legitimate factory SD check is blocked until original A7 returns from 0x400B at 0x60006268 and really invokes painter 0x60057668. No SD format/write tests or blind ENTER/OK navigation were executed.

## Optional passive ADC correlation probe

With a current build, add `--sample-adc` to the headless command above. Every approximately 20 host seconds after original `0x6003A878`, the *same worker that owns QMP* reads both original ADC MMIO controllers using `xp`:

- ADC0: `0x41041000`
- ADC1: `0x410AD000`
- Registers: `CTRL +0x10`, `STAT +0x14`, `IE +0x18`, `FCTRL +0x30`

The runner records their real guest-visible words in `passive_adc_samples` in a **private** JSON result. A zero or unresolved read **does not alone establish** an ADC trigger or a missing hardware interrupt. Correlate any new ADC activity after service `0x400B(2)` with native M4 execution of its ADC caller/RTOS wait before changing emulation.

No analog sample is synthesized by this probe. QMP framebuffer reads are still disabled by `--no-screenshots`; sampling is limited to the explicitly requested handful of MMIO registers. These experiments do **not** claim the visible factory menu is restored.

### Limitation validated on native QEMU

A direct QMP/HMP `xp` and CPU-1-selected `x` register read of `0x41041000` and `0x410AD000` on the Linux build returned **"Cannot access memory"** rather than ADC register values. Thus passive monitor MMIO sampling **cannot be treated as a successful ADC observation** on that configuration. The optional `--sample-adc` checker now explicitly outputs `accessible:false`, zero decoded registers, and the original monitor error, rather than inventing all-zero ADC status. CPU1 selection did not make these M4 peripheral addresses accessible through HMP.

**Next instrumentation must inspect the original M4 CPU-side bus transactions**, e.g. with the existing guest `-d guest_errors` ADC-write logs, opt-in MMIO plugin or an M4-specific bus hook, rather than concluding anything from the unavailable monitor read. The original 0x400B-to-ADC causality is not yet established; no ADC IRQ model has been changed.
