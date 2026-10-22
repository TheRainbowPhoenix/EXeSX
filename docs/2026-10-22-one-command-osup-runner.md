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


## Real original-firmware result after experimental LCD model

A native QEMU 10.1.0 artifact from passing [CI 39800183413](https://github.com/TheRainbowPhoenix/EXeSX/actions/runs/39800183413) was run locally using the **unchanged, checksum-verified original user-supplied OSUP**, the **two-section A7-only original BIOS/OS ELF**, source-derived private synthetic eMMC, LPIT1 IRQ and the new opt-in 864×480 LCD model. A 22-second bounded `-d in_asm,guest_errors,unimp` run yielded:

- The prior `0x601b4144..0x601b4158` **GPIOF13 high→low sync loop was traversed**: actual translated BIOS blocks `0x601b4148`, `0x601b4150`, and importantly `0x601b415c` occurred. This is genuine forward progress compared with the prior no-TE-signal run, though TB-translation is a coverage signal rather than a per-instruction execution counter.
- The BIOS then executed display-bus sequences and requested eMMC reads. The QEMU SD command log contained **69 real `sdhci_send_command` calls**. The late sequence included CMD18 and CMD17 over high user LBAs including `0x008BE46E`, `0x008BE4D7`, `0x008A3705`; these are **far beyond the OSUP-provided B/A/F source bytes** and contain zero/unknown installed-device data in the synthetic medium. Their exact logical filesystem role is **not established**; do not label them a validated resource or error based solely on a read command.
- QEMU wrote a real **864×480 P6 PPM** at `EXESX_LCD_SCREENSHOT`. It was converted privately to PNG for viewing. Pixel histogram: all **414,720 RGB888 pixels were `(255,255,255)`**, representing original guest-generated white RGB565 screen-clear data; **no text/menu glyphs** yet.
- No original OS instruction-translation block in the extracted OS region beginning `0x60400000`, no OS-entry `0x605E3AD0`, and no `0x60049C04` callback BLX were found in the bounded trace. A7 was active in BIOS routines, not a demonstrated new permanent hardware poll.
- No new MMIO abort was observed in the bounded log. The display device correctly eliminates the old `0xB0000000` RAM-only abort by decoding 16-bit commands; vendor-specific initialization remains opaque and the 60Hz/1ms TE waveform is an experimental assumption, **not proven hardware accuracy**.
- The native [CI 39800707284](https://github.com/TheRainbowPhoenix/EXeSX/actions/runs/39800707284) passed **37 steps**, including the new **synthetic ARM two-color screenshot regression**, with no private firmware or pixels in CI.

**Next gap:** the BIOS's post-TE storage/resource startup requires user-area sectors the update package does **not** provide (including high LBAs noted above). It could also await a different device, interrupt or OS callback condition. Compare a real installed eMMC layout or trace higher-level return-value decisions before claiming missing sector data is the *causal* boot blocker. Extend LCD model only on evidence of newly issued unhandled commands or a second display wait; avoid forced OS entry and forged resource data.
