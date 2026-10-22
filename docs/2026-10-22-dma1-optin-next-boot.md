# DY357 LCD-to-DMA boot continuation (2026-10-22)

## Evidence / last confirmed state

- Original OSUP firmware previously passed experimental GPIOF13 LCD sync, wrote an all-white 864x480 frame, and reached BIOS DMA1 channel15 DONE wait at `0x601B82BC`.
- Channel15 descriptor: source `0x61080000`, destination `0x6114A800`, NBYTES `0xCA800` (829440 bytes), CSR.DONE clear. **No original OS entry or text output has been demonstrated.**
- PR #35 implements opt-in DMAMUX-qualified actual memory-to-memory transfer and a synthetic ARM regression. It has **not yet demonstrated original OSUP passes the gate**.
- User-supplied OSUP.BIN was locally checksum-validated by the supplied extract_roms Python script: SHA256 `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`, model DY357, BIOS at `0x60000000`, OS at `0x60400000`. User firmware and raw traces must remain private.

## Reproduce next genuine boot boundary

Use the same *private* OSUP input and pinned QEMU build on a machine with the toolchain and emulator, and compare a controlled pair:

```bash
python3 scripts/run_osup.py /secure/path/OSUP.BIN --seconds 35 --output-dir private/control
python3 scripts/run_osup.py /secure/path/OSUP.BIN --seconds 35 --dma1-m2m --output-dir private/dma1
```

The second invocation explicitly sets `EXESX_EXPERIMENTAL_DMA1_M2M=1`; it does not force CSR.DONE without a successful memory copy. The first invocation keeps it off. The runner preserves logs and screenshots under `private/`, and uses synthetic, incomplete eMMC, not a real installed device.

Inspect *private* `qemu-trace-private.log` for `EXeSX DMA1 copied 829440 real RAM bytes ch=15` and any unsupported descriptor/mux messages. Inspect translated BIOS PC evidence and machine state to verify the firmware actually **returns from 0x601B82BC**. A DMA success log alone does not establish BIOS or OS progression. Inspect the PPM for nonwhite pixels rather than claiming text from a file existing.

Caveat: successful transfer requires the firmware's live DMAMUX ch15 configuration to satisfy the model's enabled/always-on criteria; the prior original-firmware study has not established it does. Even after DMA, unknown eMMC high user LBAs may become the next dependency. No hardware-accurate panel electrical timing or resource sectors should be fabricated to claim boot.

## Limits of this checkpoint

The current analysis environment validated the original OSUP container but **could not execute this QEMU run**: QEMU is not installed locally and outbound repository clone/build access was unavailable. Therefore this document is a reproducible next-step experiment, not a claimed new runtime result.
