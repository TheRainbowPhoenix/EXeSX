# EXeSX differential MMIO fuzzer — real BIOS experiment

**Status:** working GDB injection, **verified QEMU savevm/loadvm rollback** (including secure CP15 and provisional MMIO register state), successful **34-run** single-bit differential ARM execution, plus a five-case fast-snapshot regression. This is NOT proof of a functioning clock chip or OS boot.

## Reproduction

Prepare your *private* `a7-firmware.elf` from OSUP.BIN as described in `docs/local-firmware.md`. Never commit the firmware, the disposable VM snapshot (which contains guest RAM), or generated instruction bytes to this public repository.

```sh
# Uses the existing compiled QEMU 10.1.0 binary; no recompilation.
python3 scripts/fuzz_mmio.py private/a7-firmware.elf \
  --qemu build/qemu-system-arm \
  --profile profiles/clock-registers-probe-only.ini \
  --site poll --steps 13 --limit 34 \
  --out private/fuzz-register-4102603c

# Fast focused test (one BIOS run, repeated verified snapshot rollbacks).
python3 scripts/fuzz_mmio.py private/a7-firmware.elf \
  --qemu build/qemu-system-arm \
  --profile profiles/clock-registers-probe-only.ini \
  --site poll --steps 16 --only zero,bit29,bit30,bit31,all_ones \
  --rollback auto --out private/fuzz-recheck

# Additional sites: --site initial or --site second-poll.
```

Output: `results.json` contains every stepped PC, successor PC, r1, CPSR, and branch indicator; `report.md` shows the first path divergences; `disassembly.txt` contains LLVM's ARM instruction disassembly. You only need `llvm-objdump` for the textual disassembly. The script constructs an ephemeral ELF text section from *your local* BIOS to let LLVM disassemble it; nothing is uploaded. Without LLVM, the PC trace still works.

### What is injected?

- Break at **0x60049938**, the ARM `LDR r1,[r0]` that polls **0x4102603C**.
- Pause before executing the read, set ARM `r1` to a candidate, and advance PC by 4 bytes to **0x6004993C**. **Only that one LDR is skipped**; the following `TST` and conditional `BEQ` execute for real in QEMU.
- Step 13 real ARM instructions while observing every transition; capture exception-vector entry, if any.
- Start from a pristine guest by restoring a validated VM snapshot **or** fully rebooting and replaying to the same breakpoint. Current EXeSX native QEMU uses fast VM rollback **after validating** CPU, guest MMU, and deliberate MMIO mutations. Older binaries automatically fall back to cold replay.

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

## Snapshots and deterministic rollback — verified after board VMState fix

**Both the checkpoint and the rollback now work in EXeSX's native QEMU 10.1.0 build.** The controller uses RSP (GDB remote) and QMP to stop at the BIOS read instruction, generates a disposable QCOW2 v3 disk, invokes HMP `savevm before_mmio`, injects different register values, and invokes `loadvm before_mmio` for every subsequent trial.

During investigation we found a real mismatch in the experimental board's saved CPU state: on older builds `loadvm` restored the PC but lost secure CP15 `DACR_S` (0x55555555→0) and `TTBR1_S`. Guest code at `0x60049920` became unreadable (RSP `E14`) and execution Prefetch-Aborted with IFSR `0x9`. Also the temporary MMIO register dictionary was not serialized. The board now explicitly serializes **secure A7 DACR and TTBR1** plus all configured experimental MMIO register words in QEMU VMState. The fault was addressed in commit `2b3cf191`.

The fuzzer performs a **deliberate dirty-state rollback test** before trusting the snapshot:

1. Capture PC and read guest code and MMIO at `0x4102603C`.
2. Save a full VM snapshot (`savevm before_mmio`).
3. Overwrite the MMIO register over GDB with a deliberately different value, and change the PC.
4. Restore the snapshot; verify identical PC, guest instruction bytes, and **original MMIO register value**.
5. Only if all checks pass, use a single QEMU process and `loadvm` for each fuzz candidate.

A real firmware test using the revised machine obtained `usable=true`, `mmio_serialization_verified=true`, guest instruction bytes `30402de9` before and after, and original register value `00000040` restored after deliberately setting `ffffffbf`. The saved QCOW2 file was about **13 MB**; observed individual checkpoint restores took approximately **0.05–0.12 seconds** in a focused benchmark.

A **five-case snapshot-run** (`zero,bit29,bit30,bit31,all_ones`, 16 actual ARM instructions each) reproduced the cold-run results, including the extra polling back-edge when bit 30 was clear and the `0x4100F004` unmapped write in every case. The original full 34-case run was obtained using cold replay before this fix, so it remains a separate independent validation. The full `--limit 34 --rollback auto` run is supported; its 34-case snapshot runtime has not been separately benchmarked to completion.

If snapshot verification fails on an older build, default `--rollback auto` falls back to fresh firmware replay. `--rollback require-snapshot` stops with an error. Neither path silently trusts CPU-only state or ignores mutated virtual MMIO registers.

## Boundaries

The fuzzer only controls a selected *read's returned value*. A branch accepting bit 30 does **not** prove that hardware sets it, which clocks it enables, its polarity on the real board, or that this address is a particular chip SKU. Real hardware traces or a reliable controller reference are required to confirm those details. **No LCD framebuffer or full BIOS/OS boot is established.**
