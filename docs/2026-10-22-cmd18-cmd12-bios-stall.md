# DY357 CMD18→CMD12 inhibit differential (22 October 2026)

## Original BIOS instruction and real native QEMU state

With the original locally held, checksum-validated DY357 OSUP BIOS/OS, *not a synthetic ARM guest*, boot1 containing only checksum-valid `CASIOPVOS800` metadata at LBA0/LBA32, and pinned QEMU 10.1.0 after the USDHC clock/watermark patches, the genuine original BIOS sends `CMD23 0x20`, `CMD18 0x40`, `CMD13 0x00020000` and tries **CMD12 STOP_TRANSMISSION**. The last command never appears in QEMU `sdhci_send_command` trace.

Original BIOS disassembly `0x60017ce0` calls `0x60017918` with CMD12. In the command-submission helper, `0x60017950..0x60017970` writes `CMD_XFR_TYP`, then repeatedly reads and tests `USDHC1.INT_STATUS.CC` (bit0). The original guest encodes `CMD_XFR_TYP=0x0c030000`: command index12, R1b/busy response, **CMDTYP=normal**, not CMDTYP=abort.

Before patch, a cold private QEMU monitor snapshot in this loop observed:

| USDHC register | Value | Interpretation |
| --- | --- | --- |
| `BLK_ATT +0x04` | `0x001f7200` | BLKCNT=31 after first of original 32 blocks; 512-byte block |
| `CMD_XFR_TYP +0x0c` | `0x0c030000` | Original BIOS explicitly requested plain CMD12 |
| `PRES_STATE +0x24` | `0x01ff0a0e` | `CDIHB=1`, `RTA=1`, `BREN=1`: real multi-block read active |
| `INT_STATUS +0x30` | `0x00000000` | No CMD12 CC/TC; helper spins at `0x60017960` |
| `WTMK_LVL +0x44` | `0x08200820` | Original watermark of 32 words retained |

