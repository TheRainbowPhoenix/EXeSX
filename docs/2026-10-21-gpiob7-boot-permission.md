# GPIOB pin 7 is the missing A7 boot-permission signal — 2026-10-21

**Source/evidence scope:** The original, privately supplied DY357 Casio OSUP is SHA256 `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`. All recorded execution used the actual A7/M4 firmware in native EXeSX QEMU 10.1.0 with clearly **diagnostic** I²C mirrors (0x4B/0x40) and SNVS security-command pulse ignore. The board's true switch wiring and resting logic levels remain UNKNOWN. No proprietary firmware, account credentials, private traces or snapshots are in Git.

## Measured causal chain, starting at the M4

A **GDB write watchpoint on shared SRAM `0x2F029284`** stopped the real M4 repeatedly at `0x1FFD77A0`. M4 code actually implements:

```asm
0x1FFD7782  push {lr}; ...                ; M4_GPIOB7_UpdateSharedA7BootGate
0x1FFD778A  ldr  r0, =0x2F029204
0x1FFD778C  ldr  r1, =0x4100F050
0x1FFD778E  ldr  r1, [r1]               ; GPIOB.PDIR (pin input values)
0x1FFD7790  lsls r1, r1, #24            ; test *GPIOB pin7*
0x1FFD7792  bpl  0x1FFD779E
0x1FFD7794  mov.w r1, #0xffffffff
0x1FFD7798  str.w r1, [r0, #0x80]      ; boot permitted when pin7 high
0x1FFD779E  movs r1, #0
0x1FFD77A0  str.w r1, [r0, #0x80]      ; boot denied when pin7 low
```

The precise literal pools are `0x1FFD78C0=0x4100F050` and `0x1FFD78C8=0x2F029204`. NXP [i.MX7ULP CMSIS base addresses](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/MCIMX7U5/MCIMX7U5_cm4_COMMON.h) identify `GPIOB_BASE=0x4100F040`, and [PERI_GPIO.h](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/periph/PERI_GPIO.h) puts read-only `PDIR` at +0x10 and pin direction `PDDR` at +0x14.

**Actual runtime hardware-model sample on the blocked branch:** `GPIOB.PDIR=0x00000000`, `GPIOB.PDDR=0x00068C04` (bit7 is input), `GPIOB.PDOR=0x00000000`, `A7 shared gate=0x00000000`. Therefore QEMU's missing GPIO input is directly relevant.

## A7 confirms the startup gating, NOT an MMDC/wake-first defect

The A7 startup function `0x6004A0B4` (MainTask) reaches this exact gating sequence:

```asm
0x6004A198  bl  0x60010C80           ; A7_BootPermission_CheckM4SharedGate
0x6004A19C  cmp r0, #0
0x6004A1A0  beq 0x6004A1B4         ; no permission => shut down
0x6004A1A4  mov r0, #3
0x6004A1A8  bl  0x60008D34           ; separate startup readiness check
0x6004A1AC  cmp r0, #0
0x6004A1B0  bne 0x6004A1BC         ; continue normal startup
0x6004A1B4  bl  0x600117A0          ; A7_System_PrepareShutdown
```

The helper `0x60010C80` calls `0x6001D47C`: it loads `0x2F029204 + 0x80` and returns one iff the word is nonzero. The actual A7 breakpoint at `0x6004A19C` had `r0=0`, and execution reached the shutdown site `0x6004A1B4`.

The exit chain is confirmed by real breakpoint PCs:

```text
0x6004A1B4 → 0x600117A0
→ 0x60011858 (calls 0x601E7144)
→ 0x601CC0DC (saves privileged register/stack context)
→ 0x601CD48C (deinitialize devices)
→ 0x601CD2D4 (jump to copied SRAM suspend)
→ 0x2F02B0B8 (DDR MAPSR request/LPACK poll and WFI)
```

The NXP [MMDC register map](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/periph/PERI_MMDC.h) confirms MAPSR at `0x40AB0404`, `LPMD` bit20 and `LPACK` bit24. **This is a consequence of a denied startup**, not an unexplained decision to suspend. Making LPACK always true would simply reach WFI and cannot fix the missing input condition.

## Independent controlled counterfactual

At the actual A7 instruction `0x6004A19C`, changing **only temporary GDB register r0 from 0 to 1** after the first readiness call, without patching any ROM or MMIO, caused:
- The second check `A7_MainTask_SecondaryStartupCheck` at `0x60008D34`, argument 3, to return **1**.
- A7 to execute the **normal-startup branch `0x6004A1BC`** rather than `0x6004A1B4`.
- A7 subsequently took a distinct Data Abort in this diagnostic run; **no OS or LCD output has been demonstrated**.

This isolates GPIOB's decision as necessary for the first shutdown branch, but does not prove that an always-high GPIO pin matches physical Casio hardware.

## Correct emulator representation and test

