# 2026-10-27 — Original INPUT touch calibrations and SERVICE unlock (bounded tests)

**Source and privacy:** owner-private unchanged OSUP/A7/M4, native QEMU branch experiment `experiment/dy357-m4-inputs-0804-20261023`, reconstructed incomplete private eMMC and disposable SD both `snapshot=on`. The physical key/touch host files only set electrical M4 inputs. No A7 events, M4 IRQ flags, shared IPC replies, CPU PCs, framebuffer coverage or factory verdicts were injected. Original LCD PNGs, private exact region values, traces, and firmware remain local.

## Genuine touchscreen test outcomes

| INPUT CHECK option | Original LCD confirmation | Host input from BU21029 touch file | Trace result |
|---|---|---|---|
| 4 — TOUCHPANEL CALIBRATION | Four corner plus signs / `TOUCH ADJUST` | Four original-A7-region **center candidates** sent as raw 12-bit electrode samples with real pen release between samples | No region changed; M4 made **0** 14-byte BU21029 RX requests |
| 5 — TOUCHPANEL 2-P CALIBRATION | Two diagonal plus signs / `TOUCH ADJUST` | Two original-A7-region center candidates | No region changed; **0** 14-byte RX |
| 6 — TOUCHPANEL CROSS CALIBRATION | Original full border-and-X cross | One raw center contact | Before, contact-held, and released frames **pixel-identical**; **0** 14-byte RX |
| 7 — TOUCHPANEL ADCONV TEST | Original `A/D CONV CHECK(ROHM)` with HEX/DEC X1/X2/Y1/Y2 fields | One raw center contact | X/Y fields remained blank; **0** 14-byte RX |

Each original ROM run enabled the BU21029 on M4 LPI2C2 at 0x40. Focused logs observed physical pen scan state changes and genuine firmware PORTB.PCR3 writes. The M4 performed **350–524 one-byte STATUS reads** in each bounded run. None issued a 14-byte coordinate acquisition or consumed a completed report. The original A7's A/D conversion routine `FUN_6005D19C` visibly calls `FUN_6001EC84(1)`, which tells the M4 to disarm pen IRQ; the normal touch-init/worker lifecycle must therefore be tested across each mode rather than forced ON when a pen file changes. Neither original A7 type `0x6000` events nor a factory OK verdict have been established. A host raw-electrode center equal to an A7 output-region center is a **test hypothesis, not verified inverse calibration**.

## SERVICE

From genuine MANUAL MENU row 13, the native `ENTER UNLOCK PASSWORD!` screen was confirmed **before** sending any keys. Five real M4 electrical contacts matching the original service-mode unlock code were sent with 160 ms holds and ~1.15 s between releases. The LCD returned `**** PASSWORD NG!! ****`. Shorter contact cadences had the same outcome. No unlocked 12-item SERVICE MENU was reached or screenshotted. The next discriminator is to read each actual original A7 `FUN_60012574` return type and keycode within `FUN_6004752C(1)`, to distinguish duplicate, stale, missing or invalid events. The 49-key AUTO covering test was separately proven to acknowledge all 49 numbered input events; this does not establish the strict service-password sequence.

## Source-only reproducibility

`scripts/plan_factory_touch_calibration.py` reads the owner's private A7 ELF *locally*, decodes the four/two acceptance regions and prepares 14-byte BU21029 physical inputs in the original M4 word order (big-endian Y, X, Z1, Z2, then three zero words for a single pen). It does not upload ROM bytes, inject A7 touch events or report a factory pass. `tests/test_plan_factory_touch_calibration.py` exercises it with an entirely **fabricated** ELF and invalid-layout negative control.

**Hardware fix acceptance:** record normal original A7 touch-enable command `0x180C(0)`/M4 IRQ57 and PORTB.PCR3 state, then witness original 14-byte LPI2C2 read, original M4 touch event/envelope transfer to MU/A7, original A7 type `0x6000` record with calibrated coordinates, and original LCD change/OK. Until then, calibrations and CROSS do not pass, regardless of how precise the raw host trace is.

No destructive flash, media, reset or factory service operation was run.
