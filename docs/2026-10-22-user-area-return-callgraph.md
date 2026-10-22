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

The original firmware and PVOS synthetic medium were run with `-S -gdb tcp:127.0.0.1:15193`; genuine RSP software breakpoints `Z0` installed at **`0x60018c50`**, **`0x60018c54`** and **`0x60018cac`** before continuing. Over a bounded ten-second run, **zero hits were received**, and after interrupting the guest the A7 was at the previously established idle `0x601cbcf8`. Earlier debugger probes of helper entries `0x60017e04`, `0x60017fac`, `0x60018194` were likewise negative. Crucially, this does **not** establish that those functions were not executed: the identical emulator configuration's independent QEMU SD/MMC command trace previously observed real CMD17 user LBAs0/`0x01af5fff`. The inconsistency may arise from active CPU/thread selection, breakpoint insertion mode, instruction patching in ROM, exception/core switching or a different software call path. **Static BL analysis is not dynamic caller proof.** Diagnose the breakpoint discrepancy first, rather than claiming a sector content check failed.

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
