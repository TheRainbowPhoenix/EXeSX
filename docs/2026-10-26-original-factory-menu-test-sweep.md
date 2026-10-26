# 2026-10-26: original OSUP factory test-menu navigation sweep

## Test configuration and safety

- User-provided original `OSUP.BIN` SHA256: `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`.
- Executed unchanged original A7/M4 firmware with the native Linux QEMU from the successful diagnostic PR build, experimental M4/peripheral model and exact source-derived synthetic eMMC; a **disposable** 2GiB SD was attached. Both drives use **`snapshot=on`**.
- Explicit optional analog test samples: `EXESX_ADC0_SAMPLE_RAW=0x1230`, `EXESX_ADC1_SAMPLE_RAW=0x4560` (NOT real sensors).
- True cold-boot original physical-matrix chord `0x9C+0x90`, release, then `0x93, 0x93, 0x94` only after original A7 version-event wait. No guest RAM write, IPC response fabrication, code patch or forced guest PC.
- Real guest A7 executed `0x6003A878` (factory menu), `0x60006240` (0x400B call), `0x60006268` (0x400B returned), and `0x60057668` (menu painter) in repeated independent boots. The framebuffer showed the **actual 16-item TEST MENU**.
- Original keycodes `0x91` DOWN and `0x90` UP visibly move the selection; `0x94` ENTER invokes the selected original menu handler. All screenshots are read-only captures of the real 864×480 LCD export.
- Important discovery: 60ms navigation contacts sometimes generate **two** visible selection moves, so blindly counting DOWN pulses can select a wrong item. A separate sweep uses **40ms post-menu navigation holds**, reads actual inverted-highlight rows in the LCD, and only issues ENTER when the **requested row is visually confirmed**. The 60ms key timing for the *cold boot chord and three-key menu activation* remains unchanged.

## Observations (read-only LCD and native A7 execution; each test on a fresh cold boot)

| Original TEST MENU item | What actually occurred | Verdict / limitation |
| --- | --- | --- |
| 2 ARM PATTERN MANUAL CHECK | Confirmed second highlighted row, ENTER, fullscreen RGB color-bar/test display | **Entered, LCD pattern works**; not a full automatic end-to-end pass |
| 3 ARM PATTERN AUTO CHECK | Independently confirmed third highlighted row, ENTER, fullscreen original RGB color bars | **Entered, LCD pattern works**; not a complete factory assertion |
| 4 FIRST FINAL ASSY FUNC CHECK | Earlier deliberately observed test after two 60ms DOWN contacts (selected row 4, not 3): full-screen RGB gradient; next ENTER brought up **KEYS PRESS CHECK!** displaying keycode sequence. Several additional keys did not advance screen | **Partially entered**; keyboard test completion not established |
| 7 FFT TEST | Confirmed seventh highlighted row, ENTER, LCD showed **FFT test** and then **RECORDING** | **Blocked/incomplete** after at least 12 seconds; emulator has no proven audio-input stream and general M4 DMA/audio is not implemented. No successful FFT result claimed |
| 8 WLAN AUTO TEST | Confirmed eighth highlighted row, ENTER, LCD showed **WIFI AUTO TEST** heading but no result under it during 12-second observation | **Blocked/incomplete**; no functional WLAN hardware has been verified |
| 12 LCD UNIT CHECK | Confirmed twelfth highlighted row, ENTER, framebuffer changed to RGB gradient/test fields then solid white | **Entered; real LCD pattern transitions observed**, but full test completion not established |
| 15 VERSION | Confirmed fifteenth highlighted row, ENTER, actual **VERSION MENU** appeared with VERSION, ROM CHECK, ROM CHECK(FAST), MTP INFORMATION; subsequently returned to parent menu without further injected keys | **Submenu entered and returned**; individual ROM integrity checks not run |

QEMU was still running after each bounded test window; this alone **does not** mean tests or devices work. Note that the first exploratory *unverified* six-DOWN run skipped to highlighted row 10 RESET (due key repetition); it cannot count as an FFT test. Later sweeps safely guarded actual selection before ENTER.

## Not claimed or deliberately avoided

- No passing result for FFT audio analysis, Wi-Fi communication, microphone/codec, external sensors, or a complete factory test verdict.
- Did **not** navigate into/reset/format/write/OS UPDATE as part of the validated guarded sweeps, and did not run full destructive SD tests.
- M4 DMA0 and DMAMUX0 can accept a subset of control-register configuration but **do not implement real peripheral transfer requests**; audio I2S0/1 control registers are mapped but PCM capture/playback is absent. A screen labeled RECORDING is not proof of real PCM frames.
- LCD readout uses host QMP on the independent GUI monitor thread, with framebuffer capture **disabled before menu painter** to avoid perturbing sensitive boot keys. This does not freeze or inject guest state.
- Original firmware, extracted ELF, media, VM snapshots, pixel dumps, full logs and private RAM traces remain local; **none are committed to this public repository**.

## Minimal reproduction

Use the existing `scripts/factory_control_panel.py` or `scripts/headless_factory_menu_checks.py` with an owner-private OSUP, native tested QEMU and `profiles/imx7ulp-early-boot.ini`. For manual extension after the original painter: choose one of the above non-destructive entries only after observing the actual inverse-highlight row, then send genuine `0x94` ENTER. An automated safe per-test local sweep runner was used for the private tests; it captures snapshots on a monitor thread, computes the highlighted row from framebuffer pixels at x=740, and aborts if selection cannot be confirmed. An unverified key-count-only sweep is **not** a valid result.

Next hardware work is to follow original FFT/RECORDING control flow and the first unimplemented DMA0/I2S audio capture event without manufacturing samples or ready/IRQ bits; similarly inspect WLAN auto-test for the real missing device state/IPC timeout. Keep complete owner traces private.
