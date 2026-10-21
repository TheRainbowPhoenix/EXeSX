# DY357 BIOS 0x601B82B8: DMA1 descriptor wait and eMMC boot1 sectors

**Date:** 21 October 2026. **Evidence:** private user-provided OSUP.BIN SHA-256 `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`, privately extracted via `prepare_osup.py`, and a 4-second native QEMU 10.1.0 cold run using PR #22 native build. The same explicitly diagnostic M4 IRQ/GPIOB/I²C/SNVS flags and sparse synthetic 16 GB eMMC were used as the previous differential. No ROM, eMMC sectors, or logs are committed.

## What original ARM code **actually** does

Local disassembly of the original ARMv7-A executable at `0x601B82A8–0x601B82E4`:

```asm
601b82a8: ldr  r1, [r0,#8]       ; handle -> DMA controller base
601b82ac: ldrb r0, [r0,#16]      ; DMA channel
601b82b0: add  r0, r1, r0,lsl#5 ; 32-byte TCD stride
601b82b4: add  r0, r0,#0x1000    ; TCD window offset
601b82b8: ldrh r1, [r0,#0x1c]    ; TCDn_CSR
601b82bc: cmp  r1, #0
601b82c0: beq  0x601b82dc
601b82c4: ldrh r1, [r0,#0x1c]
601b82c8: tst  r1, #0x80         ; CSR.DONE
601b82cc: bne  0x601b82d8
601b82d0: movw r0, #0x13ed      ; not-yet-done sentinel
601b82d4: bx   lr
601b82d8: mov  r1, #0
601b82dc: strh r1, [r0,#0x1c]
601b82e0: mov  r0, #0
601b82e4: bx   lr
```

Caller `0x601B4094–0x601B40C8` polls two DMA handles by repeatedly calling `0x601B82A8`, comparing return to `0x13ED` and looping on equality. This is a DMA completion wait **not a CMD17 sector-content compare**. A7 at monitor stop reported `R15=0x601B82BC`, `R14=0x601B40AC`, `R04=0x000013ED`, `R00=0x400811E0` and was in `abt32` mode. Its mode indicates it is executing in abort context; additional exception-stack/backtrace investigation is needed before asserting whether a new abort caused this waiter or it is ordinary interrupt/abort-mode housekeeping.

NXP's [i.MX7ULP eDMA driver TCD struct](https://mcuxpresso.nxp.com/mcuxsdk/25.03.00/html/drivers/iMX/iMX7ULP/MCIMX7U5/index.html) defines 32-byte TCDs and `CSR.DONE` at bit7. Unlike a storage sector, this is a DMA channel status field.

## Actual active DMA1 channel-15 descriptor

Live QEMU monitor physical reads (not inferred from disassembly) from the private run:

| Address / field | Value | Interpretation |
|---|---|---|
| `0x400811E0` SADDR | `0x61080000` | RAM source |
| `0x400811E4` SOFF / ATTR | `0x05050020` | SOFF=32 bytes, ATTR=0x0505, 32-byte source/dest transfers |
| `0x400811E8` NBYTES | `0x000CA800` | 829,440 bytes |
| `0x400811EC` SLAST | `0x00000000` | no source rewind |
| `0x400811F0` DADDR | `0x6114A800` | RAM destination |
| `0x400811F4` DOFF / CITER | `0x00010020` | DOFF=32, CITER=1 |
| `0x400811F8` DLAST_SGA | `0x00000000` | no scatter-gather pointer |
| `0x400811FC` CSR / BITER | `0x0001000A` | BITER=1, CSR=0x000A; **DONE=0** |

This descriptor describes a **RAM-to-RAM copy of 0xCA800 bytes**, where the destination is exactly 0xCA800 bytes after the source. It is not an MMC data-port DMA. The source and destination ranges are adjacent rather than overlapping.

