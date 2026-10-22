# DY357 post-initialization status watchpoint / storage caller triage

**22 October 2026** — owner-supplied original OSUP SHA-256 `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`; pinned private QEMU 10.1.0 build after opt-in USDHC CMD12 and FIFO rollover fixes; checksum-valid PVOS at boot1 LBA0/LBA32 and otherwise synthetic 16GB card. Uses the same *unverified and private* 4 KiB RAM diagnostic window at `0xb0000000`. Firmware and raw debug logs are never committed.

## CPU0 write watchpoint, two-stage protocol

The user-requested write watchpoint `Z2,62413241,1` was exercised against original ARM firmware using QEMU's GDB Remote Serial Protocol.

Installing it **from reset** records repeated genuine writes at **`PC=0x60254714`**, LR `0x601e668d`: that is the original BIOS's RAM/BSS zero-initialization helper, writing zeros into a region that includes the flag. These are initialization effects, not evidence that a later OS-launch service cleared an already-set ready flag.

Revised controlled protocol:

1. Start original firmware **paused** with `-S -gdb tcp:127.0.0.1:1234`. Set execution breakpoint at **`0x6001000c`**, the byte-status accessor that reads `0x62413241`.
2. Continue until the genuine A7 reaches that accessor. It was reached with **LR `0x60007e50`**, `R0=0x6232c184`, and RAM byte `0x62413241=0x00`.
3. Remove this accessor breakpoint **before continuing** (otherwise repeated stops at the same instruction hide subsequent activity). Install the **one-byte write watchpoint** only now, after firmware zero initialization.
4. Continue for a bounded **12 seconds**. The genuine original BIOS issued **zero later write-watchpoint events** in that interval; the byte remained unset. This does **not** prove that no writer exists, that an earlier setter is absent, or that this flag launches the OS.
5. A separate control execution with GDB breakpoints at `0x60018c08` and `0x60018cac` returned **zero hits** over the same window and stopped normally at BIOS idle `PC=0x601cbcf8`. Therefore those low-level candidates are not confirmed to be the *higher-level user-LBA consumer*; merely treating their disassembly as the observed caller would be unsupported.

The original read status path `0x6001000c` is invoked repeatedly from **LR `0x60007e50`**; the corresponding BIOS disassembly should be traced to determine whether that caller is a persistent service/housekeeping loop. Breakpoints inside the common USDHC submitter `0x60017950` do hit, but must be single-stepped past once to avoid repeated breaks at the same PC. This is why a command-submitter hit alone does not identify the sector-validator's caller.

## Disassembly-grounded interpretation

```asm
6001000c: ldr  r0,[pc,#0xcb8]    ; pointer at 60010ccc
60010010: ldrb r0,[r0]           ; status byte 62413241
60010014: tst  r0,#1
60010018: beq  60010024
6001001c: mov  r0,#1
60010024: mov  r0,#0
6001002c: mov  r0,#0
60010030: ldr  r1,[pc,#0xc94]    ; same pointer
60010034: strb r0,[r1]          ; deliberate clear writer
```

The only watchpoint events observed **from reset** are the RAM zeroer's stores, and after the first true accessor there are **no observed writes for 12 seconds**. Consequently the original firmware still lacks a demonstrated status-set event; forcing bit0 would conceal the missing producer and is not an evidence-backed emulator fix.

The earlier original SD/MMC trace still establishes **boot1 CMD17 LBA0, boot1 CMD18 LBA64/96, user-area CMD17 LBA0 and LBA `0x01af5fff`**, with no detected OS translation at `0x60400000+`. The user-area sector consumers and return-value checks **remain unresolved**. This follow-up did *not* fabricate sector contents, change hardware registers, or claim the user LBA0 probe succeeded or failed based solely on the I/O command trace.

## Reproducible and safe next steps

A firmware-free helper `scripts/watch_postinit_status.py` encapsulates the GDB post-BSS watchpoint protocol. Invoke only against your privately run `qemu-system-arm -S -gdb tcp:127.0.0.1:1234` guest; its output is metadata, not instruction or flash bytes:

```bash
python3 scripts/watch_postinit_status.py --seconds 12
```

Before modifying further hardware, place a **return breakpoint** at the actual caller of the two user-sector reads, retaining R0 (status), LR, destination buffer address and the expected comparison fields for each invocation. Identify the parent routine by branch/call tracing from the original **CMD17 user LBA0 and `0x01af5fff` call sites** and correlate the return with later calls to the status setter. This should reveal whether the BIOS is waiting for a storage signature, a valid metadata region, M4 handoff, or another interrupt. There is no evidence yet that a particular forged sector or manually set status flag would fix boot.

**No real OS entry, display frame, or LCD text was verified.**


## Additional breakpoint stepping: genuine command-dispatch caller addresses

A follow-up private run used software breakpoints at the actual command submission instruction `0x60017950`. **Important debugger detail:** after each stop, remove `Z0`, single-step the stopped instruction once, re-add `Z0`, then continue; otherwise repeatedly stopping at the same breakpoint address produces misleading repeated hits.

Sixteen distinct command-dispatch stops in the bounded experiment identified genuine return addresses:

- Initialization: `0x60017a84`, `0x60017aa4`, `0x60017ac4`, `0x60017c74`
- eMMC setup/status: `0x6001966c`, `0x600196a4`, `0x600196c8`, `0x600196f4`
- Partition/control: `0x60018a24`, `0x60018a78`, `0x60018a90`
- Multiblock setup: `0x60018330` (observed twice)

These are **direct dispatch callers**, not yet established *user-sector validation callers*. The original ROM's `0x60018330` write of CMD23 corresponds to multiblock read setup in `0x600182c0..`; do not claim its return value means eMMC user-area content is valid.

This focused, debugger-driven trace reinforces that storage is active before the BIOS idles but **does not yet isolate the consumer of the final two user CMD17 buffers**. A next pass should break on CMD17 issuance and the final return from the PIO reader, correlating the live partition/LBA from `USDHC1.ARGUMENT` with that caller's R0 and destination pointer. No emulator semantics or flash contents were changed for this trace.
