# A7 idle-callback investigation: MainTask semaphore cycles and MU IRQ storm

> **Superseded channel labels (2026-10-20):** This is a historical capture made with EXeSX's incorrectly numbered MU v1 RF/TE flags. Actual NXP MU v1 uses nibble bit `(3 - channel)`, so an RF mask of `0x4` is **channel 1**, not channel 2, and `0x1` is **channel 3**, not channel 0. The claimed channel-0 omission/storm was an emulator bug and is not silicon behavior. The corrected real-firmware run cuts 78,665 IRQ22 entries to 2 and reveals the separate SNVS.HPCOMR fault. See [corrected study](2026-10-20-imx7ulp-mu-v1-bit-order.md).


**Date:** 2026-10-20. **Actual private DX357 / XD-SX9850 firmware**, checksum verified OSUP source SHA256 `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`. Results from native Linux x86_64 EXeSX/QEMU 10.1.0 and full A7/M4 execution, with both opt-in I²C 0x4B/0x40 **diagnostic** register mirrors. These are software experiments, not real hardware peripheral identifications. Private ROMs, snapshots and raw traces must not be committed.

## The "missing" A7 callback is intentionally NULL

The original observation was the A7 holding PC `0x60179A7C` with state base `0x62148F00` and a zero pointer at `0x62148F8C` (= state + `0x8C`). Reverse engineering and live GDB trace establish:

1. A7 firmware caller `0x600495F0` explicitly initializes configuration `[sp+0x40]=0` (later passed from `0x62100E90`).
2. Kernel initializer `0x6017A11C` receives this configuration, and `0x6017A560` loads configuration `+0x40`, then `0x6017A564` writes that value into kernel state `+0x8C`. At the same time the adjacent field `+0x90` is set from `+0x44` to a real code pointer `0x601E1334`.
3. The idle code at `0x60179A68` tests the **optional** callback; with null value it branches to the local idle loop `0x60179A7C`. Its NULL value **is not an initialization failure**.

## MainTask actually starts and makes progress

Task name from embedded ROM: `MainTask`, TCB `0x621E88C8`, entry `0x60037DA8`, calling startup at `0x6004A0B4`. Task ID 1, priority 13. The main kernel scheduler uses current-task pointer `[0x62148F34]` and its ready queues. Snapshots of a temporarily sleeping MainTask show no ready tasks and the CPU in the idle loop, but **this is not a permanent deadlock**.

The µITRON semaphore service wrapper `0x60178BE4` selects function code `0xFFFFDB01` = `TFN_WAI_SEM` and kernel implementation `0x601E1A08`. Real registers at the call: `r0=31` (semaphore ID 31), `r1=0xFFFFFFFF` (infinite wait). The allocated semaphore object is `0x621EAED0` (kernel semaphore table pointer `[0x62148F54]=0x621E8128`); its 16-bit current count is offset `+0x0C`, initially 1, maximum count 1 in the higher 16 bits. The live firmware hits:

- `0x600069EC`: `wai_sem(31)`; native handler at `0x601E1A08` can save resume PC `0x601E1AAC` in MainTask context and temporarily deschedule it.
- `0x60006A08`: subsequent `sig_sem(31)` (wrapper `0x60178B9C`, kernel implementation `0x601E17D8`); count returns to 1.
- `0x60006A2C`: another `wai_sem(31)`, again with count 1 at the entry to `0x601E1A08`; the scheduler temporarily goes idle.

At a GDB-stopped idle state, semaphore count remained 1. This *appears* inconsistent until allowing actual timers/interrupts and the rest of firmware to run. A full-speed 0.9-second cold start with the existing `plugins/memtrace.c` plugin, filtering `0x621EAED8:0x621EAEE0`, recorded **13 successful A7 decrement writes at `0x601E19CC` and 13 increment writes at `0x601E17A4`**, plus corresponding reads. No manual semaphore value, return register or resume address was changed. This establishes real repeated use of semaphore 31; a single PC sample in idle **does not demonstrate a stuck scheduler**. It does not by itself prove the kernel is perfect.

## New concrete Messaging Unit behavior

The i.MX7ULP MU has paired M4-side MUA (`0x41022000`) and A7-side MUB (`0x40220000`). The repo model `hw/arm/exesx-imx7ulp-mu.inc` has four TX/RX slots, peer RF/TE bits, W1C GIP status, plus **opt-in** `EXESX_EXPERIMENTAL_MU_IRQ=1`. Without the env var, historical IRQ delivery is disabled. Not-yet-received TR2 (`MUB+0x28 = 0x40220028`) sets TE=0 and further attempted sends are ignored until the peer consumes corresponding `MUA RR2` at `0x41022048`. The native firmware trace explicitly shows initial accepted TR2=0 followed by **five ignored attempts** TR2 values `1,2,3,4,5`. This is actionable evidence that the A7/M4 message protocol is still not synchronized; it is not proof of specific hardware identity.

