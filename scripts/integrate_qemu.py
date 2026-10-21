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


# Explicit CMD12 STOP_TRANSMISSION during i.MX7ULP PIO multiblock reads.
# The original DY357 BIOS writes CMD_XFR_TYP=0x0c030000 while the previous
# CMD18 is still active. QEMU generic SDHCI interprets the R1b response
# with CMDTYP=normal as command-inhibited, silently discards the request,
# then Casio indefinitely polls INT_STATUS.CC. Only the opt-in i.MX7ULP
# card-equipped host accepts this legacy plain CMD12 while an actual
# multi-block READ is active; the real SD bus responds, then the host
# terminates the in-progress transfer and emits TC. No card or buffer
# contents are fabricated; generic SDHCI remains unchanged.
patch_exact(
    sdhci_source,
    'static void sdhci_data_transfer(void *opaque);\n'
    '\n'
    '#define BLOCK_SIZE_MASK (4 * KiB - 1)\n',
    'static void sdhci_data_transfer(void *opaque);\n'
    'static void sdhci_end_transfer(SDHCIState *s);\n'
    '\n'
    '#define BLOCK_SIZE_MASK (4 * KiB - 1)\n',
    "Explicit CMD12 forward declaration")
patch_exact(
    sdhci_source,
    '    sdhci_update_irq(s);\n'
    '\n'
    '    if (!timeout && (s->blksize & BLOCK_SIZE_MASK) &&\n',
    '    sdhci_update_irq(s);\n'
    '\n'
    '    /* DY357 emits a normal-type CMD12 even though CMD18 data is\n'
    '     * still in flight. An actual accepted STOP_TRANSMISSION aborts\n'
    '     * remaining buffered data; no bytes or card response are faked.\n'
    '     * Skip AutoCMD12 because the physical card just received CMD12.\n'
    '     */\n'
    '    if (!timeout && s->imx7ulp_input_clock && request.cmd == 12 &&\n'
    '        (s->prnsts & SDHC_DATA_INHIBIT) &&\n'
    '        (s->prnsts & SDHC_DOING_READ) &&\n'
    '        (s->trnmod & SDHC_TRNS_MULTI) &&\n'
    '        !(s->cmdreg & SDHC_CMD_DATA_PRESENT)) {\n'
    '        s->trnmod &= ~SDHC_TRNS_ACMD12;\n'
    '        sdhci_end_transfer(s);\n'
    '    }\n'
    '\n'
    '    if (!timeout && (s->blksize & BLOCK_SIZE_MASK) &&\n',
    "Explicit CMD12 transfer completion after real card command")
patch_exact(
    sdhci_source,
    '        !(SDHC_COMMAND_TYPE(s->cmdreg) == SDHC_CMD_ABORT))))) {\n',
    '        !(SDHC_COMMAND_TYPE(s->cmdreg) == SDHC_CMD_ABORT) &&\n'
    '        !(s->imx7ulp_input_clock &&\n'
    '          (s->cmdreg >> 8) == 12 &&\n'
    '          !(s->cmdreg & SDHC_CMD_DATA_PRESENT) &&\n'
    '          (s->prnsts & SDHC_DATA_INHIBIT) &&\n'
    '          (s->prnsts & SDHC_DOING_READ) &&\n'
    '          (s->trnmod & SDHC_TRNS_MULTI)))))) {\n',
    "Allow plain CMD12 only with genuine opt-in multiblock read")


# Optional one-shot CMD12 diagnostics on the opt-in real i.MX7ULP host.
# Read-only logging of C model fields allows real-OSUP differential to
# distinguish DAT inhibit from command-type, mixer, or clock gating.
# The default emulator never logs these. Enable with:
# EXESX_TRACE_USDHC1_CMD12=1 and QEMU -d unimp.
patch_exact(
    sdhci_source,
    '            sdhci_write(opaque, offset, val | s->trnmod, size);\n'
    '            s->clkcon = saved_clkcon;\n',
    '            bool trace_stop = s->imx7ulp_input_clock &&\n'
    '                (((uint32_t)val >> 24) & 0x3f) == 12 &&\n'
    '                !g_strcmp0(g_getenv("EXESX_TRACE_USDHC1_CMD12"), "1");\n'
    '            if (trace_stop) {\n'
    '                qemu_log_mask(LOG_UNIMP,\n'
    '                    "EXESX USDHC1 CMD12 BEFORE raw=%08x trnmod=%04x"\n'
    '                    " cmdreg=%04x prnsts=%08x clkcon=%04x gate=%d"\n'
    '                    " ready=%d\\n",\n'
    '                    (uint32_t)val, s->trnmod, s->cmdreg, s->prnsts,\n'
    '                    s->clkcon,\n'
    '                    !!(s->prnsts & SDHC_IMX_CLOCK_GATE_OFF),\n'
    '                    !!(s->prnsts & SDHC_DATA_AVAILABLE));\n'
    '            }\n'
    '            sdhci_write(opaque, offset, val | s->trnmod, size);\n'
    '            if (trace_stop) {\n'
    '                qemu_log_mask(LOG_UNIMP,\n'
    '                    "EXESX USDHC1 CMD12 AFTER cmdreg=%04x"\n'
    '                    " trnmod=%04x prnsts=%08x norint=%04x err=%04x"\n'
    '                    " clkcon=%04x\\n",\n'
    '                    s->cmdreg, s->trnmod, s->prnsts,\n'
    '                    s->norintsts, s->errintsts, s->clkcon);\n'
    '            }\n'
    '            s->clkcon = saved_clkcon;\n',
    "Opt-in original BIOS CMD12 reject-path diagnostics")


# NXP MIX_CTRL transfer-mode bits are not allowed to change while CDIHB
# is asserted. Upstream generic SDHCI honors this in SDHC_TRNMOD writes,
# but its i.MX "MIX_CTRL" translation directly mutates s->trnmod, even
# between CMD18 and the later CMD12 issued by the real DY357 BIOS.
# The original ARM accesses MIX_CTRL before CMD13 and CMD12, so a
# synthetic test that only writes CMD18 followed by CMD12 missed it.
patch_exact(
    sdhci_source,
    '    case USDHC_MIX_CTRL:\n'
    '        ret = 0;\n'
    '        break;\n',
    '    case USDHC_MIX_CTRL:\n'
    '        ret = s->imx7ulp_input_clock ? s->trnmod : 0;\n'
    '        break;\n',
    "Read back opt-in uSDHC MIX_CTRL transfer bits")
patch_exact(
    sdhci_source,
    '        s->trnmod = value & UINT16_MAX;\n'
    '        break;\n'
    '    case SDHC_TRNMOD:\n',
    '        if (s->imx7ulp_input_clock &&\n'
    '            (s->prnsts & SDHC_DATA_INHIBIT)) {\n'
    '            /* As with generic SDHC_TRNMOD, the active data\n'
    '             * transfer cannot be reprogrammed via MIX_CTRL.\n'
    '             * Permit other non-TRNMOD fields to change.\n'
    '             */\n'
    '            s->trnmod = (value & ~SDHC_TRNMOD_MASK) |\n'
    '                         (s->trnmod & SDHC_TRNMOD_MASK);\n'
    '        } else {\n'
    '            s->trnmod = value & UINT16_MAX;\n'
    '        }\n'
    '        break;\n'
    '    case SDHC_TRNMOD:\n',
    "Preserve active i.MX7ULP MIX_CTRL transfer bits across CMD13/CMD12")
