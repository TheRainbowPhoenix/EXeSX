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

## Local original-ROM A/B execution (new verified evidence)

After the pinned GitHub Action `39833050218` passed and provided artifact `12449257694`, the original locally held SHA256-validated `OSUP.BIN` was used with its two-section validated A7 BIOS+OS ELF and the source-derived synthetic eMMC (PVOS boot1 LBA0/32 and only source-available B/A/F component sectors). The distributed Linux QEMU binary, checked in Linux container, was launched with the existing opt-in experimental M4/MU/LPIT1/LCD/eMMC options and generated diagnostic LCD profile. Both cases had a **30-second wall-clock timeout**, a `-d guest_errors,unimp,in_asm` instruction-translation log and the same `-trace enable=sdhci_send_command` option. Screen was a private P6 PPM; no firmware, framebuffer or raw trace is uploaded here.

| Observed | DMA1 disabled | `EXESX_EXPERIMENTAL_DMA1_M2M=1` |
| --- | --- | --- |
| Log entry `EXeSX DMA1 copied 829440 real RAM bytes ch=15` | 0 | **5** |
| Distinct translated BIOS `0x60000000..0x603fffff` block addresses | 5680 | **5722** |
| Translated OS `0x60400000..0x60cfffff` block addresses | **0** | **0** |
| Trace entries containing `sdhci_send_command` | 67 | 75 |
| PPM framebuffer | 864×480, **414720 white pixels** | 864×480, **414720 white pixels** |
| Last observed translated BIOS block in dump | `0x601B44FC` | **`0x60028290`** |

The DMA-enabled trace also contains translated `0x601B4504` and `0x601B82BC` and all five transfer-completion messages; no `unsupported descriptor` or `waiting for enabled` messages were present. The last translated block is **not** necessarily the CPU's final PC because translated-block logs only report first-time code translations. Repeated copies can also arise from authentic repeated firmware requests. This is evidence the former DMA barrier has been overcome at least for these requests, **not** evidence that the OS reached execution or that text appeared.

**New next diagnostic:** trace the control flow and BIOS return/decision around `0x60028290`, ideally with a precise paused CPU-register snapshot and narrowly scoped MMIO/storage debug. Compare the new DMA run against the control, determine whether any new callback, resource/installed-media sector, or peripheral completion is blocking OS handoff. Do not mark the OS as booted or infer text from a PPM file alone.

## Follow-up 23-second monitor stop (DMA enabled)

A second private original-OSUP DMA-enabled run with the same synthetic eMMC and experimental peripherals was stopped using the QEMU HMP monitor after approximately 23 seconds, yielding an actual CPU0 register snapshot: **R15=0x601CBCF8, R14=0x601CBCC4, PSR=0x6000011F (sys32), R0=0x00030000**. QEMU identifies CPU0 Cortex-A7 and CPU1 Cortex-M4. The paused A7 position matches an already-seen BIOS idle WFI/ISB location from the previous study, **not** the last newly translated `0x60028290` block. This is a sampled idle state, not proof of which condition is ultimately preventing OS handoff. It also does not invalidate measured DMA completion. OS still not observed and framebuffer remained white in the timed A/B experiment.

Priority now: narrow bounded trace around BIOS callback dispatch, timer/interrupt wakes and high-user-LBA storage return decisions, and sample status variables around the idle to determine which post-DMA boot condition is missing. Do not force OS PC.

## Post-DMA callback/IRQ/storage investigation (read-only original A7 GDB)

A fresh private owner-supplied checksum-valid OSUP A7 ELF and the identical synthetic eMMC, pinned QEMU from successful CI run #39833050218, opt-in DMA1/LPIT1/LCD/M4, GDB `Hg1` (CPU0) and `Hc-1` (both cores) achieved **actual instruction execution** breakpoints, rather than relying on first-time translated-block addresses.

