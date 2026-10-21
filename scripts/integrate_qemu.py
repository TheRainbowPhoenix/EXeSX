#!/usr/bin/env python3
"""Install EXeSX machine into a pinned upstream QEMU source tree."""
from pathlib import Path
import sys
root = Path(__file__).resolve().parents[1]
qemu = Path(sys.argv[1]).resolve()
meson = qemu / "hw/arm/meson.build"
assert meson.is_file() and (qemu / "hw/arm/virt.c").is_file()
target = qemu / "hw/arm/exesx.c"
source = (root / "hw/arm/exesx.c").read_bytes()
if target.exists() and target.read_bytes() != source:
    raise SystemExit("Refusing to overwrite changed upstream exesx.c")
target.write_bytes(source)
module = root / 'hw/arm/exesx-imx7ulp.inc'
module_target = qemu / 'hw/arm/exesx-imx7ulp.inc'
if module_target.exists() and module_target.read_bytes() != module.read_bytes():
    raise SystemExit('Refusing to overwrite changed upstream exesx-imx7ulp.inc')
module_target.write_bytes(module.read_bytes())
scg_module = root / 'hw/arm/exesx-imx7ulp-scg.inc'
scg_target = qemu / 'hw/arm/exesx-imx7ulp-scg.inc'
if scg_target.exists() and scg_target.read_bytes() != scg_module.read_bytes():
    raise SystemExit('Refusing to overwrite changed upstream exesx-imx7ulp-scg.inc')
scg_target.write_bytes(scg_module.read_bytes())
tpm_module = root / 'hw/arm/exesx-imx7ulp-tpm.inc'
tpm_target = qemu / 'hw/arm/exesx-imx7ulp-tpm.inc'
if tpm_target.exists() and tpm_target.read_bytes() != tpm_module.read_bytes():
    raise SystemExit('Refusing to overwrite changed upstream exesx-imx7ulp-tpm.inc')
tpm_target.write_bytes(tpm_module.read_bytes())
pmc_module = root / 'hw/arm/exesx-imx7ulp-pmc.inc'
pmc_target = qemu / 'hw/arm/exesx-imx7ulp-pmc.inc'
if pmc_target.exists() and pmc_target.read_bytes() != pmc_module.read_bytes():
    raise SystemExit('Refusing to overwrite changed upstream exesx-imx7ulp-pmc.inc')
pmc_target.write_bytes(pmc_module.read_bytes())
port_module = root / 'hw/arm/exesx-imx7ulp-port.inc'
port_target = qemu / 'hw/arm/exesx-imx7ulp-port.inc'
if port_target.exists() and port_target.read_bytes() != port_module.read_bytes():
    raise SystemExit('Refusing to overwrite changed upstream exesx-imx7ulp-port.inc')
port_target.write_bytes(port_module.read_bytes())
lpit_module = root / 'hw/arm/exesx-imx7ulp-lpit.inc'
lpit_target = qemu / 'hw/arm/exesx-imx7ulp-lpit.inc'
if lpit_target.exists() and lpit_target.read_bytes() != lpit_module.read_bytes():
    raise SystemExit('Refusing to overwrite changed upstream exesx-imx7ulp-lpit.inc')
lpit_target.write_bytes(lpit_module.read_bytes())
lptmr_module = root / 'hw/arm/exesx-imx7ulp-lptmr.inc'
lptmr_target = qemu / 'hw/arm/exesx-imx7ulp-lptmr.inc'
if lptmr_target.exists() and lptmr_target.read_bytes() != lptmr_module.read_bytes():
    raise SystemExit('Refusing to overwrite changed upstream exesx-imx7ulp-lptmr.inc')
lptmr_target.write_bytes(lptmr_module.read_bytes())
mu_module = root / 'hw/arm/exesx-imx7ulp-mu.inc'
mu_target = qemu / 'hw/arm/exesx-imx7ulp-mu.inc'
if mu_target.exists() and mu_target.read_bytes() != mu_module.read_bytes():
    raise SystemExit('Refusing to overwrite changed upstream exesx-imx7ulp-mu.inc')
