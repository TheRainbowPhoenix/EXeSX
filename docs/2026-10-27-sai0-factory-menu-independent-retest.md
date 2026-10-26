# 2026-10-27: independent retest of the SAI0 factory-menu HardFault fix (main `75b29ef`)

This is a **fresh independent replay**, not just a summary of earlier successful original-ROM runs. Source: successful Linux GitHub Actions run [40316550980](https://github.com/TheRainbowPhoenix/EXeSX/actions/runs/40316550980), compiled QEMU source commit `75b29ef16ffcde262fc78ca23ac6c266e53744cb`; native Windows counterpart [40316551035](https://github.com/TheRainbowPhoenix/EXeSX/actions/runs/40316551035) also passed CI.

**Privacy:** The original owner-supplied `OSUP.BIN` (SHA256 `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`), private extracted original ELF, source-derived sparse synthetic 15,642,656,768-byte eMMC image, 2GiB disposable SD image, original guest trace and original LCD screenshot stayed *off GitHub*. Both drives used QEMU `snapshot=on`.

## Replayed authentic factory-menu checks

From the extracted Linux QEMU distribution, `headless_factory_menu_checks.py` used existing private `--elf`/`--emmc` with the packaged `profiles/imx7ulp-early-boot.ini`, `--sd` disposable media, `--seconds 132 --retries 3 --retry-after 30 --post-menu-seconds 12 --fps 1`. It sent only original physical M4 key-matrix contacts: boot chord `0x9C+0x90`, then `0x93,0x93,0x94` when original A7 `0x600108A8` event wait executed. No ROM, A7/M4 state, IPC, or RTOS-event injection.

**All ten headless checks returned PASS (exit code 0)** on this new build:

1. Native A7 version dialog `0x60010868`.
2. Original A7 key-event wait `0x600108A8`.
3. Genuine first-key `0x93` check `0x60010910`.
4. Genuine last-key `0x94` acceptance `0x60010930`.
5. Native `0x6003A878` factory TEST MENU entry.
6. Native synchronous `0x400B` invocation at `0x60006240`.
7. **Actual `0x400B` return at `0x60006268`.**
8. **Original 864×480 menu painter at `0x60057668`.**
9. Single safe original M4 DOWN `0x91` matrix-contact action, **after** the painter.
10. **An actual post-DOWN LCD frame with different bytes** versus the pre-DOWN capture.

Six actual LCD frames were captured; the final raw PPM SHA256 was `948decc3b86a2ba5f47ed7e02ee9b01fd38e3325dd914bbe2096fbffc9ffe980`. The captured screen unmistakably shows the original factory **TEST MENU** listing 16 options: MANUAL CHECK, ARM PATTERN MANUAL CHECK, ARM PATTERN AUTO CHECK, FFT TEST, WLAN AUTO TEST, LCD UNIT CHECK, VERSION, OS UPDATE and others. The QEMU process was alive during the checks. A subsequent read-only shared IPC sample was `request=0x00004009, argument=1`; **this is a later IPC transaction, not a claim that pending `0x400B` remained**.

The real visible menu and native A7 service return strongly establish that the earlier **M4 HardFault at BFAR `0x41037008` (unmapped I2S0 TCSR)** is no longer preventing the factory-menu path in this build. The fix maps SAI0/SAI1 documented registers with strict reserved-offset faults. It does not fabricate event10, clear the M4 HardFault flag manually, skip the caller, or synthesize service replies.

**Interpretation boundary:** The DOWN test verifies a safe physical contact and different image bytes. It does not independently establish the selected item's exact ordinal or that any factory function runs successfully. No ENTER/OK, SD FORMAT/WRITE, OS UPDATE, or destructive factory test was executed.

## Startup reliability is still imperfect — separate negative control

A separate **two-pass headless `auto_driver.py`** on the *same build*, with `--attempts 2 --seconds 62 --post-menu-seconds 5`, successfully reached version popup and original event wait in the popup-only pass. But **both** later clean menu-pass boots timed out before event wait, so the auto-driver reported:

```text
RETRY menu 1 reason: bounded timeout
RETRY menu 2 reason: bounded timeout
MENU ENTRY: False MENU PAINT: False VISIBLE MENU: False TWO SCREENSHOTS: False
```

That negative result is **not a regression of the corrected I2S0 bus mapping or proof of a new 0x400B fault**: no 0x400B request was submitted in either failed auto-driver pass. It does show that original startup timing and emulated-media state must not be treated as deterministically reliable. The separate original-ROM headless menu run above passed, including visible LCD.

## Recommended reproducible command (Windows)

After downloading the successful current Windows artifact (including the `imx7ulp-early-boot.ini` with `[i2s0-m4]`), run from its extracted directory:

```powershell
py -3 .\headless_factory_menu_checks.py "C:\Casio\OSUP.BIN" `
  --qemu ".\qemu-system-arm.exe" `
  --profile ".\profiles\imx7ulp-early-boot.ini" `
  --seconds 132 --retries 3 --retry-after 30 `
  --post-menu-seconds 12 --fps 1
```

If your distribution keeps scripts in the `scripts\` subfolder, call `.\scripts\headless_factory_menu_checks.py` instead. The optional disposable `--sd` image is safe only when it is a file; QEMU uses `snapshot=on`, never a physical disk.

**Next reliable testing step:** capture both *pre- and post-DOWN* full LCD frames and verify the black selection bar moved to a new menu row, not just that some pixels changed. Actual menu-item execution remains untested and should begin with strictly non-destructive items only.