- `0x60048878`: inner BIOS service entered. `0x600488A0` showed `R0=1` after the requested 25-unit timer callback; `0x600488B8` requested the 125-unit delay. At `0x600488E0` the nested service returned its locally recorded `R4=1`. The outer caller reached `0x60048924` with **R0=1**, taking the conditional retry/service branch to `0x600488F8`.
- The earlier DMA wait **actually returned success** at `0x601B4504` with **R0=0**, and the exit instruction `0x601B450C` was reached in the controlled follow-up. The same run also reached genuine BIOS memory/storage processing at `0x60028290`. This is not merely an unverified DMA success log.
- **No breakpoint hit** was observed at startup return `0x6004A2B0`, callback loop `0x6004A2CC`, dispatcher `0x60049BCC`, BLX `0x60049C04`, OS trampoline `0x60400000` or OS target `0x605E3AD0` in the bounded experiments. Absence is bounded only.
- A second read-only private GDB milestone probe captured live `0x622E6FC4=0x3F` (all components accepted), `0x6232DA18=0x60400000` (OS entry recorded), `0x622E6FBC=0` (not yet copied into callback cache), separate `0x62413241=0` (service ready byte unset) and `0x6232E35C=0` (timer wait flag cleared). Thus, **the callback is registered but the pre-dispatch BIOS sequence is not yet known to have returned**. Timer completion is not the current evidenced blocker.
- The old bounded DMA-enabled SD command log contains repeated `CMD23 count=0x271 / CMD18 user LBA=0x008A3705` near its end. This is high user-area storage beyond OSUP-provided bytes, and those positions are unknown/zero in the synthetic image. There is **no proven content-dependent failure or validated dictionary/resource identifier** from commands alone.
- Actual machine stop can differ with elapsed wall time and debug overhead. In an 18-second instrumented run the sampled CPU0 PC was `0x601B4504` during a transient DMA return; in the preceding longer 23-second monitor run it was BIOS idle `0x601CBCF8`. Neither point alone proves a permanent stall.

The new `scripts/probe_postdma_handoff.py` provides one-shot, metadata-only QEMU ARM GDB breakpoints and targeted status reads, with generated `handoff-summary.json` remaining under the ignored `private/` directory. `scripts/run_osup.py` now exposes it via:

```bash
python3 scripts/run_osup.py /secure/path/OSUP.BIN \
    --dma1-m2m --handoff-probe --seconds 35 \
    --output-dir private/handoff-dma
python3 scripts/run_osup.py /secure/path/OSUP.BIN \
    --handoff-probe --seconds 35 \
    --output-dir private/handoff-control
```

QEMU Actions CI builds a native emulator and bundles this runner and diagnostic alongside `prepare_osup.py`, with firmware-free tests of packet/reg decoding. **Do not publish `private/`**: the logs/screenshot/ROM-derived eMMC are not public data. Next: distinguish whether `0x6001EC14`'s event result, `0x60048924` retry condition, or a high-LBA storage/content validation keeps the outer `0x60048D9C` service active. Use repeat-conditional GDB stops with both-core registers and memory readback; do not force `0x60400000` or fabricate sectors/interrupts.

### Repeated real BIOS retry breakpoint / SDHC argument correlation

A third source-identical, DMA-enabled, private QEMU/GDB run installed a breakpoint at **`0x60048924`**, and carefully used remove → *single guest instruction step* to `0x60048928` → reinsert → continue. All five observed real CPU0 breakpoint hits returned **R0=1**, which according to the verified ARM instruction `CMP R0,#0; BNE 0x600488F8` takes the retry/service path rather than falling through. The last USDHC1 command-argument register `0x40380008` at each stop held respectively:

```text
retry 1: 0x0084157C
retry 2: 0x008A3976
retry 3: 0x008A3705
retry 4: 0x008A3705
retry 5: 0x008A3705
```

This is affirmative evidence of at least **five genuine iterations** of the nested BIOS retry in a bounded run, temporally correlated with repeated high user-area CMD18 operations. The SDHC argument register is the **last submitted command argument**, not a verified current active command. **The data-dependent reason for R0=1 is still unknown**; absence of installed source data at this LBA remains a serious hypothesis, not a proven cause. The new probe re-arms this one selected breakpoint up to five times with real single-step, while leaving all others one-shot. Callback/OS entry remains unobserved.