mu_target.write_bytes(mu_module.read_bytes())
snvs_module = root / 'hw/arm/exesx-imx7ulp-snvs.inc'
snvs_target = qemu / 'hw/arm/exesx-imx7ulp-snvs.inc'
if snvs_target.exists() and snvs_target.read_bytes() != snvs_module.read_bytes():
    raise SystemExit('Refusing to overwrite changed upstream exesx-imx7ulp-snvs.inc')
snvs_target.write_bytes(snvs_module.read_bytes())
lpi2c_module = root / 'hw/arm/exesx-imx7ulp-lpi2c.inc'
lpi2c_target = qemu / 'hw/arm/exesx-imx7ulp-lpi2c.inc'
if lpi2c_target.exists() and lpi2c_target.read_bytes() != lpi2c_module.read_bytes():
    raise SystemExit('Refusing to overwrite changed upstream exesx-imx7ulp-lpi2c.inc')
lpi2c_target.write_bytes(lpi2c_module.read_bytes())
adc_module = root / 'hw/arm/exesx-imx7ulp-adc.inc'
adc_target = qemu / 'hw/arm/exesx-imx7ulp-adc.inc'
if adc_target.exists() and adc_target.read_bytes() != adc_module.read_bytes():
    raise SystemExit('Refusing to overwrite changed upstream exesx-imx7ulp-adc.inc')
adc_target.write_bytes(adc_module.read_bytes())
dma_module = root / 'hw/arm/exesx-imx7ulp-dma.inc'
dma_target = qemu / 'hw/arm/exesx-imx7ulp-dma.inc'
if dma_target.exists() and dma_target.read_bytes() != dma_module.read_bytes():
    raise SystemExit('Refusing to overwrite changed upstream exesx-imx7ulp-dma.inc')
dma_target.write_bytes(dma_module.read_bytes())
usdhc_module = root / 'hw/arm/exesx-imx7ulp-usdhc.inc'
usdhc_target = qemu / 'hw/arm/exesx-imx7ulp-usdhc.inc'
if usdhc_target.exists() and usdhc_target.read_bytes() != usdhc_module.read_bytes():
    raise SystemExit('Refusing to overwrite changed upstream exesx-imx7ulp-usdhc.inc')
usdhc_target.write_bytes(usdhc_module.read_bytes())
dmamux_module = root / 'hw/arm/exesx-imx7ulp-dmamux.inc'
dmamux_target = qemu / 'hw/arm/exesx-imx7ulp-dmamux.inc'
if dmamux_target.exists() and dmamux_target.read_bytes() != dmamux_module.read_bytes():
    raise SystemExit('Refusing to overwrite changed upstream exesx-imx7ulp-dmamux.inc')
dmamux_target.write_bytes(dmamux_module.read_bytes())
lpspi_module = root / 'hw/arm/exesx-imx7ulp-lpspi.inc'
lpspi_target = qemu / 'hw/arm/exesx-imx7ulp-lpspi.inc'
if lpspi_target.exists() and lpspi_target.read_bytes() != lpspi_module.read_bytes():
    raise SystemExit('Refusing to overwrite changed upstream exesx-imx7ulp-lpspi.inc')
lpspi_target.write_bytes(lpspi_module.read_bytes())
sema_module = root / 'hw/arm/exesx-imx7ulp-sema42.inc'
sema_target = qemu / 'hw/arm/exesx-imx7ulp-sema42.inc'
if sema_target.exists() and sema_target.read_bytes() != sema_module.read_bytes():
    raise SystemExit('Refusing to overwrite changed upstream exesx-imx7ulp-sema42.inc')
