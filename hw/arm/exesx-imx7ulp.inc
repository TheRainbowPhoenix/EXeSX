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

static bool exesx_imx7ulp_kind(const char *kind)
{
    return g_strcmp0(kind, "imx7ulp-pcc") == 0 ||
           g_strcmp0(kind, "imx7ulp-gpio") == 0 ||
           g_strcmp0(kind, "imx7ulp-pctl") == 0 ||
           g_strcmp0(kind, "imx7ulp-tstmr") == 0;
}

/*
 * Only address offsets present in MCUXpresso i.MX7ULP fsl_clock.h.
 * Generic echoes of undocumented offsets would mask missing peripherals.
 */
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

static MemTxResult exesx_imx7ulp_read(EXeSXProfileWindow *w,
                                      hwaddr off, uint64_t *value,
                                      unsigned size)
{
    uint32_t index = off / 4;
    if (size != 4 || (off & 3) || off >= w->size) {
        return MEMTX_ERROR;
    }
    if (!strcmp(w->kind, "imx7ulp-tstmr")) {
        uint64_t ticks = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) / 1000;
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
        case 0x10: /* PDIR: output pins loop back, no input attached */
            *value = w->regfile[0] & w->regfile[0x14 / 4];
            return MEMTX_OK;
        case 0x14: /* PDDR */
            *value = w->regfile[index];
            return MEMTX_OK;
        default:
            return MEMTX_ERROR;
        }
    }
    if (!strcmp(w->kind, "imx7ulp-pctl")) {
        /* Port pin control PCR[n]. Partial pinmux/drive configuration. */
        if (off < 0x80) {
            *value = w->regfile[index];
            return MEMTX_OK;
        }
        return MEMTX_ERROR;
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
    if (size != 4 || (off & 3) || off >= w->size) {
        return MEMTX_ERROR;
    }
    if (!strcmp(w->kind, "imx7ulp-tstmr")) {
        return MEMTX_ERROR; /* Read-only 64-bit timestamp timer. */
    }
    if (!strcmp(w->kind, "imx7ulp-gpio")) {
        switch (off) {
        case 0x00: w->regfile[0] = bits; break;
        case 0x04: w->regfile[0] |= bits; break; /* PSOR */
        case 0x08: w->regfile[0] &= ~bits; break; /* PCOR */
        case 0x0c: w->regfile[0] ^= bits; break; /* PTOR */
        case 0x14: w->regfile[index] = bits; break; /* PDDR */
        default: return MEMTX_ERROR;
        }
    } else if (!strcmp(w->kind, "imx7ulp-pctl")) {
        if (off >= 0x80) {
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
