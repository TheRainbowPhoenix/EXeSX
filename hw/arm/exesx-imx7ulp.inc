/*
 * i.MX7ULP early-startup MMIO models for the EXeSX research machine.
 * Hardware maps from NXP MCUXpresso CMSIS headers and NXP U-Boot DTS.
 * Included by exesx.c to keep the modeled peripherals in a separate,
 * independently reviewable source module; only the EXeSX object recompiles.
 * GPL-2.0-or-later.  No proprietary firmware.
 *
 * Scope: PCC0 gate registers (explicitly listed), GPIO PTA 32-bit data,
 * PCTLA pin configuration registers, and read-only TSTMRB.
 * This is not a full i.MX7ULP SoC: interrupt, clock tree, external pins
 * and timer synchronization are not yet emulated.
 */
#include "qemu/timer.h"
#include "exesx-imx7ulp-touch.inc"
#include "exesx-imx7ulp-scg.inc"
#include "exesx-imx7ulp-tpm.inc"
#include "exesx-imx7ulp-pmc.inc"
#include "exesx-imx7ulp-port.inc"
#include "exesx-imx7ulp-lpit.inc"
#include "exesx-imx7ulp-lptmr.inc"
#include "exesx-imx7ulp-mu.inc"
#include "exesx-imx7ulp-snvs.inc"
#include "exesx-imx7ulp-lpi2c.inc"
#include "exesx-imx7ulp-adc.inc"
#include "exesx-imx7ulp-i2s.inc"
/* The DMA1 SERQ path can trigger the already configured LPSPI2
 * peripheral. The actual implementation follows this include. */
static void exesx_lpspi2_dma_kick(EXeSXProfileWindow *w);
#include "exesx-imx7ulp-dma.inc"
#include "exesx-imx7ulp-usdhc.inc"
#include "exesx-imx7ulp-dmamux.inc"
#include "exesx-imx7ulp-lpspi.inc"
#include "exesx-imx7ulp-sema42.inc"

/* External GPIOB pins exist on real hardware; the default model has
 * none attached. Research-only static electrical input levels are opt-in
 * and never turn an output pin into an input or fabricate an interrupt.
 * NXP PERI_GPIO.h PDIR+0x10 / PDDR+0x14 and GPIOB_BASE=0x4100f040.
 *
 * The M4 firmware at 0x1ffd778e tests GPIOB.PDIR bit7 to decide whether
 * to set A7 boot-gate word 0x2f029284 (0xffffffff or 0). The real Casio
 * board's attached signal and active polarity are still unverified.
 */
/* The firmware-free diagnostic permits board input levels only on
 * pins configured as GPIO inputs. PDOR/PDDR output state always wins.
 * This does not infer actual DY357 pull-ups or keyboard matrix wiring.
 */
static uint32_t exesx_external_gpio_input_mask(const char *name)
{
    const char *source = g_getenv(name);
    char *end;
    uint64_t value;
    if (!source || !*source) {
        return 0;
    }
    value = g_ascii_strtoull(source, &end, 0);
    if (*end != '\0' || value > UINT32_MAX) {
        error_report("EXeSX %s invalid (expect 0..0xffffffff)", name);
        exit(1);
    }
    return (uint32_t)value;
}

/*
 * Optional host-controlled board voltage input. Poll a user-owned plain-text
 * hex/decimal file at most every 20ms of guest virtual time, allowing a
 * private researcher to change external pin levels after initial boot.
 * Missing/temporarily invalid files leave the last accepted mask unchanged.
 * No guest RAM, device response, IRQ, or output GPIO direction is changed.
 */
