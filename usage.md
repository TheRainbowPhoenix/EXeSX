# How to use EXeSX

This is a test emulator. Use your own `OSUP.BIN` file. Keep this file on your computer. Do not upload it to GitHub.

## 1. Get the files

1. Download this repository. Switch to branch `experiment/dy357-m4-inputs-0804-20261023`.
2. Open **Actions** on GitHub.
3. Open a **successful** Linux or Windows QEMU build.
4. Download the native QEMU artifact for your computer.
5. Unzip the artifact. If it contains a `.tar.gz` or another ZIP, unpack that too.
6. Find `qemu-system-arm` (Linux) or `qemu-system-arm.exe` (Windows).
7. Install Python 3.10 or newer. The floating keyboard also needs Tkinter.

## 2. Start the screen and keyboard

Open a terminal in the repository folder. Change the QEMU path to where you unpacked it.

**Linux:**

```sh
python3 scripts/factory_control_panel.py /path/to/OSUP.BIN \
  --qemu /path/to/qemu-system-arm \
  --tcg-thread single --release-at 4
```

**Windows (PowerShell):**

```powershell
py -3 scripts/factory_control_panel.py "C:\Casio\OSUP.BIN" --qemu "C:\EXeSX\qemu-system-arm.exe" --tcg-thread single --release-at 4
```

Wait for the window. Click **AUTO TEST MENU [93 93 94]**.

The emulator holds `0x9C` and `0x90` at boot. It then sends `0x93`, `0x93`, and `0x94` at the version popup. If it misses the popup, the driver can retry a fresh boot.

## 3. Use the keys

- Click and **hold** a key on the floating keyboard. Release the mouse to release the key.
- **DOWN** is `0x91`. **UP** is `0x90`. **ENTER** is `0x94`.
- A short click can be missed. Hold UP or DOWN until you see the black selection bar move. Then release.
- Wait for the screen to settle before you press another key.
- Click **Safe DOWN check** to test DOWN without opening a menu item.
- Use ENTER only when you can see the right menu row selected.
- To open **MANUAL MENU**, select **MANUAL CHECK** in TEST MENU and press ENTER.
- To open another safe submenu, move to its row and press ENTER.
- Click **Save screenshot** to save the current LCD. Click **Stop** to stop.

Do not select **RESET**, **OS UPDATE**, **FLASH UTILITIES**, or **SD FORMAT/WRITE** by accident.

## 4. Test the touchscreen

The emulator can read a physical touch input file, but the original factory touchscreen **OK** result is not guaranteed. Do not treat a visible touch screen as a passed test.

The factory menus include **TOUCH PANEL PRESET** and **E2 PATTERN CHECK**. MANUAL CHECK also contains touch checks under INPUT MENU. Only run them when the correct row is highlighted. Touch-controller testing needs the BU21029 model and the `EXESX_BU21029_TOUCH_FILE` setting; see `docs/2026-10-28-corrected-lpit0-irq33-genuine-a7-touch-delivery.md` and `scripts/drive_e2_cross.py`.

## 5. If it does not work

- Use a **successful CI build** from this experiment branch.
- Keep `--tcg-thread single` and `--release-at 4`.
- Wait for the full TEST MENU to appear before sending navigation keys.
- Hold keys longer if the selection does not move. Wait for the key release between presses.
- Try **AUTO TEST MENU** again if a cold boot misses the version popup.
- Keep your `OSUP.BIN`, eMMC, SD images, screenshots, and guest logs private.

This is still experimental. The original OS and tests may not always start on the first attempt.