Separate **clean cold starts**, with both I²C mirrors enabled, using 1.5-second bounded run:

| MU IRQ mode | Logged TR2 busy writes | M4 external IRQ22 (v7-M exception 38) entries | M4 MUA SR writes of 0 | M4 MUA CR writes `0xFB000000` |
| --- | ---: | ---: | ---: | ---: |
| `EXESX_EXPERIMENTAL_MU_IRQ=0` | 5 | 0 | 0 | 0 |
| `EXESX_EXPERIMENTAL_MU_IRQ=1` | 5 | **97,572** | **97,571** | **97,571** |

Actual native QEMU interrupt log shows repeated `...taking pending nonsecure exception 38`, vector read at `0x1FFD0098`, M4 IRQ handler entry `0x1FFED181`, and `Exception return ... previous exception 38` followed immediately by re-entry. The handler repeatedly writes **zero** to `MUA SR 0x41022060` and **`0xFB000000`** to `MUA CR 0x41022064`. M4 IRQ delivery therefore causes a **level-pending IRQ storm**, not successful IPC. The GIP nibble in the current model is W1C, as documented in NXP i.MX7ULP reference manual and MCUXpresso SDK MU API; a zero SR write does **not** clear any pending GIP flags. However, it remains **unproven which underlying pending flag(s) remain raised**, whether firmware itself expects a different status bit interpretation, or whether the MU peer/TR protocol and model's CR/GIP state are incomplete. Do **not** force-clear all pending flags or fake a successful OS boot without tracing the real bit state.

Sources:
- NXP i.MX7ULP Chapter 9 MU manual (document via https://manuals.plus/m/3fcef56ef531d2f11af138e90b262f740cb4b850405f230406bb863805f74d1c.pdf).
- NXP MCUXpresso MU API https://mcuxpresso.nxp.com/api_doc/dev/4596/a00188.html.
- Repository: `hw/arm/exesx-imx7ulp-mu.inc`, `hw/arm/exesx.c`, `plugins/memtrace.c`.

## Reproduce without committing private data

```sh
python3 scripts/prepare_osup.py /private/OSUP.BIN -o private/a7.elf

# Independent cold cases: only vary the MU IRQ flag.
for irq in 0 1; do
  EXESX_EXPERIMENTAL_M4_BOOT=1 \
  EXESX_I2C4B_REGISTER_MIRROR=1 \
  EXESX_I2C40_REGISTER_MIRROR=1 \
  EXESX_EXPERIMENTAL_MU_IRQ="$irq" \
    python3 scripts/run_firmware.py private/a7.elf \
    --qemu build/qemu-system-arm \
    --profile profiles/imx7ulp-early-boot.ini \
    --seconds 1.5 --results "private/mu-irq-$irq"
done

# Separately prove sem count cycles (do not compare absent plugin data with zero).
EXESX_EXPERIMENTAL_M4_BOOT=1 \
EXESX_I2C4B_REGISTER_MIRROR=1 \
EXESX_I2C40_REGISTER_MIRROR=1 \
EXESX_EXPERIMENTAL_MU_IRQ=0 \
python3 scripts/run_firmware.py private/a7.elf \
  --qemu build/qemu-system-arm --profile profiles/imx7ulp-early-boot.ini \
  --seconds 0.9 --plugin build/exesx-memtrace.so \
  --watch 0x621eaed8:0x621eaee0 --max-events 240 \
  --results private/sem31-count

python3 scripts/analyze_a7_kernel_mu.py \
 private/sem31-count/qemu-instructions.log \
 private/mu-irq-0/qemu-instructions.log \
 private/mu-irq-1/qemu-instructions.log \
 --json private/sem31-mu-comparison.json
```

**Next controlled experiment:** Observe all MUA/MUB SR/CR and internal pending TE/RF/GIP flags immediately before IRQ22 is raised and after the actual ISR, *without consuming RR registers as a side-effect of the debugger*. Check the decoded `GIPn` vs `GIEn` mask and ISR's intended W1C logic. Then inspect the actual M4 RR2 read/ack and A7 TR2 message sequence. Only implement a narrow, reversible register/IRQ fix if the reference manual and real firmware trace both support it. Still no proven OS entry or screen text.

