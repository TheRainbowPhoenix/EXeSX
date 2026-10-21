# Original DY357 updater partition selector and boot1 PVOS: verified firmware differential

**22 October 2026**. Evidence: user-owned, locally checksum-verified DY357 `OSUP.BIN` (SHA-256 `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`), its original release updater disassembled at `0x64000000`, private original BIOS/OS QEMU execution, and NXP/Samsung/U-Boot eMMC register definitions. **No Casio firmware bytes or storage sectors are committed**.

## 1. Distinguish two different partition-selection callers

`0x64004dd8` is the updater's logical-partition selector. It ultimately calls `0x64004964`, which constructs `CMD6` for `EXT_CSD[179]` (`PARTITION_CONFIG`), preserving the upper bits of the existing register. The key mapping instructions are:

- `0x64004a34: add r6,r6,#4` maps software selector to `PARTITION_ACCESS` physical number.
- `0x64004dd8`: logical `0` is conditional on `EXT_CSD[155].PARTITION_SETTING_COMPLETED`, read as byte at `card_state+0xbb` (the EXT_CSD copy begins at `card_state+0x20`). If bit0 is clear, `0x640049ac` changes the software selector to `-4`, and the CMD6 physical access number is **0 (user area)**. If bit0 is set, logical selector 0 maps to **4 (GP1)**, provided that partition exists and is enabled.
- **Bulk update-image path:** `0x6400ecb0: mov r0,#0`; `0x6400ecb4: bl 0x64004dd8`. This selects logical 0, thus **user or provisioned GP1, not boot1**. `0x6400edd8..0x6400edec` invokes the genuine sector writer `0x6400e068` with `r1=0` (destination sector zero of that selected region) and a size from caller state. The source stream had been positioned relative to `OSUP+0x80000`, the checksum-validated IPL start. This does **not** establish a direct write of the IPL to boot1.
- **Separate boot-area reader:** `0x640075b4` maps its boot-area flag `r3=1` to software selector `-2` (`mvn r3,#1` at `0x640075e0`), then `-2+4=2`: **physical eMMC boot1**, the second hardware boot partition. This wrapper calls MMC read `0x64004cc0`, not the bulk image writer.

