# Windows live LCD and floating EXeSX keyboard (original factory mode)

Download the latest **successful** Windows Actions native QEMU ZIP from main, extract the inner ZIP, and install Python 3.10+ with Tkinter (included in the standard official python.org Windows installer). Do not install MSYS2 or pygame.

From PowerShell **in the extracted QEMU directory**:

~~~powershell
py -3 .\scripts\factory_control_panel.py "C:\Casio\OSUP.BIN" `
  --qemu ".\qemu-system-arm.exe" `
  --profile ".\profiles\imx7ulp-early-boot.ini" `
  --output-dir ".\private\floating-keyboard"
~~~

On first run, OSUP is validated and locally assembled into its owner-private BIOS/OS ELF and synthetic sparse ~16 GB eMMC; this can take considerable storage. Subsequent launches can reuse them:

~~~powershell
py -3 .\scripts\factory_control_panel.py `
  --elf ".\private\floating-keyboard\private-firmware\a7-bios-os.elf" `
  --emmc ".\private\floating-keyboard\private-firmware\source-derived-synthetic-emmc.raw" `
  --qemu ".\qemu-system-arm.exe" --fps 2
~~~

The physical keyboard is reconstructed from the **49 nonzero entries** at original M4 ROM address 0x1FFD0E14. Letter buttons send their real ASCII keycodes through M4 GPIO row/column contact closure. Known special keys are shown by their firmware codes (e.g., 0x91 is confirmed DOWN); unknown human-facing legends are **not guessed** based on a keyboard photo. Clicking/holding a button holds its contact; releasing it releases it. Typing letters on your PC keyboard does the same. The window can remain floating/always-on-top.

Buttons:

- **POWER / NORMAL**: fresh ordinary QEMU boot.
- **Version popup [9C+90]**: real simultaneous boot chord until the original firmware sets CA05. It releases the chord after the designated host interval and leaves QEMU running.
- **AUTO TEST MENU [93 93 94]**: fresh boot with the 9C+90 chord; wait for genuine A7 original 0x600108A8 event wait, send separate real M4 0x93,0x93,0x94 physical contacts (60ms holds/25ms gaps), then **keep QEMU running** so the user may navigate.
- **Manual 93→93→94**: repeat the later three-key sequence, but **only if the real A7 event wait executed**. Does not forge an A7 event.
- **Safe DOWN check**: sends one real DOWN (0x91) press/release **only after original menu painter 0x60057668 has actually executed**; otherwise displays a BLOCKED message rather than pressing unknown menu choices.
- **Save screenshot**: export the latest actual RGB565 frame as PNG, locally.
- **Stop**: stop only the QEMU subprocess, not the GUI.

### Live LCD export / Windows timer regression

The former EXESX_LCD_CAPTURE_REQUEST_FILE virtual/realtime timer repeatedly failed the native Windows ARM screenshot probe: request remained unread despite QEMU running. This is not a guest exception or a Casio OS crash. The new **EXESX_LCD_FRAMEBUFFER_EXPORT=1** exposes the existing experimental LCD's actual RGB565 framebuffer at the **read-only diagnostic MMIO address 0xB1000000**, size **829,440 bytes**. QMP's synchronous host-side `pmemsave` saves the framebuffer without depending on Windows QEMU timer delivery, SDL, or a synthesised LCD redraw. QEMU does not modify original guest CPU/RAM/IPC or synthesize pixels. A worker thread runs QEMU, sends the real key contacts, samples actual executed ARM PCs, and copies this RGB565 export to an on-disk memory-mapped frame buffer. The Tk GUI runs on the main thread (Tk is *not* called from a worker). Conversion is raw RGB565 → RGB888 PPM; default live rate **2 fps**, adjusted with `--fps` (consider 1–4 fps for guest-performance sensitivity). This is a **file-backed mmap snapshot** not zero-copy OS shared memory, and not a claim of native GPU refresh rate.

