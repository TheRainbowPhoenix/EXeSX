# Original A7 RTOS initial boot gate: service 0xA004 (24 October 2026)

## Correct the prior hypothesis using owner's original decomp

The original A7 main RTOS task is `Task_MainTask`. It branches on
`_DAT_622E6FD0`: zero selects `FUN_6004A0B4` (first boot);
nonzero selects `FUN_60049D1C` (subsequent initialization).
`FUN_60011860` is *not* a separately scheduled UC3 task; it is a
reinitialization routine invoked by several application/power paths.
Its failure to execute does not prove the A7 RTOS scheduler is broken.

On first boot, `FUN_6004A0B4` calls `FUN_60049C18`
*before* `UC3_act_tsk(0x1E)`, `UC3_act_tsk(2)` and
other initial task activations. These do not happen until
`FUN_60049C18` returns.

`FUN_60049C18` calls `FUN_6000F688`;
`FUN_6000F688` calls `FUN_60009220`, which stores
`0x2D0` in a shared power setting and calls
`FUN_60009284` to send synchronous
`FUN_601782C8(2, 0xA004, {2}, 1)`.
Original M4 `FUN_1FFD9D44(2)` dispatches to
`FUN_1FFDF49E`, which updates power-setting state.
These are firmware source facts, **not assumptions that the response
has already been acknowledged**.

## Actual no-debugger original OSUP evidence

Linux native QEMU, owner's unchanged original BIOS and M4,
source-derived synthetic eMMC and real `-d exec` trace.
The local trace remains PRIVATE: `a7_cold_trace_private.log`.
This is a real executed translated-block log (not `in_asm`).

The A7 executed TBs starting at `0x6004A0B4`,
`0x6004A104` (BL to `FUN_60049C18`),
and in `FUN_60049C18` through **`0x60049C4C`**.
Disassembly of the original A7 at `0x60049C4C` gives
`BL 0x6000F688`, the function that invokes
synchronous **power IPC `0xA004`**. The next A7
TB start `0x60049C50` was **not** present in this
six-second bounded trace, and neither was
`0x6004A108` (return to initial task activation path).
`0x601782C8` (IPC dispatcher) *was* executed.

A previous original guest GDB breakpoint run recorded the A7
`FUN_601782C8` call for `0xB000` at approximately 1.27 host
seconds and `0xA004` at approximately 1.53 seconds. That agrees
with this stage ordering; those breakpoints perturb scheduling and
are not completion proof.

### What this means

**The A7 RTOS main task IS running, and its choice of first-boot
branch is correct.** We have narrowed the first observed non-return
to the initial **`0xA004` power IPC stage, before initial auxiliary
task activation**. This corrects the earlier assertion that the
scheduler never dispatched a supposed `FUN_60011860` startup task.
A later shared slot containing `0xA002` does not contradict the
short trace: commands can progress at different rates in subsequent
runs, so a strict permanent deadlock still needs a longer differential
and return-site proof.

Remaining diagnostic steps: correlate service request envelope/status,
original M4 `0x1FFD9D44`/`0x1FFDF49E` execution, and the
**A7 return at `0x60049C50`**, without debugging the two CPUs into a
different scheduling regime. Next check `0x8800`/`0x9000` services
and `UC3_act_tsk` boundary. Do not patch guest ROM or fabricate a
reply. Use `scripts/analyze_a7_cold_start_exec.py` on private
`-d exec` logs.

The test menu is **not yet visibly rendered** by cold boot.
The existing authentic `version-event-wait` replay previously
reached `0x6003A878` using actual key events; the new held power-on
chord implementation is independently ARM GPIO tested.