Before this change `GPIO.PDIR = GPIO.PDOR & GPIO.PDDR` everywhere: GPIO input-only bits always read low, regardless of real-world power keys/sensor signals. The proposed fix preserves this as the **default** but adds a selected GPIOB **electrical input voltage mask** via `EXESX_GPIOB_INPUT_MASK=0x80`, read only for pins configured as inputs. It **never** forces an output pin high, generates an LLWU/port IRQ, or changes other GPIO ports. Missing real board wiring is not guessed or enabled by default.

```sh
# Firmware-free native ARM GPIOB pin direction test (CI)
python3 scripts/probe_gpiob_input.py --qemu build/qemu-system-arm \
  --profile profiles/imx7ulp-early-boot.ini

# Real proprietary OSUP differential, local only
python3 scripts/prepare_osup.py /absolute/path/to/OSUP.BIN -o private/a7.elf
python3 scripts/probe_a7_boot_gate.py private/a7.elf \
  --qemu build/qemu-system-arm \
  --profile profiles/imx7ulp-early-boot.ini \
  --out private/boot-gpio-test
```

The second tool runs two **clean cold boots** (mask=0 and mask=0x80), breaks on the *actual M4* store of 0 or 0xFFFFFFFF, measures M4 PDIR and A7 shared word, and then observes which of the two actual A7 branch sites is reached. It does not patch a return register or rewrite a firmware image. Private outputs must never be committed.

## Completed native CI and original-ROM GPIOB7 differential

- [GitHub Actions run 39574881093](https://github.com/TheRainbowPhoenix/EXeSX/actions/runs/39574881093) **SUCCESS**: compiled native QEMU and ran synthetic ARM GPIOB external pin/direction regression along with existing MU, SNVS, USDHC and DMA regression checks. Independently downloaded the exact native artifact and re-ran `probe_gpiob_input.py`: with mask=0 it returned `PDIR=[0,0x80,0]`; with mask=0x80 it returned `[0x80,0x80,0]`, including correct output-direction priority.
- **Original untouched A7 and M4 firmware**, separate native QEMU run, with opt-in diagnostic I²C mirrors and SNVS pulses **unchanged**: `EXESX_GPIOB_INPUT_MASK=0x80` made a GDB breakpoint at real M4 PC **`0x1FFD7798`** see **`r1=0xFFFFFFFF`** before storing to shared startup permission. GPIOB.PDIR actually read `0x00000080`, PDDR `0x00068C04`, PDOR 0. Thus M4 takes its own *high-input* branch, not an A7 debugger-injected return value.
- The independent **real A7 MainTask** stop at `0x6004A19C` now had `r0=1` and shared word `0x2F029284=0xFFFFFFFF`—no register or ROM modifications. It passed the secondary check and reached the normal startup branch **`0x6004A1BC`**. In an otherwise identical low-mask cold run, the actual M4 wrote zero and A7 took shutdown at `0x6004A1B4`.
- **Next precise A7 fault after normal-startup unlock:** original firmware progressed until A7 Data Abort **DFSR `0x1808`, DFAR `0x40380044`**, actual ARM store at **`0x600179B0`**. This is NXP USDHC1 **`WTMK_LVL`** at host base 0x40380000 plus 0x44, a FIFO watermark configuration register ([NXP PERI_USDHC.h](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/periph/PERI_USDHC.h)). There is still NO verified Casio OS entry, storage device, DMA completion or LCD content. This new fault is **not** MMDC self-refresh; the normal branch skips that shutdown entirely.

Therefore the missing external GPIOB7 input really is the cause of the observed MMDC shutdown path. **It does not prove pin7 is always high on real Casio hardware**; GPIOB7 board function and any subsequent LLWU wake mechanism still require physical or firmware cross-reference.

## Which wakeup event?

The **first necessary signal** is now concretely GPIOB pin 7 sampled by M4; its *board-level role and polarity are unknown*. It is a *startup permission*, **not proven to be an LLWU wakeup IRQ**.

After A7 intentionally enters DDR low-power and WFI, possible wake/reset paths involve the A7 application-domain power controller PMC1/SMC1, interrupt controller GIC, and M4/LLWU handling. NXP's [MCUXpresso power mode switch demonstration](https://docs.mcuxpresso.nxp.com/mcuxsdk/26.09.00-pvw1/html/examples/_boards/evkmcimx7ulp/demo_apps/power_mode_switch/example_board_readme.html) explicitly distinguishes **waking, booting, rebooting, and shutting down A7**. [NXP's A7/M4 low-power discussion](https://community.nxp.com/t5/i-MX-Processors/i-MX7ULP-in-low-power-boot/m-p/1166065/highlight/true) describes M4-driven wake/power-state coordination, but these are *reference EVK workflows*, not proof of Casio's command protocol.

**Next:** run the unmodified M4+ A7 binary with controlled GPIOB7 input state (mask 0 vs 0x80), compare branch, OS entry, CPU exceptions and next genuine MMIO fault. If a later A7 wakeup becomes necessary, first trace Casio's LLWU/SMC/MU configuration and interrupt source rather than fabricate a wake event.

See [hardware source index](HARDWARE_REFERENCES.md) and [the prior MMDC investigation](2026-10-21-usdhc1-mmdc-lowpower.md).
