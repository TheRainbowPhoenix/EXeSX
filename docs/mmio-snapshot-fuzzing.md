# EXeSX differential MMIO fuzzer — real BIOS experiment

**Status:** working GDB injection, actual paused VM snapshot creation, automatic rejection of unsafe VM restore, successful **34-run** single-bit differential ARM execution. This is NOT proof of a functioning clock chip or OS boot.

## Reproduction

Prepare your *private* `a7-firmware.elf` from OSUP.BIN as described in `docs/local-firmware.md`. Never commit the firmware, the disposable VM snapshot (which contains guest RAM), or generated instruction bytes to this public repository.

```sh
# Uses the existing compiled QEMU 10.1.0 binary; no recompilation.
python3 scripts/fuzz_mmio.py private/a7-firmware.elf \
  --qemu build/qemu-system-arm \
  --profile profiles/clock-registers-probe-only.ini \
  --site poll --steps 13 --limit 34 \
  --out private/fuzz-register-4102603c

# Fast focused test (still replays actual BIOS to each breakpoint).
python3 scripts/fuzz_mmio.py private/a7-firmware.elf \
  --qemu build/qemu-system-arm \
  --profile profiles/clock-registers-probe-only.ini \
  --site poll --steps 16 --only zero,bit29,bit30,bit31,all_ones \
  --rollback restart --out private/fuzz-recheck

# Additional sites: --site initial or --site second-poll.
```

Output: `results.json` contains every stepped PC, successor PC, r1, CPSR, and branch indicator; `report.md` shows the first path divergences; `disassembly.txt` contains LLVM's ARM instruction disassembly. You only need `llvm-objdump` for the textual disassembly. The script constructs an ephemeral ELF text section from *your local* BIOS to let LLVM disassemble it; nothing is uploaded. Without LLVM, the PC trace still works.

### What is injected?

- Break at **0x60049938**, the ARM `LDR r1,[r0]` that polls **0x4102603C**.
- Pause before executing the read, set ARM `r1` to a candidate, and advance PC by 4 bytes to **0x6004993C**. **Only that one LDR is skipped**; the following `TST` and conditional `BEQ` execute for real in QEMU.
- Step 13 real ARM instructions while observing every transition; capture exception-vector entry, if any.
- Start from a pristine guest by restoring a validated VM snapshot **or** fully rebooting and replaying to the same breakpoint. Current EXeSX uses the second choice for correctness.

This is *single-read return-value injection*, not a true complete model of a physical peripheral. Other reads after the injected one are made against the clearly provisional `clock-registers-probe-only.ini` echo-back model.

## Actual 34-case measurement

The run used 34 distinct values: `0x00000000`, `1 << 0` through `1 << 31`, and `0xFFFFFFFF`. Each was captured after an independent cold replay to PC 0x60049938.

| Candidate(s) | Outcome at the first status test | First differing path |
| --- | --- | --- |
| Zero and individual bits 0–29 or 31 | `TST` finds bit 30 clear, `BEQ` back to 0x60049938 | 0x60049940 → 0x60049938 |
| Bit 30 alone (`0x40000000`) | `TST` finds bit 30 set, `BEQ` **not** taken | 0x60049940 → 0x60049944 |
| All ones (`0xFFFFFFFF`) | `TST` finds bit 30 set; same fall-through path | 0x60049940 → 0x60049944 |

In both bit-30-set cases, QEMU subsequently reaches `0x60049964`, performs the next still-unmodeled write to **0x4100F004**, and enters the Data Abort vector `0x60000010`. With bit 30 clear, this occurs one read-and-poll iteration later; the 13-instruction budget stops just before that same write. **That difference reflects the experiment's step budget, not that other bits permanently block startup.**

Relevant ARM code, disassembled from the BIOS:

```asm
6004992c: ldr r1, [r0]            ; first MMIO read
60049930: orr r1, r1, #0x40000000
60049934: str r1, [r0]
60049938: ldr r1, [r0]            ; fuzzed status read
6004993c: tst r1, #0x40000000
60049940: beq 0x60049938         ; bit 30 clear => poll again
60049944: ldr r1, [r0, #0xc0]     ; second register 0x410260fc
60049948: orr r1, r1, #0x40000000
6004994c: str r1, [r0, #0xc0]
60049950: ldr r1, [r0, #0xc0]
60049954: tst r1, #0x40000000
60049958: beq 0x60049950
60049960: mov r0, #0x10
60049964: str r0, [r4]           ; r4 = 0x4100f004, not modeled
```

The bit-30 comparison and loop can also be determined by ordinary static disassembly. The useful new evidence is that the actual QEMU guest follows the predicted branches under selective injection and continues to the next unmapped region.

## Snapshots: observed QEMU 10.1.0 restoration defect

Our controller connects to QEMU via **RSP (remote GDB)** and **QMP**, stops at the exact firmware instruction, creates a disposable QCOW2 v3 image, performs HMP `savevm before_mmio`, modifies the CPU, and calls `loadvm before_mmio`. The snapshot is real (around 13 MB; approximately 11.9 MiB of guest VM state), and the saved program counter **does restore**. But a controlled probe detected a serious problem:

- Before restore, guest virtual instruction `0x60049920` is readable (`30402de9`); after restore the GDB memory read returns **E14**, despite the physical ROM words still being correct.
- The guest's secure CP15 `DACR_S` went from `0x55555555` to `0`, while secure `TTBR1_S` and `TTBR1_EL1_S` also lost values. The next instruction raises a **Prefetch Abort**, IFSR `0x9`, IFAR `0x6004992c`.
- The provisional `kind=registers` device stores values in a plain C dictionary, **without a QEMU VMStateDescription**. It would also require snapshot serialization for full rollback correctness.

Therefore **the fuzzer does not reuse `loadvm` for its trials**. Instead it launches an independent QEMU process and re-executes the firmware to the same breakpoint for each value. That is slower but produces valid comparable input states. `--rollback require-snapshot` intentionally aborts rather than silently using broken restore. We can fix the A7 secure CP15 VMState and provisional MMIO device serialization in future board updates, then safely switch to fast snapshots.

## Boundaries

The fuzzer only controls a selected *read's returned value*. A branch accepting bit 30 does **not** prove that hardware sets it, which clocks it enables, its polarity on the real board, or that this address is a particular chip SKU. Real hardware traces or a reliable controller reference are required to confirm those details. **No LCD framebuffer or full BIOS/OS boot is established.**
