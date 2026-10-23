# Original DY357 M4 matrix: true scanner execution and row-gated contact model

23 October 2026. The source of all original addresses and table entries below
is the owner-supplied checksum-valid **unchanged OSUP.BIN** (never committed)
with SHA256 `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`.
Firmware data and complete runtime logs remain under private local directories.

## Genuine M4 keyboard scanner is now executing

A 95-second private native-QEMU GDB run against original source-derived
firmware/eMMC, `EXESX_EXPERIMENTAL_LPTMR_IRQ=1`,
DMA1 M2M, MU, LPIT1, experimental LCD and initial GPIOA=0/GPIOB=0x88,
observed these **actual M4 thread-2 instruction breakpoints**:

- M4 `0x1FFD8610` keyboard debounce, 0.26 s
- M4 `0x1FFD8564` column scan, 0.70 s
- M4 `0x1FFD8412` drive row, 1.14 s
- M4 `0x1FFD85C6` read column, 1.58 s
- M4 `0x1FFED3B0` actual LPTMR0 IRQ handler, 2.03 s

These routines previously **did not fire** with missing LPTMR0 NVIC
delivery. Their execution confirms a genuine original-firmware
scanner, **not** yet a delivered logical key event.

The original A7 then reached `0x60010898` (service 0x0804 returns 1);
changing only external M4 GPIO voltage files to
A=`0x808c6008`/B=`0xc8` caused the *real M4 response* to
switch to 0. A7 actually hit `0x600108A8` (event reader),
and `0x600108B4` (event reader return R0=0).
Reading the **live event-reader stack** at A7 SP=0x620FFF78
showed `local_34 == 5`, the original firmware's timeout-class
event; its type/subtype were **not** the required key-down
`2/1`. Host GPIOA31 column-only low pulses still produced
no validated diagnostic keyboard event. The presence of an A7
event-reader return or R0=0 alone **does not establish a keypress**.

## Original relocated Thumb firmware: row drive, debounce and mapping

Read original M4 image from OSUP offset `0x001ED8A0` mapped to
`0x1FFD0000`. Thumb `0x1FFD8412` uses a 9×12-byte row
lookup table at **`0x1FFD0DA8`** to select either
M4 GPIOB `0x4100F040` or GPIOA `0x4100F000`.
When requested to activate a row it writes a one-bit mask
to **GPIO.PCOR (port + 0x08)** and configures that pin
as an output. Another helper `0x1FFD8564` picks an
8-column input, reads **GPIO.PDIR (port + 0x10)**,
inverts selected pin bits (**active-low contacts**), and
compares three consecutive readings for stability.
`0x1FFD8610` includes repeated keyboard debounce cycles.

The original ROW table maps indices 0–8 to:
`B2, A9, A2, A11, A15, A16, A17, A20, A21`.
The COLUMN table at `0x1FFD0D48` maps 0–7 to:
`B6, A3, A13, A14, A18, A19, A23, A31`.

The original `9×8` little-endian logical keycode matrix
at `0x1FFD0E14` uniquely locates:

| Firmware keycode | Row, column | Original M4 GPIO row | Original M4 GPIO column |
| --- | --- | --- | --- |
| `0x93` | row 8 / col 7 | A21 | A31 |
| `0x94` | row 6 / col 6 | A17 | A23 |
| `0x95` | row 5 / col 6 | A16 | A23 |
| `0x80` | row 0 / col 0 | B2 | B6 |

This is a source-derived **electrical matrix** mapping, not proof of
the human-facing key names. The previous host approach pulled one
column low continuously for the duration of a "press", affecting
every scanned row and potentially causing ghost/incorrect keys.

## New research-only physical contact input, NOT A7 event injection

`hw/arm/exesx-imx7ulp-keyboard.inc` adds the explicit opt-in
`EXESX_M4_KEY_MATRIX_FILE=/private/path/key.txt`.
The private file has one numeric firmware key code
(e.g. `0x93`, or `0` to release). QEMU maps it through the
**verified original row and column tables** and drives the selected
column low **only if the guest's own GPIO.PCOR selected the matching
row, PDDR still makes that pin an output, and PDOR is low**.
Other columns remain at externally configured inactive levels.
No ROM/guest RAM is patched and no A7 event, M4 service result, or
NVIC interrupt is invented. The original M4 must still scan,
debounce and publish the resulting key event via MU to the A7
event queue. This input source defaults **off** if the file
is absent; it is not a claim of authenticated physical
wiring, only an opt-in source derived from the matching firmware's
own pin-selection table.

`scripts/drive_factory_menu.py --matrix-keys --lptmr-irq`
uses this opt-in file as a Python-driven virtual contact:
it writes `0x93`, releases to `0`, then repeats `0x93`
and `0x94` while running the genuine original firmware
from its existing private QCOW2 `version-event-wait` checkpoint.
No synthetic BIOS event responses are involved in this mode.
`scripts/probe_m4_key_matrix.py` uses an actual synthetic ARM guest
to exercise real M4 GPIOA output-row selection and PDIR reads,
including no-input-file and output-direction priority controls.
Both native Windows and Linux CI build/run this test.

