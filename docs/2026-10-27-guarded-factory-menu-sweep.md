# DY357: guarded original-ROM factory-menu sweep (27 October 2026)

Experiment branch: `experiment/dy357-m4-inputs-0804-20261023`.
Owner-private original `OSUP.BIN` was unmodified; QEMU's physical M4 GPIO contacts were used to hold `0x9C+0x90` at cold boot and send separate `0x93,0x93,0x94` after the authentic version-event wait. Original A7 execution reached the factory menu, `0x400B(2)` returned, and the genuine menu painter ran. eMMC and a disposable SD card were opened with `snapshot=on`. QMP exported the real 864x480 framebuffer read-only. The compiled QEMU from `e6d473b9` has the same emulator C code as `585b3a93`, whose Linux/Windows synthetic CI passed after correcting a BUSY-window test expectation.

**Critical selection control:** the MENU can begin with no row highlighted, and its framebuffer can be captured in the middle of redraw. This sweep sent ENTER only after the intended row's full-width black inverse bar remained consistent across a second LCD observation about one second later. Navigation occasionally moved more than one row; arrow counts alone are not evidence. Failed cold boots before the version dialog were retried, not misclassified as factory-test failures. After ENTER, each entry received ~9–13 seconds of passive screenshot observation. No guest PC, RTOS events, M4 IRQ pending bits, A7 input records, or factory verdicts were changed.

## Direct original-LCD observations

| Row | Menu label | What was actually observed | Verification boundary |
| ---: | --- | --- | --- |
| 1 | MANUAL CHECK | Native 14-item MANUAL MENU opens | Nested hardware and storage tools not run |
| 2 | ARM PATTERN MANUAL CHECK | Fullscreen color bands | Display only; no final factory OK asserted |
| 3 | ARM PATTERN AUTO CHECK | Fullscreen repeated color gradients | Display only; no final factory OK asserted |
| 4 | FIRST FINAL ASSY FUNC CHECK | Color-gradient screen | Additional functional checks not completed |
| 5 | SECOND FINAL ASSY FUNC CHECK | Menu unchanged throughout observation | Handler entry/return must be traced; not classified PASS/NG |
| 6 | SECOND FINAL ASSY CURRENT CHECK | Menu unchanged throughout observation | No independent current/ADC measurement verified |
| 7 | FFT TEST | `FFT test` and `PLEASE TOUCH` | No valid touch-start/PCM FFT verdict |
| 8 | WLAN AUTO TEST | `WIFI AUTO TEST` heading, no result | No Wi-Fi transport/scan success |
| 9 | FINISHING CHECK | Menu unchanged throughout observation | Handler entry/return must be traced; not classified PASS/NG |
| 10 | RESET | Not executed | Intentionally excluded system-reset action |
| 11 | TOUCH PANEL PRESET | Native border/X pattern | No original touchscreen coverage OK |
| 12 | LCD UNIT CHECK | Fullscreen color-gradient patterns | LCD pixel output seen; not all subchecks verified |
| 13 | E2 PATTERN CHECK | Native border/X briefly appears, later blank LCD | No accepted original touch event or OK verified; possible premature exit |
| 14 | JK PATTERN CHECK | Menu unchanged throughout observation | Handler entry/return must be traced; not classified PASS/NG |
| 15 | VERSION | Version submenu with VERSION, ROM CHECK, ROM CHECK(FAST), MTP INFORMATION | Submenu only; ROM checks unexecuted |
| 16 | OS UPDATE | Not executed | Intentionally excluded firmware-update action |

**Do not interpret a heading, unchanged menu, color pattern, or live QEMU as a passing test.** These are display/entry observations, not validated final factory results.

## Implement/verify next, in causal order

1. **Original touch pipeline:** current opt-in ROHM BU21029 digital subset does not establish normal original-A7 E2 touch events. Make controller-attached cold boot reliable; inspect normal `0x180C(0)` input-service enable, `PORTB.PCR3` IRQC, M4 NVIC IRQ57 ISER1, PTB3 voltage, genuine I2C2 `0x40` 14-byte reads, the M4 key/touch worker, and A7 type `0x6000` records. Measure raw-to-LCD calibration before attempting exact line coverage. Do not directly inject factory events or mark a framebuffer filled.
2. **WLAN:** trace `FUN_60059404` / original bus transactions to prove actual controller/CS/IRQ wiring. A photographed candidate ATWINC1510 is not proof of this DY357 board. The existing LPSPI2 register subset lacks clocked TX/RX FIFO and slave protocol. Add a legitimate SPI-device model only after grounding the host bus.
3. **FFT/audio:** `FUN_60058650` first waits for touch input; only after a real trigger is its audio acquisition result meaningful. Trace I2S0/SAI, DMAMUX0/DMA0 peripheral requests, codec input and guest PCM stream. Register readback alone cannot produce valid recorded audio.
4. **Assembly/current/finishing/JK:** instrument the original dispatch/return PCs `0x60058084`, `0x60057e50`, `0x60057ccc`, `0x60057dec`, and `0x60058118` with bounded post-menu tracing. Correlate ADC, timer, DMA, storage and IPC requests to the actual selected test; do not invent analog readings, ISR posts, or a verdict to advance it.
5. **Real keyboard timing:** after each mechanical-equivalent press, observe firmware's M4 queue/debounce and A7 consumption; adjust emulated physical clocks to resolve repeated/missed navigation. Preserve actual row/column GPIO scanning.
6. **Version/storage integrity:** the source-derived synthetic eMMC is not a complete original device dump; future ROM checks require appropriate authentic data and negative controls. Do not equate a missing sector with an original hardware failure.

The user OSUP, decompilation, source-derived media, private screenshots, raw QMP captures, traces, and addresses/identifiers copied from guest runtime remain local. Do not commit them. Prior background: [original sweep](2026-10-26-original-factory-menu-test-sweep.md), [touch IPC](2026-10-26-e2-original-touch-ipc-command.md), [BU21029](2026-10-26-bu21029-penirq-original-e2.md), [WLAN candidate](2026-10-26-bu26154-touch-and-atwinc1510-wlan.md).
