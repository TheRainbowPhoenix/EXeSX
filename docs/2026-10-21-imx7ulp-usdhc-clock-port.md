# USDHC1 reset/clock port — i.MX7ULP opt-in experiment (2026-10-21)

## Origin of the deadlock

Private checksum-validated DY357 OSUP, original SHA-256
`d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`,
reached A7 `0x60017134–0x60017144`: read `SYS_CTRL`, ORR
`RSTA=0x01000000`, write it, then repeatedly read `PRES_STATE` and
test `SDSTB=0x8` before any MMC command. QEMU 10.1.0's generic SDHCI
`sdhci_reset` clears `clkcon` while its i.MX `usdhc_read` derives
`SDSTB` from `clkcon.SDHC_CLOCK_INT_STABLE`. The observed controller
had `SYS_CTRL=0`, `VEND_SPEC=0`, `PRES_STATE=0x01ff0000` after reset.

NXP's **i.MX7ULP PERI_USDHC.h** differs from generic SDHCI: `SYS_CTRL`
bits 0–3 are not the normal SDHCI clock enable bits; supported fields begin
at `DVS[7:4]` and `SDCLKFS[15:8]`; `RSTA` is bit24; `PRES_STATE.SDSTB`
is bit3. `VEND_SPEC.FRC_SDCLK_ON` bit8 means *force output clock when 1,
return to hardware control when 0*; zero is not proof that the controller
clock input is absent. Linux's i.MX7ULP DTS connects USDHC1 to SCG1
`NIC1_BUS_DIV` and `NIC1_DIV` and to the PCC2 `USDHC1` peripheral clock
gate, i.e. separate from the standard SDHCI clock-control bit fields.

Manufacturer reference:
https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/periph/PERI_USDHC.h

Upstream QEMU pinned version:
https://github.com/qemu/qemu/blob/v10.1.0/hw/sd/sdhci.c

## Limited opt-in compatibility port (NOT verified hardware gate timing)

`scripts/integrate_qemu.py` now carries *exact-match, idempotent,
version-pinned* patches into QEMU's `sdhci.h` and `sdhci.c`.
A new **default-off** `imx7ulp-input-clock` property is set **only** by
EXeSX's `EXESX_USDHC1_EMMC=1` host. It is treated as an externally
provided clock input, not as a fake card-ready/SDSTB register constant:

- After the synchronous `RSTA` reset, `SDSTB` reflects the root input
  (provided and not internally gated) or the original SDHCI clock path.
  It does **not** become unconditional for all QEMU i.MX devices.
- `VEND_SPEC.FRC_SDCLK_ON=0` returns clock-output control to hardware;
  it does not force *off* a separately present input root clock.
- Low `SYS_CTRL` nibble is write-ignored in EXeSX opt-in mode, consistent
  with the i.MX7ULP peripheral register layout, while divisor/timeout
  fields and reset commands retain their existing implementation.
- On CMD writes, EXeSX temporarily maps the known supplied root clock
  into the upstream SDHCI command-clock guard and then restores
  `clkcon`. No OCR/card insertion/sector is invented.
- The original **no-card/no-media** register path, empty-slot CMD1 timeout
  and ordinary QEMU i.MX USDHC devices remain unchanged.

