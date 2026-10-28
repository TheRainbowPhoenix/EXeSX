# Single-thread TCG: genuine physical-key TEST MENU and MANUAL submenu (28 Oct 2026)

**Result (local owner-ROM evidence):** the original unchanged DY357 OS reached its genuine 16-item factory TEST MENU and the nested 14-item MANUAL MENU with original A7/M4 firmware, QEMU `-accel tcg,thread=single`, and **physical M4 matrix contacts only**. A genuine highlighted row moved in both menus. No CPU PC/RAM/RTOS/key-event/mailbox or LCD pixel was injected.

## Exact setup and positive execution

* Firmware: owner's private OSUP.BIN SHA256 `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`.
* Emulator: Linux GitHub Actions native QEMU at experiment SHA `3ed4d12297e514125bb41b8426cdac4482dc7c45`, built from the Oct 28 experiment branch. The local diagnostic used its included factory GUI worker and profile backfill.
* Storage: original owner-derived sparse synthetic eMMC and disposable 2GiB SD, both `snapshot=on`. Analog samples `EXESX_ADC0_SAMPLE_RAW=0x7000` / ADC1 same are *diagnostic values*, not physical battery measurements.
* Startup: hold simultaneous **0x9C+0x90** electrical contacts for 4.0 host seconds; at the actual original `0x600108A8` version-dialog event wait send **0x93,0x93,0x94** as separate 90ms down/60ms up contacts.
* Executed original A7 PCs: `0x60010930` (third key accepted), `0x6003A878` (TEST MENU), `0x60006240` (0x400B request), `0x60006268` (service returned), `0x60057668` (genuine painter).

After the TEST MENU was **fully painted and stable**, the host pressed **0x91** using the private contact file and kept the contact closed until the real LCD generated a new inverse-highlighted bar. Another genuine physical **0x90** UP moved selection to row 1, **MANUAL CHECK**, followed by physical **0x94** ENTER. The A7 actually painted the 14-item **MANUAL MENU**; a further **0x91** produced an inverse bar selecting its row 1, **DISPLAY MENU**. All images were exported read-only from QMP's real emulated LCD; screenshot/trace/raw guest contents remain owner-private.

## Root cause found: host contact duration was shorter than real M4 debounce

The earlier GUI/headless safe DOWN action used a fixed 80ms (or diagnostic 300ms) host pulse. After a post-menu DOWN pulse, read-only SRAM at original `0x1FFEA320` showed M4 keyboard debounce **state 2**, with original row/column `0x0607` (key `0x91`) at a **0.508s** host sample. Meanwhile original 20-byte queue `0x1FFEA34C` was empty. The host had already released its 300ms contact, so no stable 0x91 type2/subtype1 event completed before release. No change on the LCD was expected.

With a **3.0 second held physical 0x91**, the original LCD hash changed from `cca51d6a34710121af59b4654e8c79abc32f2ccde837e1157290704cddafae3` to `00de6144c82a3cca31644cf774f77f51abb5e5e223814b103e722746de9372c2`, visibly highlighting TEST MENU row 3. The extended hold permits auto-repeat, so exact row cannot be inferred from key-count alone. In the successful guarded replay, the host observed pixels and **released the physical contact immediately after a highlighted row appeared or changed**, then verified the next intended row before ENTER.

A separate screenshot-check bug required a solid black header at LCD y=10. Once any row became selected, the genuine original menu **inverted the header to white**, so the old detector discarded valid post-navigation frames. The corrected test identifies the full sixteen-row TEST MENU from its persistent original row-13 and row-16 text, and detects the actual full-width selection band.

## Source changes and guardrails

* `scripts/headless_factory_menu_checks.py`: wait for two identical native menu frames, physically hold DOWN until an original highlighted row changes, release immediately; bounded timeout/controlled retries, no ENTER.
* `scripts/factory_control_panel.py`: floating GUI's **Safe DOWN** now holds the physical electrical contact until real LCD highlights change (or 4.5s timeout), instead of a short blind pulse; ordinary mouse hold/release remains available for navigating submenus.
* `tests/test_headless_factory_menu_lcd.py` and `tests/test_factory_control_panel.py`: fabricated frames test actual inverse bands and header inversion without owner firmware.
* The code never blindly runs destructive RESET, OS UPDATE, FLASH UTILITIES, SD FORMAT/WRITE, or SERVICE. ENTER was applied only after confirming the highlighted original row 1 MANUAL CHECK, which is safe. Menu/screen success is distinct from completing any factory hardware test.

**Scope:** authentic menu navigation in single-threaded TCG is established, including the MANUAL submenu. This does not yet prove the original E2 factory touch coverage verdict or every nested menu. The proprietary OS image/decompilations, original guest RAM/logs and LCD screenshot bytes were **not committed to this public repository**. GitHub CI checks the public emulator and fabricated test fixtures; the original-OS menu validation is local.
