# Why main cold boot does not reach the startup chord: mode CA00 and later M4 A002 event wait

**2026-10-25; original, unchanged owner OSUP.** This document contains only firmware-independent evidence, original-function addresses and short diagnostic labels. The firmware, extracted A7/M4 ELF, complete instruction trace, raw MMIO/SRAM samples and reconstructed storage are not published.

## Controlled experiment

Source baseline is `main` at `28e321159341c5f901ad74dc3de92e3148b73499`, with the latest previously successful native Linux QEMU CI build sourced from `cc2a7bd419175a22292f8aeab60d433b587c6036`. Original `OSUP.BIN` matches SHA256 `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`. Reconstructed eMMC and disposable SD are attached with `snapshot=on`. Held startup chord contacts `0x80,0x95,0x92` are modeled as original GPIO/IOMUX row-gated electrical closures. No guest PC, CPU register, ROM, IPC record, keyboard code, or event flag was mutated. Original Cortex-A7/M4 `-d exec` TB traces were acquired without GDB; read-only QMP/HMP checked memory and CPU state. Earlier GDB RSP breakpoint observation is *not* used as negative proof because it slowed boot significantly.

## Direct BIOS startup gate: 0xCA00 versus 0xCA05

The original A7 enters `0x6004A0B4`, returns through `0x6004A1E8`, `0x6004A1EC`, `0x6004A2A4`, and calls startup service `0x60048D9C` at `0x6004A2AC`. Earlier short captures incorrectly implied permanent blockage in the initial display/media initializer. Longer actual-TB traces show that call **returns**.

The original code at `0x60048E08` calls `0x6001EDA8` and compares its return to **0xCA05** at `0x60048E10`; only a match calls the original version-dialog `0x60010868` at `0x60048E18`. Repeated original read-only samples of `0x20007810` (approx. host seconds 3, 10, 18, 26, 34 and later) held **0x0000CA00**. Thus the current path proceeds into normal power initialization, not the factory version dialog. This is the immediate *branch decision*, not a demonstrated reason why the original desired CA05 mode was never selected by the startup chord.

## The later synchronous A002(2) request stalls after real M4 dispatch

After an original firmware `0x1808` check, the A7 takes the normal startup branch, reaches `0x60048F10` (`MOV R0,#2`), and executes `0x60048F14` (`BL 0x60008CBC`). That wrapper submits synchronous original IPC `0xA002(2)` using `0x601782C8`.

**Address correction:** `0x60048F14` is the **call site**; the expected **post-call return** is `0x60048F18`, *not* `0x60048F14`.

In a bounded **85-second host-time** no-debugger original-ROM trace, original A7 `0x60048F10` executed, but TB at `0x60048F18` or service caller return `0x6004A2B0` did not execute. At 10 and 25 seconds the original shared control-slot data looked previously completed (`0x040208FF`, A002 argument1); at 40, 55, 70, and 85 seconds it consistently held a newly submitted `0x0001A002` with argument `2` and status `0x04020800` (also a fourth word `0x000000AF`). These raw words are recorded in **private** logs only. Correlating the pending slot with actual original caller execution is much stronger evidence than declaring every stale A002 request a deadlock.

The original Cortex-M4 dispatcher `0x1FFD5510` executed and routed original A002 to real handler `0x1FFD9A02`. Native TB execution at `0x1FFD9A1A` and `0x1FFD9A22` confirms the handler takes its original conditional path; its Thumb disassembly:

- `0x1FFD9A16` calls `0x1FFD939E(1)` (reads state index1 from original RAM array `0x1FFE9B0C`).
- If state index1 equals `1`, `0x1FFD9A22` sets `R0=1`, and `0x1FFD9A24` calls `0x1FFD960A(1)`.
- `0x1FFD960A` checks original state index1 again; when it equals 1, `0x1FFD9622` selects M4 RTOS **event object 8**, and `0x1FFD9624` invokes `0x1FFD635C(8, 0xFFFFFFFF)`, an unbounded wait; its continuation is `0x1FFD9630`.

A second **65-second** narrowly filtered original-firmware trace observed the last A002 handler entry `0x1FFD9A02` followed immediately by `0x1FFD9A22`, `0x1FFD960A`, `0x1FFD635C`, **without a subsequent observed return** through the later A7 caller or M4 post-wait continuation. QEMU TB starts are not individual-instruction tracepoints; absence of a TB beginning exactly at `0x1FFD9624` is **not** proof that the instruction at 9624 was skipped. The real wait call and longer no-return evidence together isolate the boundary.

## Real producer callbacks and missing hardware questions

Original M4 ROM function `0x1FFD949A`, when `state[0] == 1`, calls RTOS event post `0x1FFD53BA(8, 1)` at `0x1FFD94A2`. The other original helper `0x1FFD9654(0)` posts `0x1FFD53BA(8, 4)`; called with `1`, the latter instead posts event9/bit8. The original ROM contains a small callback descriptor at `0x1FFD02C0` pointing at `0x1FFD949B` and carrying the diagnostic name **`ISR INPUT REQ`**; a separate descriptor at `0x1FFD02A8` points at `0x1FFD94AD` (`ISR SOUND REQ`). Firmware `0x1FFD955E` passes the selected descriptor into original service `0x1FFDF0FE`.

The 65-second private trace **did** show `0x1FFD94A2` executing **three times before** the later A002/RTOS wait, but **did not show it running afterward** in this window. That distinction matters: it is wrong to claim event8 has no producer. Events may have been posted and consumed earlier; a *post-request* callback/IRQ is what is still unverified. The `0x1FFD9654` helper was not seen in the filtered sample. Original callback registration and its actual peripheral DMA/IRQ trigger still need to be correlated. The current EXeSX `hw/arm/exesx-imx7ulp-dma.inc` explicitly has **no M4 DMA0 transfer or IRQ engine**, and `exesx-imx7ulp-dmamux.inc` stores M4 source configuration **without synthesizing DMA requests**. This is a **plausible unmodeled hardware dependency**, not yet proof that DMA0 would produce this exact event8 wakeup.

## Next executable, non-forged proof

1. Set read-only stop/trace at the **real M4 event8 wait** `0x1FFD9624` and capture CPU registers, state[1] and RTOS object8 wait flags; do not change R0, R1, PC, or semaphore state. If breakpoints excessively perturb the cold boot, use narrowly filtered no-debugger TB+MMIO trace.
2. Correlate the original **ISR INPUT REQ** descriptor `0x1FFD02C0`, its registration `0x1FFDF0FE`, actual M4 DMA0 `0x41008000`/DMAMUX0 `0x41020000` configuration and real interrupt signaling. Check whether a plausible hardware completion occurs *after* the later A002 enters event8 wait.
3. Determine whether the expected event8 producer is a real peripheral completion, another original M4 task, or a firmware protocol state transition. Fix only observed emulated hardware semantics, with a synthetic actual-ARM regression and disabled/control case. **Do not simply post event8, modify the original queue, overwrite the return value, or force A7 boot mode to CA05**.
4. First confirm A7 resumes at `0x60048F18` and `0x6004A2B0`, then examine how genuine 0xCA05/special startup selection is established. After native `0x600108A8` event wait is reached, release the held startup chord and drive original `0x93,0x93,0x94`; only count A7 `0x60010910`/`0x60010928`/`0x6003A878` as a confirmed accepted factory sequence. Finally distinguish the separate `0x400B(2)`/LCD menu-painter gate.
