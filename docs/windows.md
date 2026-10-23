# Native Windows x64 build

The `Build and smoke-test EXeSX QEMU for Windows` Actions workflow adds a
Windows target alongside the Linux workflow. It builds pinned QEMU 10.1.0
with MSYS2 MINGW64, bundles recursive MinGW DLL imports and licenses, and
runs CP15, peripheral, DMA1, LPIT1 IRQ and LCD probes using Windows Python
with MSYS2 removed from PATH. Download its ZIP artifact and SHA256SUMS-windows.

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
