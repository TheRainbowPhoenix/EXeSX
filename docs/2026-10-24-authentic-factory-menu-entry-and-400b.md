# Original OSUP: authentic factory-menu entry, remaining LCD blocker (24 October 2026)

## Reproduced, with ORIGINAL firmware and physical contacts

On the owner-provided unchanged `OSUP.BIN`, resumed from an authentic private
`version-event-wait` QEMU QCOW2 checkpoint, a Linux native QEMU compiled by
GitHub Actions at EXeSX commit `2347938` executed real Cortex-A7 and Cortex-M4
instructions. No debugger socket, register/stack mutation, fabricated RTOS
events, or synthetic A7 key-return response was used in the successful run.

The host supplied only original-row-gated electrical matrix contacts:

```
0x93 held 0.07s -> released 0.03s
0x93 held 0.07s -> released 0.03s
0x94 held 0.07s -> released
```

Experimental clock settings (not confirmed physical-board oscillator values):

- `EXESX_DIAGNOSTIC_A7_TPM6_KHZ=32`: unblocks real A7 TPM6
  double-read stability loop while holding SEMA42 gate2;
  measured 17,763 to 15 A7 loop TB executions in a 0.25s comparison.
- `EXESX_EXPERIMENTAL_LPTMR_PCS_CLOCKS=1`: respects M4 LPTMR1
  `PSR=0x05` selecting actual 1kHz LPO source, rather than a
  fabricated 1MHz clock. Original `CSR=0xC1`, `CMR=4` imply a
  ~5ms comparison, not ~5 microseconds.
- `EXESX_EXPERIMENTAL_M4_TPM0_INPUT_MHZ=48`: diagnostic TPM0
  input hypothesis, not hardware clock proof.

The PASSING **QEMU `-d exec` TB execution** (not `in_asm` translation)
contained the original A7 at `0x60010910` (first-keys branch),
`0x60010928` (third-key check), then
**`0x6003A878` (the genuine factory TEST MENU)**.
The original M4 keyboard queue was independently observed containing
key-down type2/subtype1 codes `0x93` and `0x94`.
The original M4 queue-consumer `0x1FFD838A`, IPC router
`0x1FFD874A`, envelope builder `0x1FFDE672`, and queue
`0x1FFDE74A` all appeared in actual guest execution.
The MU trace recorded 22 accepted original M4 transmit words and
22 matched original A7 receive/acknowledge reads. These MU words
are zero-valued notifications, not a decoded keyboard payload;
the untouched BIOS menu branch is the stronger end-to-end event
acceptance proof.

The native Linux build/test workflow `40042304527` passed.
A second run with the replay harness's built-in tuning options
independently confirmed `factory_menu_observed=true` and saved
a **private** `factory-menu-real-post` VM checkpoint.

## How to replay

Requires an existing **owner-private** `version-event-wait`
checkpoint and derived BIOS/OS ELF, source-derived eMMC and profile,
prepared by the existing `scripts/drive_factory_menu.py` flow.
Use the tested QEMU native or Windows build of this branch:

```bash
python3 scripts/drive_physical_menu_qmp.py \
  --qemu ./qemu-system-arm \
  --output-dir private/factory-menu \
  --keys 0x93,0x93,0x94 \
  --tpm0-mhz 48 --a7-tpm6-khz 32 --lptmr-pcs-clocks \
  --hold 0.07 --gap 0.03 --seconds 2 --poll 0.02 \
  --no-wait-idle --trace --mailbox-trace \
  --save-menu-snapshot --overwrite
```

The actual branch at `0x6003A878` is checked in the original guest
execution trace; keyboard-created records are **not** injected.
The private `factory-menu-real-post` VM snapshot is saved only if
that original PC executed. Replaying the exact host timing is
not deterministic across systems because peripheral clocks and
host virtual time are experimental. Do not publish the snapshot.

## New exact blocker: original menu paints NO TEXT yet

Entering `0x6003A878` is **not** equivalent to painting the menu.
The actual original BIOS executed the initializer `0x6003A7D4`,
IPC service `0x4009` via `0x600061C4`, then service
**`0x400B` with argument 2** via `0x60006240`.
In a 3-second original-key run it did **not** return to
`0x6003A7F0`, nor reach menu-paint routine `0x60057668`.
LCD screenshot remained entirely black (864x480).
A further 12-second original-firmware run restored from the
new genuine post-menu checkpoint: original A7 continued running
(0x601CBBxx idle/service paths), but LCD stayed solid black.

Next: inspect real M4 handler/response for IPC `0x400B(2)`
and original A7 `0x601782C8` synchronous command queue completion.
Trace the shared-memory envelope and target M4 service alongside
MU TR/RR—do NOT hardcode a success response, skip the IPC wait,
force the menu PC, or fabricate LCD glyphs.
No proprietary ROM, memory dump, raw trace or source-derived image
is checked into the repository.
