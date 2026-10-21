# OSUP release updater → USDHC1 writer → eMMC boot1: evidence and limits

**21 October 2026.** Private input: the original SHA-verified DY357 `OSUP.BIN`. Only metadata, known ARM instruction locations and host-side synthetic code are committed here. No Casio updater executable, firmware payload, source sector, real boot partition or full disk image is published.

## Results

The update is **not merely BIOS+OS data**. Its release-ROM wrapper begins at OSUP byte `0`, has loader load `0x64000000`, entry `0x64000100`, executable length `0x4f40a`, and is followed by the IPL image at byte `0x80000`. These fields were read from OSUP[0x30..0x38]. Its installer directly addresses **USDHC1 at `0x40380000`** by constructing the MMIO address in ARM immediates; searching only for the literal byte sequence `00 00 38 40` would miss it.

Relevant original updater instructions (locally disassembled at original load addresses with `llvm-objdump`):

| Original ARM code | Evidence |
| --- | --- |
| `0x64003b54` | USDHC1 command-submission helper |
| `0x640041ac` → `0x64004264` | CMD25 WRITE_MULTIPLE_BLOCK, writes command at USDHC1 `+0x0c` |
| `0x640042f8` → `0x6400435c` | CMD24 WRITE_BLOCK, writes command at USDHC1 `+0x0c` |
| `0x6400439c..0x640043d0` | 32-word PIO write tranches to USDHC1 data port and W1C `INT_STATUS.BWR` |
| `0x64004964` → `0x64004a30..0x64004a50` | CMD6 switch of EXT_CSD[179] `PARTITION_CONFIG`, preserves other configuration bits |
| `0x64004dd8` | Compares requested logical partition selector to current EXT_CSD state before switching |
| `0x6400e398` | Loads/checks IPL/PVOS data from the update stream, including a separate transformed-header path |
| `0x6400ed74` | Adds `0x80000` to update-stream offset, matching the validated IPL source offset |
| `0x6400edd8..0x6400edec` | Invokes sector copy at `0x6400e068` with logical start sector 0 |
| `0x6400e068` | Reads and writes sector batches, comparing requested byte counts with actual counts |
| `0x6400ee30..0x6400ee64` | Verifies installed component after the write stage |

The CMD6 `PARTITION_CONFIG` argument is **constructed, not stored as a literal**. At `0x64004a34`, the routine adds 4 to the requested logical selector; `0x64004a44` builds `0x03b30000` (write byte, index `0xb3`) and `0x64004a48` inserts the configured partition-access byte shifted by eight. For a partition-access value `0x02` with other bits zero this yields **`0x03b30200`**, the **same register and value** observed in the earlier original BIOS trace just before CMD17 LBA `0` and LBA `0x20`. See [U-Boot's documented eMMC PARTITION_CONFIG access values](https://git.ti.com/cgit/ti-u-boot/ti-u-boot/commit/?id=8746aa0f5da740c593cef95b7c28386716f128d6): 0=user, 1=boot0, 2=boot1.

This establishes that the **updater and BIOS use compatible, actual hardware USDHC1/EXT_CSD partition mechanisms**. It does **not** yet establish that they program/read *identical physical sectors*: the updater may use different logical partition selectors for each stage, and the package has more than one storage region.

## Exact checksum-validated OSUP layout

| OSUP file offset | Component | Logical position relative to IPL start |
| --- | --- | --- |
| `0x000000` | Executable release-ROM updater wrapper | not a disk sector |
| `0x080000` | `CASIOIPL_V00`, IPL length `0x3ce00` bytes | sector 0 |
| `0x0e0000` | `CASIOPVOS800` | sector `0x300` |
| `0x140000` | `CASIODICS06B`, BIOS | sector `0x600` |
| `0x395a00` | `CASIODICS06A`, OS | sector `0x18ad` |
| `0xc18400` | `CASIODICS06F`, resources | sector `0x5cc2` |

All headers above have checksum-verified lengths / offsets. BIOS has **4,781 declared 512-byte sectors**, OS has **17,429**. The PVOS field `+0x2c` equals `0x14000` sectors (40 MiB); the updater compares it against card capacity, but its full meaning (minimum capacity or logical extent) still needs confirmation. It **cannot** be the capacity of a 4 MiB eMMC boot partition. The F component declares **59,710 sectors**, substantially more bytes than physically included in the updater's stored F payload (17,988,096 bytes). Therefore **OSUP is not a complete sector-for-sector installed image**; do not invent absent resources or partition metadata.

## Explicitly unverified boot1 IPL hypothesis

If—and **only if**—the firmware's boot1 partition-relative LBA0 maps to the IPL block at `OSUP+0x80000`, then the two originally observed CMD17 addresses correspond to:

| Original boot1 CMD17 | Candidate IPL-relative byte | Candidate OSUP byte | Candidate content |
| --- | --- | --- | --- |
| LBA `0` | `0x0000` | `0x080000` | `CASIOIPL_V00` header |
| LBA `0x20` | `0x4000` | `0x084000` | Bytes within IPL payload |

This mapping is a **test hypothesis**, not an established flash-write offset. `scripts/analyze_osup_install_layout.py` reports both candidate sector hashes without copying proprietary content and refuses unknown firmware/updater opcode revisions.

### Private original firmware differential

Two isolated **five-second cold runs** were made using the earlier verified QEMU clock/watermark build, the same original DY357 OSUP-derived BIOS/OS ELF, the same experimental diagnostic peripherals, and QEMU `snapshot=on`.

- **Control:** original 15.64 GB sparse synthetic eMMC, all boot1 sectors zero.
- **Candidate:** same sparse eMMC geometry with **only** original OSUP's `0x3ce00`-byte IPL copied at the start of emulated eMMC boot1 (file byte offset 4 MiB); no BIOS/OS/content beyond IPL was installed.
- **Both runs:** original card CMD6 `0x03b30200`, CMD17 LBA `0` then `0x20`. A7 remained at `0x601b82bc` or `0x601b82c8` in the known eDMA1 TCD DONE wait (`0x400811fc = 0x0001000a`; DONE clear). No OS entry / LCD output / validated on-media signature occurred.

**Interpretation:** merely staging the plausible IPL sectors is **not sufficient to advance boot in this controller build**. It does not prove the IPL is wrong: the eDMA1 transfer model still does not execute its 0xCA800-byte RAM copy, and the corrected later DMAMUX1/SERQ path independently exposed an unmapped `0xb0000000` device and did not reach CMD17 within its bounded run. The experiments and their binary images/logs are private, not in GitHub.

## Next verification required before creating an installed flash image

1. Trace *which* logical partition selector (`0x64004dd8` arguments) is active when the updater invokes `0x6400e068` and its CMD24/25 writer; in particular determine where it selects partition access 2.
2. Trace boot1 LBA0 and LBA32 **consumers** to see which header/checksum they validate after a completed data transfer.
3. Implement the documented eDMA1 request/transfer behavior and identify the external `0xb0000000` device instead of forging DMA completion or inventing media.
4. Build a private eMMC flash image **only for destinations proven by both write and boot-read paths**, keeping missing resources/partition tables absent and unknown.

Reproduce *metadata-only* analysis locally:

```bash
python3 scripts/analyze_osup_install_layout.py private/OSUP.BIN \
  --json private/osup-install-layout.json
python3 -m unittest discover -s tests -p 'test_analyze_osup_install_layout.py'
```

No OSUP bytes, boot-sector payloads or candidate image are generated into the public repository.
