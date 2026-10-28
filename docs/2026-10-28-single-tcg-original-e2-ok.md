# Original E2 touchscreen `OK` — single-thread QEMU, physical contact (2026-10-28)

## Result

**The original, unmodified owner A7 BIOS executed its genuine E2 `OK` branch at PC `0x6005CD08` under `-accel tcg,thread=single`. The original `NG` branch at `0x6005CD30` did not execute in that physical-input replay. This is a real E2 pass, not a host-side fabricated status.

Owner OSUP SHA-256: `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`. The QEMU native Linux binary came from GitHub Actions for the experiment branch. All proprietary OSUP/ELF, decompilations, media, MMIO dumps and original screenshots remain **private**.

### Unchanged guest execution

1. Genuine M4 matrix startup chord `0x9C+0x90` -> original A7 `CA05` mode.
2. Separate physical `0x93,0x93,0x94` -> original A7 third-key acceptance `0x60010930` and factory TEST MENU `0x6003A878`.
3. Original M4 IPC `0x400B(2)` **returned**; the original TEST MENU painter executed.
4. Original M4 physical DOWN/UP keys selected row 13. Physical ENTER reached genuine `0x6005830C` E2 entry. The framebuffer displayed the full border and X with **113,969 black pixels**.
5. Raw ROHM BU21029 input (one stationary pen held down): `X=961, Y=1139, Z1=800, Z2=1200`. The unchanged M4 acquired and posted touch input. The original A7 erased **exactly one black pixel** on the diagonal at LCD coordinate **(200,111)**; black pixels changed **113,969 -> 113,968**.
6. The host released the real physical pen, allowed the firmware to rearm `PORTB.PCR3=0x00080000`, then pressed physical key `0x94` for the E2 result event. The original A7 executed PC **`0x6005CD08`**. The guest-executed TB trace contained exactly one OK-branch hit and no NG-branch hit.
7. The screen subsequently cleared. This alone is not evidence of success; the distinct original OK branch is.

No A7/M4 PC, registers, memory, event queue, MU envelopes, NVIC pending flags, framebuffer or factory result was written by the host. Storage was original-owner-derived synthetic eMMC plus disposable SD with `snapshot=on`. Diagnostic ADC raw sample values are hypothetical, not physical voltage measurements.

## Why one carefully placed touch works

The owner A7 decompilation `FUN_6005C6BC` and corresponding unchanged ARM disassembly show that E2:

- Draws its black border/X using `FUN_6005C618(..., color=1, ...)`.
- Processes genuine event type `0x6000` and renders touches with XOR pixels (`FUN_601B2060`).
- On original exit event `0x12` (physical key code `0x94` is mapped to that event by `FUN_600132B4`), **redraws the E2 target with color selector 2** *before* scanning for remaining zero pixels.
- Enters the real OK path at `0x6005CD08` if no zero pixels remain; otherwise enters NG at `0x6005CD30`.

The trace-verified one-point test placed its touch **on** an already black diagonal, toggling black to white with no extra black marks elsewhere. In contrast, sweeping arbitrary raw coordinates over the white area creates new zero pixels and can yield NG. E2 does **not** require the host to manually erase the entire initial pattern before the firmware's own final redraw. This corrects an earlier assumption in the project notes.

## Repeat the result safely

`usage.md` explains the simple GUI boot/keys. Once original E2 is visible, run `scripts/drive_e2_original_ok.py`. It:

- Checks the original PPM geometry and black-target pixel first;
- writes only electrical BU21029/keyboard contact files;
- checks one genuine touch-driven black-to-white pixel change;
- sends the genuine physical `0x94` exit;
- reports success **only when it sees the unchanged A7 `0x6005CD08` in an opt-in translated-block log** (`EXESX_TRACE_E2_A7=1`).

CI includes fabricated-frame and fabricated-execution-log positive and negative controls. It cannot run the owner's proprietary image.

## Distinct limitations

The separate A7 factory-result array at `0x62344EF0` was **inactive** (`0x62344EEC=0`) in this direct E2 session. Empty result-array slots do not mean NG and cannot replace the executed original verdict branch.

The original TOUCH PANEL PRESET accepts real touch points (observed in this session family), but complete **INPUT MENU calibration subtests** and physical-device accuracy are not all certified by this E2 pass. The touch-coordinate transform was measured only for this original ROM and model.
