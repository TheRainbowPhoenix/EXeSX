# Original BIOS startup chords: direct OSUP disassembly and main cold-boot A/B tests (2026-10-25)

**Private firmware is not included.** The owner's unchanged `OSUP.BIN` has SHA-256 `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`. The original A7 BIOS/OS ELF and synthetic media were reconstructed privately from the supplied owner-local SD test kit, and the **exact completed native Linux QEMU main artifact from commit `cc2a7bd419175a22292f8aeab60d433b587c6036`** was used. No original-ROM bytes, QMP RAM samples, emulator instruction traces, or private media are committed.

## Startup keys confirmed from ORIGINAL A7 ARM disassembly

The owner's A7 ELF independently verifies the documented two *simultaneous* startup chords, not merely guessed mappings:

| A7 wrapper (original) | Original ARM immediates | Electrical matrix keys |
| --- | --- | --- |
| `0x6001D93C` | `MOV R2,#0x92; MOV R1,#0x95; MOV R0,#0x80` | **`0x80 + 0x95 + 0x92`** |
| `0x6001D94C` | `MOV R2,#0x96; MOV R1,#0x90; MOV R0,#0x80` | **`0x80 + 0x90 + 0x96`** |

Both wrappers branch to `0x6001D864`, which resolves the three code coordinates and repeatedly checks three GPIO-scanned contacts via `0x6001D95C`. It requests a repeated timed hold (literal **2000 firmware delay units**, not a calibrated wall-clock duration). The real M4 ROM matrix table already maps `0x80=(row0,col0)`, `0x95=(row5,col6)`, `0x92=(row7,col7)`, `0x90=(row7,col6)`, and `0x96=(row8,col4)`.

**Do not mix up the later step:** after the original A7 reaches `0x60010868` / event wait `0x600108A8`, type2/subtype1 key-down **`0x93 → 0x93 → 0x94`** makes its original checker reach factory-menu entry `0x6003A878` (previously verified in an older private version-dialog VM checkpoint, not reproduced in these new cold boots). The exact physical button *legends* remain unverified: ROM numeric codes do not by themselves label human keys.

## Actual trials on completed main build: six independent no-debugger cold boots

Each run used opt-in physical `EXESX_M4_KEY_MATRIX_FILE` simultaneous contact closures **before A7 reset release**, unchanged original A7/M4 guest code, source-derived sparse eMMC with `snapshot=on`, original row IOMUX/IRQ/debounce semantics, diagnostic TPM0 input 48 MHz and A7 TPM6 32 kHz, LPTMR PCS clocks enabled, and read-only QMP/HMP plus narrowly filtered `-d exec` (rather than GDB, synthetic queue events, CPU writes, or service-response overrides). The chord was **kept held** throughout each run, unless a real A7 version-dialog event-wait TB appeared (none did). The three later single keys were deliberately **not** sent into a BIOS that was not yet waiting for them.

| Trial | Startup chord | SD inserted | GPIO external readiness | Host observation window | Reached chord checker or dialog? |
| --- | --- | --- | --- | --- | --- |
| A1 | 0x80,0x95,0x92 | yes | ready A=0x808c6008, B=0xc8 from reset | 15 s | **NO** |
| B1 | 0x80,0x90,0x96 | yes | ready from reset | 17 s | **NO** |
| A2 | 0x80,0x95,0x92 | yes | boot A=0, B=0x88; raise readiness after 4 s | 18 s | **NO** |
| B2 | 0x80,0x90,0x96 | yes | boot A=0, B=0x88; raise readiness after 4 s | 18 s | **NO** |
| A3 | 0x80,0x95,0x92 | no | ready from reset | 13 s | **NO** |
| B3 | 0x80,0x90,0x96 | no | ready from reset | 13 s | **NO** |

Across all six trials, a properly parsed QEMU **executed TB** log observed original A7 first-boot entries `0x6004A0B4` and `0x6004A108`, but no execution at `0x60011CA4`, either of the chord wrappers `0x6001D93C` or `0x6001D94C`, original version-dialog `0x60010868` or `0x600108A8`, or genuine menu `0x6003A878`. The RAM selector `0x6232E33C` remained 0 at all sampled endpoints; original shared slot `0x2F02800C` retained `0x0001A002` and previous status word `0x040208FF`. **A stale shared slot is not proof of a still-blocked A002 service**. The no-SD primary-chord trial independently saw a genuine original-M4 20-byte keyboard event with type2/subtype1 and `code=0x0080`: at least that chord contact was physically recognized by original M4; it does **not** demonstrate the A7 chord checker ran.

### Specific conclusion and next step

**The keys and their simultaneous semantics are now directly confirmed in the supplied original A7 BIOS; both were actually driven in QEMU. Neither made the current main cold boot enter the startup-chord detection routine.** A7 not executing the checker must not be misreported as an invalid chord or missing M4 electrical contact. Stage readiness and attaching/detaching the SD card did not resolve this within the bounded test windows.

Trace the original **A7 initialization after `0x6004A108`**, with explicit original caller/service return observations through the startup-mode initializer `0x60011CA4`. When `0x600108A8` is genuinely reached, release the held chord and send the three independent original contacts `0x93,0x93,0x94` (for example `--hold 0.07 --gap 0.03` under a suitable calibrated virtual-time configuration). Keep the existing `scripts/drive_factory_menu.py --startup-chord ... --matrix-keys` harness as a GDB milestone probe and favor QMP-only control for timing experiments. After authentic A7 menu entry, the separate service `0x400B(2)` completion/LCD paint gate still requires proof.

Test logs and media were local/private; no destructive SD-card diagnostics were attempted.