sema_target.write_bytes(sema_module.read_bytes())
# The QEMU 10.1.0 eMMC model accepts a real sector count in EXT_CSD, but
# its SD-card-only power-of-two drive-size assertion incorrectly rejects
# Samsung's published 15,634,268,160-byte eMMC user area. Preserve that
# assertion for actual SD cards; eMMC may have non-power-of-two density.
# Exact-source match and idempotence prevent accidentally patching a new
# upstream revision whose behavior we have not examined.
sd_card_source = qemu / "hw/sd/sd.c"
sd_card_text = sd_card_source.read_text()
sd_restrict = "if (blk_size > 0 && !is_power_of_2(blk_size)) {"
emmc_relax = ("if (blk_size > 0 && !is_power_of_2(blk_size) &&\n"
              "            !sd_is_emmc(sd)) {")
if sd_restrict in sd_card_text:
    if sd_card_text.count(sd_restrict) != 1 or "static bool sd_is_emmc" not in sd_card_text:
        raise SystemExit("Unsupported QEMU eMMC-size check; refusing to patch")
    sd_card_source.write_text(sd_card_text.replace(sd_restrict, emmc_relax))
elif emmc_relax not in sd_card_text:
    raise SystemExit("QEMU SD/eMMC density check differs from pinned 10.1.0; refusing to guess")

line = "arm_ss.add(when: 'CONFIG_ARM_V7M', if_true: files('exesx.c'))"
content = meson.read_text()
if line not in content:
    meson.write_text(content.rstrip() + "\n" + line + "\n")
print("Installed exesx board into", qemu)


# The pinned QEMU 10.1.0 i.MX uSDHC maps SYS_CTRL (+0x2c) through
# standard SDHCI clock bits 0..3. On i.MX7ULP these are reserved (NXP
# PERI_USDHC.h): SYS_CTRL.RSTA at bit24 performs a synchronous reset,
# then Casio polls PRES_STATE.SDSTB bit3 without writing SDHCI CLKCON.
# Only the EXeSX board opts into an externally supplied controller root
# clock; ordinary i.MX controllers retain upstream semantics.
def patch_exact(path, before, after, label):
    contents = path.read_text()
    if contents.count(before) == 1:
        path.write_text(contents.replace(before, after))
    elif after not in contents:
        raise SystemExit("Unsupported QEMU 10.1.0 " + label + "; refusing blind patch")

sdhci_header = qemu / "include/hw/sd/sdhci.h"
patch_exact(
    sdhci_header,
    "    bool wp_inverted;\n",
    "    bool wp_inverted;\n"
    "    /* EXeSX i.MX7ULP board input clock, not a card-detect override. */\n"
    "    bool imx7ulp_input_clock;\n",
    "SDHCI input-clock property field")

sdhci_source = qemu / "hw/sd/sdhci.c"
patch_exact(
    sdhci_source,
    '    DEFINE_PROP_BOOL("wp-inverted", SDHCIState,\n'
    '                     wp_inverted, false),\n',
    '    DEFINE_PROP_BOOL("wp-inverted", SDHCIState,\n'
    '                     wp_inverted, false),\n'
    '    DEFINE_PROP_BOOL("imx7ulp-input-clock", SDHCIState,\n'
    '                     imx7ulp_input_clock, false),\n',
    "SDHCI input-clock property")
patch_exact(
    sdhci_source,
    '        if (s->clkcon & SDHC_CLOCK_INT_STABLE) {\n'
    '            ret |= USDHC_PRNSTS_SDSTB;\n'
    '        }\n',
    '        /* i.MX7ULP SDSTB follows its clock input, not reserved\n'
    '         * SYS_CTRL[3:0] SDHCI-clock aliases. Other i.MX unchanged.\n'
    '         */\n'
    '        if ((s->clkcon & SDHC_CLOCK_INT_STABLE) ||\n'
    '            (s->imx7ulp_input_clock &&\n'
    '             !(s->prnsts & SDHC_IMX_CLOCK_GATE_OFF))) {\n'
    '            ret |= USDHC_PRNSTS_SDSTB;\n'
    '        }\n',
    "PRES_STATE clock status")
