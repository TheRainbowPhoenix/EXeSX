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

The gate0 helper at `0x6017748c` was a preliminary apparent blocker, but per-CPU tracing below disproved the presumed interference: it is a hot acquire/release loop from CPU0. Whether solving it causes execution of post-`0x6004a1c0` startup callbacks and the OS entry is **not yet demonstrated**. It must be cross-checked against the earlier validated `prepare_osup.py` run because that produced different bounded A7 states.


## Non-invasive CPU attribution probe (source committed)

The EXeSX SEMA42 register model has an **opt-in tracing hook**, enabled by `EXESX_TRACE_SEMA42_CPU=1` plus QEMU `-d unimp`, which logs `current_cpu->cpu_index`, the guest instruction address and gate state on each actual SEMA42 MMIO write. It **does not change** gate ownership, register response or release semantics. This permits separately identifying which real QEMU core issues the unexpected zero write during A7's `0x60177488..98` acquisition loop. Trace logs can be large; use bounded runs/private log paths and filter gate 0. Do not publish proprietary guest PCs as raw instruction bytes or entire logs.

A specification-correct, *future* owner-tracked model should be enabled only after observing the A7/M4 CPU↔domain assignments in the native run and must be verified against CPU0 + CPU1 positive/negative unlock controls. The present trace by itself does not implement owner enforcement or resolve the boot blocker.


## CPU attribution overturns the cross-core unlock hypothesis

