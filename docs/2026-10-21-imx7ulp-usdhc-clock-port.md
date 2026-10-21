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
