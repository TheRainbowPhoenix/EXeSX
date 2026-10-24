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


## Reproduction and negative timing controls (24 October follow-up)

Fresh original-firmware native QEMU no-debugger run with the unchanged
`version-event-wait` VM checkpoint and authentic host-controlled
`0x93,0x93,0x94` physical contacts reaches the genuine
`0x6003A878` A7 factory menu branch. The original M4 keyboard queue
is seen constructing the keydown records. The MU transport reports
23 accepted M4 TX words and 23 matching A7 RR consumption/ACK reads.
These are notification words, **not a decoded key payload**.
The authentic BIOS branch is the end-to-end key acceptance proof.

At the still-unfinished `0x400B(2)` IPC request:

- A7 submitted request word `0x0001400B` and argument `2` into
  original shared RAM at `0x2F02800C/10`.
- The M4 executed original MU callback `0x1FFE4776`, posting RTOS
  event object 7 / mask `0x80`. The interrupt and this wakeup
  therefore occurred; application-level service completion has
  **not** been observed.
- The native `-d exec` trace contains A7 `0x60006240` but
  not `0x60006268` (service caller return),
  `0x6003A7F0` (factory initializer post-IPC), or
  `0x60057668` (menu paint). The 864×480 screenshot remains black.
- After restoring the **authentic** post-menu checkpoint in a fresh
  emulator and continuing for additional seconds, A7 still executes
  normal service/idle functions but the menu painter is not reached.

New opt-in source changes on this branch add
`EXESX_DIAGNOSTIC_M4_TSTMR_KHZ` / `--m4-tstmr-khz` and report
the independent IPC and paint milestones. These are **diagnostic**
differentials; no guest ROM, mailbox, register, or event has been
altered. Linux native GitHub Actions build
[40044781318](https://github.com/TheRainbowPhoenix/EXeSX/actions/runs/40044781318)
succeeded and its QEMU artifact was downloaded and used locally.

Measured differential on the owner's unchanged original firmware:

| M4 TSTMR model / QEMU option | Authentic menu | `0x400B` return | Menu paint |
| --- | --- | --- | --- |
| Historical TSTMR 1 MHz | YES | NO | NO |
| Diagnostic 32 kHz | YES | NO | NO |
| Diagnostic 1 kHz | NO in bounded replay | NO | NO |
| Historical 1 MHz + QEMU `-icount shift=0`, resumed from genuine post-menu snapshot | Previously entered | NO | NO |

NXP's i.MX7ULP TSTMR reference specifies **1 MHz**, so lowering
the rate is not a hardware-verified solution. Original M4
`0x1FFD4D04` performs a coherence-checked 64-bit timestamp read,
and `0x1FFD4E62` uses repeated reads for a timed delay. The large
number of those loops is **not evidence by itself** of a broken
timestamp counter. The 32 kHz and icount controls did not unblock
the IPC completion. Do not bake the lower rate into default board
emulation.

**Current investigation must follow the original M4 event-object-7
consumer and the actual service-0x400B reply**, correlating its
result with A7 `0x601782C8` waiting for completion. Confirm the
response envelope/return path before modifying MMIO semantics.