The separate `scripts/auto_driver.py` performs a two-pass headless cold boot and captures exactly two PPM/PNG files (`version-dialog.*`, `factory-test-menu.*`) with the same QMP export. Its summary differentiates successfully entered menu code, 0x400B service completion, menu painting, screen changes, and a real QEMU crash. `--attempts` retries fresh, unmodified boots if original firmware timing is unstable.

### Menu-testing limits

Original firmware reached the **factory menu entry PC 0x6003A878** with the real chord and keys, but its synchronous service **0x400B(2)** remained pending at original M4/A7 IPC, and **0x60057668** menu painter did not run in the tested window. Previous two real screenshots showed the same *version popup*, **not** a visible TEST MENU. Until 0x400B completes and the menu is actually painted, there is no credible assertion that menu choices, SD diagnostics, or further factory tests passed. The GUI intentionally allows non-destructive manual exploration but never auto-selects SD FORMAT/WRITE. eMMC and optional disposable SD images always use `snapshot=on`.

## Portable regression tests

~~~powershell
py -3 -m unittest discover -s tests -p test_factory_auto_driver.py -v
py -3 -m unittest discover -s tests -p test_factory_control_panel.py -v
py -3 .\scripts\probe_lcd_qmp.py --qemu ".\qemu-system-arm.exe" --profile ".\profiles\imx7ulp-early-boot.ini"
~~~

The last probe executes a synthetic *real ARM program* writing red/green/blue/red via GPIOA16 and LCD RGB565 MMIO. It then obtains two QMP-exported raw frames and validates each byte, without user OSUP. These run automatically on both Linux and Windows CI.

Do not publish your extracted original ELF, sparse eMMC, SD contents, original guest execution logs or screenshots to the public repository.


## Diagnosis: floating GUI says "Booting attempt" with no visible QEMU window

**EXeSX launches QEMU with `-display none` by design.** It will *never* open a separate QEMU desktop window. The Tk floating panel is the only screen. The initial special-mode boot also deliberately defers expensive RGB565 frame reads until original A7 code has reached its version-dialog event wait, to avoid perturbing the three-key timing.

A headless test from the **same downloaded build** runs the **exact same QEMU-spawning worker, key-contact harness and QMP handshake** without Tk:

~~~powershell
py -3 .\scripts\factory_control_panel.py "C:\Casio\OSUP.BIN" `
  --qemu ".\qemu-system-arm.exe" `
  --headless-check --check-mode menu --check-seconds 35 --retries 1
~~~

Expected first successful stage is a line saying **QEMU PID #### running** and then **original A7/M4 firmware started**. The new control panel also displays a periodic three-second process/boot heartbeat and its PID. The test reports separately: process spawned, QMP monitor ready, original A7 dialog reached, original menu reached, and frames captured. A successful QEMU launch is **not** a claim that the original BIOS reached TEST MENU. The emulator can run headlessly with no guest dialog due to emulation startup timing/resource limitations.

If launch fails, the UI reports the underlying `OSError` (wrong EXE path, missing MSYS2 DLL from an incomplete extracted Windows artifact, or antivirus quarantine). Inspect **`private\floating-keyboard\gui-console-private.log`** and **`gui-execution-private.log`**, but do not upload proprietary guest traces publicly.

The first OSUP-derived ~15.64 GB synthetic eMMC extraction can be expensive on Windows: media preparation now reports its stage and the complete validated ELF/eMMC/manifest is reused on restarts and retry boots. A different OSUP hash invalidates reuse. For an isolated host-launch diagnosis with prebuilt private media, provide `--elf` and `--emmc` instead of the original update file. This avoids any media regeneration.

The latest native Linux headless **real OSUP + disposable SD** control spawned and kept QEMU alive for 30 seconds but did not reach the original A7 version-event-wait checkpoint within that bounded window. This is **not a QEMU spawn failure**; the firmware path is not deterministic across host runs. Menu service 0x400B(2) remains separately blocked after authenticated factory menu entry in a successful attempt.
