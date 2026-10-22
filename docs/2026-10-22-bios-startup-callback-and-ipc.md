# Original DY357 BIOS startup after 0x6004A1C0 — callback and inter-core evidence

**22 October 2026.** Private user-owned OSUP SHA-256 `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`. This study uses original A7 BIOS ARM instructions; the private OSUP, extracted ELF, sparse flash media, execution traces and temporary `0xB0000000` RAM workaround are not committed.

## Evidence from original executable (static, checksum-validated)

The component-header coordinator already returned success (six bits `0x3f`) in prior private runs; `0x6004a1c0` resumes this original A7 startup chain. Verified original ARM `BL` calls:

| Call PC | Service target | Immediate control-flow fact |
| --- | --- | --- |
| `0x6004a1c0` | `0x6000bd14` | Runs immediately after component-table setup |
| `0x6004a1c4` | `0x601cd5ec` | Subsequent BIOS service |
| `0x6004a1c8` | `0x601cad9c` | Subsequent BIOS service |
| `0x6004a1cc` | `0x601b3d10` | Further startup |
| `0x6004a1d0` | `0x601b3d48` | Further startup |
| `0x6004a1d4` | `0x60049f5c` | Calls a mode-dependent routine |
| `0x6004a224` | `0x60049b30` | Startup arbitration/service |
| `0x6004a228` | `0x601b3d48` | Next service |
| `0x6004a22c` | `0x60008e98` | Next service |
| `0x6004a24c` | `0x60007284` | Indirect vector: `LDR PC,[PC,#-4]` to `0x2000402c`, **not** a normal local BIOS function |
| `0x6004a2cc` | `0x60049bcc` | Event/indirect callback attempt inside repeating BIOS service loop |

The original startup around `0x6004a250` branches based on the result of `0x60007284`. It therefore potentially depends on a service/vector located at `0x2000402c`. The semantics of that mapped target have not been verified; do not inject a fabricated successful return. `0x6004a2c8..0x6004a2d4` zeroes a state word, invokes the callback helper and repeats BIOS services. It is a persistent event loop, not an unconditional jump into the OS. The exact extracted OS-entry target remains `0x605e3ad0`.

### The callback is subject to **two** independent conditions

Actual ARM code at `0x60049bcc..0x60049c14`:

```asm
60049bcc  push {ip,lr}
60049bd0  ldr r0,[pc,#...]  ; ROM literal 0x622e6fbc: callback storage
60049bd4  ldr r1,[pc,#...]  ; ROM literal 0x6232d5c8: service state ptr
60049bd8  ldr r1,[r1]
60049bdc  ldr r1,[r1,#0x2c]
60049be0  str r1,[r0]
60049be4  ldr r1,[pc,#...]  ; another value from the status structure
60049be8  ldr r1,[r1]
60049bec  tst r1,#2        ; gated on status bit 1
60049bf0  beq 0x60049c10
60049bf4  ldr r1,[r0]
60049bf8  cmp r1,#0        ; callback pointer nonzero?
60049bfc  beq 0x60049c10
60049c00  ldr r0,[r0]
60049c04  blx r0           ; only a *registered* callback is called
60049c08  mov r0,#1
60049c10  mov r0,#0        ; no callback when gated
60049c14  pop {r1,pc}
```

Do not conflate `0x622e6fbc` (last copied callback target), `0x6232d5c8` (pointer used for a different status check) and earlier `0x62413241` (an unrelated byte flag read from `0x6001000c`). They are separate data stores. The **bit-1 and pointer test are proven**, but whether the callback target is the OS entry or a normal service is unproven.

### Differential runner limitation

A fresh privately extracted ELF and QEMU 10.1.0 native artifact with source-authentic user B/A/F bytes and boot1 PVOS were executed using the experimental memory profile and A7/M4 diagnostic flags. After nine wall-clock seconds the sampled A7 PC was **`0x6017748c`**, within early semaphore/IPC BIOS activity, rather than the previously reported idle `0x601cbcf8`. `0x6232d5c8`, `0x622e6fbc` and `0x62413241` all read zero at that snapshot; no callback target can be inferred from the empty values. The private `-d guest_errors,unimp` log contains **repeated SEMA42 gate0 acquire/release traffic with domains 0 and 2** on `0x4101b003`. This shows communication attempts, **not a proven hardware deadlock** or an authentic owner/IRQ implementation. Earlier successful component-coordinator traces used a differently prepared private runtime ELF and cannot automatically be equated with this re-extraction.

The EXeSX SEMA42 early model at `hw/arm/exesx-imx7ulp-sema42.inc` documents **no fairness or IRQ support**, and the release path has only an approximate domain-owner model. Potential inter-core completion and correct gate semantics warrant investigation, but there is **insufficient evidence** to alter register behavior or force ownership/DONE and claim it unlocks the BIOS.

Remote GDB hardware breakpoint attempts on the high startup PCs in this newer runner did not trigger in a bounded run even though monitor shows real BIOS execution; the **same runtime-path reproducibility issue** must be resolved by matching exact loader ELF preparation, QEMU version, profile and both core states before attributing a specific callback return. No callback address, caller execution count or OS entry has been confirmed from that test.

## What's actually the next blocking dependency?

The known B/A/F user-area signature/sector mapping and component coordinator status were solved in the earlier controlled private tests, so another arbitrary USDHC patch is not justified. The most defensible next questions are:

1. Capture the live **pointer at `0x6232d5c8`**, the structure field at +0x2c and the copied target at `0x622e6fbc` *when `0x60049bcc` executes*, with the original verified loader and A7 core selected.
2. Identify the live bit-1 control word, any setter, and whether the callback target ultimately reaches the OS entry `0x605e3ad0`. Do not set these flags without establishing a real device-generated event.
3. Trace `0x60007284`'s indirect dispatch via `0x2000402c`; it can gate extra initialization after `0x6004a24c`.
4. If the BIOS stalls in `0x6017748c`, record the SEMA42 gate0 register (byte at `0x4101b003`), both CPU PCs, exception modes and **exact acquire/release order** before implementing an IRQ/fairness/ownership mechanism. It may be a transient semaphore loop, not the failure.
5. Re-run with **matching prevalidated `prepare_osup.py` ELF** to avoid misattributing layout or M4 IPL loading differences; compare against source-authentic B/A/F eMMC and no-media controls.

A new firmware-free inspector at `scripts/inspect_bios_startup_callback.py` extracts only addresses and decoded direct `BL` destinations from a user-owned ELF. It checks critical known opcodes to fail closed if the binary differs. Synthetic tests do not contain Casio code.

**Status:** original OS entry and LCD text still not demonstrated. No sound basis for a production hardware fix or fabricated callback/flag yet.
