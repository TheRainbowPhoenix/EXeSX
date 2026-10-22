# Original DY357 user-area CMD17 caller/return triage — 22 October 2026

## Source and execution context

Private, user-owned `/mnt/data/work27/private.elf` extracted from checksum-validated original `OSUP.BIN`; QEMU v10.1.0 EXeSX opt-in USDHC1 with boot1 PVOS metadata; same diagnostic 4 KiB RAM mapping at `0xb0000000`. No private ROM, sectors, executable, or execution log committed. All addresses below are the original guest virtual/physical ROM addresses and were obtained by disassembling the genuine original ARM payload; do not equate static call targets with dynamic execution.

## Direct caller map, established by scanning real ARM BL encoding

The new, firmware-free `scripts/scan_arm_bl_calls.py` walks ELF32 ARM PT_LOAD segments, finds *direct ARM BL* instructions, resolves PC+8-relative signed displacement and outputs caller addresses only. Local output for original DY357:

| Callee | Direct caller(s) |
| --- | --- |
| `0x60018194` single-block PIO reader | **`0x60018c50`** |
| `0x60017fac` multiblock PIO reader | `0x60018c7c`, `0x60018d0c`, `0x60018d94`, `0x60018df4` |
| `0x60017e04` multiblock PIO writer | `0x60018c88`, `0x60018d18` |
| `0x60018c08` higher-level transfer wrapper | `0x6000aad8`, `0x60018e5c`, `0x60020dbc`, `0x60030abc`, `0x6005846c`, `0x6005882c`, `0x6006347c`, `0x6006b728`, `0x6006bda0` |

At `0x60018c08`, arguments `r0=LBA`, `r1=block count`, `r2=buffer` are saved in `r4/r5/r6`. The code selects the **single-block** path only when `r1 == 1`: `0x60018c48 mov r1,r6; 0x60018c4c mov r0,r4; 0x60018c50 bl 0x60018194`; `0x60018c54 mov r7,r0` captures the actual reader's return. Multi-block paths use `0x60017fac` when the request is a read. Its completion handling at `0x60018c90..0x60018cb0` retries **at most ten** times while return `r7 != 0`, then returns `r7`; negative errors can trigger `0x60019c18` before retry. This is a **hardware transfer result**, not necessarily a metadata validation result. The higher-level caller is where any sector-content signature, capacity, or CRC check must be established.

## Live breakpoint experiment and important negative result

The original firmware and PVOS synthetic medium were run with `-S -gdb tcp:127.0.0.1:15193`; genuine RSP software breakpoints `Z0` installed at **`0x60018c50`**, **`0x60018c54`** and **`0x60018cac`** before continuing. Over a bounded ten-second run, **zero hits were received**, and after interrupting the guest the A7 was at the previously established idle `0x601cbcf8`. Earlier debugger probes of helper entries `0x60017e04`, `0x60017fac`, `0x60018194` were likewise negative. Crucially, this does **not** establish that those functions were not executed: the identical emulator configuration's independent QEMU SD/MMC command trace previously observed real CMD17 user LBAs0/`0x01af5fff`. As resolved in the later section, these accesses can use the independent SDMA reader. The inconsistency may arise from active CPU/thread selection, breakpoint insertion mode, instruction patching in ROM, exception/core switching or a different software call path. **Static BL analysis is not dynamic caller proof.** Diagnose the breakpoint discrepancy first, rather than claiming a sector content check failed.

Separate direct GDB `Z0` at low-level `0x60017950` generated at least one breakpoint hit. Subsequent attempts to single-step across it and re-enable the breakpoint were not reliable in the bounded run; do not infer return-value patterns from that incomplete trace.

## What can and cannot be concluded

- **Confirmed from original native QEMU SD/MMC trace:** with source PVOS metadata at boot1 LBA0/32 and earlier USDHC CMD12/BRR corrections, original BIOS reads user LBAs `0` and `0x01af5fff` after two 32-sector boot1 reads.
- **Confirmed from original ARM source disassembly:** the single-block wrapper `0x60018c08` chooses `0x60018194` and returns its status in R0 after a bounded retry policy. Nine direct callers of the wrapper are address-resolved.
- **Not yet confirmed:** whether these *particular* CMD17 user reads take the `0x60018c08` wrapper, the actual dynamic return value for either read, a metadata compare following them, the true installed user-area contents, or a status setter leading to OS entry.
- **Independent missing hardware:** the private FlexBus `0xb0000000` RAM mapping is diagnostic, not authentic. DMA1 remains only partially modeled.

## Next experiment

Resolve the GDB breakpoint paradox using an ARM guest control breakpoint at a **known** executing site plus explicit `Hg` and `Hc` thread selection, then correlate command issuance (`CMD_XFR_TYP=0x11220010` and live `USDHC1.ARGUMENT`) with R14/LR and the first return. Alternatively use QEMU TCG plugin memory/MMIO tracing and a precise PC filter or QEMU gdbstub hardware breakpoints `Z1` rather than software `Z0` on the XIP ROM mapping. Watch `0x60018c54` and `0x60018cac` only after establishing that they execute in the actual command path, and capture `r0,r4,r5,r6,r7,r14` at each return.

