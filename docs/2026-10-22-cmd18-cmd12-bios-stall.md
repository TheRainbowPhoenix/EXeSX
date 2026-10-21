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
