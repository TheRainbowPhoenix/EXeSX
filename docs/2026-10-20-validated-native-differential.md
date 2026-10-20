# Verified dual-core differential result — 2026-10-20

This is a **real-firmware local measurement**, not a proof of a successful OS boot. Proprietary binaries and full logs are excluded from Git.

## Exact artifacts

- User OSUP SHA256: `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`.
- Native CI artifact `exesx-qemu-native-aa5f55b0d4513d2f2847903a9aae16c5d4993f7e`, associated with PR #6; archive sha256 `c1ec23d20c43b40ab6ed73f2834f207f0d7669b33a07812d1c12404b688d2c40`.
- Source commit stamped inside bundle: `aa5f55b0d4513d2f2847903a9aae16c5d4993f7e`.
- Native QEMU 10.1.0 experimental EXeSX machine with actual user-provided ARM firmware. Separate clean processes, each 0.9 seconds, M4 opt-in boot, `profiles/imx7ulp-early-boot.ini`.

## Real cold-run comparisons

| Diagnostic mode | A7 PC | M4 PC | Shared IPC `0x2F028000` | I²C NACKs counted | ADC log hits | DMA0 config log hits |
| --- | --- | --- | --- | --- | ---: | ---: |
| No modeled slave | `0x60179A7C` | `0x1FFD4D16` | `0xEEEEEEEE` | `0x96` 19; `0x97` 9 | 0 | 0 |
| `EXESX_I2C4B_REGISTER_MIRROR=1` | `0x60179A7C` | `0x1FFDA0A0` | `0xEEEEEEEE` | `0x80` 22; `0x81` 3 | 12 | 1 |
| **Both 4B and 40 mirrors** | `0x60179A7C` | `0x1FFDA0A0` | `0xEEEEEEEE` | None in bounded log | 12 | 1 |
| Diagnostic fixed 4B reply `ff` | `0x60179A7C` | `0x1FFDA0A0` | `0xEEEEEEEE` | `0x80` 22; `0x81` 3 | 12 | 1 |
| Only 40 mirror | `0x60179A7C` | `0x1FFD4D18` | `0xEEEEEEEE` | `0x96` 52; `0x97` 26 | 0 | 0 |

Diagnostic 4B mirror readbacks included reg `0x14=0x62`, reg `0x17=0xF6`, reg `0x14=0x66`. Diagnostic 40 mirror readbacks included reg `0x58=0x00`, then `0x58=0x50`, then reg `0x68=0x00`. All are invented **register echoes**, not verified peripheral semantics. The real M4 executed an early DMA0 write `0x41008000=0x90` (NO transfers performed by emulator).

**New static fact:** `0x1FFDA09E` is Thumb `WFI`, and observed PC `0x1FFDA0A0` is its following `ISB`, within an M4 low-power/idle helper. This could reflect ordinary waiting for interrupts; it is NOT proof that this is the single remaining boot blocker. The A7 remains in a real holding/error path (`0x60179A7C`) and `0xEEEEEEEE` is still an error marker. **Do not claim that 0x40 mirror yields a working OS, valid M4 handshake, or text pixels.**

The no-slave sample here also reached the `0xEEEEEEEE` marker by 0.9 s, unlike an *earlier sampled point* where the marker was still zero. This is a timing distinction, not a contradictory successful handoff.

## Reproduction (never upload OSUP/ELFs)

```sh
python3 scripts/prepare_osup.py /path/to/OSUP.BIN -o private/a7-firmware.elf
# Compare separate cold boots with 0.9 s waits, captured via QEMU HMP.
# Mode none: no diagnostic env vars
# Mode 4B:   EXESX_I2C4B_REGISTER_MIRROR=1
# Mode both: EXESX_I2C4B_REGISTER_MIRROR=1 EXESX_I2C40_REGISTER_MIRROR=1
EXESX_EXPERIMENTAL_M4_BOOT=1 EXESX_I2C4B_REGISTER_MIRROR=1 EXESX_I2C40_REGISTER_MIRROR=1 \
  python3 scripts/run_firmware.py private/a7-firmware.elf \
  --qemu build/qemu-system-arm --profile profiles/imx7ulp-early-boot.ini \
  --seconds 0.9 --results private/diagnostics-both-mirrors
```

Review private logs and compare M4 returns and IRQ/IPC state, not just NACK count. At this point, proving correct RTC/PMIC/touch chip behavior requires hardware identification or firmware-derived status constraints; firmware passes artificial register echo but still fails initialization.

## Priority next investigations

1. Recover why A7 receives `0xEEEEEEEE`: instrument shared mailbox writers (`0x2F028000`), A7 error branch around `0x601786CC`, and M4 call chain responsible for its error code. Distinguish a completed M4 initialization from a terminal error.
2. Verify whether M4 idle WFI is being woken, what NVIC interrupts it enables, and whether DMA0 requires a real transfer or IRQ. Implement specific interrupts/transfer descriptors only after observing guest demands.
3. Identify 0x4B/0x40 externally; register mirror hypotheses are not the corresponding physical chips. Published Microchip maXTouch 0x4A/0x4B address range alone is insufficient, especially because this ROM uses one-byte register write/readback.
4. Only after a real successful M4/A7 handshake, prove A7 OS entry and guest LCDIF framebuffer.