Cross-check against [U-Boot eMMC PARTITION_CONFIG access values](https://lists.u-boot-project.org/pipermail/u-boot/2024-May/553473.html), [Samsung KLMxGxJETD-B041 EXT_CSD](https://file.elecfans.com/web2/M00/4E/EF/pYYBAGK9bGKAJZotAAtd8EIeHTc571.pdf) for indexes 155 and 160, and NXP USDHC definitions. The Samsung candidate reference has PARTITION_SETTING_COMPLETED=0 by default; the original DY357 device's setting has **not** been measured.

## 2. What the updater expects at boot1 LBAs 0 and 32

The original updater's `0x64007488` routine:

1. `0x640074a0..0x640074b0`: selects boot1 and reads **LBA 0**;
2. `0x640074bc..0x640074cc`: invokes header validator `0x6400725c`;
3. if read or validation fails, `0x640074d8..0x640074e4`: reads **LBA 32** from boot1 and validates it;
4. after success, `0x64007504..`: copies the accepted 512-byte sector to a RAM metadata buffer.

`0x6400725c` verifies an updater literal, found at `0x6401df44`: **`CASIOPVOS800`**, 12 bytes. It computes the byte-sum checksum over bytes `0..509`, compares the 16-bit trailer, requires marker `0x55aa` and sector size `512` at bytes `12..15`, and checks capacity/address-range metadata. These checks match the actual checksum-validated `CASIOPVOS800` sector at **OSUP offset `0x0E0000`**, not the `CASIOIPL_V00` header at `0x080000`.

Relevant PVOS metadata (source-derived fields, not independently authenticated physical card geometry):

| PVOS field offset | Value | Confirmed observation |
| --- | --- | --- |
| `+0x00` | `CASIOPVOS800` | Exact header signature |
| `+0x0c` | `0x55aa` | 16-bit marker |
| `+0x0e` | `0x0200` | 512-byte sectors |
| `+0x10` | `0x01b36000` | Compared with available eMMC sector capacity by updater |
| `+0x14` | `0x01af6000` | Compared in bounds checks |
| `+0x28` | `0x00000000` | Start-sector field involved in component parsing |
| `+0x2c` | `0x00014000` | 81,920 sectors = 40 MiB; not boot1 capacity |
| `+0x3c` | `0x01af6000` | Additional capacity/bounds comparison |

PVOS source-sector SHA-256: `4f26081b535cc8cb3ceb8ca8d6a6d1c2d35a1acdbdefaf2c330ad434333c1518`. **A hash of a source sector is not a claim that an installed sector is byte-identical**: the updater could rewrite its fields or recompute a checksum.

## 3. Private original BIOS A/B test: PVOS header acceptance

Each test used the same original user-owned BIOS/OS ELF, QEMU 10.1.0 opt-in i.MX7ULP/USDHC1+real synthetic eMMC branch containing the verified FIFO watermark fix, the same diagnostic MU/I2C/SNVS/GPIOB settings, and `snapshot=on`. The eMMC backing was sparse, comprised QEMU's `boot0` first 4 MiB and `boot1` next 4 MiB, with blank other sectors. PVOS bytes were privately copied from original OSUP offset `0xe0000`; **no raw bytes are published**.

| boot1 PVOS placement | Original BIOS command sequence after CMD8 | Latest bounded A7 observation |
| --- | --- | --- |
| Neither (blank) | CMD17 LBA0, CMD17 LBA32; prior abort-mode DMA DONE wait | `0x601b82b8..0x601b82d0` |
| **Only LBA0** | CMD17 LBA0, **CMD23 count32, CMD18 LBA64, CMD13** | `0x60017960` |
| **Only LBA32** | CMD17 LBA0, CMD17 LBA32, **CMD23 count32, CMD18 LBA64, CMD13** | `0x60017960` |
| **Both LBA0 and LBA32** | CMD17 LBA0, **CMD23 count32, CMD18 LBA64, CMD13** | `0x6001796c` |
| Both PVOS + candidate original IPL at boot1 LBA64 | Same CMD23/CMD18 sequence; **no further boot progress** | `0x6001796c` |

This establishes **behavioral compatibility** of the OSUP PVOS header with the original BIOS's **boot1 primary/fallback metadata reader**; it does not prove the installer generated exactly those two physical sectors. Placing IPL bytes at boot1 LBA0 was a **wrong hypothesis**: updater requires `CASIOPVOS800` there, not `CASIOIPL_V00`.

The newly exposed wait at `0x6001795c..0x60017970` polls USDHC1 `INT_STATUS`; after the observed CMD18/CMD13 path, monitor showed `INT_STATUS=0x00000000` and command register `CMD_XFR_TYP=0x0c030000` (CMD12). We **do not yet know whether this is missing QEMU transfer-complete/stop behavior or later firmware control logic**. This is not an OS entry; no LCD text or framebuffer has been established.

**Important differential qualifier:** On the *more accurate later* DMA1/DMAMUX1 register branch from PR #24, the original firmware instead encounters another missing external-device access at `0xb0000000` before it reaches this storage path in a bounded run. The PVOS experiments deliberately reused the earlier, reproducibly working eMMC boot-reader configuration to compare media contents without simultaneously changing hardware models.

## 4. What partition data is actually known

| Hardware area | What we can currently establish |
| --- | --- |
| **boot1** (physical access 2) | Primary **PVOS-compatible** 512-byte metadata at LBA0 and fallback at LBA32; BIOS issues CMD23/18 reading **32 sectors starting at LBA64** once PVOS is valid. Actual LBA64+ contents and installation writer still unknown |
| **boot0** (physical access 1) | No authenticated sector layout or installed content has been established |
| **user** (physical access 0) | The bulk installer writes LBA0+ **if EXT_CSD[155] bit0 is clear**. OSUP contains IPL, BIOS, OS and partial resources with verified relative offsets; complete destination-sector layout and preservation of old files not established |
| **GP1** (physical access 4) | Alternate logical-0 destination when `PARTITION_SETTING_COMPLETED` bit0 is set. No actual GP1 allocation or installed content verified |
| **RPMB / GP2–GP4** | Nothing established from this trace |

The OSUP `F` resource component declares more data than the updater file stores. No authentic disk image can be assembled by simply concatenating all components.

## 5. Reproducibility without distributing proprietary data

`scripts/analyze_osup_install_layout.py` now checks the updater's actual ARM opcode sites for logical-to-physical partition translation and boot1 primary/fallback reads, confirms the embedded updater PVOS signature pointer, validates PVOS checksums and emits source sector hashes and a precise evidence map.

It also supports an **opt-in, private, sparse, synthetic** 15.64 GB QEMU image. It refuses to overwrite an existing file and writes only the 512-byte PVOS source sector to selected test locations in boot1, leaving everything else blank:

```bash
python3 scripts/analyze_osup_install_layout.py private/OSUP.BIN \
  --json private/boot1-pvos-metadata.json \
  --private-pvos-test-image private/pvos-boot1-test.raw \
  --placement both
```

For a real-ROM experiment, use the private user-owned ELF with opt-in USDHC1 host and `-drive if=none,id=exesx-emmc,file=private/pvos-boot1-test.raw,format=raw,snapshot=on`. Do **not** commit the ROM, the synthetic image, traces or proprietary bytes. The synthetic CI tests verify opcode rev guards, PVOS routing, sparse primary/backup offsets and absence of copied IPL data at boot1 LBA64.

**Next independent tasks:** trace exactly which installer path creates/upgrades boot1 PVOS, decode what the BIOS expects in CMD18 LBA64+ and diagnose the CMD12/INT_STATUS wait; separately resolve `0xb0000000` and execute actual eDMA transfers on the corrected hardware path. None is yet proved.