**Success requires more evidence than an input voltage read.**
An original-firmware GDB trace must show:
(1) original M4 scanner active after the contact closes;
(2) genuine A7 `0x600108B4` event reader return whose
type/subtype and keycode are `2/1` and
`0x93`/`0x94`; and (3) authentic BIOS PC
`0x6003A878` reached with no debugger-synthesized event.
The actual factory menu `0x400B` initializer remains a
separate required service for *visible* menu options.

## Private Windows invocation once a passing artifact is available

```powershell
# First create and save a version dialog checkpoint if absent.
py -3 .\scripts\drive_factory_menu.py $osup `
  --qemu .\qemu-system-arm.exe `
  --profile .\profiles\imx7ulp-early-boot.ini `
  --output-dir .\private\factory-menu `
  --matrix-keys --lptmr-irq --seconds 90 --trace-m4

# Follow-up: fast restore same firmware state, drive real matrix contacts
py -3 .\scripts\drive_factory_menu.py $osup `
  --qemu .\qemu-system-arm.exe `
  --profile .\profiles\imx7ulp-early-boot.ini `
  --output-dir .\private\factory-menu `
  --resume --matrix-keys --lptmr-irq --seconds 50 --trace-m4
```

`factory-menu-probe.json` distinguishes the host's
`physical_matrix_contact_closed` events from original
`guest_breakpoint` events. Only an observed guest
`factory_test_menu` PC can set `factory_menu_observed=true`.
Do not publish the QCOW2, synthetic eMMC, raw ROM-derived ELF or LCD.

## Genuine original firmware snapshot experiment: still no accepted keyboard event

**Distinct from the passing synthetic ARM test above**, an original
owner-held unchanged OSUP run used the compiled Linux QEMU corresponding
to commit `fadb83883541e319062bf277c6cc2de9c7e3c3ab` and a
**real previously saved** QCOW2 `version-event-wait` checkpoint.
Original A7 IPC `0x0804` was verified R0=1 before the GPIO voltage
transition, R0=0 after, and A7 PC `0x600108A8` was reached. The
saved checkpoint includes M4 VM state and source-derived eMMC bytes
and was restored into a fresh QEMU process.

With `EXESX_EXPERIMENTAL_LPTMR_IRQ=1` and
`EXESX_M4_KEY_MATRIX_FILE` enabled on the restored emulator,
the Python host drove **0x93, release, 0x93, release, 0x94,
release** (each closed for 3 seconds, with 2-second release gaps).
The original A7 event reader returned repeatedly, but
the **ten observed copied records** at `0x600108CC` all had
`local_34/status = 5`, `event_type=0`,
`event_subtype=0`, not accepted key-down type 2 / subtype 1;
there was **no genuine original keycode 0x93 or 0x94**.
No authentic menu-entry PC `0x6003A878` executed.

M4 LPTMR0 interrupt handler `0x1FFED3B0` was observed
once after reload, but the original M4 scanner breakpoints
`0x1FFD8412` / `0x1FFD8564` / `0x1FFD85C6` /
`0x1FFD8610` did **not** fire again in the bounded
post-checkpoint replay. This contrasts with the **separate
cold-start** original-ROM trace, where scanner instructions
executed early in initialization. Do **not** infer from
the earlier trace that LPTMR0 itself always starts recurring
scans; initial and periodic scheduling must be separated.

New static Thumb reverse engineering identifies the actual
full matrix scan caller `0x1FFD7FCA` and full scanner
`0x1FFD8634`. Its parent `0x1FFD7FB0` reads the M4
scan-state word at `0x1FFEA320` (literal loaded at
`0x1FFD860C`) and bypasses scanning for certain
nonzero states. A focused second private QEMU replay
sampled `0x1FFEA320=0` at an M4 timer ISR, but did not
hit **any** of these scan-task entry/call breakpoints
after checkpoint reload; the disabled condition may be
a task scheduler/wake dependency rather than that state
word alone. This is bounded negative execution evidence,
**not yet proof of a permanent scheduling failure**.

The private Python driver now optionally records repeated
M4 entries `0x1FFD7FB0`, `0x1FFD7FCA`,
`0x1FFD8634`, the LPTMR ISR, original NVIC
pending/enabled bits, and the M4 `0x1FFEA320`
scan-state word with `--trace-m4`.
Only genuine A7 copied event fields count as keys.
A new complete cold original-firmware validation
with the latest runtime is still required before declaring
hardware key support or merging this experiment.

### Next precise hardware target

Identify **which M4 scheduler ISR or IPC mode-0x0803
callback dispatches the task at `0x1FFD7FB0`**,
why it does not reexecute after version-dialog checkpoint
restore, and whether QEMU is missing a required NVIC or
timer/RTC wakeup. Then verify actual original M4
`0x1FFD7FCA` scan calls and A7 type=2/subtype=1 events
for each host matrix contact. Do not fabricate a BIOS
event or set the M4 task-state word by hand.
