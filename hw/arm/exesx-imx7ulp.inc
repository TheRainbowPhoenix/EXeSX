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
        if ((w->base == 0x41026000 &&
             (off == 0x3c || off == 0xfc || off == 0x100)) ||
            (w->base == 0x403f0000 && off == 0x40)) {
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
        if (!((w->base == 0x41026000 &&
               (off == 0x3c || off == 0xfc || off == 0x100)) ||
              (w->base == 0x403f0000 && off == 0x40))) {
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
