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

Install/build the native EXeSX QEMU integration first according to the project README. QEMU must be built with the opt-in USDHC1 eMMC and LPIT1 IRQ changes. The default output directory is `private/osup-run/`, ignored by Git; the script keeps the original bytes, ELF, synthetic eMMC, QEMU console log, trace and any LCD metadata local. `-drive ... snapshot=on` protects the staged image against guest updates.

**Important limitations:**

- This is **not** an authentic full installed flash dump. The F component's declared extent exceeds the bytes present in OSUP; source-absent sectors are sparse/zero.
- Boot1 beyond the two PVOS metadata sectors is unknown and blank, so some subsequent loader behavior may differ from a device.
- Until the external panel is properly modeled, the runner adds a clearly named **4KiB diagnostic RAM sink at `0xb0000000`** to a generated *private* memory profile. This only prevents an MMIO abort. It does **not** implement the panel, panel read responses or its PTF13 TE sync output; it must not be treated as hardware fidelity.
- The emulator uses current experimental MU/M4, GPIOB, I2C and LPIT options used in the previously verified research run; it does **not** invent an OS entry or force any firmware flag.
- Optional `--lcd-trace` records proprietary command/pixel write values to a **private trace**. Never upload that raw trace. The decoder emits sampled command and pixel metadata rather than a rendered LCD or complete frame.

In the original owner-held firmware comparison on the earlier pinned emulator version, the already established post-LPIT boot boundary was a **GPIOF13 high-then-low wait** at `0x601b4144..0x601b4158`. The actual original panel init sends TEON (`0x35`) and scanline setup (`0x44`), making a TE pin connection a strong but not physically proven hypothesis. The temporary RAM sink does **not** generate TE pulses, so the one-command experiment can stop there. Next: model LCD command state and its real TE pin timing, then verify original BIOS proceeds to callback `0x60400000`.

**Testing:** `tests/test_run_osup.py` creates a fabricated OSUP fixture and verifies sparse disk partition offsets, source-only B/A/F sector headers, private manifest and valid ELF signature. No Casio byte is included in CI fixtures. The LCD decoder and plugin also have synthetic/opt-in controls. 