static uint32_t exesx_live_external_gpio_input_mask(const char *mask_env,
                                                     const char *file_env,
                                                     uint32_t *cached,
                                                     int64_t *next_read_ns,
                                                     bool *initialized)
{
    const char *path = g_getenv(file_env);
    int64_t now;
    gchar *content = NULL;
    char *end;
    uint64_t parsed;

    if (!path || !*path) {
        return exesx_external_gpio_input_mask(mask_env);
    }
    if (!*initialized) {
        *cached = exesx_external_gpio_input_mask(mask_env);
        *initialized = true;
    }
    now = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    if (now < *next_read_ns) {
        return *cached;
    }
    *next_read_ns = now + INT64_C(20000000);
    if (g_file_get_contents(path, &content, NULL, NULL)) {
        g_strstrip(content);
        if (*content) {
            parsed = g_ascii_strtoull(content, &end, 0);
            if (*end == '\0' && parsed <= UINT32_MAX) {
                *cached = (uint32_t)parsed;
            }
        }
        g_free(content);
    }
    return *cached;
}

static uint32_t exesx_gpiob_external_input_mask(EXeSXState *board)
{
    static uint32_t cached;
    static int64_t next_read_ns;
    static bool initialized;
    uint32_t levels = exesx_live_external_gpio_input_mask(
        "EXESX_GPIOB_INPUT_MASK", "EXESX_GPIOB_INPUT_MASK_FILE",
        &cached, &next_read_ns, &initialized);

    /*
     * Original A7 FUN_60035250 samples M4 GPIOB PDIR bit14,
     * inverts it, and publishes the SD card-detect byte at 0x2f029214.
     * This is a separate physical contact from the USDHC CINST flag.
     *
     * Tie PTB14 to the installed SD medium ONLY when explicitly requested;
     * preserve legacy diagnostic GPIO masks otherwise. Active-low:
     * inserted -> PDIR14=0, no card -> PDIR14=1. Normal GPIO PDDR
     * output priority and PORT edge/interrupt handling still apply.
     */
    if (!g_strcmp0(g_getenv("EXESX_USDHC0_SD_DETECT_GPIO"), "1")) {
        if (!g_strcmp0(g_getenv("EXESX_USDHC0_SD"), "1")) {
            levels &= ~UINT32_C(0x00004000);
        } else {
            levels |= UINT32_C(0x00004000);
        }
    }
    return exesx_bu21029_gpio_b_levels(board, levels);
}

static uint32_t exesx_gpioa_external_input_mask(void)
{
    static uint32_t cached;
    static int64_t next_read_ns;
    static bool initialized;
    return exesx_live_external_gpio_input_mask(
        "EXESX_GPIOA_INPUT_MASK", "EXESX_GPIOA_INPUT_MASK_FILE",
        &cached, &next_read_ns, &initialized);
}

/*
 * Model the *external* PORT pin input edges while the original M4 sleeps
 * in RTOS flag wait. PDIR read interception alone is insufficient: the
 * CPU cannot notice a newly closed contact without a hardware IRQ.
 * PORT PCR.IRQC and ISFR remain the authoritative interrupt source.
 */
static void exesx_m4_port_tick(void *opaque)
{
    EXeSXProfileWindow *port = opaque;
    EXeSXState *b = port->board;
    EXeSXProfileWindow *gpio = port->base == 0x4103f000 ?
                               b->m4_gpio_a : b->m4_gpio_b;
    uint32_t external, levels, pddr;
    if (gpio) {
        external = port->base == 0x4103f000 ?
                   exesx_gpioa_external_input_mask() :
                   exesx_gpiob_external_input_mask(b);
        external = exesx_m4_keyboard_column_levels(gpio, external);
        pddr = gpio->regfile[0x14 / 4];
        levels = (gpio->regfile[0] & pddr) | (external & ~pddr);
        exesx_m4_port_observe_inputs(port, levels);
    }
    timer_mod(port->m4_port_poll_timer,
              qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) +
              ((g_getenv("EXESX_M4_KEY_MATRIX_FILE") ||
                g_getenv("EXESX_BU21029_TOUCH_FILE")) ?
               INT64_C(1000000) : INT64_C(20000000)));
}

