# Authentic 0xCA05 recovery mode from original M4 two-key chord (2026-10-25)

All original `OSUP.BIN`/A7/M4 ROM and extracted ELFs, private RAM/IPC dumps, QEMU traces, SD/eMMC images and screenshots remain **local**. Firmware SHA256: `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`.

## Exact firmware mechanism — *different* from the later triple-key chords

Disassembly of the unchanged owner M4 Thumb ROM at `0x1FFD5B54` calls `0x1FFD7F08`, which looks up **0x9C (matrix row4/col5)** and **0x90 (row7/col6)** and scans both simultaneously for three passes via original keyboard/GPIO machinery `0x1FFD8610`. If both are held, the original M4 places `0xEEEEEEEE` at shared address `0x2F028000` (M4 code `0x1FFD5B5C..60`); otherwise it writes `0xFFFFFFFF` (M4 `0x1FFD5B64..68`).

Original A7 IPC init `0x60178608` is called via `0x60177CB8`. Its code at `0x601786B8..D4` reads/compares the shared boot word against `0xEEEEEEEE`. On match, `0x601786D8` loads `0xCA05` and `0x601786DC` invokes `0x6001EE68`, which stores boot-mode value at `0x20007810`. Normal boot was repeatedly observed as `0xCA00`.

The original BIOS startup path calls `0x6001EDA8` from `0x60048E08` and checks `0xCA05` at `0x60048E10`; if equal, `0x60048E18` calls `0x60010868`, the version dialog. **This original-M4 pre-boot two-key chord must NOT be confused with A7's later held `0x80+0x95+0x92` or `0x80+0x90+0x96` checks** (`0x6001D93C` and `0x6001D94C`), nor with the even later **sequential** version-dialog key-downs `0x93 → 0x93 → 0x94`.

## Authentic test on main — no RAM/PC/event injection

Main branch added opt-in physical closed contact `{0x9c, 4, 5}` to `hw/arm/exesx-imx7ulp-keyboard.inc`, alongside existing `{0x90, 7, 6}`. Original M4 row selection via IOMUXC0 and original GPIO PDDR/PDOR gates the actual active-low column voltage; host writes only a text contact file `0x9c,0x90`. No guessed key legend is asserted.

