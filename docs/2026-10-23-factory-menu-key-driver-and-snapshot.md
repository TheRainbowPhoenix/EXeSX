# DY357 factory keyboard candidate inputs and fast QEMU checkpoint

**23 October 2026. Private original firmware only.**
Do not upload `OSUP.BIN`, extracted ELF, synthetic installed eMMC,
`*.qcow2`, LCD dumps, or complete QEMU instruction traces to GitHub.

## Result of original Casio boot experiment

The original ROM's `FUN_60010868` requires actual delivered A7
type=2/subtype=1 key-down events. A sequence of logical codes
**`0x93, 0x93, 0x94`** makes it return nonzero, reaching
`FUN_6003A878` (genuine factory `TEST MENU`). That is
confirmed by the owner's decomp; it is **not** evidence of executed
test-menu code.

We built a Python-driven hardware *candidate* input interface using the
existing opt-in M4 GPIOA/B external-voltage files, with the first usable
private persistent QCOW2 checkpoint on the version dialog.
`scripts/drive_factory_menu.py` boots normally with A=0/B=0x88,
waits for real `0x0804=1`, then changes external inputs to
A=0x808C6008/B=0xC8. The original M4 is responsible for producing
`0x0804=0` (previously confirmed by dual-core QEMU). At
A7 instruction `0x600108A8` it executes QEMU **`savevm
version-event-wait`** in a persistent **QCOW2 overlay** with explicit
raw backing format, while leaving the underlying sparse 15GB updater
media unmodified. The snapshot includes VM RAM/CPU and QCOW2 changed
sectors, not just the firmware's PC.

The actual owner-private native QEMU run saved
`version-event-wait`; starting a **new QEMU process** with
`--resume` loaded that snapshot and reached genuine
A7 PC `0x600108A8` at approximately **0.9–1.5 seconds**
(the cold original boot reached the same PC around 25 seconds).
The source-derived eMMC raw file **must stay at its original absolute
path**, because QCOW2 embeds its backing-file location.
A firmware-free regression `scripts/probe_factory_snapshot.py`
verifies savevm/loadvm across separate QEMU processes using an
actual synthetic ARM guest, comparing RAM before/after.

## Candidate key-pulse interface: no menu reached yet

The `--keys` option drives **real emulated external pin levels**,
not A7 RAM or kernel RTOS messages. The original M4 lookup associated
logical code 0x93 with GPIOA bit31 *column*, 0x94/0x95 with
GPIOA bit23, 0x80 with GPIOB bit6. That alone does **not**
identify a physical key: another M4-controlled **row**
must also be selected, debounced and delivered over M4/A7
IPC. The host script drives active-low candidates, releases
to the A=0x808C6008/B=0xC8 ready-state, and records both the
actual original A7 event-return breakpoint and test-menu PC.
The script never calls `FUN_6003A878` itself or overwrites
a firmware event queue.

A private cross-process --resume test drove the complete
**0x93, 0x93, 0x94** candidate column pulses:
- External GPIO mask changes were recorded for each press/release.
- **No real A7 `0x600108B4` event-reader return** or
  `0x6003A878` menu entry was observed.
- The original M4 scanner / key-debounce breakpoints
  `0x1FFD8412`, `0x1FFD8564`, `0x1FFD85C6`,
  `0x1FFD8610` also did not fire in the bounded replay.
- No text beyond the original centered MODEL/version dialog.
This is a real **negative hardware-model result**,
not successful virtual key injection. Keyboard
scanner scheduling / row drive / event enqueue remains the
next prerequisite for an authentic menu.

## Run on Linux or Windows

Use the native QEMU distribution built on this PR. On Windows,
run from the extracted distribution directory in PowerShell:

```powershell
$osup = "C:\Users\Phoebe\Downloads\OSUP.BIN"
py -3 .\scripts\drive_factory_menu.py $osup `
  --qemu .\qemu-system-arm.exe `
  --profile .\profiles\imx7ulp-early-boot.ini `
  --output-dir .\private\factory-menu `
  --seconds 90 --keys "0x93,0x93,0x94" --trace-m4

# Subsequent attempts: reuse the persisted 25-second checkpoint
py -3 .\scripts\drive_factory_menu.py $osup `
  --qemu .\qemu-system-arm.exe `
  --profile .\profiles\imx7ulp-early-boot.ini `
  --output-dir .\private\factory-menu `
  --resume --seconds 30 --keys "0x93,0x93,0x94" --trace-m4
```

