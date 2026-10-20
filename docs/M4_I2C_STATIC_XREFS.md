# M4 LPI2C2 I²C reverse engineering — verified SX9850 firmware

This note contains **static ARM Thumb disassembly findings** from the user's private `OSUP(1).BIN`, not electrical bus captures or proof of a successful boot. Source OSUP SHA256: `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`. A7 BIOS SHA256: `eb7dafa1b544bbb8d79081866af280e6c0f88197de9f635c6887f8486155da66`. Embedded M4 SHA256: `25f95e3a5cfe2a898b2110d874075e6da5b288c706c03bc5a051a1f8c8e54fb0`.

## Firmware mapping

The M4 program is copied from **A7 BIOS address 0x600AD6A0** to **M4 SRAM 0x1FFD0000** (length `0x14F70` = 85,872 bytes). Initial MSP is `0x20001C00`; vector's reset pointer is `0x1FFE19E5` (Thumb code starts `0x1FFE19E4`). **Do not confuse the independent updater IPL, whose base is also 0x1FFD0000, with this BIOS-embedded runtime M4 image.**

## Recovered driver functions and hardware registers

| M4 address | Static role |
| --- | --- |
| `0x1FFD6CB6` | Master status error check |
| `0x1FFD6CF8` | Send START and target address byte |
| `0x1FFD6DA0` | Send caller-specified number of data bytes |
| `0x1FFD6E28` | Receive caller-specified number of bytes |
| `0x1FFD6D52` | Send STOP and wait/check completion |
| `0x1FFD6F4C` | 7-bit `0x4B` **single-byte register/command read** (write 1, restart, read 1) |
| `0x1FFD6F7E` | 7-bit `0x4B` **two-byte write** |
| `0x1FFD6FA6` | 7-bit `0x6B` one-byte read |
| `0x1FFD6FD8` | 7-bit `0x6B` two-byte write |

Literal pool at `0x1FFD6F34` contains `0x41035014` (LPI2C2 MSR), `0x1FFD6F38` contains `0x41035010` (MCR), `0x1FFD6F3C` contains `0x4103505C` (MFSR), and `0x1FFD6F48` contains `0x41035018` (MIER). The controller MTDR is at `0x41035060`, and MRDR at `0x41035070`.

At `0x1FFD6CBA`, firmware tests **MSR & 0x3C00** for master error flags. If set, it clears these status bits and resets controller FIFOs before returning `-1`. The receive routine at `0x1FFD6E54` writes **`0x100 | (n - 1)`** to MTDR (request `n` bytes); at `0x1FFD6E68` it checks **MFSR & 0x70000** for RX FIFO count and drains MRDR. It checks the common error routine and a bounded timeout on every receive. This supports identifying exact requested lengths even with a missing device; it does **not** establish successful data transfer.

## Confirmed static transfer sizes at direct read callsites

| Read callsite | Argument | Context |
| --- | --- | --- |
| `0x1FFD6F70` | 1 byte | Inside 0x4B read-byte wrapper |
| `0x1FFD6FCA` | 1 byte | Inside 0x6B read-byte wrapper |
| `0x1FFD708A` | 1 byte | Another 0x4B read-byte wrapper |
| `0x1FFD73F6` | **9 bytes** | 0x4B transaction: write `0x2D`, repeated START read |
| `0x1FFDB9AE` | 1 byte | Another I²C device (0x40, address byte 0x81) |
| `0x1FFDBA04` | **variable, r5** | Dynamic caller-provided length, must trace argument |
| `0x1FFDBA24` | **14 bytes** | Other I²C device (0x40, address byte 0x81) |

Additional verified static `0x4B` write: `0x1FFD74E4` sends **8 bytes** after START `0x96`. Wrapper `0x1FFD6F7E` sends 2 bytes and STOPs.

**Critical correction:** earlier notes interpreted the two bytes `0x14,0x62` as a possible 16-bit LE pointer `0x6214`. The decompiled M4 driver proves that two-byte write payloads exist independently of reads and that single-byte command/register reads are also used. The prior transaction is therefore **ambiguous without precise STOP/repeated-START grouping**. Do not bake a maXTouch 0x6214 pointer into the model on this evidence.

## Reproducible tool workflow

Use `scripts/prepare_i2c_ghidra.py` (the repo's already-present `scripts/prepare_osup.py` supplies the checksum-validated parser). Create a private output directory:

```bash
python3 scripts/prepare_i2c_ghidra.py "/private/path/OSUP.BIN" \
  --out private/i2c-ghidra
```

This writes **PRIVATE** `a7-firmware.elf`, `m4-firmware.elf`, manifest and `m4-i2c-static-xrefs.json`; when `llvm-objdump` is installed it also records direct Thumb calls and immediately evident constant receive sizes. It refuses an unrecognized BIOS checksum/embedded-M4 checksum or incorrect reset vector rather than silently mislabeling another model. The proprietary ELFs and Ghidra project must never be committed or uploaded.

For the Ghidra project, import M4 **separately from A7**:

```bash
mkdir -p private/ghidra-project
"$GHIDRA/support/analyzeHeadless" "$(realpath private/ghidra-project)" ExesxM4 \
  -import "$(realpath private/i2c-ghidra/m4-firmware.elf)" \
  -processor ARM:LE:32:Cortex -cspec default \
  -scriptPath "$(realpath ghidra)" \
  -postScript ExesxI2CXrefs.java "$(realpath private/i2c-ghidra)/m4-ghidra-xrefs.tsv"
```

Then view code at `0x1FFD6CB6`, `0x1FFD6F4C`, `0x1FFD73D0`; press **X** in Ghidra to inspect callers and follow argument origins. The script validates the entire M4 fingerprint, annotates functions/literal pools, and exports a TSV of Ghidra references. It has **not** been headless-tested here (Ghidra not installed); inspect the analysis log for compile/disassembly errors. The additional attached exword-sx-analysis-kit can separately import A7 annotations; it is not needed for the M4 mapping.

To correlate live `-d guest_errors` logs from `scripts/run_firmware.py`:

```bash
python3 scripts/decode_i2c_transactions.py private/firmware-trace/qemu-instructions.log \
  --json private/i2c-ghidra/actual-attempted-transactions.json
```

These are MTDR **command attempts**, not successful I²C reads. Without a live native QEMU execution trace on this tool run, the full **observed runtime** sequence, dynamic `r5` receive length, device identity, return values, A7/M4 successful IPC handoff and LCD output are not recovered.

## Follow-up

1. Join STOP-aware transaction attempts and NACKs to the 0x4B callers above; compare cold real-firmware runs.
2. In Ghidra, inspect callers of `0x1FFD6F4C`, `0x1FFD73CC` and `0x1FFD6CB6`; recover their register/command meaning and required return/status predicates, including `r5` dynamic length.
3. Identify the physical target before implementing valid replies; maXTouch remains only a possibility. No OS boot, guest text or LCD screenshot has been demonstrated.

NXP register source: https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/periph/PERI_LPI2C.h