static bool exesx_imx7ulp_kind(const char *kind)
{
    return g_strcmp0(kind, "imx7ulp-pcc") == 0 ||
           g_strcmp0(kind, "imx7ulp-gpio") == 0 ||
           g_strcmp0(kind, "imx7ulp-pctl") == 0 ||
           g_strcmp0(kind, "imx7ulp-iomuxc") == 0 ||
           g_strcmp0(kind, "imx7ulp-flexbus") == 0 ||
           g_strcmp0(kind, "imx7ulp-smc") == 0 ||
           g_strcmp0(kind, "imx7ulp-sim") == 0 ||
           g_strcmp0(kind, "imx7ulp-scg1") == 0 ||
           g_strcmp0(kind, "imx7ulp-scg0") == 0 ||
           g_strcmp0(kind, "imx7ulp-tpm") == 0 ||
           g_strcmp0(kind, "imx7ulp-pmc1") == 0 ||
           g_strcmp0(kind, "imx7ulp-pmc0") == 0 ||
           g_strcmp0(kind, "imx7ulp-port") == 0 ||
           g_strcmp0(kind, "imx7ulp-lpit") == 0 ||
           g_strcmp0(kind, "imx7ulp-lptmr") == 0 ||
           g_strcmp0(kind, "imx7ulp-mu") == 0 ||
           g_strcmp0(kind, "imx7ulp-snvs") == 0 ||
           g_strcmp0(kind, "imx7ulp-lpi2c") == 0 ||
           g_strcmp0(kind, "imx7ulp-adc") == 0 ||
           g_strcmp0(kind, "imx7ulp-i2s") == 0 ||
           g_strcmp0(kind, "imx7ulp-dma") == 0 ||
           g_strcmp0(kind, "imx7ulp-usdhc") == 0 ||
           g_strcmp0(kind, "imx7ulp-usdhc1") == 0 ||
           g_strcmp0(kind, "imx7ulp-dmamux") == 0 ||
           g_strcmp0(kind, "imx7ulp-lpspi") == 0 ||
           g_strcmp0(kind, "imx7ulp-sema42") == 0 ||
           g_strcmp0(kind, "imx7ulp-wdog") == 0 ||
           g_strcmp0(kind, "imx7ulp-tstmr") == 0;
}

/*
 * Only address offsets present in MCUXpresso i.MX7ULP fsl_clock.h.
 * Generic echoes of undocumented offsets would mask missing peripherals.
 */
/*
 * Valid IOMUXC1 mux/pad/select-input register offsets extracted from NXP
 * MCIMX7U5 fsl_iomuxc.h (six contiguous runs). Do not map reserved gaps.
 */
/*
 * IOMUXC0 (real-time domain) valid mux/pad addresses from NXP's
 * i.MX7ULP fsl_iomuxc.h. 128 allowed word registers in three blocks.
 * M4 firmware programs +0x194 during port setup.
 */
static bool exesx_imx7ulp_iomuxc0_offset(hwaddr off)
{
    return !(off & 3) &&
           (off <= 0xcc ||
            (off >= 0x100 && off <= 0x228) ||
            off == 0x294);
}

static bool exesx_imx7ulp_iomuxc_offset(hwaddr off)
{
    return !(off & 3) &&
           ((off <= 0x4c) ||
            (off >= 0x80 && off <= 0xac) ||
            (off >= 0x100 && off <= 0x13c) ||
            (off >= 0x180 && off <= 0x1cc) ||
            (off >= 0x200 && off <= 0x33c) ||
            (off == 0x39c));
}

