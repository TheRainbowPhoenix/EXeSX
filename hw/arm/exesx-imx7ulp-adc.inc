/*
 * i.MX7ULP ADC0/ADC1 register bank (NXP PERI_ADC.h, ADC_Type).
 *
 * Models register configuration, controller/FIFO reset strobes, write-one-
 * to-clear status and explicitly empty result FIFO. No fabricated analog
 * samples: until an analog input is modeled, SW trigger logs a warning and
 * the result FIFO remains empty (RESFIFO.VALID=0).
 *
 * Supports both 0x41041000 (ADC0) and 0x410ad000 (ADC1).
 * All software-visible state is in VMState-backed w->regfile.
 */
static bool exesx_adc_register(hwaddr off)
{
    if (off == 0 || off == 4 ||
        (off >= 0x10 && off <= 0x24 && !(off & 3)) ||
        off == 0x30 || off == 0x34 || off == 0x300) {
        return true;
    }
    if ((off == 0xc0 || off == 0xc4) ||
        (off >= 0x100 && off < 0x178 && !(off & 3)) ||
        (off >= 0x200 && off <= 0x20c && !(off & 3))) {
        return true;
    }
    return false;
}

static bool exesx_adc_valid(EXeSXProfileWindow *w,
                            hwaddr off, unsigned size)
{
    return size == 4 && off < w->size &&
           (w->base == 0x41041000 || w->base == 0x410ad000) &&
           exesx_adc_register(off);
}

static MemTxResult exesx_adc_read(EXeSXProfileWindow *w,
                                 hwaddr off, uint64_t *data, unsigned size)
{
    if (!exesx_adc_valid(w, off, size)) {
        return MEMTX_ERROR;
    }
    if (off == 0x300) {
        /* No analog samples injected. VALID=0; this is NOT a chip ID. */
        *data = 0;
    } else if (off == 0x30) {
        /* FIFO count is hardware-provided and currently always empty. */
        *data = w->regfile[off / 4] & ~UINT32_C(0x1f);
    } else if (off == 0x34) {
        *data = 0; /* software-trigger command auto clears */
    } else {
        *data = w->regfile[off / 4];
    }
    return MEMTX_OK;
}

static MemTxResult exesx_adc_write(EXeSXProfileWindow *w, hwaddr off,
                                  uint64_t value, unsigned size)
{
    uint32_t word = (uint32_t)value;
    if (!exesx_adc_valid(w, off, size) ||
        off == 0 || off == 4 || off == 0x300) {
        return MEMTX_ERROR;
    }
    if (off == 0x10) {
        /* ADC_CTRL.RST (bit1) and RSTFIFO (bit8) are command strobes. */
        if (word & 2) {
            for (unsigned i = 0; i < 15; ++i) {
                w->regfile[(0x100 + i * 8) / 4] = 0;
                w->regfile[(0x104 + i * 8) / 4] = 0;
            }
            w->regfile[0x14 / 4] = 0; /* STAT */
            w->regfile[0x30 / 4] = 0; /* FCTRL */
        }
        if (word & 0x100) {
            w->regfile[0x14 / 4] &= ~3U; /* Ready/overflow clear */
        }
        w->regfile[off / 4] = word & ~UINT32_C(0x102);
    } else if (off == 0x14) {
        /* Ready/overflow and trigger completion bits: sticky W1C. */
        w->regfile[off / 4] &= ~word;
    } else if (off == 0x34) {
        if (word) {
            qemu_log_mask(LOG_GUEST_ERROR,
                          "EXeSX ADC @0x%" HWADDR_PRIx
                          " SW trigger=0x%08x (analog source not modeled)\n",
                          w->base, word);
        }
        w->regfile[off / 4] = 0;
    } else if (off == 0x30) {
        /* FIFO count is hardware-owned; watermark is writable. */
        w->regfile[off / 4] = word & ~UINT32_C(0x1f);
    } else {
        w->regfile[off / 4] = word;
    }
    qemu_log_mask(LOG_GUEST_ERROR,
                  "EXeSX ADC WRITE @0x%" HWADDR_PRIx " =0x%08x\n",
                  w->base + off, word);
    return MEMTX_OK;
}
