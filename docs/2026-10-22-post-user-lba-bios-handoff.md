# After boot1 PVOS: user-area boundary reads and BIOS idle-path audit

**22 October 2026** — original private SHA-validated DY357 `OSUP.BIN`, pinned EXeSX QEMU native build from PR #27, 3- and 5-second bounded runs. Local inputs and traces remain uncommitted.

## Firm evidence: CMD18 stop is no longer current blockage

Reproduced the original ARM BIOS (not synthetic guest) with user-supplied BIOS/OS loader ELF, boot1 PVOS metadata at LBA0/32, opt-in USDHC1 eMMC, and previous diagnostic board settings. The synthetic storage is blank beyond the two PVOS header sectors. To get past the separately unidentified FlexBus peripheral at `0xb0000000`, the local run uses a **temporary 4KiB experimental RAM** mapping at that address; it is *not* modeled device semantics, not an authenticated physical component, and not committed.

Native `sdhci_send_command` trace:

```text
CMD06 ARG[0x03b30200]   eMMC boot1
CMD17 ARG[0x00000000]   boot1 primary PVOS header
CMD23 ARG[0x00000020]   32 blocks
CMD18 ARG[0x00000040]   boot1 64..95
CMD23 ARG[0x00000020]   32 blocks
CMD18 ARG[0x00000060]   boot1 96..127
CMD06 ARG[0x03b30000]   return to user area
CMD17 ARG[0x00000000]   user LBA 0
CMD17 ARG[0x01af5fff]   user LBA 28,270,591
```

The terminal LBA is precisely **`PVOS[0x14]=0x01af6000` minus one** and is thus consistent with a bounded storage-region geometry or verification probe. This equality does not identify the sector data format or prove whether the original firmware *accepted* the blank sectors. Do not populate data without discovering the installed writer/validator for these user-area sectors.

QEMU monitor at three seconds with CPU#0 explicitly selected:

```text
R15 = 0x601cbcf8
R14 = 0x601cbcc4
PSR = 0x6000011f ... sys32
PRES_STATE = 0x01ff0008   (USDHC1 idle; SDSTB=1)
INT_STATUS = 0x00000003  (command + transfer complete)
```

There is **no new USDHC data inhibit**. Previous claim that `0x601cbcf8` itself was an unknown storage poll was misleading: disassembling the original BIOS yields:

```asm
601cbc9c  push  {ip,lr}
601cbca0  ldr   r0, [pc,#0x3ec] ; pointer to housekeeping flag
601cbca4  ldr   r0, [r0]
601cbca8  cmp   r0,#0
601cbcac  beq   0x601cbcc0
601cbcb0  ldr   r0, [pc,#0x3e0]
601cbcb4  ldr   r0, [r0]
601cbcb8  cmp   r0,#0
601cbcbc  beq   0x601cbcfc
601cbcc0  bl    0x60007f88
601cbcc4  cmp   r0,#0
601cbcc8  bne   0x601cbcfc
601cbccc  mov/orr r0, #0x40410010
601cbcd4  ldr   r1, [r0]
601cbcd8  mvn/bic/and/orr   ; update SMC1 status bits
601cbce8  str   r1,[r0]
601cbcec  ldr   r0,[r0]
601cbcf0  dsb   sy
601cbcf4  wfi
601cbcf8  isb
601cbcfc  pop   {r0,pc}
```

At `0x60007f88`, the BIOS reads an SCG1 clock-state register (literal at BIOS `0x60008374` resolves to **`0x403e060c`**), masks low 6 bits and compares to `0x1d`. Thus the routine can be a normal idle/sleep decision. Two independent monitor snapshots (3s and 7s) instead show the **actual SCG1 register** at `0x403e060c` is `0x8080805d`; its low six bits are **exactly `0x1d`**, so `0x60007f88` returns **zero** according to the literal `CMP r0,#29; BHS` branch. The CPU register `r4=0x19` belongs to a different context and must **not** be mistaken for SCG1 clock status. This does **not** mean the SCG1 physical clock tree is proven accurate; the emulator's SCG1 behavior is still an approximation.

