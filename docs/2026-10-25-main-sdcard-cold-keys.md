# Main-branch cold-boot keyboard and MU: SD kit differential (2026-10-25)

This is **public metadata only**. Do not commit `OSUP.BIN`, extracted firmware/ELF, sparse installed-media approximations, original SRAM/IPC dumps, screenshots, QMP reports, or detailed original-QEMU traces.

## Precise tested baseline

The owner-supplied SD-card local suite is explicitly built from **main** commit `bb1f5925dfd87328e7daaf973840dba2bea62bad`, and supplies a matching native Linux QEMU binary, source-derived A7 ELF, sparse synthetic eMMC, disposable 2-GiB SD, and diagnostic profile. Independently supplied original `OSUP.BIN` matched the prior project SHA-256 `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`. All executable original firmware and media remained local.

**Physical inputs, not fabricated firmware events:** held simultaneous original M4 startup contacts `0x80,0x95,0x92` from reset; released at 5 seconds host time; then closed/released `0x93`, `0x93`, `0x94` (0.15s holds, 0.08s gaps). This host schedule is an investigation tool, **not** a claim the A7 startup verifier was waiting for the chord. The original BIOS has separate startup-chord and version-dialog stages.

The main native QEMU passed actual ARM MMIO regression `probe_m4_key_matrix.py` for 0x93 (row8/column7), 0x94 (row6/column6), simultaneous contacts, unpressed/malformed states, and GPIO output priority. It also passed `probe_mu_v1_channels.py`, confirming transmit-empty and receive-full acknowledgment behavior.

## Genuine original M4 event records during cold boot

The new firmware-free `scripts/probe_cold_factory_keys_qmp.py` drives only the electrical input file and repeatedly **reads** original M4 queue slot `0x1FFEA34C` by QMP/HMP at 60 ms intervals, with no debugger or guest RAM/register writes. With original `OSUP.BIN` and removable SD enabled, the original M4 queue contained the 20-byte type2/subtype1 record header `0x00010002` and 16-bit codes:

| Host contact | Sample around | Original queue code |
| --- | --- | --- |
| First 0x93 | 5.03-5.09 s | 0x0093 |
| Second 0x93 | 5.34 s | 0x0093 |
| Third 0x94 | 5.58 s | 0x0094 |

Sample times are *host wall time* and not calibrated device timers. Distinct closures were driven and release gaps recorded; capturing a queue record proves M4 construction, **not** that the A7 received it.

### Controlled LPTMR comparison, 10-second original-ROM cold run

| Test flag | M4 queue 0x93 and 0x94 | M4 MU TR0 / A7 RR0 | M4 MU TR3 / A7 RR3 | Startup selector @0x6232E33C |
| --- | --- | --- | --- | --- |
| LPTMR IRQ disabled | observed | 3 / 3 | 0 / 0 | 0 |
| LPTMR IRQ enabled | observed | 3 / 3 | 568 / 568 | 0 |

The MU model's opt-in passive trace logged accepted zero-valued words and matching receiver reads with `rf_before=1` and `peer_te_before=0` in the enabled configuration. No dropped TX was recorded in these two runs. The 568 TR3 notifications are **not 568 keyboard events**; they may be periodic service/IRQ traffic. Zero-valued TR words are **doorbells**, not decoded key payloads. This table confirms physical key-event construction and MU hardware acknowledgment **separately**, not M4-to-A7 end-to-end key identity.

An earlier 13-second high-frequency run on the same original/main combo saw three distinct key records and 734/734 TR3 acknowledgments (3/3 TR0). These are illustrative counts, not deterministic timing expectations.

## Reproduce on the private SD-card kit

Run from a local unpacked kit root, without uploading any generated files:

```bash
python3 qemu/probe_cold_factory_keys_qmp.py \
  --qemu qemu/qemu-system-arm \
  --profile diagnostic-memory-profile.ini \
  --elf a7-bios-os.elf \
  --emmc source-derived-synthetic-emmc.raw \
  --sd disposable-sd-2g.raw \
  --output-dir private/main-cold-keys \
  --seconds 10 --contact-at 5 --poll 0.06 \
  --lptmr-irq --mailbox-trace
```

The script uses `snapshot=on` for both media; a `--mailbox-trace` run can produce a **large private QEMU MMIO log**. Change only `--lptmr-irq` for a differential. If the runner is used from the portable suite `qemu/` folder rather than a checked-out Git tree, place this single source file next to its sibling `drive_factory_menu.py`.

## Remaining required proof for real factory menu

The original A7 startup selector at `0x6232E33C` stayed `0` in the tested cold-boot samples. None of these read-only queue samples proves original execution of `0x600108A8` (version dialog event wait), the A7 decoded record `FUN_60009FB0`, original `0x60010910/0x60010928` diagnostic checks, or native menu `0x6003A878`. The prior owner-private **post-version-wait snapshot** experiment did execute native `0x6003A878` with the genuine keys, but that checkpoint is **not included** in the attached portable SD test kit. In the prior successful entry, later `0x400B(2)` service completion and menu LCD paint `0x60057668` remained blocked.

**Prioritize the original A7 cold-start task/IPC service gate** (`0xB000`, `0xA004`, `0xA002`) and the call chain enabling `FUN_60011860` / `FUN_60011CA4`, not speculative keyboard remapping or forced mailbox/event injections. Then obtain the original version-event checkpoint, verify each A7 event payload, and follow the genuine `0x400B(2)` completion to LCD paint. Do not classify the SD factory diagnostics as passed based on host-side emulation tests.

## Branch cleanup

On 2026-10-25 the existing safe-prune workflow removed four old merged-PR branches (#37–#40). The post-merge `experiment/dy357-m4-inputs-0804-20261023` head `a8c9852` was first archived as immutable tag `archive/2026-10-25/experiment/dy357-m4-inputs-0804-20261023`. `main` is the sole new development baseline. `test/dy357-dma1-boot-20261022` is preserved because open PR #36 still refers to it; it is not silently deleted or force-merged.