Use an **empty output directory** for the first run:
`--resume` is mandatory once `dy357-menu-checkpoint.qcow2`
exists. The tool will not silently overwrite snapshots.
Keep the `a7-bios-os.elf`, raw media, input-voltage files
and QCOW2 overlay in the same `private\factory-menu`
directory and do not move the raw media. The generated
`factory-menu-probe.json` logs original A7/M4 breakpoint
hits separately from **candidate** host input pulses.
Only `factory_menu_observed:true` with a real breakpoint
at `0x6003A878` verifies reaching the menu.

If the menu becomes reachable, the driver also saves
a second named `factory-menu` snapshot at first menu
entry (before it has necessarily painted the LCD).
The **main OS** at `0x60400000` remains a distinct route
and is not reached by forcing CPU PC or fabricating keys.

Next engineering step: investigate original M4 ISR/task scheduling
for scanner `0x1FFD8412` after A7 requests input mode
via IPC `0x0803`, and determine the row/column protocol.
Check whether the scan is interrupt-driven, GPIO-triggered,
or disabled due to another modeled MCU peripheral, then
provide a native emulated keyboard source with verified
row stimulation and real M4 IPC-to-RTOS event delivery.

## Separate synthetic debugger-only preview: BIOS menu entry achieved

This is **not** a hardware keyboard test, and must never be reported
as a real original M4 keypress. The hardware GPIO candidate experiment
above still produced **no key events**.

Using the genuine owner-private original firmware resumed from the
validated `version-event-wait` QCOW2 snapshot, a second opt-in
experiment stopped at A7 `0x600108B0` (the instruction that calls
the blocking event reader), placed a synthetic 40-byte event-return
record in its **volatile guest stack**, and set **CPU0 R0=0 /
PC=0x600108B4** to skip *only that one blocked call*. The synthetic
record used the real decompiled event ABI: status word at record+8=0,
type=2/subtype=1 at record+16/18, key-code halfword at record+24.

Three explicitly synthetic injected records, `0x93,0x93,0x94`,
caused genuine untouched BIOS control flow to hit:
- A7 `0x60010910` twice, with R0=`0x93` and R4=0 then 1;
- A7 `0x60010928`, R0=`0x94`, R4=2;
- **A7 `0x6003A878`**, the actual original BIOS factory-menu
  entry, R0=`0xFFFFFFFF`.

The corresponding host-only QCOW2 **`factory-menu-synthetic`**
snapshot was successfully saved at that original menu entry.
This proves the BIOS version-dialog/menu-branch logic is executable;
it does **not** demonstrate the M4 scan, keyboard IRQ/IPC delivery,
or successful visual display of the menu.

Resuming `factory-menu-synthetic` in another QEMU instance and
allowing 10 more seconds generated an **entirely black 864x480 LCD**
instead of menu text. Original-ROM A7 breakpoints then reached
`FUN_6003A878` and its initializer `FUN_6003A7D4`,
returning from `FUN_6000FF90`, `FUN_60008E28`,
and `FUN_60008EC0`, but **not returning** from the next
`FUN_6002D5D0(2)` within a bounded 20-second run.
Ghidra shows this call requests BIOS service **0x4009**
via `FUN_600061C4`, then service **0x400B** with argument
2 via `FUN_60006240`, conditional on boot-mode flags.
Which service is awaited, and its real M4/IPC response semantics,
still requires execution-level investigation. The first currently
demonstrated post-menu-entry wait is separate from the keyboard gate.

The source-controlled `scripts/probe_synthetic_factory_menu.py`
reproduces this *debugger-only control-flow experiment* with an
explicit acknowledgement flag:

```powershell
py -3 .\scripts\probe_synthetic_factory_menu.py `
  --qemu .\qemu-system-arm.exe `
  --output-dir .\private\factory-menu `
  --allow-synthetic-events --seconds 15
```

It will refuse to run without `--allow-synthetic-events`.
It requires the owner's original private `version-event-wait`
checkpoint created by `drive_factory_menu.py`, never uploads
firmware or snapshot, and saves a second private snapshot only when
the **real BIOS `0x6003A878` breakpoint** fires.
The command deliberately changes A7 RAM registers at the event
reader, so it must **never** be described as functional emulated
keyboard hardware or a genuine full boot.

**Remaining two independent tasks:** fix/verify M4 scanner scheduling
and real event delivery (authentic keypress), and then trace service
0x4009/0x400B in the factory menu initializer (actual visible menu).
