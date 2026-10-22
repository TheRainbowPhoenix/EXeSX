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


## Major finding: actual content validator rejects blank user headers; real OSUP headers pass

The immediately downstream classifier `0x60020cd0..0x60020d6c` is a genuine **CASIODICS06 component header validator**. It sums bytes 0–509, compares with its stored 16-bit checksum at bytes 510–511, compares the first 11 signature bytes with the literal `CASIODICS06`, then classifies byte 11: **B→R0=1, A→R0=2, F→R0=3**; unknown signature/checksum returns zero. A live software breakpoint at `0x600212cc` on the original **blank synthetic user area** observed `R0=0` immediately after `BL 0x60020cd0`; `CMP R0,#1; BNE 0x600213cc` rejects this initial boot component. This is now a proven **content-level rejection** after successful CMD17, distinct from the transfer-status return.

The user supplied original OSUP contains each of the three checksum-valid header sectors:

| Original component | Source OSUP offset | True installed user LBA (experiment) | Declared span |
| --- | --- | --- | --- |
| `CASIODICS06B` BIOS | `0x00140000` | **0** | `0x12ad` = 4,781 sectors |
| `CASIODICS06A` OS | `0x00395a00` | **`0x12ad`** | `0x4415` = 17,429 sectors |
| `CASIODICS06F` resources | `0x00c18400` | **`0x56c2`** = 22,210 | `0xe93e` = 59,710 *declared* sectors, with resource payload truncated in OSUP |

These source byte offsets match **exactly** the sum of the preceding component's declared 512-byte sectors. The headers are not synthetic guesses and pass the same checksum condition the BIOS uses. Physical production media is still not dumped, so equivalence of *all* installed payload bytes remains unproven.

### Private reversible media experiment A/B/C/D

The QEMU emulated eMMC backing is sparse; boot1 PVOS metadata at LBA0/LBA32 was retained across all variants, and only source-authentic data from the user-owned OSUP was inserted into the *user* partition, starting at host backing byte offset 8 MiB. No Casio bytes, derived media or private traces were committed.

1. **Blank user area (baseline):** original A7 breakpoint `0x600212cc`: **R0=0** (CASIODICS06B header classification failed).
2. **Only genuine B header at user LBA0:** same breakpoint: **R0=1**. Original BIOS continues to the **next CMD17, LBA `0x12ad`** (4,781).
3. **B, A, F header sectors at user LBAs 0, `0x12ad`, `0x56c2`:** original A7 reaches all three validator stages. Breakpoint `0x60021384`: **R0=3** for F; `0x600213c4` is reached, after which wrapper `0x60021290` returns the component-table success flag. USDHC1 command register at these stops confirms LBA `0x56c2`.
4. **Original available OSUP component bytes, copied contiguously starting at user LBA0** (source OSUP offset `0x140000`; 29,360,130 bytes total including container trailer): header checks pass, and CPU enters additional storage/BIOS functions. At ten seconds the independently captured A7 is **back at idle `0x601cbcf8`** with `0x62413241=0`, USDHC1 idle `PRES_STATE=0x01ff0008`, `INT_STATUS=0x3`. A five-second snapshot landed at `0x60006908` during active work; that is a **transient**, not a stable blocker. The declared F resource payload extends beyond the bytes available in the package, so this image is **not a faithful full installation**.

**Conclusion:** The **user-area component header layout is now byte-for-byte consistent with the original BIOS's own validation logic and the original updater's relative sector lengths**. The blank-image boot problem is not a mysterious lower-level read error: the first classifier requires `CASIODICS06B` at the start of the user area. Staging valid header sectors demonstrably unlocks the A and F reader branches. Nevertheless no OS entry, LCD pixels, or text have been confirmed; a separate readiness/handoff dependency persists after the header chain.

### Immediate next trace to target boot launch

In `0x60021290..0x600213c8` the accepted header chain sets per-component flags including bit4, bit3 and bit5 in a table based at the pointer stored near `0x60021768`. Compare this table after blank vs header-only vs contiguous-update runs, and trace **where the OS startup coordinator checks these flags**. Couple this to the true producer/consumer of global byte `0x62413241`, not a forced bit write. Also determine the firmware's actual semantics for the incomplete F component (its declared `0xe93e` sectors versus the smaller stored resource blob), and how the real updater provisions GP1/user partitions. Do not forge the absent resource data.


## Hardware-state comparison after header acceptance (four private images)

Fresh private QEMU monitor snapshots after four seconds on identical original firmware, varying only source-authentic user-area data, recorded a reliable memory-table differential:

| Private user medium | `0x6232D5D8` | `0x6232D5DC` | `0x62413241` | Interpretation |
| --- | --- | --- | --- | --- |
| Blank user area | 0 | `0x2` (initial/default) | 0 | B-header classification fails |
| Authentic **B header only** at user LBA0 | 0 | `0x2` (initial/default) | 0 | B accepted, next A header missing |
| Authentic **B/A/F headers** at user 0/`0x12AD`/`0x56C2` | **`0x12AD`** | **`0x56C2`** | 0 | BIOS successfully records OS and resource component locations |
| Available contiguous update payload from original BIOS component offset | **`0x12AD`** | **`0x56C2`** | 0 | Same component map; additional storage work can be in progress during snapshot |