This is **not evidence of missing sector contents**: QEMU had actual card-buffer data for the first block and an active transfer. QEMU upstream [`hw/sd/sdhci.c` v10.1.0](https://github.com/qemu/qemu/blob/v10.1.0/hw/sd/sdhci.c) refuses a busy-response command under `SDHC_DATA_INHIBIT` unless `CMDTYP=abort`. The guest's CMD12 therefore never reaches real `sdbus_do_command()`.

The generic SDHCI behavior matches documented expectations for abort CMDTYP: the [NXP USDHC driver reference](https://mcuxpresso.nxp.com/api_doc/dev/1581/group__usdhc.html) distinguishes abort commands, and the [Linux i.MX eSDHC driver](https://github.com/torvalds/linux/blob/master/drivers/mmc/host/sdhci-esdhc-imx.c) contains special CMD12 handling for multi-block read completion. **The reason Casio emits CMDTYP=normal on the actual DY357 is not yet established.** Do not claim that every i.MX7ULP host accepts this combination unconditionally or that plain CMD12 is the documented optimal command type.

## Narrow opt-in compatibility fix

Only the EXeSX opt-in real eMMC host (`imx7ulp-input-clock=1`) accepts plain CMD12 with a busy response when **all** of these hold:

- `CMD12` and no data-present bit in the new command
- The existing host is already `DATA_INHIBIT` and `DOING_READ`
- The transfer mode is multi-block
- Controller input clock is enabled as in the existing opt-in model

The real eMMC **must actually respond to CMD12**, via QEMU's `sdhci_send_command` and `sdbus_do_command`. On success, end the actual host transfer: discard still-unread FIFO data, clear host read-active/inhibit state, signal normal transfer completion (TC), and avoid duplicate auto CMD12. **No card command, data bytes, sector headers, or success bits are generated without a real attached card response**. Non-opt-in QEMU/EXeSX host behavior remains unchanged.

The guest-ARM regression in `scripts/probe_upstream_emmc.py` now issues real eMMC CMD23(count32), CMD18(LBA64), reads a genuine 128-byte FIFO tranche, submits original-style CMD12 normal/R1b, and checks that the card produces CC, host TC and cleared CDIHB/BREN; a following genuine CMD13 must also complete. It also preserves existing RSTA/SDSTB, WTMK_LVL, EXT_CSD and CMD17 tests. Disabled input clock and no-media control remain separate.

## Storage layout and important limits

`OSUP.BIN` includes an updater whose main bulk-sector writer selects logical region0 (user or GP1 depending on EXT_CSD[155] completion bit), **not boot1**. A separate boot1 reader checks `CASIOPVOS800` at LBA0 and falls back to LBA32. Both source-PVOS placements were accepted in earlier original-BIOS runs and allowed CMD18 LBA64; *genuine LBA64+ on-card bytes remain unknown*. No OS entry or LCD framebuffer is claimed until an original-ROM differential confirms it.

**Private verification status:** Requires new native QEMU artifact and original-ROM rerun; synthetic CI by itself does not establish original firmware progression.


## Exact original-ROM discrepancy found after first synthetic CI pass

The initial opt-in CMD12 active-multiblock fix passed its **direct CMD18→CMD12 synthetic ARM test**, but a new private original-DY357 firmware run using the identical patched native QEMU still stalled at `0x60017960`. A separate opt-in *read-only* C-model diagnostic `EXESX_TRACE_USDHC1_CMD12=1` with `-d unimp` revealed:

```text
EXESX USDHC1 CMD12 BEFORE raw=0c030000 trnmod=0000 cmdreg=0d02 prnsts=01ff0a06 clkcon=0207 gate=0 ready=1
EXESX USDHC1 CMD12 AFTER cmdreg=0c03 trnmod=0000 prnsts=01ff0a06 norint=0000 err=0000 clkcon=0207
```

Original BIOS function `0x60017918..0x60017958` **reprograms MIX_CTRL around an intermediate CMD13** before submitting CMD12. The upstream i.MX-specific QEMU handler unconditionally assigned `s->trnmod = value & 0xffff` even while `PRES_STATE.CDIHB=1`. It thereby **erased the MULTI flag of the still-active CMD18**. Generic SDHCI's own TRNMOD handler correctly ignores transfer-mode bit writes during `DATA_INHIBIT`, but QEMU's i.MX MIX_CTRL translation bypassed it. The original command guard correctly requires a genuinely in-flight read **and prior multiblock mode**, so restoring that state is the accurate first fix, not loosening the guard on any bus transaction.

New opt-in i.MX7ULP behavior:
- Return real `MIX_CTRL` transfer-mode readback, instead of QEMU's upstream hardcoded zero.
- While `CDIHB` is asserted, preserve QEMU's `SDHC_TRNMOD_MASK=0x0037` active data-transfer bits on writes to `USDHC_MIX_CTRL` (in line with generic SDHCI write protection). Other high/non-transfer fields are still writable.
- The real guest-ARM regression now does **CMD18→32 FIFO words→MIX_CTRL clear attempt→CMD13→MIX_CTRL clear attempt→CMD12**, validates MIX_CTRL readback stayed `0x32`, and demands a *fresh* card response CC+TC rather than inheriting stale CMD13 CC.
- The real card CMD12 still must be accepted before the host marks the read stopped.

Relevant upstream/SDK comparison: [QEMU 10.1.0 `sdhci.c`](https://github.com/qemu/qemu/blob/v10.1.0/hw/sd/sdhci.c), [NXP USDHC transfer flag definitions](https://mcuxpresso.nxp.com/api_doc/dev/1581/group__usdhc.html). The same original ROM and only a private diagnostic 4 KiB RAM window for the previously unidentified external FlexBus target `0xb0000000` allow comparing CMD12 behavior without undoing the more-accurate DMA1/DMAMUX1 fixes. This private window **is not a hardware implementation** and is not committed.

**Actual original-ROM outcome** is documented below; synthetic CI alone was not used to claim BIOS progress.


## Final private original-ROM differentials after MIX_CTRL + FIFO rollover

**Verified native build:** pinned QEMU 10.1.0 with the opt-in i.MX7ULP modifications, [CI run 39690017476](https://github.com/TheRainbowPhoenix/EXeSX/actions/runs/39690017476) passing all 35 original test steps, plus further FIFO rollover correction tested independently. The original user-owned OSUP-derived ELF and QEMU TYPE_EMMC were used without binary modifications. All disk snapshots/logs are local.

First, the MIX_CTRL fix alone **unblocked real CMD12**:

```
EXESX USDHC1 CMD12 BEFORE raw=0c030000 trnmod=0032 cmdreg=0d02 prnsts=01ff0a06
sdhci_send_command CMD12 ARG[0x00020000]
sdcard_normal_command eMMC STOP_TRANSMISSION CMD12 arg 0x00020000
EXESX USDHC1 CMD12 AFTER ... prnsts=01ff0000 norint=0003 err=0000
```

The firmware no longer stalled on the old CMD12 command-complete poll. However, it retried **CMD23(32) → CMD18(LBA64) → CMD13 → CMD12** ten times. Disassembly of genuine read driver `0x600182c0..0x60018444` shows four 32-word FIFO batches per sector, and the ten-attempt wrapper `0x60018c08..0x60018cb0`. The host snapshot after the first 512-byte block still had **BLKCNT=31**, `PRES_STATE` read available, but no new `INT_STATUS.BRR`.

**Identified second root cause:** When QEMU's SDHCI PIO read consumes a 512-byte block, it synchronously prefetches the next actual sector, sets `s->data_count=0` and raises `BRR`. The BIOS then W1C-acks the *last tranche* of the previous block, which clears this already-raised BRR event. The previous EXeSX watermark fix only rearmed if `s->data_count > 0`, so it failed exactly at block rollover. The final correction reasserts BRR when and only when **genuine `SDHC_DATA_AVAILABLE` is set**, `RD_WML` is nonzero and either consumed bytes are an exact watermark multiple **or** the next real buffered sector starts at offset zero. It does not synthesize a new SD-bus data buffer or a fake final interrupt. Existing single-sector final-BRR negative controls still pass. Synthetic guest-ARM now tests **five 32-word tranches spanning two distinct backing sectors**, and full **32 × 512-byte** multiblock PIO completion (BLKCNT zero, TC set, no BRR after final block).

### Original BIOS, after both fixes (five- and ten-second bounded snapshots)

Two independent real multiblock transfers now **complete without issuing CMD12 recovery**:

```text
CMD17 boot1 LBA 0              # accepted OSUP-derived PVOS header
CMD23 count 32
CMD18 boot1 LBA 0x40          # complete 32 sectors
CMD23 count 32
CMD18 boot1 LBA 0x60          # complete another 32 sectors
CMD6 PARTITION_CONFIG 0      # switch from boot1 to user area
CMD13 / CMD8
CMD17 user LBA 0
CMD17 user LBA 0x01AF5FFF   # exactly PVOS capacity field 0x01AF6000 minus 1
```

Last observed USDHC host is **idle and not inhibited**, `PRES_STATE=0x01ff0008`, `CMD_XFR_TYP=0x11220010` (last genuine CMD17), `INT_STATUS=0x3`. No `sdhci_error`, new A7 Data Abort or invalid MMIO event was observed in these bounded traces. A7 monitor **R15=0x601CBCF8**, a barrier in BIOS housekeeping, consistently after five, six and ten seconds; **this is an observation, not evidence that this exact instruction is a poll or the next causal blocker**.

### Private media A/B/C comparison; do not mistake a hypothesis for installed flash

| Test media (same QEMU and BIOS) | New card command progression | Observed A7 result |
| --- | --- | --- |
| Checksum-valid OSUP PVOS at **boot1 LBA0 and 32**, blank remaining eMMC | Two complete CMD18 transfers, switch to user, CMD17 LBA0 and `0x01AF5FFF` | BIOS `0x601CBCF8`, no OS entry |
| Same PVOS + tentative OSUP IPL at **boot1 LBA64** | Identical commands | Same BIOS `0x601CBCF8`, no OS entry |
| Same PVOS + OSUP stream from **IPL source offset 0x80000** placed at **user LBA0**, with user rest still blank | Identical commands | Same BIOS `0x601CBCF8`, no OS entry |
| Fully blank boot1, no PVOS | CMD17 boot1 LBA0, LBA32; **no CMD18** | Independent negative control |

The user-area last-LBA probe uses `0x01AF5FFF`, matching `OSUP.PVOS[0x14]=0x01AF6000` minus one. This suggests a capacity/bounds check, but the caller consuming the returned sector must be disassembled to prove whether the data is being *validated*, rather than just probed. The three candidate media variants differ in real sectors but not in the observed command sequence, so no physical sector placement beyond PVOS has been verified.

### New remaining questions, in order

1. Trace the *post-user-area* result handling of the two CMD17 reads (LBA0 and PVOS-capacity-minus-one), including whether missing installed metadata/content causes a quiet return to BIOS housekeeping, or whether the OS loader waits for another device/service.
2. Verify whether **any** original OS entry at `0x605e3ad0` executes; the latest bounded monitor snapshot is within BIOS, and no OS framebuffer/text has been observed.
3. Identify the real FlexBus device at `0xb0000000`. This test still uses a strictly **private diagnostic 4 KiB RAM window** at that address to prevent an earlier abort; it is not a physically grounded device model and is not committed.
4. Implement actual eDMA1 request-triggered RAM copying and DONE rather than faking controller success; the current firmware trace no longer stalls at that DMA1 status for the bounded storage path, but the engine is incomplete.
5. Prove installer destination offsets for **user/GP1** and boot1 regions before creating any public flash layout. OSUP does not contain full installed resources.

**No Casio OS boot, LCD pixels or text are claimed. No private input, metadata-sector bytes, disk images, or logs were committed.**