The rebuilt native Linux QEMU artifact from **successful [CI 40215730868](https://github.com/TheRainbowPhoenix/EXeSX/actions/runs/40215730868)**, commit `4f7471ea272ae7fdacfc902c772530391182c9f5`, ran the unchanged owner's original A7/M4 OSUP image with source-derived synthetic eMMC and optional SD, both `snapshot=on`. Standard opt-in MU, keyboard PORT/TPM0, LPIT/LPTMR and speculative TPM0 48MHz/A7 TPM6 32kHz clock diagnostics were enabled. No GDB attached, original CPU code/data or mailbox written, no guest CPU register or PC redirected.

With `EXESX_M4_KEY_MATRIX_FILE` holding `0x9c,0x90` from reset, a **read-only QMP** capture observed:

- ~0.5 host seconds: authentic shared M4 boot word **`0xEEEEEEEE`** at `0x2F028000`.
- ~0.5 host seconds: authentic A7 mode **`0x0000CA05`** at `0x20007810`.
- A7 mode stayed **`0xCA05` through 14 seconds** in the bounded first run.

Firmware-free *actual ARM MMIO* GPIO/IOMUX probe separately passed original row4/PTA15/column5/PTA19 (`0x9C`), row7/PTA20/column6/PTA23 (`0x90`), simultaneous closure, released/no-file/wrong-output controls, and malformed input.

A diagnostic **two-column constant-low** control also made the genuine firmware generate `EEEEEEEE`→`CA05`, but grounds extra scan rows and is **not an authentic physical keyboard implementation**. Preloading the EEEE word before cold boot **failed**, because original M4 overwrites the shared slot; a separate debugger RAM-write exactly at A7 compare confirmed the conditional but is **not accepted as a real boot solution**. The true row-gated two-key test above is the authoritative result.

## Continued to the version dialog and key handling

A no-debugger original-firmware `-d exec` **executed guest TB** run with authentic two-key chord held from reset recorded A7 `0x60048E08`, `0x60048E18` and **`0x60010868`**. This **proves** the original A7 actually enters its version-dialog handler after `CA05`.

A further no-debugger experiment **released** the physical `0x9C+0x90` chord after ~1.2 host seconds (after the M4 handshake), and after genuine A7 event-wait `0x600108A8` executed at ~12.22s, issued real, separate electrical contacts `0x93 → 0x93 → 0x94`, holding each ~75ms and releasing for ~30ms. The unchanged original A7 then executed `0x600108B4` (event returns), `0x600108CC` (event type), `0x60010910` (early code check) **and** `0x60010928` (third-key check). The trace showed normal exit `0x60010974`, **not** successful factory menu `0x6003A878`. Reaching these TBs is **not** proof that all three key-down payloads were accepted in order. The original BIOS can see repeated keys and system events; contact pulse durations and original key-down state/queue must be correlated to why this particular replay did not trigger the menu. The older private `version-event-wait` checkpoint replay had already authentically entered the menu at `0x6003A878`; LCD paint later blocked at `0x400B(2)`.

A second cold-boot timing variant was bounded before the event wait and cannot count as a key rejection. Host time/experimental SoC clocks are not calibrated.

**Working entry sequence from reset:** hold **`0x9c+0x90`** as real simultaneous physical contacts → observe original M4 `EEEEEEEE` and original A7 `CA05` → allow A7 to reach `0x600108A8`, releasing the chord → send **`0x93,0x93,0x94`** as separate key-downs. Use `scripts/drive_factory_menu.py --startup-chord 0x9c,0x90 --matrix-keys` to trigger the correct early physical chord and preserve a private version-dialog QCOW2 checkpoint; it must have authentic original eMMC backing at its original absolute path. Do not put checkpoint, trace or original ROM on GitHub.

**Remaining proof:** correlate original 20-byte M4 queue `0x1FFEA34C` and A7 copied 20-byte keyboard records at the `0x600108B4..60010928` checkpoints, tune physical press/release durations and/or wait for genuine M4 idle between presses, then show original `0x6003A878` in execution trace before asserting the factory menu entered or rendered. No ROM patch, fabricated event, forced PC, or manually posted mailbox.

## Complete authentic cold-boot TEST MENU executed (new positive result)

A further successful **no-debugger / unchanged-original-ROM / physical-contact-only** replay on the Linux CI artifact for commit `4f7471ea` reached actual **`0x6003A878`**, starting from a fresh boot with no saved VM checkpoint and with original source-derived eMMC plus a disposable SD. Procedure:

1. Hold simultaneous row-gated **0x9C+0x90** before boot.
2. At ~1.22 host seconds, release the chord after original M4 boot word `0xEEEEEEEE` caused A7 mode `0xCA05`.
3. Native A7 reaches original version dialog at ~12.51 seconds and its original event wait `0x600108A8` at ~12.57 seconds.
4. Physically close/release **0x93, 0x93, 0x94** with *0.060-second holds and 0.025-second gaps*, triggered only after the real event wait executed.
5. The native `-d exec` TB trace reports `0x60010910`, `0x60010928`, specifically **`0x60010930`** (successful final 0x94 check), then **`0x6003A878`** (actual factory TEST MENU entry) at ~12.84 seconds.

The trace contained one original TB at the authentic `0x6003A878` entry and a genuine branch from the A7 dialog; no guest ROM/CPU/register/IPC/RAM event was injected, no breakpoint attached, no forced PC jump, and no synthetic event publication. The host only controlled electrical matrix contact closure and read original executed TB logs. Unlike prior saved-checkpoint results, **this is a direct cold-boot entry**.

One previous 75ms-hold/30ms-gap pulse run executed 93/94 check paths but exited normally, so exact host timing is an experimental, *non-calibrated* tuning parameter. This success does **not** assert that the subsequent menu text is rendered; original service `0x400B(2)` and LCD painter remain independent checkpoints.

Public reproducible harness: [`scripts/drive_ca05_factory_menu_nogdb.py`](../scripts/drive_ca05_factory_menu_nogdb.py), which needs **owner-private** ELF/media and writes original guest TB trace only to a private output folder. Example:

```bash
python3 scripts/drive_ca05_factory_menu_nogdb.py \
  --qemu /private/qemu-system-arm \
  --elf /private/a7-bios-os.elf \
  --emmc /private/source-derived-synthetic-emmc.raw \
  --profile profiles/imx7ulp-early-boot.ini \
  --sd /private/disposable-sd-2g.raw \
  --output-dir /private/ca05-cold-menu \
  --release-at 1.2 --hold 0.060 --gap 0.025 --seconds 35
```

The old GDB driver also now supports `--startup-chord 0x9c,0x90 --matrix-keys` for privately saving a version-dialog checkpoint; for timing-proof prefer the no-debugger harness.
