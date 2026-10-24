# Native Windows x64 build

The `Build and smoke-test EXeSX QEMU for Windows` Actions workflow adds a
Windows target alongside the Linux workflow. It builds pinned QEMU 10.1.0
with MSYS2 MINGW64, bundles recursive MinGW DLL imports and licenses, and
runs CP15, peripheral, DMA1, LPIT1 IRQ and LCD probes using Windows Python
with MSYS2 removed from PATH. Download its ZIP artifact and SHA256SUMS-windows.

Windows uses a separate 650 MB ccache with compiler-content checks. The workflow
restores prior entries and explicitly saves the cache with `actions/cache/save@v4`
immediately after compilation, before packaging/runtime probes. A failed runtime
probe therefore retains compiled objects for the next run, like the Linux job.

Extract the whole ZIP before running `qemu-system-arm.exe`. No MSYS2 installation
is needed at runtime. This is a headless research build: no GTK/SDL window or
TCG memory-tracer plugin. The HMP monitor, GDB stub, and experimental LCD PPM
screenshots remain available. Python 3.10+ is needed for the helper scripts.

From PowerShell in the extracted directory, using your own private OSUP:

```powershell
python scripts/run_osup.py C:/path/to/XD-SX9850-OSUP.BIN --qemu ./qemu-system-arm.exe --seconds 15
```

This does not establish a successful Casio OS boot. Firmware and private traces
are excluded from the distribution. Experimental device settings and synthetic
eMMC media retain the same limitations documented by the Linux runner.

To build locally, install the packages listed in `.github/workflows/qemu-windows.yml`
in MSYS2 MINGW64, then run `bash scripts/build_windows.sh` from the repository.
Upstream build guidance: https://www.qemu.org/docs/master/devel/build-environment.html


## Windows ARM probe fix (October 2026)

The Windows QEMU monitor sometimes echoed piped `xp /48wx ...` commands
character by character rather than executing them. This caused the Python
`hmp_memory.memory_words` assertion `Missing HMP word at 0x62002000`,
although the earlier CP15 probe passed. The Windows peripheral, DMA1 and
LPIT1 probes now use **QMP over a temporary localhost TCP port** to issue
`stop` and `human-monitor-command` and receive an atomic `xp` response.
Linux continues using its previous HMP stdio path. Nothing about the
emulated peripheral register values or ARM probe expectations changed.

### Run from an extracted Windows CI artifact

Download the `exesx-qemu-windows-x86_64-<commit>` artifact from a
**successful** [Windows CI run](../.github/workflows/qemu-windows.yml).
Extract the inner `exesx-qemu-windows-x86_64.zip` fully to a folder,
then open **PowerShell in the folder containing `qemu-system-arm.exe`**:

```powershell
# Verify the bundled executable and Python availability:
.\qemu-system-arm.exe --version
py -3 --version

# Provide your own genuine Casio update file locally:
py -3 .\scripts\run_osup.py "C:\Casio\OSUPD.BIN" --qemu ".\qemu-system-arm.exe" --seconds 30

# Screenshots and non-sensitive analysis metadata:
# .\private\osup-run\lcd-screenshot.ppm
# .\private\osup-run\lcd-summary.json
# .\private\osup-run\manifest.json

# Optional read-only A7/M4 IPC checkpoint probe:
py -3 .\scripts\run_osup.py "C:\Casio\OSUPD.BIN" --qemu ".\qemu-system-arm.exe" --seconds 30 --ipc1808-probe
```

The script accepts either `OSUPD.BIN` or `OSUP.BIN` filename. There is
**no need to rename** your file or upload it anywhere. `--lcd-trace`
requires the QEMU memory-plugin build, which this headless Windows
distribution **does not include**; basic LCD screenshots work without it.
Screenshots are **PPM (P6)** and can be opened in GIMP, ImageMagick or
other image viewers supporting PPM. The latest framebuffer may contain
only a white fill, and does not prove the Casio OS has booted.

All disk media and ROM output is locally synthesized from your update,
and unknown installed-device sectors remain absent. Never treat the
generated `source-derived-synthetic-emmc.raw` as a full device dump.