patch_exact(
    sdhci_source,
    '        if (value & USDHC_IMX_FRC_SDCLK_ON) {\n'
    '            s->prnsts &= ~SDHC_IMX_CLOCK_GATE_OFF;\n'
    '        } else {\n'
    '            s->prnsts |= SDHC_IMX_CLOCK_GATE_OFF;\n'
    '        }\n',
    '        /* FRC_SDCLK_ON=0 returns control to hardware. It does not\n'
    '         * disable a supplied i.MX7ULP controller input clock.\n'
    '         */\n'
    '        if (s->imx7ulp_input_clock ||\n'
    '            (value & USDHC_IMX_FRC_SDCLK_ON)) {\n'
    '            s->prnsts &= ~SDHC_IMX_CLOCK_GATE_OFF;\n'
    '        } else {\n'
    '            s->prnsts |= SDHC_IMX_CLOCK_GATE_OFF;\n'
    '        }\n',
    "VEND_SPEC FRC clock behavior")
patch_exact(
    sdhci_source,
    '    case USDHC_MIX_CTRL:\n'
    '        /*\n'
    '         * So, when SD/MMC stack in Linux tries to write to "Transfer\n',
    '    case SDHC_CLKCON:\n'
    '        /* i.MX7ULP SYS_CTRL low nibble is reserved; generic SDHCI\n'
    '         * CLKCON enable bits do not exist at this guest address.\n'
    '         * RSTA and the NXP divisor/timeout fields still work.\n'
    '         */\n'
    '        if (s->imx7ulp_input_clock) {\n'
    '            val &= ~UINT32_C(0xf);\n'
    '        }\n'
    '        sdhci_write(opaque, offset, val, size);\n'
    '        break;\n'
    '    case USDHC_MIX_CTRL:\n'
    '        /*\n'
    '         * So, when SD/MMC stack in Linux tries to write to "Transfer\n',
    "SYS_CTRL i.MX7ULP reserved clock bits")
patch_exact(
    sdhci_source,
    '        sdhci_write(opaque, offset, val | s->trnmod, size);\n'
    '        break;\n'
    '    case SDHC_BLKSIZE:\n',
    '        {\n'
    '            uint16_t saved_clkcon = s->clkcon;\n'
    '            /* The upstream SDHCI command engine requires its clock\n'
    '             * bits. Temporarily translate EXeSX input-clock state;\n'
    '             * never change the guest-visible SYS_CTRL or synthesize\n'
    '             * a card response. On a missing root, commands remain\n'
    '             * gated. This is restricted to the opt-in board device.\n'
    '             */\n'
    '            if (s->imx7ulp_input_clock &&\n'
    '                !(s->prnsts & SDHC_IMX_CLOCK_GATE_OFF)) {\n'
    '                s->clkcon |= SDHC_CLOCK_CHK_MASK;\n'
    '            }\n'
    '            sdhci_write(opaque, offset, val | s->trnmod, size);\n'
    '            s->clkcon = saved_clkcon;\n'
    '        }\n'
    '        break;\n'
    '    case SDHC_BLKSIZE:\n',
    "SDHCI command clock bridge")


# i.MX7ULP FIFO watermark BRR behavior: QEMU 10.1.0 ignores WTMK_LVL
# entirely and only raises RBUFRDY once per whole SDHCI block. Original
# DY357 polls for a fresh BRR after 32 data words while reading EXT_CSD.
# Use the genuine SD-bus 512-byte FIFO and its existing data_count; never
# synthesize a data word or announce BRR when no data remains.
patch_exact(
    sdhci_header,
    "    bool imx7ulp_input_clock;\n".replace("\\\n", "\n"),
    "    bool imx7ulp_input_clock;\n"
    "    uint32_t imx7ulp_wtmk_lvl; /* FIFO RX/TX watermarks, opt-in */\n",
    "USDHC WTMK_LVL storage field")
