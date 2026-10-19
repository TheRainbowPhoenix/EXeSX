# XD-SX9850 BIOS accesses at 0x61080000 and 0x67100000

Evidence basis: user-supplied OSUP.BIN extracted locally. All numbers in this note are extracted facts or explicitly marked hypotheses. **No proprietary firmware data is committed.**

## Actual faulting operation, not a status poll
The Thumb function at 0x60254700 processes an array of (destination,size) zero-initialization pairs. Key instructions:

```asm
60254700: ldr  r1, [r0], #4   ; read destination from table
6025470e: subs r2, r2, #4   ; remaining byte length
60254710: movs r3, #0
60254714: str  r3, [r1], #4 ; WRITE 0, then destination += 4
60254718: bhs  0x6025470e ; repeat
60254734: ldr  r2, [r0], #4 ; next length
6025473a: bne  0x60254700 ; next pair
```

At `0x6025483c` the BIOS table contains `(0x61080000,0x00100000)`: zero 1,048,576 bytes, exclusive end `0x61180000`. At `0x60254874` it contains `(0x67100000,0x00002608)`: zero 9,736 bytes, exclusive end `0x67102608`. Next pair `(0x67124000,0x00020000)` zeros a further 128 KiB. **No device status register read is required to explain either original abort.**

The earlier native-QEMU unmapped stores caused ARM Data Aborts with DFSR `0x808`, DFAR matching the destination. Provisioning the first 16-MiB `0x61000000` window allowed firmware to proceed to the second fault. This validates a need for memory backing during initialization, not the physical technology behind it.

## BIOS memory-mapping descriptor evidence
The repeated five-word descriptor pattern around BIOS address `0x6000023c` appears to encode **length, physical address, virtual address, flags, attribute**:

| Descriptor location | Length | Physical | Virtual | Flags | Attribute |
| --- | --- | --- | --- | --- | --- |
| 0x6000023c | 0x05d80000 | 0x61000000 | 0x61000000 | 0x00000c30 | **0x0000104c** |
| 0x60000250 | 0x00500000 | 0x67100000 | 0x67100000 | 0x00000c30 | **0x00002080** |
| 0x60000264 | 0x00a00000 | 0x67600000 | 0x67600000 | 0x00000c30 | **0x0000104c** |

Crucially, **0x67100000 uses different mapping attributes** from its neighbors. Do not assume these are three physically identical RAM chips. We have not decoded the firmware-specific attribute format or identified actual RAM/FPGA/display controllers. A differently cached or device-like *writable backing window* remains possible. This descriptor interpretation needs verification by following the MMU mapping helper.

Other little-endian occurrences of `0x67100000` appear near `0x600acdb4`, `0x600ad690`, and `0x6018abc8`, suggesting additional later uses; not evidence of a particular chip.

## Iterating without rebuilding QEMU

1. The one-time EXeSX machine change accepts `EXESX_MEMORY_PROFILE=/path/to/profile.ini`. INI `kind=ram` windows provide experimental writable memory; `kind=registers` windows represent explicitly configured 32-bit MMIO registers. Missing MMIO registers **abort** rather than always returning made-up success. See `profiles/`.
2. Build the standalone out-of-tree QEMU TCG plugin with `bash scripts/build_memtrace.sh` whenever its instrumentation changes. This rebuilds one shared object, not QEMU's 3,000 source files. It logs vCPU, instruction PC, read/write, guest virtual and physical address, width and memory-region backing name.
3. `python3 scripts/analyze_init_regions.py private/a7-firmware.elf --json private/init-table.json` extracts and validates the startup table without executing it.
4. `python3 scripts/probe_profile.py --plugin build/exesx-memtrace.so` writes distinct **synthetic** markers to both addresses through the actual QEMU CPU and reads them back in QEMU's monitor.
5. For *real* firmware: `python3 scripts/run_firmware.py private/a7-firmware.elf --profile profiles/boot-ram-experimental.ini --plugin build/exesx-memtrace.so --seconds 2`. QEMU `guest_errors` remains essential: **TCG plugin memory callbacks only see successful loads/stores**, not faulting accesses.
6. For interactive stoppoints: `python3 scripts/make_gdb_commands.py -o private/zero-init.gdb`, run QEMU with `-S -gdb tcp:127.0.0.1:1234` and `gdb-multiarch -x private/zero-init.gdb`. The breakpoint is set on the Thumb `STR` and conditioned on the target destination; it may be slow when the zeroing loop executes hundreds of thousands of times.

The accompanying profiles are **hypotheses**, not production hardware maps. More faults are expected. Do not claim a working OS or display until the guest has genuinely reached the scheduler and written an LCD framebuffer. No genuine boot screenshot is available.
