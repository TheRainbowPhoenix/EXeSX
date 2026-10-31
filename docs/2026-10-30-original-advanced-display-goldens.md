# Genuine original-ROM DY357 advanced DISPLAY E2E

All four tests below were executed locally from the genuine unchanged private
OSUP, native Linux QEMU build `7b27d737`, physical M4 contacts,
`-accel tcg,thread=single`, source-derived eMMC and disposable SD
(`snapshot=on`). The original A7 passed its version dialog and `0x400B`
IPC, then the original LCD painted **TEST MENU → MANUAL CHECK → DISPLAY
MENU → DISPLAY TEST MENU**, the requested row was visibly selected, and
real physical ENTER reached the full-screen pattern.

Read-only QMP screenshots were captured twice and exact 864×480 P6 PPM
pixel SHA-256 was verified. The same pattern rendered continuously without
host pixel synthesis, guest PC/RAM changes, or fabricated A7 keyboard events.

| DISPLAY TEST row | Original name | 864×480 PPM SHA-256 | Original pixel counts | Local |
|---:|---|---|---|---|
| 4 | CHIDORI | `e7b16ad2c9f0f78bd3b6d2af65e1e667fea228f4fc2b2748bdc9cfc3af55eaf3` | 207360 black, 207360 white | PASS |
| 5 | R-CHIDORI | `3d1395bbb76379ca9f706c7ffe151aa628e8263a14690b5f735fd8b55b2bf91d` | 207360 black, 207360 white | PASS |
| 6 | FRAME | `6a73559f416f12f85796679dcb2c58176b9813a1194c3eae554a5e5555fdca51` | 412036 black, 2684 white | PASS |
| 7 | W-B GRADATION | `78f1a4a3ba9fa1de9b2440084acd70b926ab5a60792b898dab07664aa4dfddda` | 32 RGB565-derived gray levels | PASS |

**CI:** original ARM PATTERN MANUAL and AUTO plus nested CHIDORI and FRAME
already passed together in [Actions run 41085620592](https://github.com/TheRainbowPhoenix/EXeSX/actions/runs/41085620592).
R-CHIDORI and W-B GRADATION were added in the present commit and require
a new full green CI run to confirm. See
`scripts/ci_e2e_display_advanced.py` and `.github/workflows/qemu.yml`.
All screenshots and private guest logs remain out of Git source and are
provided only as owner-local proof or short-retention CI framebuffer artifacts.

**Not yet validated:** DISPLAY TEST 8 COLORS AUTO, COLOR BAR 2,
MENU 1–3, PATTERN AUTO, SETTINGS controls, and original panel optical
properties. These cannot be reported passing simply because their names
appear in the menu. Return from a static pattern may cascade through
several menus when the original physical key is held; independent clean
boots avoid confusing return/navigation with framebuffer correctness.