Only a verified negative return and a subsequent branch dependent on the actual blank-user-sector contents would justify synthesizing further **source-derived** media; never forge an OS-launch flag, sector signature, or hardware success response.


## Critical alternate low-level I/O route found after negative PIO breakpoint result

The PIO reader `0x60018194` is **not the only way the original BIOS can read a block**. Genuine disassembly of `0x60018458..0x60018588` shows an independent host-controller read setup using a DMA system address register (`USDHC1.DS_ADDR`), CMD23, and multi-block transfer; it is called directly from `0x60018ef8`, `0x60018f84`, and `0x60018ffc`. A second routine `0x60018590` has caller `0x60019310`. Thus the failure to hit `0x60018c50` **may be expected** if the two user-sector requests use one of these other paths. The traced host command proves an MMC command occurred, not that the PIO wrapper was its origin.

**Follow-up candidate breakpoints** (not yet proven dynamic): `0x60018ef8`, `0x60018f84`, `0x60018ffc` before the `BL 0x60018458`; `0x60018584` for its direct return value; `0x60019310` for the alternate routine. Also test the higher-level `0x6000a8e4` invocation of `0x60018e20`, since this function loops over single-block `0x60018c08` calls. Do not assume CMD17 necessarily uses `0x60018194` when there are DMA-backed alternatives.


## Confirmed live user-area last-LBA return path (subsequent private native run)

The initial PIO breakpoint discrepancy is now resolved: the original user-area last-LBA read uses the **SDMA-backed** routine `0x60018458`, not PIO `0x60018194`.

The following CPU0 **actual hardware execution breakpoints** were hit in a cold original-ROM run with the same private PVOS-backed synthetic eMMC. At all stops `USDHC1.ARGUMENT=0x01af5fff` and `CMD_XFR_TYP=0x11220010` (CMD17):

| Breakpoint | Observed original A7 state | Interpretation |
| --- | --- | --- |
| `0x60018458` | `LR=0x60018f88`, `R0=3` | Entry of actual SDMA reader from wrapper |
| `0x60018f88` | `R0=0` | Return from reader: successful host transfer |
| `0x60018f90` | `R0=0` | Wrapper's no-error branch reached |
| `0x60018fa4` | `R0=0`, `SP=0x620ffe88`, `[SP+20]=0x600211b0` | Wrapper returns 0 to higher storage function |
| `0x600211b0` | `R0=0`, `R4=3`, `R5=0`, `R6=0x624134e0`, `[SP+20]=0x60021274` | Higher storage wrapper receives successful SDMA result and has actual 512B buffer |
| `0x600211d4` | `R0=0` | Transfer result is nonnegative |
| `0x600211e0` | `R7=1` | Higher wrapper's success flag set, returns **R0=1** |
| `0x60021274` | Original ARM `CMP R0,#0; BNE 0x60021284` | Caller accepts nonzero returned success and marks its initialization flag |

Original instruction path:

```asm
600211ac  bl  0x60018f3c   ; SDMA transfer wrapper
600211b0  cmp r0,#0       ; 0 means no low-level error
600211b4  bpl 0x600211d4
600211d4  mov r7,#1       ; set success
600211e0  mov r0,#1
600211e4  pop {r4,r5,r6,r7,r8,pc}
60021270  bl  0x60021114
60021274  cmp r0,#0
60021278  bne 0x60021284
60021284  strb r5,[r4]    ; sets a per-device init byte, not yet identified as OS flag
60021288  mov r0,r5        ; R5 was 1 in this caller
```

**Conclusion grounded by live return-value captures:** the last user-area `CMD17 LBA0x01af5fff` was *successfully transferred*, and the immediate higher wrapper **accepted it**. No low-level sector-read failure, CRC error or host timeout was observed at this call chain. This does **not prove the sector CONTENTS are valid**—the shown code checks transfer status and sets a byte after success. The buffer address `0x624134e0` is now known. It is not the separate global status byte `0x62413241`, which remained 0 during the earlier 12-second watchpoint window.

The next consumer to investigate is `0x60021290..`, which calls `0x60020cd0` as a **distinct downstream metadata/content classifier**, with early branches for return types `1,2,3`. Do not treat `0x60020cd0` as proven to validate this exact same LBA until the dynamic caller and buffer are correlated. After user sector reads, the BIOS still returns to WFI housekeeping and no extracted OS-entry translation has been seen.

**Candidate next breakpoint locations:** `0x60021274`, `0x60021284`, `0x600212b4`, `0x600212cc`, `0x60021328`, `0x60021380`. Record caller LR, R0/R1 and buffer pointer at each and compare PVOS-only versus source-derived user-area candidate **without forging bytes or forcing boot flags**.