**Important limitation:** EXeSX's PCC2/SCG1 peripheral gate has **not yet**
been physically connected to this upstream SDHCI device. For now the
opt-in board explicitly supplies a root clock by default, because this
run targets a configured controller. Set `EXESX_USDHC1_INPUT_CLOCK=0`
to test an absent input. This is a testable clock-source working assumption,
not a measurement of the actual Casio clock net or reset settling time.
Once original-firmware behavior advances, add dynamic PCC2 clock gate
wiring and hardware-appropriate clock transition timing if needed.
The contemporary QEMU vendor-gate patch for a different i.MX SoC
(https://mid.mail-archive.com/qemu-devel@nongnu.org/msg1231901.html)
was not applied blindly: its `IPGEN/HCKEN/PEREN/CKEN` bit assumptions
are not the i.MX7ULP VEND_SPEC field definition.

## Test contract

Native QEMU guest-ARM `scripts/probe_upstream_emmc.py` executes the
original reset/write/read/test/branch **instruction sequence**, with
only the address register changed to r6 because the probe uses r0 for
its subsequent commands. It proves the loop exits under the explicit
root clock before real CMD0/CMD1/CMD2/CMD3/CMD9/CMD7, CMD17 backed
sector read, and CMD8 EXT_CSD; also checks `SYS_CTRL[3:0]` remain zero.

`scripts/probe_usdhc1_clock_gate.py` uses the same input card with the
input-clock property disabled, proving reset does not set SDSTB and the
VEND_SPEC force-output bit alone cannot create an input source. CI also
runs existing no-card regressions independently.

**CI tests are synthetic ARM programs, not the private original OSUP.**
Only a private native run with the original file and explicit diagnostic
I2C/SNVS/GPIO flags can establish whether `0x60017144` is passed and
whether the *real Casio firmware* reaches CMD0/CMD1 or the OS section.
Never upload the OSUP, ROM slices, eMMC dumps or private traces to GitHub.


## Private original-DY357 firmware differential — actually executed

The source OSUP used here has SHA-256 `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`. Extracted with repository `prepare_osup.py` into the checksum-validated BIOS and OS ELF; **no source firmware, ELF or trace was uploaded**. Identical 5-second old/new runs used the synthetic reference-size sparse eMMC and identical opt-in diagnostic flags:

`EXESX_EXPERIMENTAL_M4_BOOT=1`,
`EXESX_EXPERIMENTAL_MU_IRQ=1`,
`EXESX_GPIOB_INPUT_MASK=0x80`,
`EXESX_I2C4B_REGISTER_MIRROR=1`,
`EXESX_I2C40_REGISTER_MIRROR=1`,
`EXESX_SNVS_DIAGNOSTIC_SECURITY_PULSES=1`,
`EXESX_USDHC1_EMMC=1`,
and `profiles/imx7ulp-early-boot.ini`.

* **Before port:** native QEMU artifact from run 39648471273; A7 decoded original `0x60017140/44` and remained in its SDSTB loop. No original CMD0/CMD1 observed.
* **After port:** new native QEMU 10.1.0 artifact from [run 39669985642](https://github.com/TheRainbowPhoenix/EXeSX/actions/runs/39669985642) (**SUCCESS**, including real ARM RSTA/SDSTB, negative gate, eMMC sector, and no-media regressions). A7 passed `0x60017144` and entered original `0x60017988` MMC logic. The QEMU SDHCI/eMMC traces **from this real DY357 firmware**, not a synthetic ARM guest, confirmed **CMD0 arg 0**, **CMD1 arg `0x40ff8000`** and R3 `0xc0ffff00`, then CMD2, CMD3 RCA `0x00020000`, CMD9, CMD7, CMD6, CMD13 and CMD8 (SEND_EXT_CSD).
* **New observed bounded stall:** original A7 PC `0x60018784`; after `CMD8`, the firmware is polling `USDHC1.INT_STATUS` `0x40380030` waiting for a buffer-ready/error condition. The live host at this moment reports `PRES_STATE=0x01ff0a0a`, `SYS_CTRL=0x008d0800`, `VEND_SPEC=0x100`, `CMD_XFR_TYP=0x08220010`, `INT_STATUS=0x1`. No original OS section execution or LCD text is verified.

### Next likely root cause: uSDHC FIFO watermark, not CMD1

Disassembly of unmodified BIOS `0x60018758–0x6001878c` shows the guest reading **32 32-bit data-port words** (128 bytes) from `USDHC1.DATA_BUFF_ACC_PORT` `0x40380020`, clearing `INT_STATUS.BRR` bit5 with write-one-to-clear `0x20`, then polling `INT_STATUS` until the next ready/error event before another 32-word batch. At the bounded observation the batch index was 1, consistent with the first 128-byte batch completed.

The original firmware earlier writes `WTMK_LVL=0x08200820`, specifically **RD_WML=32 words**, while QEMU 10.1.0's `usdhc_write` **ignores `USDHC_WTMK_LVL`**. Its generic SDHCI PIO model announces buffer-ready for an entire block, not yet proven to reassert BRR each 32-word watermark as this Casio path expects. That mismatch is the **leading, source-supported explanation**, not yet a separately fixed peripheral. Next task: implement/regress correct i.MX7ULP watermark-boundary BRR behavior in QEMU without faking a data block or completion and compare real firmware again.

Synthetic backing has no authentic Casio user sectors and the eMMC identification is QEMU's, so later failures may expose contents/CID mismatches. **Do not claim real OS boot or screen pixels.**