static bool exesx_imx7ulp_pcc_present(uint64_t base, hwaddr off)
{
    static const uint16_t pcc0[] = {
        0x20, 0x3c, 0x50, 0x6c, 0x80, 0x88, 0x94, 0xa4, 0xa8,
        0xb0, 0xb4, 0xb8, 0xbc, 0xc0, 0xc4, 0xc8, 0xcc, 0xd0,
        0xd4, 0xd8, 0xdc, 0xe0, 0xe4, 0xe8, 0xec, 0xfc,
        0x100, 0x104, 0x108, 0x10c, 0x110, 0x114, 0x1c0
    };
    static const uint16_t pcc1[] = {
        0x50, 0x94, 0xa0, 0xa4, 0xa8, 0xac, 0xb0, 0xb4
    };
    static const uint16_t pcc2[] = {
        0x20, 0x3c, 0x40, 0x6c, 0x84, 0x90, 0x94, 0x98, 0x9c,
        0xa4, 0xa8, 0xac, 0xb0, 0xb4, 0xb8, 0xc4, 0xcc, 0xd0,
        0xd4, 0xd8, 0xdc, 0xe0, 0xf4, 0x10c
    };
    static const uint16_t pcc3[] = {
        0x84, 0x88, 0x90, 0x94, 0x98, 0x9c, 0xa0, 0xa4, 0xa8,
        0xac, 0xb8, 0xbc, 0xc0, 0xc4, 0x140, 0x144
    };
    const uint16_t *list = NULL;
    size_t n = 0, i;
    switch (base) {
    case 0x41026000:
        list = pcc0; n = G_N_ELEMENTS(pcc0); break;
    case 0x410b2000:
        list = pcc1; n = G_N_ELEMENTS(pcc1); break;
    case 0x403f0000:
        list = pcc2; n = G_N_ELEMENTS(pcc2); break;
    case 0x40b30000:
        list = pcc3; n = G_N_ELEMENTS(pcc3); break;
    default:
        return false;
    }
    for (i = 0; i < n; i++) {
        if (off == list[i]) {
            return true;
        }
    }
    return false;
}

/* FB CS0..CS5 each have CSAR/CSMR/CSCR; one CSPMCR at +0x60. */
/* Permitted SIM offsets from NXP PERI_SIM.h; unknown offsets fault. */
static bool exesx_imx7ulp_sim_offset(hwaddr off)
{
    return off == 0 || off == 4 || off == 0xc || off == 0x28 ||
           off == 0x2c || off == 0x30 || off == 0x3c ||
           (off >= 0x50 && off <= 0x80 && !(off & 3)) ||
           off == 0x88 || off == 0x8c || off == 0x90 ||
           off == 0x94 || off == 0x98;
}

static bool exesx_imx7ulp_flexbus_offset(hwaddr off)
{
    return !(off & 3) && (off < 6 * 0xc || off == 0x60);
}