patch_exact(
    sdhci_source,
    '    s->data_count = 0;\n'
    '    s->stopped_state = sdhc_not_stopped;\n',
    '    s->data_count = 0;\n'
    '    s->imx7ulp_wtmk_lvl = 0;\n'
    '    s->stopped_state = sdhc_not_stopped;\n',
    "USDHC watermark reset")
patch_exact(
    sdhci_source,
    '    .name = "sdhci",\n'
    '    .version_id = 1,\n'
    '    .minimum_version_id = 1,\n',
    '    .name = "sdhci",\n'
    '    .version_id = 2,\n'
    '    .minimum_version_id = 1,\n',
    "USDHC VMState version")
patch_exact(
    sdhci_source,
    '        VMSTATE_UINT16(data_count, SDHCIState),\n',
    '        VMSTATE_UINT16(data_count, SDHCIState),\n'
    '        VMSTATE_UINT32_V(imx7ulp_wtmk_lvl, SDHCIState, 2),\n',
    "USDHC WTMK migration field")
# Replace the exact group handling of WTMK_LVL in usdhc_read and write.
patch_exact(
    sdhci_source,
    '    case USDHC_MIX_CTRL:\n'
    '    case USDHC_WTMK_LVL:\n'
    '        ret = 0;\n',
    '    case USDHC_MIX_CTRL:\n'
    '        ret = 0;\n'
    '        break;\n'
    '    case USDHC_WTMK_LVL:\n'
    '        ret = s->imx7ulp_input_clock ? s->imx7ulp_wtmk_lvl : 0;\n',
    "WTMK_LVL readback")
patch_exact(
    sdhci_source,
    '    case USDHC_TUNING_CTRL:\n'
    '    case USDHC_WTMK_LVL:\n'
    '        break;\n',
    '    case USDHC_TUNING_CTRL:\n'
    '        break;\n'
    '    case USDHC_WTMK_LVL:\n'
    '        if (s->imx7ulp_input_clock) {\n'
    '            /* NXP WTMK_LVL: RD_WML[7:0], RD_BRST_LEN[12:8],\n'
    '             * WR_WML[23:16], WR_BRST_LEN[28:24].\n'
    '             */\n'
    '            s->imx7ulp_wtmk_lvl = value & 0x1fff1fff;\n'
    '        }\n'
    '        break;\n',
    "WTMK_LVL write")
patch_exact(
    sdhci_source,
    '        s->norintsts &= mask | ~value;\n'
    '        s->errintsts &= (mask >> 16) | ~(value >> 16);\n',
    '        s->norintsts &= mask | ~value;\n'
    '        s->errintsts &= (mask >> 16) | ~(value >> 16);\n'
    '        /* uSDHC FIFO watermark level: the original Casio ARM code\n'
    '         * drains RD_WML=32 words and W1C-acks BRR before waiting for\n'
    '         * the next FIFO tranche. Upstream SDHCI keeps one full block\n'
    '         * buffered; only re-arm the real buffered bytes at a multiple\n'
    '         * of the configured threshold, while data remains.\n'
    '         */\n'
    '        if (s->imx7ulp_input_clock && (value & SDHC_NIS_RBUFRDY) &&\n'
    '            (s->prnsts & SDHC_DATA_AVAILABLE) &&\n'
    '            (s->norintstsen & SDHC_NISEN_RBUFRDY)) {\n'
    '            uint32_t wml = s->imx7ulp_wtmk_lvl & 0xff;\n'
    '            uint32_t consumed = s->data_count;\n'
    '            uint32_t block = s->blksize & BLOCK_SIZE_MASK;\n'
    '            if (wml && consumed && consumed < block &&\n'
    '                consumed % (wml * 4) == 0) {\n'
    '                s->norintsts |= SDHC_NIS_RBUFRDY;\n'
    '            }\n'
    '        }\n',
    "RX watermark BRR W1C re-arm")
