# Original BIOS has a separate three-key startup chord (24 October 2026)

## Decompilation and original ROM proof

The unchanged owner-provided A7 decomp `XD-SX9850.0.c` establishes
the previously missing **pre-version-dialog boot-mode gate**:

- `FUN_60011CA4` enters the relevant start-mode branch only when
  original selector `_DAT_6232E33C == 0x80` and other startup
  conditions are satisfied.
- `FUN_6001D93C` retrieves original key coordinates via A7 service
  `0x0809` for logical keys **0x80, 0x95, 0x92**. It suspends
  the regular scan, performs direct GPIO row/column scans through
  `FUN_6001D95C`, and returns true when the chord is held for
  the expected startup interval.
- `FUN_6001D94C` similarly checks alternative
  **0x80, 0x90, 0x96**.
- The factory-menu event sequence **0x93, 0x93, 0x94** is a
  *different*, later sequence in `FUN_60010868`; it is not the
  chord that first selects the startup path.

The owner-provided unchanged M4 ROM keymap at relocated
`0x1FFD0E14` confirms these exact contact coordinates:

| Code | Row | Column |
| --- | ---: | ---: |
| 0x80 | 0 | 0 |
| 0x95 | 5 | 6 |
| 0x92 | 7 | 7 |
| 0x90 | 7 | 6 |
| 0x96 | 8 | 4 |
| 0x93 | 8 | 7 |
| 0x94 | 6 | 6 |

## Correct electrical emulation

Previously `EXESX_M4_KEY_MATRIX_FILE` represented **one** closed
contact; the original three-key held startup chord was unrepresentable.
The board now accepts comma-separated **simultaneously closed**
original keycodes (e.g. `0x80,0x95,0x92`) and still accepts one
keycode for backwards compatibility. On each real guest-selected
IOMUX/GPIO output row, only matching closed keys pull their input
columns low. No A7 key return, firmware event, register or RAM is
injected. Malformed or unknown contact lists release all contacts.

The no-debugger firmware runner's *new diagnostic option* is
`--startup-chord 0x80,0x95,0x92 --matrix-keys` (alternative:
`0x80,0x90,0x96`). It places the contact closure and normal idle
input pull-ups **before boot**, releases the chord on the original
`0x600108A8` event-wait breakpoint, then sends
`0x93,0x93,0x94` as actual row-gated physical contacts.
The runner now reports independent boot-main and both chord-check
breakpoint hits and the original startup-mode selector.

Linux and Windows GitHub Actions passed on
`508addaf4c71eca09222e0ba7c2b63e98b9a8211` (native artifact
source SHA `d4e852a207a526e2f5bb87b7ecec1ed46f46a0e7`).
Native QEMU synthetic ARM MMIO tests independently passed no-key,
0x93, 0x94, simultaneous 0x93+0x94, malformed-combination,
and output-direction-precedence controls.

## Genuine original cold-start results (no synthetic events)

- A 24-second original-OSUP cold boot with primary startup chord
  held **from power-on** did not reach `0x60011CA4`,
  `0x6001D93C` or `0x600108A8`.
- An extended **90-second** original-OSUP GDB breakpoint run with
  the same genuine held chord and experimental source clocks
  also did not hit those functions or create a checkpoint.
  The source-derived storage image and BIOS/M4 remained unmodified.
- An independent no-GDB 6-second QMP run sampled
  `_DAT_6232E33C=0` and later observed a power-service
  `0xA002` record; M4-to-A7 MU TX/RX matched **337/337**.
- Original A7 `FUN_601782C8` submits IPC `0xB000`,
  `0xA004` and `0xA002`. The original M4 ROM dispatcher
  `FUN_1FFD5510` maps them to `0x1FFD4C64` (SNVS reset pulse),
  `0x1FFD9D44` (power state), and `0x1FFD9A02`
  (power settings), respectively. A separate **no-debugger**
  `-d exec` trace confirmed execution of all three handlers.
  MU receive acknowledgment alone is not service-result proof.
  The SNVS0 HPCOMR `0x41070004` reset-command bit already
  self-clears in EXeSX; do not 'fix' the IPC by forging a reply.

**Important distinction:** the three-key startup chord was a real
missing input capability, and is now test-validated. **The current
cold boot still stops or diverts before even invoking the startup
chord checker**. It is therefore incorrect to call `0xA002`
a demonstrated storage failure, or to claim the factory menu is now
painted. The next priority is the exact A7 boot-task/startup-selector
state that should call `FUN_60011CA4`; recover
`version-event-wait`, then replay the proven later keyboard path
and diagnose service `0x400B(2)`.

## Long no-debugger held-chord control

With the genuine unchanged private OSUP, original source-derived eMMC,
new QEMU native build including simultaneous physical contacts, and
`0x80,0x95,0x92` held from power-on, a **140-second** QMP/`-d exec`
original-firmware run sampled CPU/IPC/startup-selector 14 times at
10-second intervals. No GDB software breakpoints or guest CPU/memory
modifications were used. The original selector at `0x6232E33C`
remained zero, and the shared IPC slot at `0x2F02800C` remained
`0x0001A002` with preceding word `0x04020800`. Neither original
`0x60011CA4` startup checker nor `0x6001D93C` / `0x6001D94C`
chord checker nor `0x600108A8` version event wait was observed.
The trace window was bounded/filtered, so absence of any individual TB
should be interpreted together with the repeated original RAM samples.

The independent synthetic ARM MMIO test passes exact simultaneous
`0x80+0x95+0x92` input; this is **not** a claim the original cold-start
firmware reached that test. Linux and Windows CI now include the
firmware-free exact-chord regression `scripts/probe_startup_chord.py`.

**Conclusion:** do not change the expected startup key combination.
The remaining upstream problem is original A7 boot-task progression,
startup selector initialization, or IPC service result/state, not a
lack of simultaneous keyboard contacts or lost MUA notifications.
