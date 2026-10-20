# Actual M4 IPC writer and GPIO input-scan dependency (2026-10-20)

**Verified by a local, private, checksum-validated Casio XD-SX9850 BIOS/M4 image executing in native EXeSX QEMU. This is NOT a successful OS boot.** Do not add proprietary firmware, raw instruction traces or snapshots to Git.

### Tested inputs

- User updater source SHA256 `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`.
- CI native artifact compiled from `aa5f55b0d4513d2f2847903a9aae16c5d4993f7e`, SHA256-validated release archive as in `2026-10-20-validated-native-differential.md`.
- Opt-in `EXESX_EXPERIMENTAL_M4_BOOT=1`, `EXESX_I2C4B_REGISTER_MIRROR=1`, `EXESX_I2C40_REGISTER_MIRROR=1`; these are diagnostic, **unverified** slave models.
- Independent cold firmware run with QEMU TCG `plugins/memtrace.c`; watched mailbox `0x2F028000..04` and GPIO region `0x4100F000..80`, bounded 1.4 seconds and 30000 events/range. Plugin records guest **access sites**, not the data values; values below are established by Thumb/ARM disassembly and a separate HMP mailbox value read.

### CPU-specific mailbox writes

| CPU | Instruction PC | Verified instruction | Significance |
| --- | --- | --- | --- |
| A7 (0) | `0x601B9DE8` | `str r0,[r1]` after `mov r0,#0` | Resets shared IPC `0x2F028000` to zero |
| M4 (1) | `0x1FFD5B60` | `str r0,[r4]` after `mov.w r0,#0xEEEEEEEE` | Actual source of IPC error/diagnostic marker |

**Exact M4 branch from SHA-verified Thumb disassembly:**

```text
0x1FFD5B54  bl    0x1FFD7F08
0x1FFD5B58  cmp   r0, #0
0x1FFD5B5A  beq   0x1FFD5B64
0x1FFD5B5C  mov.w r0, #0xEEEEEEEE
0x1FFD5B60  str   r0, [r4]          ; observed M4 store to 0x2F028000
0x1FFD5B62  b     0x1FFD5B6A
0x1FFD5B64  mov.w r0, #0xFFFFFFFF
0x1FFD5B68  str   r0, [r4]          ; alternative static path, NOT observed
```

The A7 polls this word at `0x601786BC`. Earlier A7 analysis shows the special `0xEEEEEEEE` branch near `0x601786CC`, followed by its holding path `0x60179A7C`. **`0xFFFFFFFF` is only an alternate mailbox value; it is NOT proof of a successful M4 handoff, let alone a Casio OS boot.**

### What does M4 function 0x1FFD7F08 check?

It converts two input codes, **`0x9C` and `0x90`**, to board input positions with lookup routine `0x1FFD852A`, then calls test routine `0x1FFD8610` on both in a three-iteration loop. The test reads GPIO input states through `0x1FFD8564`. Exact private ROM lookup-table results:

- `0x9C` → 9×8 table row **4**, column **5**; the subsequent GPIO table is indexed by the **column** and gives candidate pin index **16**.
- `0x90` → table row **7**, column **6**; the subsequent GPIO table is indexed by the **column** and gives candidate pin index **17**.

These are **logical firmware input codes/positions**, not validated keyboard legends, wiring or physical chip IDs. The first byte of the mapped pair is used to index the second GPIO table in `0x1FFD8564`; the second byte selects a logical scan position for `0x1FFD8412`. Even the derived pin indices are NOT independently confirmed physical wiring. The polling function can also change result when masked input states vary across reads; do not assume one constant PDIR bit will unlock startup. Literal `0x1FFD8994` points to GPIO PTA base `0x4100F000`; `0x1FFD8564` polls PDIR at **`0x4100F010`**.

The real QEMU memory plugin registered:
- 30 successful M4 GPIO PDIR reads at PC `0x1FFD85C6`.
- 90 further successful M4 PDIR reads at PC `0x1FFD85D8`.
- 38 M4 GPIO clear writes at `0x1FFD8444` to `0x4100F008`, and 38 M4 direction writes at `0x1FFD8456` to `0x4100F014`.

The EXeSX `imx7ulp-gpio` model currently implements **PDIR = PDOR & PDDR**: output pins loop back, and **external input pins are not attached**. The code's polling behavior and the absence of an input-matrix model make GPIO-driven startup checks a strong, newly localized **hypothesis for the remaining `0xEEEEEEEE` decision**. We have not proven which physical signal(s) should change or their correct values. This function is not an I²C receive handler.

### Reproduce and confirm locally

```sh
python3 scripts/prepare_osup.py /private/OSUP.BIN -o private/a7-firmware.elf

EXESX_EXPERIMENTAL_M4_BOOT=1 \
EXESX_I2C4B_REGISTER_MIRROR=1 \
EXESX_I2C40_REGISTER_MIRROR=1 \
python3 scripts/run_firmware.py private/a7-firmware.elf \
  --qemu build/qemu-system-arm \
  --profile profiles/imx7ulp-early-boot.ini \
  --plugin build/exesx-memtrace.so \
  --watch 0x2f028000:0x2f028004 \
  --watch 0x4100f000:0x4100f080 \
  --max-events 30000 --seconds 1.4 \
  --results private/ipc-gpio-study

grep EXESX_ACCESS private/ipc-gpio-study/qemu-instructions.log
```

Firmware ELF, RAM, and raw trace stay private. This uses no direct writes to actual hardware.

### Next experiment (DO NOT bypass as an alleged success)

1. Identify the real row/pin wiring and whether the two codes are keys, switches, wakeup, or test inputs. Decode their polarity, pull resistors and the configured direction from the M4 PDDR/PORT instructions.
2. Instrument the actual values read at `0x4100F010` and the return from `0x1FFD8610`, recording CPU state at each call. The QEMU plugin above logs addresses only, not register contents.
3. If a controlled input-matrix hypothesis is justified, add an **opt-in** GPIO input model that preserves correct output loopback. Differentially rerun from the same state; look for the M4 alternate `0x1FFD5B68` and a subsequent verified A7 branch, not simply no I²C NACKs.
4. Model genuine IRQ, storage, LCDIF and UI only based on actual guest behavior.

A public Casio XD-SX calibration guide confirms these products include touch input but gives **no motherboard chip identities**: https://www.casio.com/jp/support/exword/faq/article/00/12/69/09/. Microchip maXTouch 0x4A/0x4B addressing alone does not establish a matching chip, especially with the observed 8-bit register-style transactions.