The literals in real original ARM code at `0x60021798` point to RAM `0x6232D5DC`, and at `0x600217B8` to `0x6232D5D8`. In the `0x60021290..0x600213C8` success path, those arrays receive the dynamically computed subsequent component LBAs. This is an *independent runtime confirmation* of the installed relative-sector layout, not merely arithmetic from OSUP file offsets.

The external `0x62413241` readiness flag remains **zero** even with full available source-derived component bytes, so **header classification alone is not the OS-launch gate**. An intermediate snapshot at `0x60006908` or `0x60017374` during the full-component run is transient; a later ten-second snapshot returned to `0x601CBCF8` idle with USDHC host `0x01FF0008` / `INT_STATUS=0x3`. The F component's declared length exceeds the source file payload, so treating the truncated OSUP as a complete installed eMMC remains unjustified.

Exact original checksum-valid bytes from OSUP were staged only in *private local sparse synthetic eMMC files*. Public documentation exposes component names, LBAs and bounded register snapshots, not the actual update bytes or sectors.


## Complete original BIOS component-loader status and outer caller

The accepted B/A/F chain is not merely three signatures: the original BIOS's coordinator `0x600213D8..0x60021664` constructs six-bit status flags at `0x622E6FC4`. It checks required bits 0,4,5,2,1 in its final exit path and returns an explicit negative error if any required flag is absent. The status word was observed **`0x0000003F`** at a genuine CPU0 hardware breakpoint at `0x60021604` in both authentic-header-only and authentic-available-component-data runs. At `0x6002162C`, `0x60021650` and `0x60021660` the same `R8=0x622E6FC4` state satisfied each required branch and the coordinator returned **R0=0 (success)**.

The stack-saved parent return at `[SP+28]` was **`0x600216BC`**. That wrapper, `0x60021668..0x600216CC`, returned zero after running the successful coordinator, and `[SP+20]` at its return was **`0x6004A1C0`**. Genuine BIOS disassembly shows:

```asm
6004a1bc bl 0x600216d0     ; component setup/coordinator
6004a1c0 bl 0x6000bd14     ; next boot/BIOS initialization
6004a1c4 bl 0x601cd5ec
6004a1c8 bl 0x601cad9c
6004a1cc bl 0x601b3d10
6004a1d0 bl 0x601b3d48
6004a1d4 bl 0x60049f5c
```

This confirms the *actual dynamic high-level caller* and that accepting all three headers brings firmware back to the broader BIOS initialization sequence, **not directly to extracted OS entry**.

In a 10-second bounded native run with all available real OSUP component bytes staged contiguously in private synthetic eMMC, the A7 eventually returned to `0x601CBCF8` idle. The separate global service status `0x62413241=0` and no extracted OS translation still prevent claiming OS boot. An intermediate 5-second snapshot on this more complete media at `0x60006908` with USDHC transfer in flight was a transient; no conclusion about a permanent timeout should be drawn from it.

**Updated next focus:** trace boot coordinator `0x6004A1C0` onward, especially the results of `0x6000BD14` and `0x60049F5C`, and identify which event/setter makes `0x62413241` nonzero. The verified storage-header stage has fully succeeded (status `0x3f`), so further arbitrary SDHCI fixes or forcing the status byte would not be evidence-based. The full F resource payload is absent from OSUP and may eventually matter, but **the current trace does not prove it causes the idle state**.


## Actual execution beyond the component-loader return

A separate original ARM breakpoint run using the same three authentic user component headers captured the following **live** high-level startup instruction sites:

| Guest PC | Captured original A7 state / significance |
| --- | --- |
| `0x6004a1c0` | Returned from `0x600216d0`, **R0=0** successful component-loader status |
| `0x6004a1d8` | Later startup service reached with **R0=1** |
| `0x6004a1e0` | Subsequent initialization reached |
| `0x6004a1ec` | Additional BIOS initialization reached with R0=4 |
| `0x6004a224` | Further branch sequence reached; R6=0 on this run |

This confirms that the original firmware does not immediately abort initialization on the component table: it actually executes a significant portion of the next high-level BIOS startup function `0x6004a170..`. By later bounded snapshots it still reaches `0x601cbcf8` WFI idle with global byte `0x62413241=0`; **no verified OS entry**. Values seen at these PCs are intermediate registers, not proven success/failure outcomes of their preceding calls. The precise next missing service/event is still unresolved.

Next candidates from original disassembly: trace the outputs of `0x60049b30`, `0x60008e98`, `0x60007284` and the conditional branch at `0x6004a250` if those sites execute, and identify the event that leads to the guest OS entry `0x605e3ad0`. Use the same private media A/B controls and retain source-only data.