static MemTxResult exesx_imx7ulp_read(EXeSXProfileWindow *w,
                                      hwaddr off, uint64_t *value,
                                      unsigned size)
{
    uint32_t index = off / 4;
    if (!strcmp(w->kind, "imx7ulp-sema42")) {
        return exesx_sema42_read(w, off, value, size);
    }
    if (!strcmp(w->kind, "imx7ulp-dma")) {
        return exesx_dma0_read(w, off, value, size);
    }
    if (!strcmp(w->kind, "imx7ulp-dmamux")) {
        return exesx_dmamux1_read(w, off, value, size);
    }
    if (size != 4 || (off & 3) || off >= w->size) {
        return MEMTX_ERROR;
    }

    if (!strcmp(w->kind, "imx7ulp-adc")) {
        return exesx_adc_read(w, off, value, size);
    }
    if (!strcmp(w->kind, "imx7ulp-i2s")) {
        return exesx_i2s_read(w, off, value, size);
    }
    if (!strcmp(w->kind, "imx7ulp-usdhc")) {
        return exesx_usdhc0_read(w, off, value, size);
    }
    if (!strcmp(w->kind, "imx7ulp-usdhc1")) {
        return exesx_usdhc1_read(w, off, value, size);
    }
    if (!strcmp(w->kind, "imx7ulp-lpspi")) {
        return exesx_lpspi2_read(w, off, value, size);
    }
    if (!strcmp(w->kind, "imx7ulp-lpi2c")) {
        return exesx_lpi2c_read(w, off, value, size);
    }
    if (!strcmp(w->kind, "imx7ulp-snvs")) {
        return exesx_snvs_hp_read(w, off, value, size);
    }
    if (!strcmp(w->kind, "imx7ulp-mu")) {
        return exesx_mu_read(w, off, value, size);
    }
    if (!strcmp(w->kind, "imx7ulp-lptmr")) {
        return exesx_lptmr_read(w, off, value, size);
    }
    if (!strcmp(w->kind, "imx7ulp-lpit")) {
        return exesx_lpit_read(w, off, value, size);
    }
    if (!strcmp(w->kind, "imx7ulp-port")) {
        return exesx_port_read(w, off, value, size);
    }
    if (!strcmp(w->kind, "imx7ulp-pmc0")) {
        return exesx_imx7ulp_pmc0_read(w, off, value, size);
    }
    if (!strcmp(w->kind, "imx7ulp-pmc1")) {
        return exesx_imx7ulp_pmc1_read(w, off, value, size);
    }
    if (!strcmp(w->kind, "imx7ulp-tpm")) {
        return exesx_tpm_read(w, off, value, size);
    }
    if (!strcmp(w->kind, "imx7ulp-scg1") ||
        !strcmp(w->kind, "imx7ulp-scg0")) {
        return exesx_scg1_read(w, off, value, size);
    }
    if (!strcmp(w->kind, "imx7ulp-sim")) {
        if (w->base != 0x410a3000 ||
            !exesx_imx7ulp_sim_offset(off)) {
            return MEMTX_ERROR;
        }
        *value = w->regfile[index];
        return MEMTX_OK;
    }
    if (!strcmp(w->kind, "imx7ulp-smc")) {
        /* SMC0 register layout from NXP PERI_SMC.h. */
        switch (off) {
        case 0x00: /* VERID */ *value = 0x000000aa; break;
        case 0x04: /* PARAM */ *value = 0; break;
        case 0x08: /* PMPROT */ case 0x10: /* PMCTRL */
        case 0x24: /* RPC */ case 0x28: /* SSRS */
        case 0x2c: /* SRIE */ case 0x30: /* SRIF */
        case 0x34: /* CSRE */ case 0x60: /* FM */
            *value = w->regfile[index]; break;
        case 0x18: /* PMSTAT */ case 0x40: /* MR */
            *value = 1; break; /* RUN mode, not a full PM controller */
        case 0x20: /* SRS */ *value = 0; break;
        default: return MEMTX_ERROR;
        }
        return MEMTX_OK;
    }
    if (!strcmp(w->kind, "imx7ulp-wdog")) {
        if (off > 0x0c) {
            return MEMTX_ERROR;
        }
        *value = w->regfile[index];
        return MEMTX_OK;
    }
    if (!strcmp(w->kind, "imx7ulp-tstmr")) {
        uint64_t ns = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
        uint64_t ticks = ns / 1000;
        /*
         * Original M4 FUN_1FFD4D04 repeatedly reads both halves of
         * TSTMR at 0x410A3C00 and retries if the upper bits of the
         * low word change during the read sequence. The previous
         * uncalibrated 1 MHz clock causes tens of thousands of retries
         * in genuine firmware runs. Compare lower clock hypotheses
         * without altering guest instructions, RAM or mailbox traffic.
         * Default is unchanged. Host option is DIAGNOSTIC ONLY.
         */
        const char *clock = g_getenv("EXESX_DIAGNOSTIC_M4_TSTMR_KHZ");
        if (w->base == UINT64_C(0x410a3c00) && clock && *clock) {
            char *end;
            uint64_t khz = g_ascii_strtoull(clock, &end, 0);
            if (*end == '\0' && khz >= 1 && khz <= 1000) {
                ticks = (ns / 1000000) * khz +
                        ((ns % 1000000) * khz) / 1000000;
            }
        }
        if (off != 0 && off != 4) {
            return MEMTX_ERROR;
        }
        *value = (off == 0) ? (uint32_t)ticks : (uint32_t)(ticks >> 32);
        return MEMTX_OK;
    }
    if (!strcmp(w->kind, "imx7ulp-gpio")) {
        switch (off) {
        case 0x00: /* PDOR */
            *value = w->regfile[0];
            return MEMTX_OK;
        case 0x04: /* PSOR: write-one-to-set, not storage */
        case 0x08: /* PCOR */
        case 0x0c: /* PTOR */
            *value = 0;
            return MEMTX_OK;
        case 0x10: { /* PDIR: read pin voltage, not output latch alone */
            uint32_t output_direction = w->regfile[0x14 / 4];
            uint32_t output_levels = w->regfile[0] & output_direction;
            uint32_t external_inputs =
                w->base == UINT64_C(0x4100f000) ?
                exesx_gpioa_external_input_mask() :
                w->base == UINT64_C(0x4100f040) ?
                exesx_gpiob_external_input_mask(w->board) : 0;
            if (w->base == UINT64_C(0x4100f000) ||
                w->base == UINT64_C(0x4100f040)) {
                external_inputs = exesx_m4_keyboard_column_levels(
                    w, external_inputs);
            }
            if (w->base == UINT64_C(0x400f00c0) &&
                exesx_lcd_te_high(w->board)) {
                external_inputs |= 1U << 13;
            }
            *value = output_levels | (external_inputs & ~output_direction);
            return MEMTX_OK;
        }
        case 0x14: /* PDDR */
            *value = w->regfile[index];
            return MEMTX_OK;
        default:
            return MEMTX_ERROR;
        }
    }
    if (!strcmp(w->kind, "imx7ulp-flexbus")) {
        if (w->base != 0x40100000 ||
            !exesx_imx7ulp_flexbus_offset(off)) {
            return MEMTX_ERROR;
        }
        *value = w->regfile[index];
        return MEMTX_OK;
    }
    if (!strcmp(w->kind, "imx7ulp-iomuxc")) {
        if (w->base != 0x40ac0000 ||
            !exesx_imx7ulp_iomuxc_offset(off)) {
            return MEMTX_ERROR;
        }
        *value = w->regfile[index];
        return MEMTX_OK;
    }
    if (!strcmp(w->kind, "imx7ulp-pctl")) {
        /* Historical model name for IOMUXC0 at 0x4103d000. */
        if (w->base != 0x4103d000 ||
            !exesx_imx7ulp_iomuxc0_offset(off)) {
            return MEMTX_ERROR;
        }
        *value = w->regfile[index];
        return MEMTX_OK;
    }
    if (!strcmp(w->kind, "imx7ulp-pcc")) {
        /* Only the gate registers observed in the BIOS, not full clock tree. */
        if (exesx_imx7ulp_pcc_present(w->base, off)) {
            /* Present bit 31 (PR) is read-only; all listed modules exist. */
            *value = w->regfile[index] | UINT32_C(0x80000000);
            return MEMTX_OK;
        }
        return MEMTX_ERROR;
    }
    return MEMTX_ERROR;
}

