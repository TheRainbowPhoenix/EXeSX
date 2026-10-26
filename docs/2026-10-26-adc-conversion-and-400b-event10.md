# ADC conversion proof versus native factory IPC 0x400B(2) (2026-10-26)

Firmware **not** included. Original owner-only OSUP SHA256 `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`. Test input uses the original user-derived A7/M4 ELF, sparse synthetic installed eMMC, and disposable 2GiB SD, with both media `snapshot=on`. No proprietary firmware, extracted instructions, QMP original RAM dumps, or original execution traces have been uploaded to GitHub.

## Implemented real ADC digital conversion path

`hw/arm/exesx-imx7ulp-adc.inc` now models the original guest's software-triggered command, bounded result FIFO, FIFO-count, watermark/ready flag, and real M4 NVIC ADC0/ADC1 IRQ **58/59**. It *does not* claim to emulate actual analog input circuitry. Conversion results exist **only** if a researcher explicitly provides one of `EXESX_ADC0_SAMPLE_RAW` or `EXESX_ADC1_SAMPLE_RAW` (unsigned 16-bit values), and only after real guest CPU writes a valid software trigger while ADC enabled and TCTRL has a command. The default still has a disconnected analog source and no invented sample or conversion IRQ.

Original ROM disassembly and read-only original-MMIO registers caught a crucial initial bug: `TCTRL0 = 0x01000000` selects command1 in **bits 24..27**, not the low nibble. Corrected in `bf8980f8` and verified via original guest register reads. Original synthetic real-ARM firmware-free QEMU regression `scripts/probe_adc_conversion.py` exercises both ADCs with the **correct** TCTRL and explicit sample `0x1230/0x4560`, and independently verifies the no-sample control, FIFO count, ready threshold, pop and clear semantics. It runs on Linux and Windows CI.

Linux [40247076480](https://github.com/TheRainbowPhoenix/EXeSX/actions/runs/40247076480) and Windows [40247076496](https://github.com/TheRainbowPhoenix/EXeSX/actions/runs/40247076496) **both passed** at commit `6613063fce20a820980d6a2eef67137692e30d13`.

## Actual unchanged original OSUP test with corrected ADC decoder

Using the QEMU native artifact from that successful CI commit, opt-in environment `EXESX_ADC0_SAMPLE_RAW=0x1230` and `EXESX_ADC1_SAMPLE_RAW=0x4560`, real row-gated 0x9C+0x90 boot chord, and the original 0x93,0x93,0x94 sequence only after genuine A7 `0x600108A8` event wait:

- Original A7 entered the real version dialog, accepted all menu keys and executed authentic factory menu `0x6003A878`, then native synchronous `0x400B` entry `0x60006240`.
- Unlike the old nonmodelled ADC, **both ADC hardware FIFO counters advanced** from `FCTRL=0x00020000` to **`FCTRL=0x00020001`** after original firmware `SWTRIG=1`. This is genuine digital conversion triggered by the guest, with an explicitly provided synthetic analog sample. Original guest ADC0/ADC1 registers remained `CTRL=1`, `IE=1`, `TCTRL0=0x01000000`.
- Both ADC STATUS registers stayed **0** because each FIFO has **only one queued result**, less than the firmware's configured watermark of **two**. The model correctly does not invent an interrupt or alter the guest's programmed threshold.
- The original shared IPC still contained `0x0001400B` with argument `2`. A7 neither returned through `0x60006268` nor reached factory painter `0x60057668` in the bounded original ROM runs (including a trace to >100 host seconds). The full menu did **not** become visible.
- With ADC source disabled, the FIFO remains zero and no conversion result/IRQ appears: independent no-analog baseline retained.

**Conclusion:** the ADC command decoding and result FIFO are now genuinely exercised; this alone did **not** fix original firmware `0x400B`. Merely asserting an ADC IRQ below the firmware-programmed watermark or forcing an IPC completion would fabricate hardware behavior and invalidate the test.

## New narrower IPC root-cause trace: original M4 waits on event object 10

A minimally filtered original M4+A7 **executed-TB trace**, separate from synthetic tests, captured the following sequence *immediately after* actual original A7 `0x60006240` during native menu entry:

1. Original M4 entered the subroutine at **`0x1FFE4748`**, with executed translated-block entries `0x1FFE474E`, `0x1FFE475C`, `0x1FFE476A`.
2. It executed **`0x1FFE4776`**, posting **RTOS object 7, mask `0x01000000`** by original ARM `0x1FFD53BA`.
3. It executed **`0x1FFE4780`**, which loads `R1=0xffffffff`, `R0=10`, and calls original RTOS wait routine **`0x1FFD635C`** from instruction `0x1FFE4786`.
4. There was **no executed block at `0x1FFE478A`** (post-wait continuation) and no A7 synchronous return at `0x60006268` or factory glyph-painter `0x60057668`. The M4 and A7 keep executing other original code, so QEMU itself did not crash.
5. The native shared request stayed `0x0001400B` / arg2 for the duration.

These facts precisely establish **service call reaches its M4 event7 handoff then waits on M4 RTOS event object10**. The M4 event10 producer or dependent peripheral completion is the next unfulfilled transition. Do **not** confuse this event10 service wait with the separate original ADC0 event-object8 or ADC1 event-object7 wait: multiple independent tasks/interrupts use event7.

## Next fix must be tied to the actual event-10 producer

Trace the real M4 consumer of posted object7 mask `0x01000000`, any downstream callback or peripheral IRQ, and the original **event10 post/give**. Specifically test original execution after `0x1FFE4780` and before expected `0x1FFE478A`, with separate read-only observation of the RTOS object/task state. Avoid indiscriminate broad `-d exec` filters before version dialog, which are intrusive and can alter cold-boot timing. Only after genuine M4 event10 completion should the A7 service response path and menu painter be asserted.

The existing `scripts/headless_factory_menu_checks.py` accepts `--adc0-sample 0x1230 --adc1-sample 0x4560 --no-screenshots --tcg-thread multi` to reproduce a **diagnostic**, not true board-analog, input. Use `--trace-m4-400b` only for focused M4 execution evidence, and keep full private guest traces local.

**No factory menu items, SD full test, SD FORMAT or destructive write were executed**, because the original menu is not painted yet.
