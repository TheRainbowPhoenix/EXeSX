# Cold-start diagnostic: M4 keyboard to mailbox (24 Oct 2026)

This run used the owner's unchanged OSUP image, the native QEMU build
downloaded from GitHub Actions, and a freshly source-derived eMMC and ELF.
It did **not** restore a previously successful version-dialog checkpoint.

Two bounded Cortex-A7/Cortex-M4 GDB-RSP runs set non-mutating software
breakpoints at the original ROM keyboard scan, consumer, IPC envelope
and event-reader addresses. A second run scheduled actual electrical
matrix contacts `0x93,0x93,0x94` at host time +2 seconds independently
of the A7 dialog breakpoint. This prevents the previous script from
quietly withholding every key merely because `0x600108A8` is not hit.
No guest RAM/PC/stack/key event was patched.

Observed during the second ~11-second cold-start probe:

| Original PC | Meaning | Breakpoint hits |
| --- | --- | ---: |
| `0x1FFD8412` | M4 row drive | 11 |
| `0x1FFD8610` | M4 debounce | 1 |
| `0x1FFD8564` | M4 column scan | 1 |
| `0x1FFD85C6` | M4 GPIO column read | 1 |
| `0x1FFD838A` | M4 key event queue consumer | 0 |
| `0x1FFD874A` | M4-to-A7 keyboard IPC router | 0 |
| `0x1FFDE672` | M4 IPC envelope builder | 0 |
| `0x1FFDE74A` | M4 IPC envelope queue | 0 |
| `0x600108A8` | A7 version-dialog event wait | 0 |
| `0x6003A878` | A7 factory menu | 0 |

A separate prior cold-start QMP capture sampled A7 in the USDHC
initialization path and the shared IPC request word `0x0001A002`
at `0x2F02800C`, *not* the menu's later `0x0001400B`.

**Interpretation:** the new cold-start failure is upstream of the
version-dialog and cannot be called an A7 rejection of dispatched
keyboard codes. A physical-contact request was scheduled, but the
trace did not observe the queue-consumer/IPC-router path. This also
does not supersede the prior successful real-firmware key replay
from a genuine private `version-event-wait` snapshot, which did
reach `0x6003A878` with `0x93,0x93,0x94`.

The committed diagnostic adds `--contact-delay N --matrix-keys
--trace-m4` to run a physical-contact probe independently of A7
event-wait and adds original M4 queue/IPC software-breakpoint
addresses. Breakpoints perturb scheduling; repeat with QEMU
`-d exec` and optional MU logging for definitive timing.

**Next specific target:** resolve the outstanding cold-start
`0xA002` storage/IPC request and recover the original
`0x600108A8` event-wait checkpoint; then compare M4 queue slots,
MU TX/RR words, A7 decoded records and the later `0x400B(2)`
completion before claiming menu text.