static MemTxResult exesx_imx7ulp_write(EXeSXProfileWindow *w,
                                       hwaddr off, uint64_t value,
                                       unsigned size)
{
    uint32_t index = off / 4;
    uint32_t bits = (uint32_t)value;
    if (!strcmp(w->kind, "imx7ulp-sema42")) {
        return exesx_sema42_write(w, off, value, size);
    }
    if (!strcmp(w->kind, "imx7ulp-dma")) {
        return exesx_dma0_write(w, off, value, size);
    }
    if (!strcmp(w->kind, "imx7ulp-dmamux")) {
        return exesx_dmamux1_write(w, off, value, size);
    }
    if (size != 4 || (off & 3) || off >= w->size) {
        return MEMTX_ERROR;
    }

    if (!strcmp(w->kind, "imx7ulp-adc")) {
        return exesx_adc_write(w, off, value, size);
    }
    if (!strcmp(w->kind, "imx7ulp-i2s")) {
        return exesx_i2s_write(w, off, value, size);
    }
    if (!strcmp(w->kind, "imx7ulp-usdhc")) {
        return exesx_usdhc0_write(w, off, value, size);
    }
    if (!strcmp(w->kind, "imx7ulp-usdhc1")) {
        return exesx_usdhc1_write(w, off, value, size);
    }
    if (!strcmp(w->kind, "imx7ulp-lpspi")) {
        return exesx_lpspi2_write(w, off, value, size);
    }
    if (!strcmp(w->kind, "imx7ulp-lpi2c")) {
        return exesx_lpi2c_write(w, off, value, size);
    }
    if (!strcmp(w->kind, "imx7ulp-snvs")) {
        return exesx_snvs_hp_write(w, off, value, size);
    }
    if (!strcmp(w->kind, "imx7ulp-mu")) {
        return exesx_mu_write(w, off, value, size);
    }
    if (!strcmp(w->kind, "imx7ulp-lptmr")) {
        return exesx_lptmr_write(w, off, value, size);
    }
    if (!strcmp(w->kind, "imx7ulp-lpit")) {
        return exesx_lpit_write(w, off, value, size);
    }
    if (!strcmp(w->kind, "imx7ulp-port")) {
        return exesx_port_write(w, off, value, size);
    }
    if (!strcmp(w->kind, "imx7ulp-pmc0")) {
        return exesx_imx7ulp_pmc0_write(w, off, value, size);
    }
    if (!strcmp(w->kind, "imx7ulp-pmc1")) {
        return exesx_imx7ulp_pmc1_write(w, off, value, size);
    }
    if (!strcmp(w->kind, "imx7ulp-tpm")) {
        return exesx_tpm_write(w, off, value, size);
    }
    if (!strcmp(w->kind, "imx7ulp-scg1") ||
        !strcmp(w->kind, "imx7ulp-scg0")) {
        return exesx_scg1_write(w, off, value, size);
    }
    if (!strcmp(w->kind, "imx7ulp-sim")) {
        /*
         * SIM_DGO_CTRL0/1: GP update request bits 0..5/0..4
         * set hardware WR_ACK bits 13..18/13..17 once shadowed in
         * DGO domain. ACK flags are software write-one-to-clear.
         * Model the transfer as immediately completed; no DGO clock
         * latency or deep-power state transition has been validated.
         * Source: NXP i.MX7ULP CMSIS PERI_SIM.h.
         */
        if (w->base != 0x410a3000 ||
            !exesx_imx7ulp_sim_offset(off) || off == 0x8c) {
            return MEMTX_ERROR;
        }
        if (off == 0x50 || off == 0x54) {
            uint32_t update_mask = off == 0x50 ? 0x3f : 0x1f;
            uint32_t ack_mask = update_mask << 13;
            uint32_t updates = bits & update_mask;
            uint32_t old = w->regfile[index];
            uint32_t ack = (old & ack_mask) & ~(bits & ack_mask);
            ack |= updates << 13;
            /* Preserve writable IRQ enables, but not strobe requests. */
            w->regfile[index] = (bits & ~(update_mask | ack_mask)) |
                                (ack & ack_mask);
            qemu_log_mask(LOG_GUEST_ERROR,
                          "EXeSX SIM DGO update @0x%" HWADDR_PRIx
                          " requested=0x%x ack=0x%x\\n",
                          w->base + off, updates, ack);
            /*
             * In i.MX7ULP Single Boot the CA7 advertises the CM4 entry
             * via DGO_GP7 and the CM4 ROM then branches to that image.
             * Omit the ROM stage only when explicitly opted in.
             */
            if (off == 0x54 && (updates & 1) && w->board) {
                exesx_m4_rom_handoff(w->board, w->regfile[0x70 / 4]);
            }
        } else {
            w->regfile[index] = bits;
        }
        return MEMTX_OK;
    }
    if (!strcmp(w->kind, "imx7ulp-smc")) {
        if (off != 0x08 && off != 0x10 && off != 0x24 &&
            off != 0x28 && off != 0x2c && off != 0x30 &&
            off != 0x34 && off != 0x60) {
            return MEMTX_ERROR;
        }
        if (off == 0x28 || off == 0x30) {
            /* Sticky reset / interrupt status flag: write-one-to-clear. */
            w->regfile[index] &= ~bits;
        } else {
            w->regfile[index] = bits;
        }
        return MEMTX_OK;
    }
    if (!strcmp(w->kind, "imx7ulp-wdog")) {
        if (off > 0x0c) {
            return MEMTX_ERROR;
        }
        if (off == 0x04) { /* CNT: unlock sequence C520/D928 */
            if (bits == 0xc520) {
                w->regfile[0x3c / 4] = 1;
            } else if (bits == 0xd928 && w->regfile[0x3c / 4]) {
                w->regfile[0] |= 0x800;  /* CS.ULK */
                w->regfile[0x3c / 4] = 0;
            } else {
                w->regfile[0x3c / 4] = 0;
            }
        } else if (off == 0) {
            if (!(w->regfile[0] & 0x800)) {
                qemu_log_mask(LOG_GUEST_ERROR,
                              "EXeSX WDOG CS write while locked @0x%"
                              HWADDR_PRIx "\\n", w->base);
                return MEMTX_ERROR;
            }
            /* EN/UPDATE/CLK configured; RCS succeeds, ULK locks again. */
            w->regfile[0] = (bits & ~UINT32_C(0xc00)) | 0x400;
        } else {
            w->regfile[index] = bits;
        }
        qemu_log_mask(LOG_GUEST_ERROR,
                      "EXeSX WDOG WRITE @0x%" HWADDR_PRIx
                      " data=0x%08x CS=0x%08x\n",
                      w->base + off, bits, w->regfile[0]);
        return MEMTX_OK;
    }
    if (!strcmp(w->kind, "imx7ulp-tstmr")) {
        return MEMTX_ERROR; /* Read-only 64-bit timestamp timer. */
    }
    if (!strcmp(w->kind, "imx7ulp-gpio")) {
        if (w->base == 0x400f0000) {
            exesx_lcd_gpioa(w->board, off, bits);
        }
        switch (off) {
        case 0x00: w->regfile[0] = bits; break;
        case 0x04: w->regfile[0] |= bits; break; /* PSOR */
        case 0x08:
            w->regfile[0] &= ~bits; /* PCOR */
            exesx_m4_keyboard_row_drive(w->board, w->base, bits);
            break;
        case 0x0c: w->regfile[0] ^= bits; break; /* PTOR */
        case 0x14: w->regfile[index] = bits; break; /* PDDR */
        default: return MEMTX_ERROR;
        }
    } else if (!strcmp(w->kind, "imx7ulp-flexbus")) {
        if (w->base != 0x40100000 ||
            !exesx_imx7ulp_flexbus_offset(off)) {
            return MEMTX_ERROR;
        }
        /*
         * Record control register programming. The FlexBus external
         * target/CS decode is not modeled; it must remain separate.
         */
        w->regfile[index] = bits;
    } else if (!strcmp(w->kind, "imx7ulp-iomuxc")) {
        if (w->base != 0x40ac0000 ||
            !exesx_imx7ulp_iomuxc_offset(off)) {
            return MEMTX_ERROR;
        }
        w->regfile[index] = bits;
    } else if (!strcmp(w->kind, "imx7ulp-pctl")) {
        if (w->base != 0x4103d000 ||
            !exesx_imx7ulp_iomuxc0_offset(off)) {
            return MEMTX_ERROR;
        }
        w->regfile[index] = bits;
    } else if (!strcmp(w->kind, "imx7ulp-pcc")) {
        if (!exesx_imx7ulp_pcc_present(w->base, off)) {
            return MEMTX_ERROR;
        }
        /* CGC bit 30 writable; INUSE bit 29 / PR bit 31 read-only. */
        w->regfile[index] = bits & ~UINT32_C(0xa0000000);
    } else {
        return MEMTX_ERROR;
    }
    qemu_log_mask(LOG_GUEST_ERROR,
                  "EXeSX i.MX7ULP %s WRITE @0x%" HWADDR_PRIx
                  " data=0x%08x\n", w->kind, w->base + off, bits);
    return MEMTX_OK;
}
