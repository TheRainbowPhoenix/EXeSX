# DY357 BIOS factory TEST MENU: verified event sequence and caller
**2026-10-23.** Derived from the owner-provided decompiled **XD-SX9850.0.c**,
and prior private original-firmware execution. Only addresses, conditions, and
short diagnostic string names are committed. The 33 MB original decomp, ROM,
event trace, screenshots, and original installed eMMC are **not** uploaded.

## Direct original A7 route, not an OS shortcut

In the actual BIOS at `FUN_60010868`:

1. Draw the centered version dialog `FUN_600105CC` (verified on genuine
   QEMU with the original ROM).
2. Poll `FUN_6001D524` (IPC request `0x0804`) with repeated
   125-unit firmware timer delays while the M4 result is nonzero.
   This gate was **actually cleared** by changing only external M4 input
   voltages *after* initial boot, as recorded in
   `2026-10-23-dy357-m4-input-ready-0804.md`.
3. Call `FUN_6001D77C(0xffffffff)` (sends IPC request `0x0803`),
   then repeatedly receive a typed keyboard/system event with
   `FUN_60009FB0(buffer,0xffffffff)`. For this parameter the decomp
   routes through `FUN_60009F68` and blocking kernel wrapper
   `FUN_601D7404`; **do not assume it is the direct mailbox-ID-1
   peek**, which is a different branch when the second parameter is 0/1.
4. When event fields are `type == 2` and `subtype == 1`, it consumes
   a 16-bit key code and resets its ten-unit non-key-event counter.

Exact accepted key-code state machine:

- Initially `consecutive_0x93 = 0`.
- `0x93` increments this count until it reaches 4; a fifth consecutive
  `0x93` resets it to 0.
- Once at least **two** consecutive `0x93` events have arrived,
  a subsequent **`0x94` returns `0xffffffff` immediately**.
  The minimal diagnostic entry sequence is `0x93, 0x93, 0x94`.
  Other key codes reset the count. These are **original firmware
  logical codes, not authenticated physical Left/Enter labels**.
- `0x80` or `0x95` calls the normal dialog-cleanup path and
  returns `0`. Ten events with `local_34 == 5`, in the absence
  of an intervening accepted key-down event, also end the dialog
  normally. The decomp does **not** establish whether such
  countdown events should occur under the current emulator.

The caller is `FUN_60011CA4` (contains the direct call around
`0x60012xxx`), in its special startup mode
`_DAT_6232E33C == 0x80`, after `FUN_6001D93C` succeeds.
On a **nonzero** version-dialog result it initializes test state,
issues IPC/power setup, and calls **`FUN_6003A878()`**.

`FUN_6003A878` contains the **actual BIOS `TEST MENU`**, not a
missing main-OS file: it has options for MANUAL CHECK, ARM PATTERN
checks, FINAL ASSEMBLY, FFT, WLAN, LCD UNIT CHECK, VERSION and OS UPDATE.
`LCD UNIT CHECK` (menu ID 10) dispatches into `FUN_60058008`.
This strongly suggests the **factory test menu can be reached from the
BIOS without executing OS code at 0x60400000**, provided actual key
events reach the BIOS with proper initialization. This is a **static
control-flow conclusion**, not an observed menu boot.

## Real execution breakpoints / missing event production

The private original-ROM QEMU with staged host-only pin levels
successfully hit `0x60010898` with `R0=1` then `R0=0`,
and `0x600108A8` (begin keyboard-event wait), but no key event
return, dialog exit, test menu or OS trampoline was seen within the
bounded observation. A second **58-second** private GDB
experiment armed true original M4 keyboard-scanner addresses
`0x1FFD8412` (drive row), `0x1FFD8564` (scan),
`0x1FFD85C6` (read column), `0x1FFD8610` (debounce)
after `0x600108A8`, and pulsed external M4 GPIOA bit31 low
then high for ~1.75 host seconds. **None of these scanner PCs
was observed**, nor was an A7 event return / menu entry.
Bounded missing hits do not prove those routines can never execute,
nor that bit31 maps to a certain physical key in every matrix phase.

The opt-in private `scripts/probe_ipc_0804.py` now includes
one-shot A7 instruction milestones:

- `0x600108B4`: event-read return
- `0x600108CC`: event type check
- `0x60010910`: diagnostic code/sequence path
- `0x60010974`: normal dialog exit
- `0x6003A878`: **actual BIOS test-menu entry**
- `0x60058008`: LCD UNIT CHECK dispatcher target

**Next** identify the actual M4 row scanner *scheduling / wake condition*
after IPC `0x0803`, and the A7 event enqueuer / correct delivery
path. Test a normal externally induced key transition with response
metadata and the A7 keyboard-event buffer. Do **not** inject key
codes directly into the BIOS queue, overwrite a return register, jump
to `0x6003A878`, or hardcode the result of `0x0804` and
claim a genuine boot.
