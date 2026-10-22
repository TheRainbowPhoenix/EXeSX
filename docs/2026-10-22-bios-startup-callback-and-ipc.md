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

The literal at `0x6004a2f4` is **`0x622e6fc4`**, which supplies the **bit-1 status test** (`LDR`, `TST #2`) at `0x60049be4..0x60049bec`. Do not conflate `0x622e6fbc` (last copied callback target), `0x6232d5c8` (pointer to a service object that exposes the +0x2c callback), `0x622e6fc4` (bit-1 status word), and earlier `0x62413241` (a separate byte flag read from `0x6001000c`). They are separate data stores. The **bit-1 and pointer test are proven**, but whether the callback target is the OS entry or a normal service is unproven.

### Differential runner limitation

A fresh privately extracted ELF and QEMU 10.1.0 native artifact with source-authentic user B/A/F bytes and boot1 PVOS were executed using the experimental memory profile and A7/M4 diagnostic flags. After nine wall-clock seconds the sampled A7 PC was **`0x6017748c`**, within early semaphore/IPC BIOS activity, rather than the previously reported idle `0x601cbcf8`. `0x6232d5c8`, `0x622e6fbc` and `0x62413241` all read zero at that snapshot; no callback target can be inferred from the empty values. The private `-d guest_errors,unimp` log contains **repeated SEMA42 gate0 acquire/release traffic with domains 0 and 2** on `0x4101b003`. This shows communication attempts, **not a proven hardware deadlock** or an authentic owner/IRQ implementation. Earlier successful component-coordinator traces used a differently prepared private runtime ELF and cannot automatically be equated with this re-extraction.

The EXeSX SEMA42 early model at `hw/arm/exesx-imx7ulp-sema42.inc` documents **no fairness or IRQ support**, and the release path has only an approximate domain-owner model. Potential inter-core completion and correct gate semantics warrant investigation, but there is **insufficient evidence** to alter register behavior or force ownership/DONE and claim it unlocks the BIOS.

Remote GDB hardware breakpoint attempts on the high startup PCs in this newer runner did not trigger in a bounded run even though monitor shows real BIOS execution; the **same runtime-path reproducibility issue** must be resolved by matching exact loader ELF preparation, QEMU version, profile and both core states before attributing a specific callback return. No callback address, caller execution count or OS entry has been confirmed from that test.

## What's actually the next blocking dependency?

The known B/A/F user-area signature/sector mapping and component coordinator status were solved in the earlier controlled private tests, so another arbitrary USDHC patch is not justified. The most defensible next questions are:

1. Capture the live **pointer at `0x6232d5c8`**, the structure field at +0x2c and the bit-1 status at `0x622e6fc4` and the copied target at `0x622e6fbc` *when `0x60049bcc` executes*, with the original verified loader and A7 core selected.
2. Identify the live bit-1 control word, any setter, and whether the callback target ultimately reaches the OS entry `0x605e3ad0`. Do not set these flags without establishing a real device-generated event.
3. Trace `0x60007284`'s indirect dispatch via `0x2000402c`; it can gate extra initialization after `0x6004a24c`.
4. If the BIOS stalls in `0x6017748c`, record the SEMA42 gate0 register (byte at `0x4101b003`), both CPU PCs, exception modes and **exact acquire/release order** before implementing an IRQ/fairness/ownership mechanism. It may be a transient semaphore loop, not the failure.
5. Re-run with **matching prevalidated `prepare_osup.py` ELF** to avoid misattributing layout or M4 IPL loading differences; compare against source-authentic B/A/F eMMC and no-media controls.

A new firmware-free inspector at `scripts/inspect_bios_startup_callback.py` extracts only addresses and decoded direct `BL` destinations from a user-owned ELF. It checks critical known opcodes to fail closed if the binary differs. Synthetic tests do not contain Casio code.

**Status:** original OS entry and LCD text still not demonstrated. No sound basis for a production hardware fix or fabricated callback/flag yet.


## Actual sustained loop found at 9s and 17s: SEMA42 gate0 acquisition

The A7 snapshots in the newly extracted ELF runtime were not merely incidental IPC. They remained in the **same original ARM acquisition retry loop** at **9 seconds and 17 seconds**:

```asm
60177484  mov   r1,#2
60177488  ldr   r0,[pc,#0xbe8]       ; 0x60178078 -> 0x4101b003
6017748c  strb  r1,[r0]             ; try lock gate0 using owner value 2
60177490  ldrb  r0,[r0]
60177494  cmp   r0,#2
60177498  bne   0x60177488         ; retry if another domain won
6017749c  bx    lr
601774a0  mov   r1,#0
601774a4  ldr   r0,[pc,#0xbcc]     ; same gate0
601774a8  strb  r1,[r0]           ; unlock
601774ac  ldrb  r0,[r0]
601774b0  cmp   r0,#2
601774b4  beq   0x601774a4        ; retry if still owner2
```

The observed native QEMU diagnostic log contains repeated `EXeSX SEMA42 gate=0 domain=2 state=2` alternating with `domain=0 state=0` for this *same* `0x4101b003` register. That is **stronger evidence of an acquisition retry than a generic semaphore-housekeeping observation**, and revises the preliminary characterization earlier in this report.

**Official specification:** NXP i.MX7ULP Reference Manual, ch.10 SEMA42: the gate is a 4-bit state machine; write `domain ID + 1` to try to acquire; only the domain that locked it may release using zero. See [NXP reference manual PDF, chapter 10](https://manuals.plus/m/3fcef56ef531d2f11af138e90b262f740cb4b850405f230406bb863805f74d1c.pdf) and [MCUXpresso SEMA42 API](https://mcuxpresso.nxp.com/api_doc/dev/1095/group__sema42.html). The current EXeSX `exesx_sema42_write` instead executes `*gate=0` for **any** zero write, even from a non-owner, and the guest's domain and CPU identity are not checked. This **is a real model/spec discrepancy** and plausibly explains why the original ARM cannot observe its own acquisition with value 2 under concurrent A7/M4 activity.

**Do not simply forbid all zero writes or force gate0=2.** Correct modeling requires mapping the actual QEMU requesting CPU to the hardware SEMA42 domain for **both** A7 and M4, tracking the successful owning domain per gate, and allowing release only from that owner, with the documented reset-key sequence still overriding locks. The current `EXeSXProfileWindow` callback does not yet provide an authenticated requester/domain; logging only `data=0` is insufficient to attribute the source. A safe patch must first instrument *CPU index + guest PC + gate state* on writes to determine which CPU sends the observed zero writes, then implement domain-aware ownership and prove with guest-ARM/M4 negative/positive tests. Without this, changing ownership semantics may incorrectly prevent a legitimate unlock and deadlock the reverse direction.

The sustained `0x6017748c` loop with gate0 traffic is the **highest-priority live blocker in this current re-extraction runtime**. Whether solving it causes execution of post-`0x6004a1c0` startup callbacks and the OS entry is **not yet demonstrated**. It must be cross-checked against the earlier validated `prepare_osup.py` run because that produced different bounded A7 states.
