# Snapshot-backed M4 GPIO/input-matrix → IPC differential — 2026-10-20

**Measured result with actual locally supplied XD-SX9850 firmware in native EXeSX QEMU: raising either of two selected GPIO *input* bits for one PDIR read makes real Cortex-M4 code write `0xFFFFFFFF` instead of `0xEEEEEEEE` to shared IPC. A7 executes the corresponding *non-diagnostic* branch, but subsequently still reaches its existing `0x60179A7C` holding loop. No OS boot or LCD text is established.**

## Fixed inputs, validated snapshots

- Original proprietary OSUP SHA256 `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`; locally extracted A7 ELF SHA256 `55aa616df7fe31cd3fc6811a0921b072b9318b5dbeefac8a7b4c8c1ae3cdd78d`. Neither image is in GitHub.
- Linux x86_64 native EXeSX/QEMU 10.1.0 from CI build source `aa5f55b0d4513d2f2847903a9aae16c5d4993f7e`, released with the previously verified SHA256-bearing Actions ZIP/tar archive. QEMU runs real A7 and M4 TCG firmware.
- Existing `fuzz_mmio.py` GDB RSP + QMP savevm/loadvm infrastructure. A disposable QCOW2 holds a private VM snapshot at **M4 PC `0x1FFD85C6`**, just before the initial input PDIR LDR. The probe verified rollback restored M4 PC/SP, shared IPC and GPIO PDIR, **and** undid a deliberate GPIO PDOR modification. No results are accepted if rollback fails.
- Both `EXESX_I2C4B_REGISTER_MIRROR=1` and `EXESX_I2C40_REGISTER_MIRROR=1` remain enabled solely as explicit *diagnostic* dependencies; these are not actual chip models.

At snapshot time: `PDIR(0x4100F010)=0x00000010`, `PDDR(0x4100F014)=0x000081F1`, `PDOR(0x4100F000)=0x00330E10`, and IPC `0x2F028000=0`. Both tested bits are configured as **inputs**, so the experiment preserves all configured GPIO **output** values.

The M4 firmware `0x1FFD7F08` checks logical input codes `0x9C` then `0x90`, which the scanner at `0x1FFD8564` turns into test masks for PDIR. Observed `r8` at `0x1FFD85C6`: **bit 19** (`0x00080000`) for the first code, **bit 23** (`0x00800000`) for the second. The second input first reaches the same LDR after five baseline scan hits. These are actual guest-register masks, **not confirmed physical key/pad identity or pulled-up electrical levels**.

The probe only replaces the value of one **16-bit Thumb** `ldr r0,[r6,#0x10]` at `0x1FFD85C6`: set M4 r0 to observed PDIR with the single selected input bit high/low, then advance PC by 2. No other reads, RAM, ROM bytes, instruction results, returned function values, mailboxes or interrupts are modified. The remaining original firmware runs normally. The probe sets breakpoints on M4's two genuine IPC `STR` sites and on the A7's genuine IPC `BNE` instruction.

## Same-checkpoint outcomes

| Case | Replaced single GPIO read | M4 IPC STR site | Guest IPC after actual STR | A7 BNE at `0x601786D4` goes to | A7 sampled later |
| --- | --- | --- | --- | --- | --- |
| `code9c:pass` | `0x00000010` (baseline) | `0x1FFD5B60` | `0xEEEEEEEE` | `0x601786D8` (diagnostic path) | `0x60179A7C` |
| `code9c:low` | `0x00000010` (bit 19 remains low) | `0x1FFD5B60` | `0xEEEEEEEE` | `0x601786D8` | `0x60179A7C` |
| `code9c:high` | `0x00080010` (bit 19 high) | `0x1FFD5B68` | `0xFFFFFFFF` | `0x601786E0` (skips special diagnostic call) | `0x60179A7C` |
| `code90:high` | `0x00800010` (bit 23 high) | `0x1FFD5B68` | `0xFFFFFFFF` | `0x601786E0` | `0x60179A7C` |

The A7 genuinely read IPC in `r0` before the `BNE`; its comparison reference `r1` was `0xEEEEEEEE` in every case. Those registers and the exact successor PC were read with RSP after a real M4 mailbox store, not inferred from screenshots or a synthetic ARM-only probe.

A separately extended high-case run sampled A7 after follow-up intervals 0.12, 0.45 and 1.2 seconds: it was still at `0x60179A7C` at all three. M4 was sampled near `0x1FFDA0A0` (WFI-adjacent idle instruction), but that alone does not prove missing IRQ or a failed M4 OS.

## Reproduce in repo checkout

```sh
python3 scripts/prepare_osup.py /private/path/OSUP.BIN -o private/a7-firmware.elf
python3 scripts/probe_gpio_ipc.py private/a7-firmware.elf \
  --qemu build/qemu-system-arm \
  --profile profiles/imx7ulp-early-boot.ini \
  --cases code9c:pass,code9c:low,code9c:high,code90:high \
  --follow-seconds 0.25 \
  --out private/gpio-ipc-differential
```

This writes a **private** `results.json`, QEMU console and debug logs. Do not upload those logs, extracted ROM or QCOW2 to public GitHub/CI. The script fails closed if the expected first M4 scan, GPIO input direction, snapshot restoration, mailbox stores or A7 IPC compare site is absent.

## Why A7 still holds — actual callback-slot observation

Further bounded real-firmware GDB samples on both `code9c:pass` and `code9c:high` captured A7 **`r4=0x62148F00`** at `PC=0x60179A7C`. ARM disassembly at `0x60179A68` reads **`[r4+0x8c]`**, tests zero and branches to `0x60179A7C` if the value is zero. Live guest memory at **`0x62148F8C`** was **`0x00000000`** under both conditions. This explains the immediate cause of the holding loop in these tests: the callback/function slot is unset. It does **not** prove which initialization routine should set it, that it is an error rather than intended idle state, or that manually filling the slot would boot the OS.

The reusable probe also logs the A7 r4, callback slot and observed pointer when the final PC is the known holding loop. The next non-speculative task is to locate firmware writes/XRefs to the pointer slot, correlate scheduler/IRQ dependencies, and detect actual OS entry (rather than synthesizing a callback).

## What this does and does not unlock

**Verified progress:** establishes the exact M4 GPIO input condition that chooses between two real shared-memory sentinel writes, plus the corresponding observed A7 branch around the diagnostic handler. The earlier claim that simply setting `0xFFFFFFFF` constitutes startup success is **not** supported. Both branches converge on subsequent A7 execution leading to the `0x60179A7C` holding loop in this bounded experiment.

**Next:** find what later A7 code/interrupt, peripheral/OS state, callback or scheduler setup would replace the holding loop, and determine the physical GPIO input-matrix polarity and wiring. A future proper GPIO device model must not hardcode the `0xFFFFFFFF` sentinel or fabricate a touch/display success. Guest framebuffer and actual OS entry remain unverified.

Related: [prior IPC/GPIO tracing](2026-10-20-ipc-gpio-input-scan.md), [dual-core differential](2026-10-20-validated-native-differential.md), [M4 static cross-references](M4_I2C_STATIC_XREFS.md).
