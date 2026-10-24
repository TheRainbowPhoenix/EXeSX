# Experimental OSUP-derived eMMC candidate archive

**Local artifact:** `candidate_ipl_at_boot1_0x40_exword.zip`

**ZIP password:** `exword`

The archive stores a **15,642,656,768-byte raw eMMC image** in encrypted ZIP64 format, compressed to **27,482,235 bytes** (SHA-256 of ZIP: `b0194acdb55810501d40c312d4fd707834ddafc308ef4ec09c88de13aa9a838f`). Extraction requires ZIP64 support and roughly 15.7 GB of free disk space; the extracted file can be made sparse. Encryption is traditional ZIP password encryption, **not cryptographic confidentiality**.

The candidate was reconstructed locally from the owner's OSUP image using `scripts/run_osup.py` and a hypothesis: copying source IPL bytes to **eMMC Boot1 LBA `0x40`**, while preserving the OSUP-derived PVOS and user components B/A/partial F. This placement has *not* been authenticated against a physical flash dump. Remaining blank areas are unknown, **not verified zeros from a real device**.

A 19-second original-firmware QEMU experiment with the candidate issued the same 66 USDHC commands as the baseline synthetic image. This did **not** unblock startup. The command trace shows real CMD17/CMD18 reads after Boot1 partition switching; the last tested user-area read was `CMD18 ARG=0x00839E73`, with CMD23 block count `0x7709`.

**Privacy/provenance:** This archive contains derived firmware bytes and is not a clean-room emulator implementation. Do not put the archive or extracted raw in a source tree or Git without deliberately confirming redistribution rights. Original firmware may be downloadable from third-party archives, but public availability alone does not establish a redistribution license.

**Repository status:** The 27 MB archive was generated and verified locally but was **not uploaded to GitHub**: this session's GitHub connector only exposes text-file commits and Git blob content arguments; the local runtime has no network access to push a binary. A maintainer can attach the archive to a GitHub release or push it to an explicitly authorized repository after reviewing redistribution rights. The exact ZIP is available in the conversation as a separate download.

**Reproduce and compare:** Run both the baseline synthetic raw image and this candidate under identical QEMU flags, trace `sdhci_send_command`, and compare the earliest divergent command or A7 PC. Matching commands alone do not prove identical response data or filesystem acceptance.
