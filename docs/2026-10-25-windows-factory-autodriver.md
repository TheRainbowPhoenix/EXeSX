# Windows factory auto-driver: authentic key entry and LCD screenshots

The original firmware checks simultaneous 0x9C + 0x90 **at power-on**; M4 publishes 0xEEEEEEEE and A7 selects boot mode 0xCA05. Later, after original A7 event wait 0x600108A8, drive three distinct physical contacts 0x93, 0x93, 0x94. Successful original TEST MENU entry executes 0x6003A878. The program never injects RAM/IPC values, synthetic keyboard events or a forced PC.

## Fresh Windows build

Download a successful Windows native QEMU GitHub Actions artifact containing the new scripts/auto_driver.py and on-demand LCD support. Extract the inner exesx-qemu-windows-x86_64.zip completely. Install Python 3.10+; MSYS2 is not needed at runtime.

From PowerShell inside the extracted directory:

~~~powershell
py -3 .\scripts\auto_driver.py "C:\Casio\OSUP.BIN" `
  --qemu ".\qemu-system-arm.exe" `
  --profile ".\profiles\imx7ulp-early-boot.ini" `
  --output-dir ".\private\factory-auto" --attempts 3 --seconds 55
~~~

With the original OSUP argument, the driver calls the existing local run_osup.prepare helper to checksum-validate the update and build private ELF and source-derived synthetic eMMC. That approximately 16GB raw eMMC image can consume substantial disk space on Windows. This is not a complete real eMMC dump; only sectors derivable from the supplied OSUP are populated.

For later runs, skip recreating the media:

~~~powershell
py -3 .\scripts\auto_driver.py `
  --elf ".\private\factory-auto\private-firmware\a7-bios-os.elf" `
  --emmc ".\private\factory-auto\private-firmware\source-derived-synthetic-emmc.raw" `
  --qemu ".\qemu-system-arm.exe" `
  --profile ".\profiles\imx7ulp-early-boot.ini" `
  --output-dir ".\private\factory-auto" --attempts 3 --seconds 55
~~~

The optional --sd path must be an existing disposable raw SD image at least 2GiB in size. Both eMMC and SD drives always use QEMU snapshot=on. The driver performs no destructive SD FORMAT/WRITE diagnostics.

## Exact two-pass capture

* Popup pass: fresh cold boot; hold 0x9C+0x90, release after original handshake, observe actual A7 version dialog, request an on-demand LCD capture before sending **any** menu keys.
* Menu pass: another fresh cold boot; repeat early chord; wait for original 0x600108A8 before making 60ms 0x93, 0x93, 0x94 contacts separated by 25ms gaps. After original factory menu PC 0x6003A878 and a short service/paint window, capture the second framebuffer.

The script saves the PPM and standard-library-generated PNG files as **version-dialog.ppm/png** and **factory-test-menu.ppm/png** in private/factory-auto. They are actual emulator pixels; if they are solid black, that is a valid capture but **not** proof of visible popup/menu text. Capture is requested by the host using EXESX_LCD_CAPTURE_REQUEST_FILE and a guest-virtual-time timer, avoiding continuous screenshot file writes that perturb key timing.

The private summary-private.json contains actual original A7 milestone hits, host contact times, capture SHA256 and black/white/other pixel counts, retry attempts and conditions. Unsuccessful runs and incomplete screenshots are explicitly reported; the program exits nonzero when requested proof is missing. The popup and menu folders also contain original guest execution and console logs. Never publish proprietary ROM, extracted ELF, synthetic media or private traces/screenshots.

## Safe automated checks

The driver checks real original version dialog (0x60010868), key checks (0x60010910 and 0x60010928), native menu entry (0x6003A878), service 0x400B entry (0x60006240) and **completion** (0x60006268), and menu painter execution (0x60057668). A service that never returns is an *uncompleted wait*, not a demonstrated crash. Unexpected QEMU exit is reported separately. The --guest-errors option adds potentially large private MMIO diagnostics.

Before using private OSUP, validate host code and LCD with firmware-free tests:

~~~powershell
py -3 -m unittest discover -s tests -p test_factory_auto_driver.py -v
py -3 .\scripts\probe_lcd_on_demand.py --qemu ".\qemu-system-arm.exe" --profile ".\profiles\imx7ulp-early-boot.ini"
~~~

Both tests are now part of Windows CI; QEMU writes known pixel colors under actual synthetic ARM execution. Current factory SD test-items are **not** automatically selected; menu painter/IPC completion must be confirmed first, and destructive items require an explicit disposable-card plan.
