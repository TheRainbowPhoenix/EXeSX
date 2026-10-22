# One-command private DY357 OSUP boot experiment

`scripts/run_osup.py` accepts a privately held Casio DY3xx update file (any filename, e.g. `OSUPD.bin` or `OSUP.BIN`). It validates the original update checksum, IPL/PVOS/component checksums and pinned ARM updater opcodes; builds an A7-only ELF with the original BIOS and OS entry addresses; creates a **sparse, expressly synthetic** emulated eMMC with authentic PVOS sectors at boot1 LBA0/32 and all available update B/A/F component data at original-reader-verified user LBAs 0, 0x12AD and 0x56C2; then runs pinned QEMU for a bounded number of seconds.

```bash
python3 scripts/run_osup.py OSUPD.bin \
  --qemu build/qemu-system-arm \
  --profile profiles/imx7ulp-early-boot.ini \
  --seconds 20

# Optional value-aware LCD MMIO capture, private trace only:
python3 scripts/run_osup.py OSUPD.bin \
  --qemu build/qemu-system-arm \
  --plugin build/exesx-memtrace.so --lcd-trace \
  --seconds 20

# To inspect the validated input/layout without starting QEMU:
python3 scripts/run_osup.py OSUPD.bin --prepare-only
```

The command automatically runs `scripts/build.sh` to fetch and build the pinned QEMU v10.1.0 with EXeSX patches if `build/qemu-system-arm` is absent (the first run needs network access and a working C/QEMU build toolchain). If `--lcd-trace` is requested it also builds the opt-in `exesx-memtrace.so` plugin automatically. QEMU is run with the opt-in USDHC1 eMMC and LPIT1 IRQ changes. The default output directory is `private/osup-run/`, ignored by Git; the script keeps the original bytes, ELF, synthetic eMMC, QEMU console log, trace and any LCD metadata local. `-drive ... snapshot=on` protects the staged image against guest updates.

**Important limitations:**

- This is **not** an authentic full installed flash dump. The F component's declared extent exceeds the bytes present in OSUP; source-absent sectors are sparse/zero.
- Boot1 beyond the two PVOS metadata sectors is unknown and blank, so some subsequent loader behavior may differ from a device.
- Until the external panel is properly modeled, the runner adds a clearly named **4KiB diagnostic RAM sink at `0xb0000000`** to a generated *private* memory profile. The latest opt-in implementation uses a **stateful 16-bit DCS/RGB565 LCD command and GRAM model** instead of that RAM sink. It recognizes 0x2A/0x2B window selection, 0x2C pixel writes, 0x3A RGB565 and 0x35/0x34 TE enable/disable, using GPIOA16 command/data phase. Unsupported vendor-specific commands remain inert; reads are not emulated. It supplies an *experimental* 60Hz/1ms-wide TE pulse to GPIOF13 while TE is enabled; the exact panel timing/wiring is not yet authenticated. The private screenshot `private/osup-run/lcd-screenshot.ppm` is periodically updated from an 864x480 backing buffer (800px init width and a later observed 864px window). This image can be opened in standard image applications; it only depicts pixels actually written by the guest.
- The emulator uses current experimental MU/M4, GPIOB, I2C and LPIT options used in the previously verified research run; it does **not** invent an OS entry or force any firmware flag.
- Optional `--lcd-trace` records proprietary command/pixel write values to a **private trace**. Never upload that raw trace. The decoder emits sampled command and pixel metadata rather than a rendered LCD or complete frame.

In the original owner-held firmware comparison on the earlier pinned emulator version, the already established post-LPIT boot boundary was a **GPIOF13 high-then-low wait** at `0x601b4144..0x601b4158`. The actual original panel init sends TEON (`0x35`) and scanline setup (`0x44`), making a TE pin connection a strong but not physically proven hypothesis. The new opt-in device **does** generate the hypothesized TE pulse, allowing an original firmware *experimental differential*. That does not make its electrical timing or panel vendor authentic. Next: model LCD command state and its real TE pin timing, then verify original BIOS proceeds to callback `0x60400000`.

**Testing:** `tests/test_run_osup.py` creates a fabricated OSUP fixture and verifies sparse disk partition offsets, source-only B/A/F sector headers, private manifest and valid ELF signature. No Casio byte is included in CI fixtures. The LCD decoder and plugin also have synthetic/opt-in controls. 

## Latest unchanged-firmware local bounded comparison

The original owner-held OSUP was locally re-prepared with checksum-verified A7 BIOS and OS, plus the source-authentic B/A/F installed-header medium and the prior diagnostic display RAM mapping. With the known LPIT1 interrupt and earlier eMMC improvements enabled, a 20-second real-time QEMU run stopped CPU0 at **R15=0x601cbcf8** (BIOS WFI/ISB idle), `0x622e6fc4=0x0000003f` (valid component status), `0x6232da18=0x60400000` (OS entry callback still recorded) and `GPIOF.PDIR=0x00040010` (PTF13 remains low). No observed OS trampoline execution. A prior instruction breakpoint positively saw the **GPIOF13 high→low poll** after panel initialization. The bounded 20-second CPU idle snapshot is **not** evidence of exclusive residence in the GPIO poll, and timer/second-core scheduling may affect where a pause lands. The synthesized `0xb0000000` RAM sink does not emit TE pulses, so it cannot prove LCD-origin boot progress. This is the next genuine device-model gap, *not a reason to force the OS PC or overwrite callback flags*.

### LCD screenshot and validation

An opt-in LCD device at `0xB0000000` follows observed GPIOA16 D/C and DCS commands. Periodic screenshots are written as **binary PPM (P6)** at `private/osup-run/lcd-screenshot.ppm`; RGB565 is decoded to RGB888. The model deliberately does not invent actual Casio menu pixels or an LCD-ID reply. The QEMU virtual frame period (60Hz, 1ms TE active) is provisional, not established by firmware. `scripts/probe_lcd_screenshot.py` uses fabricated ARM instructions to write exactly two RGB565 pixels (red, green), then verifies the generated PPM. No proprietary bytes are in the test.