The repository's `hw/arm/exesx-imx7ulp-dma.inc` explicitly *stores* TCD register bytes but performs **no transfers** or hardware-owned completion. Thus `CSR.DONE` cannot transition due to an actual DMA engine. This is now the **most defensible next hardware-model blocker**. Do **not** force DONE or mark a speculative memory copy completed: first trace the actual software request/enable mechanism, source/destination validity and eDMA side effects (request disable, interrupts, CITER, START clearing). The input registers alone do not identify the exact request event.

## Actual original MMC command arguments and boot partition selection

Re-running the private firmware with QEMU's native `-trace enable=sdhci_send_command` yielded these final relevant bus transactions:

```text
sdhci_send_command CMD06 ARG[0x03b30200]
sdhci_send_command CMD13 ARG[0x00020000]
sdhci_send_command CMD08 ARG[0x00000000]
sdhci_send_command CMD17 ARG[0x00000000]
sdhci_send_command CMD17 ARG[0x00000020]
```

CMD6 access 3, EXT_CSD index **179** (`PARTITION_CONFIG`), value **0x02**, selects eMMC **hardware boot partition 2 (boot1)** for subsequent data transfers. This interpretation is defined by [U-Boot's MMC PARTITION_CONFIG field definitions](https://lists.u-boot-project.org/pipermail/u-boot/2024-May/553473.html). It is *not* a user-area LBA switch.

CMD17 arguments `0` and `32` therefore mean **boot1 partition-relative sectors 0 and 32**, with byte offsets 0 and `0x4000` if sector addressing is in effect (the CMD1 OCR in prior run reported high capacity `0xC0FFFF00`). The synthetic eMMC model is backed by boot0/boot1 and user partitions but has no proprietary Casio boot1 contents. As a result, the actual byte-level sector expectations cannot be reconstructed from `OSUP.BIN` alone; OSUP is an updater container and **not a sector-for-sector dump**. No authentic sector signature, checksum, or boot1 file-system layout was established by this test.

If investigating expected data later: disassemble the caller of the CMD17 issue function and the first consumer of its destination buffer, capturing only parsed call-site locations/lengths in shared Git; preserve real sector images and decoded proprietary data privately.

## Reproducible tools (no firmware bundled)

```bash
# Run private ROM on an opt-in native build with the environment in
# docs/2026-10-21-usdhc-watermark-brr-study.md.
# Enable QEMU's native command trace with:
-trace enable=sdhci_send_command

python3 scripts/inspect_emmc_cmds.py private/cold-run-trace.txt

# Use QEMU monitor "stop", "cpu 0", "info registers" and eight
# "xp /1wx 0x400811E0" through "...FC" MMIO words, then:
python3 scripts/inspect_dma1_tcd.py private/monitor.txt --channel 15 \
    --elf private/a7.elf
```

Tests: `python3 -m unittest tests.test_dma1_mmc_metadata -v`. Both decoders operate on *metadata*, not proprietary contents. Data-copy and DONE behavior remain intentionally **unimplemented** until request activation is independently established. **No Casio OS execution, LCD pixels, or text output has been verified.**


## Reproducible transfer-trigger instrumentation

The DMA1 descriptor model now supports **explicitly opt-in, write-only TCD logging** (no DMA side effects). In a private QEMU run, set `EXESX_TRACE_DMA1_TCD=1` and include `-d unimp`; each guest TCD write then produces channel index, 32-byte TCD field offset, width and written value. The default log remains unchanged. Polling reads are deliberately not logged to avoid multi-gigabyte log spam. This supplies the missing evidence for identifying the correct *software-trigger or DMAMUX request* rather than faking `TCD_CSR.DONE`.

Local sparse synthetic-card inspection confirmed both **boot1 sector 0 and sector 32 contain 512 bytes of zero**. This is a property of the synthetic test image, not a claim about any physical Casio eMMC. A real device's boot1 contents cannot be inferred from an updater container. Neither those sector bytes nor proprietary ROM bytes are uploaded to Git.