The main BIOS service function `0x601cbd00` includes calls to `0x6001000c`, `0x600162a0` and `0x6004d72c`, and loops over recurring housekeeping. `0x6001000c` reads a global status flag (address loaded from literal `0x60010ccc`) and returns its low bit. Determining the producer of that global flag and the success/failure return value of the post-CMD17 validator is the **next best reverse-engineering task**, not another arbitrary memory mapping or a forced jump to OS.

## OS-entry audit

The private five-second native QEMU `-d in_asm` log translates **no A7 blocks in the extracted OS region starting `0x60400000`**. Therefore no observation of the OS entry target `0x605e3ad0` occurred. Translation logs are a *coverage signal*, not a chronological per-instruction execution trace or a substitute for GDB breakpoints. The new `scripts/audit_osup_boot_handoff.py` reports command sequence and translated OS-range PCs from a user-owned text trace; it deliberately does not dump or embed ARM instructions or storage bytes.

## Next prioritized work

1. Disassemble the caller and *return-value decision* for user LBA0 and `0x01af5fff`, including any header compare and PVOS capacity check; capture results with a QEMU GDB breakpoint or focused trace point.
2. Identify the global byte at `0x60010ccc`'s referenced RAM address, all writes/callers to its low status bit, and whether empty synthetic user area prevents OS handoff.
3. Model external FlexBus target at `0xb0000000` from actual chip-select and halfword protocol; the provisional RAM mapping is not a production implementation.
4. Implement documented eDMA1 RAM transfer and DONE events from real requests, avoiding fake completion; no full DMA engine is yet available.
5. Only populate missing user-area sectors from **verified installer output**, never guessed signatures or ROM fragments.

No original Casio OS entry or LCD/text output established. No private files uploaded.


## Stable flag snapshot and direct decision path (second private test)

Independent original BIOS cold-run snapshots at **3 and 7 seconds** using the identical private PVOS boot1 synthetic backing and opt-in controller both reported:

| Guest address | Read value | Evidence-backed interpretation |
| --- | --- | --- |
| `0x62413240` | `0x00000000` | Global status storage containing the byte below |
| `0x62413241` | `0x00` | Firmware global flag currently unset |
| `0x403e060c` | `0x8080805d` | SCG1 state; low 6 bits `0x1d` |
| `0x40410010` | `0x00030000` | SMC1 power-state register after BIOS writes |
| `0x40380024` | `0x01ff0008` | USDHC1 no active data/command inhibit |
| `0x40380030` | `0x00000003` | CC+TC latched |
| CPU0 `R15` | `0x601cbcf8` | ISB after WFI (not data read poll) |

Disassembly links the **only literal occurrence** of `0x62413241` in the extracted original BIOS executable to BIOS `0x60010ccc`. The `0x6001000c` function loads that pointer, performs `LDRB`, tests bit0, and returns 1 only when bit0 is set. `0x6001002c..0x60010038` explicitly **clears that byte to zero**. The main BIOS service at `0x601cbd30` calls this status accessor and, if zero, branches past the subsequent calls to `0x600162a0` and `0x6004d72c`. However, this alone **does not prove** that setting the byte launches the OS: the writer that sets it has not been identified and may use an indirect pointer or an interrupt handler. Do not force the byte.

The low six bits of SCG1 status are `0x8080805d & 0x3f = 0x1d`, so `0x60007f88` returns zero, permitting the BIOS sleep sequence. Prior speculation that clock status was **below 0x1d** was incorrect; corrected here. Both snapshots confirm the **same idle state** rather than a transient CPU PC sampling coincidence.

**Next strongest trace:** catch the real writer(s) of guest RAM byte `0x62413241` with a QEMU memory-access watchpoint and trace the exact caller/return of `0x6001000c`; separately trace the user-LBA0/`0x01af5fff` read consumer. A buffer write to the global flag and a valid OS launch must be independently demonstrated, not inferred from this disassembly.