The **new instrumented native QEMU build** from [CI 39757523357](https://github.com/TheRainbowPhoenix/EXeSX/actions/runs/39757523357) compiled and passed all 35 workflow steps. A fresh three-second **private original-firmware** run enabled the opt-in per-CPU SEMA42 trace, retained the authentic user B/A/F data + boot1 PVOS, and observed:

```text
EXeSX SEMA42 CPU=0 guest-pc=6017748c gate=0 write=2 state=2
EXeSX SEMA42 CPU=0 guest-pc=601774a8 gate=0 write=0 state=0
EXeSX SEMA42 CPU=0 guest-pc=6017748c gate=0 write=2 state=2
EXeSX SEMA42 CPU=0 guest-pc=601774a8 gate=0 write=0 state=0
```

**Both writes are by CPU0 (A7)**, at the exact lock and unlock helper instructions already disassembled. This directly **contradicts the previous hypothesis that a second CPU illegitimately releases this gate during the sampled alternation**. It is simply repeatedly being acquired/released by the *same core*. The gate0 ownership implementation is still objectively less strict than NXP's domain ownership specification, but the currently observed lock/unlock pattern is not evidence that discrepancy blocks boot. The PC `0x6017748c` is a hot repeated helper, **not proof that the acquisition branch failed**. A snapshot alone was misleading. The true startup dependency remains **unidentified**.

A coding problem in the initial optional trace concatenated line terminators as literal `\\n`, and the repeating A7 helper generated an extremely large single log line. The committed tracer was updated to emit actual newlines and cap diagnostic records at 128, with all register behavior unchanged. The above representative four events are extracted from that original (private) trace. All QEMU build outputs and private logs remain uncommitted.

**Correct next path:** instrument actual completion/return of each startup call after `0x6004a1c0`, the indirect vector `0x2000402c`, and the `0x60049bcc` callback-gate state at the moment of execution. Do not claim CPU0's gate0 lock/unlock sequence is an inter-core deadlock and do not change semaphore release policy to try to advance boot without a proven incorrect unlock.


## Reproduction fix: A7-only ELF versus M4-IPL-preloaded ELF

The different runtime behavior was traced to a **firmware-loader configuration error**, not to a new undocumented ROM revision:

- The previously successful private ROM experiments used the repository's documented `scripts/prepare_osup.py` logic, producing **A7 BIOS+OS only** in a two-PT_LOAD ELF. This leaves the M4 IPL at `0x1FFD0000` to be populated by the modeled handoff rather than preinstalled with the loader.
- The fresh independent `extract_roms(1).py` extraction created a **three-PT_LOAD ELF**, including IPL at `0x1FFD0000`. This changes the M4 reset-vector state and can alter semaphore/IPC interactions. Therefore snapshots from the two loaders are *not comparable*.
- A local reconstruction of the repository's exact A7-only ELF layout (identical BIOS/OS source sections, checksum validated) and same private eMMC/profile reached **`0x60006908` around 5s** and **`0x600068e4` around 12s**, both real BIOS SEMA42 gate0 helpers; the USDHC read remains active in the snapshots. Those PCs are *hot functions*, not proof a single transfer or acquire is stuck. This does not yet reproduce every earlier boot snapshot under fully identical external timing/loader details.

### A7-only original-firmware callback object snapshot

A private A7-only run with actual OSUP-derived user B/A/F data and boot1 PVOS yielded:

| Guest physical RAM | Read value | Basis |
| --- | --- | --- |
| `0x6232d5c8` | **`0x6232d9ec`** | Service-object pointer from original startup code |
| `0x6232da18` | **`0x00000000`** | `0x6232d9ec + 0x2c`: callback function slot |
| `0x622e6fbc` | **`0x00000000`** | Last published callback pointer |
| `0x622e6fc4` | **`0x00000001`** | Callback-dispatch status: bit1 `0x2` is **clear** |
| `0x62413241` | **`0x00`** | Earlier, independent BIOS global service byte |
| `0x6232d5dc` | `0x00000002` | Ancillary component state, purpose not established |
| `0x40380024` | `0x01ff0a0e` | In this sample USDHC still has an active data path |

The proven static predicate at `0x60049bec` requires `0x622e6fc4 & 2 != 0` and its callback target must be nonzero. **Neither condition holds at this snapshot**. That is a concrete unregistered/ineligible callback, **not evidence the missing callback was meant to launch the OS**. The registered target's producer and timing must be found. It would be wrong to force either bit or fill in a fabricated function pointer.

### Correct interpretation of the repeated semaphore trace

The first per-CPU write trace (before the logging-format correction) conclusively identified **CPU0 for both write2 acquisition and write0 release** at gate0; the NXP owner-only-release model mismatch is genuine in source but *not demonstrated as the cause of the observed loop*. Only after controlling the A7-only ELF and comparing both CPU contexts can any proposed domain ownership implementation be judged against the original BIOS handoff.

**Current best unresolved dependency:** service-object callback registration and whatever initialization event sets `0x622e6fc4` bit1, plus the independent `0x62413241` readiness byte. Cross-core semaphore ownership is a secondary model discrepancy, not a verified gate to OS entry. No verified boot at `0x605e3ad0`.


## New optional RAM watch instrumentation

The existing QEMU memory-access tracer `plugins/memtrace.c` calls `qemu_plugin_get_hwaddr` in every callback. In the current private original-ROM experiment, QEMU 10.1 repeatedly reports `invalid use of qemu_plugin_get_hwaddr` for these accesses, producing no usable physical-address events. Rather than assuming an unreported RAM write occurred, an opt-in `virtual_only=1` mode was added. It does **not** ask QEMU for physical address; it logs the **guest virtual address only**, explicitly labels the backing `virtual-only`, and compares requested ranges against that guest virtual address. This is suitable for the BIOS identity-mapped RAM region only after MMU translation has been checked. The default physical/MMIO tracer retains its old behavior for existing tests.

Example diagnostic plugin argument (owner-held ROM only):

```text
-plugin exesx-memtrace.so,virtual_only=1,max=48,range=0x622e6fbc:0x622e6fc8,range=0x6232da18:0x6232da1c,range=0x62413241:0x62413242
```

The plugin deliberately records only CPU index, instruction PC, access type/address/width, not sensitive RAM **values**. Source-derived callback storage addresses are safe metadata; callback producer/owner is not known until a successful live write trace establishes it.


## New controlled live debugger: callback state is not cleared; boot passes control to `0x60048D9C`

On **22 October**, independently repeated using the exact checksum-validated original user OSUP SHA `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`, reconstructed **two-section A7-only ELF**, source-authentic user BIOS/OS/F component bytes, source-authentic boot1 PVOS at LBA0/LBA32, QEMU native from passing PR32 CI, and the same explicitly *private and unverified* `0xb0000000` RAM diagnostic window. QEMU's virtual-only memory-access plugin was enabled using **`-d plugin,guest_errors,unimp`**; without `plugin` in `-d` the log output is not visible. It emitted 45 bounded matching accesses, including:

- `0x60021730`: original boot loader writes `0x622e6fc4` (initial component status).
- `0x60021684`: writes `0x622e6fc4` (component setup/reset).
- `0x60021450`: clears/initializes the four callback-object bytes `0x6232da18..1b` **before** subsequent component discovery.
- `0x60018908`: SDHCI buffered data is written into `0x6232da18` (not a status/OS callback reset).
- `0x600214b4`, `0x600212e0`, `0x60021354`, `0x6002139c`, `0x60021508`, `0x600215ec`: component-loader code records status bits.
- **No later write** to `0x6232da18` or `0x622e6fc4` occurred after component setup during the logged 12-second interval. Nor was `0x60049be0` observed storing the cached callback `0x622e6fbc`.

At 7 seconds and independently at 12 seconds, original guest memory had **`0x622e6fc4=0x3f`** and **`0x6232da18=0x60400000`**, which *contradicts previous uncontrolled-run speculation that these must get cleared to status 1/null later*. The cached `0x622e6fbc` stays zero, and distinct BIOS readiness byte `0x62413241=0`.  The storage controller was active at the earlier snapshot, but idle `PRES_STATE=0x01ff0008` after the longer one. This is not a callback-ineligibility problem in the verified run: **bit1 is set and the OS entry target is populated**. Rather, the callback-copy/BLX routine `0x60049bcc` is not yet reached.

### True CPU0 breakpoint execution path (QEMU `-S -gdb`, explicit `Hg1`/`Hc1`)

Breakpoints at the following **actual instructions** hit with component status `0x3f` and OS callback target `0x60400000` at each check:

```text
0x60021660   original component coordinator successful completion
0x6004a1c0  coordinator returns to BIOS startup
0x6004a1e0
0x6004a1ec
0x6004a224
0x6004a24c  BL 0x60007284 -> indirect physical 0x2000402c
0x2000402c  actual vector code executes; returns R0=1
0x6004a250  conditional comparison R0=1
0x6004a258  branch takes nonzero service path
0x6004a268  next initialization service
0x6004a270  later startup
0x6004a278  later comparison
0x6004a294  later startup branch
0x6004a2a4  prepares args for BL 0x60048d9c
0x6004a2ac  callsite, R0=0
0x60048d9c  callee reached, LR=0x6004a2b0
```

The later `0x6004a2b0` return, `0x6004a2cc` callback loop entry, `0x60049bcc` dispatcher, `0x60049c04` BLX and `0x60400000` OS trampoline **did not break** in bounded follow-ups. After interrupting CPU0 after that last confirmed call, the original A7 was `0x601cbcf8` (BIOS WFI idle, LR=`0x601cbcc4`). This is evidence that `0x60048d9c` **does not return through the expected `0x6004a2b0` during the observed window**, not proof that a particular blocking instruction inside `0x60048d9c` runs forever. An exception, task-context switch, or wait for an external event could have transferred control to the idle handler.

The `0x60048d9c` function begins with peripheral/service initialization and has its own branches to persistent error/wait loops at `0x60048e24` and `0x60048e2c` when a timer/status source reports particular values; neither loop's breakpoint hit was observed in a 12-second follow-up, so do **not** claim one of these is the actual blocker.

**Next decisive test**: trace entry into `0x60048d9c`, all calls and returns to `0x6000fee8`, `0x60007e0c` and `0x6001eda8`, and the transition into scheduler/exception/idle; inspect the original A7 interrupt status and both A7/M4 PCs at the transfer of control. Only then identify whether an interrupt/event from an unimplemented peripheral needs a correct hardware model. Do **not** force `BLX`, fabricate a callback registration, or set `0x62413241`.


### Deeper original instruction trace: condition `0x80` and nested wait/service

Another independent cold-run series (always the exact A7-only BIOS+OS ELF and checksum-valid original update-derived private media) captured:

```text
0x60048d9c   entry from 0x6004a2ac, LR=0x6004a2b0
0x60048dac   initial setup
0x6000fee8   first service call; returns to 0x60048db4
0x60048df8   calls 0x60007e0c
0x60048dfc   returned R0=0x00003c86
0x60048e04   R0 & 0x80 != 0; calls 0x600488e8
0x600488e8   special service; LR=0x60048e08
0x600488f0   setup from 0x600066bc
0x60048908   calls 0x600066ec
0x60048918   R0=0
0x60048920   calls 0x60048878
0x60048878   entry; LR=0x60048924
0x60048888   next nested service call to 0x6001deac
```

Breakpoints at `0x6004a2b0` (startup return), `0x6004a2cc` (callback dispatcher outer loop), `0x60049c04` (indirect BLX) and `0x60400000` (OS trampoline) **did not fire before a bounded timeout**. On asynchronous debugger interrupt, the A7 was again in BIOS idle at `0x601cbcf8`. This disambiguates the preceding trace: the firmware takes the **bit-7-set `0x600488e8` branch**, reaches a subsequent **`0x60048878`** service and does not return through the expected outer startup PC during the observed window. It has not yet been proved whether the nested call, scheduler, or an external event blocks progress, and the measured `R0=0` at `0x60048918` is *not* an error return without inspecting the later caller's branch semantics.

**Next isolated breakpoint chain:** `0x6001deac` (nested service from `0x60048888`), return `0x6004888c`, then `0x6001eca8`, `0x6001ebf0`, and loop condition `0x6001ec14`. At each, record both A7 and M4 PCs, interrupts and any WFI callsite. Explicitly compare the service status returned by `0x600066ec` with the actual wait predicate in `0x600488f8..0x60048928`. **Do not fabricate an interrupt, override status bit0x80 or branch directly into OS.**

**Practical outcome of this turn:** conditional callback is *eligible* (status `0x3f`, target `0x60400000`), but execution is held up **before the dispatcher** by a nested BIOS startup/service path under `0x60048d9c`. The exact missing hardware event remains unidentified. No new device response or boot success was invented.
