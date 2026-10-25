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

/*
 * Diagnostic-only ADC conversion path. A Casio analog voltage must never be
 * invented: without EXESX_ADC{0,1}_SAMPLE_RAW, conversion FIFO remains empty
 * exactly as before. The input is a user-provided 16-bit ADC result, not a
 * presumed voltage or calibration value. This models digital ADC result/FIFO
 * and IRQ plumbing to test the ORIGINAL M4 ADC ISR and factory IPC.
 *
 * i.MX7ULP: TCTRLn.TCMD at bits24..27 (original guest=0x01000000),\n * NVIC ADC0=58 / ADC1=59; RESFIFO0 VALID bit31;
 * FCTRL.FCOUNT0 bits0..4, FWMARK0 bits16..20; IE.FWMIE0 bit0;
 * STAT.RDY0 bit0 becomes set when FCOUNT0 > FWMARK0.
 * This single-FIFO proof is not a complete analog peripheral emulator.
 * FIFO contents are kept in unused high regfile words and migrate via VMState.
 */
#define EXESX_ADC_FIFO_MAX 16U
#define EXESX_ADC_FIFO_DATA 0x310U
static qemu_irq exesx_adc_irq(EXeSXProfileWindow *w)
{
    return w->board ? (w->base == 0x41041000 ?
                         w->board->adc0_irq : w->board->adc1_irq) : NULL;
}
static uint32_t exesx_adc_fifo_count(EXeSXProfileWindow *w)
{
    return w->regfile[0x30 / 4] & 0x1fU;
}
static void exesx_adc_sync_fifo_irq(EXeSXProfileWindow *w)
{
    uint32_t count = exesx_adc_fifo_count(w);
    uint32_t watermark = (w->regfile[0x30 / 4] >> 16) & 0x1fU;
    qemu_irq line = exesx_adc_irq(w);

    if (count > watermark) {
        w->regfile[0x14 / 4] |= 1; /* STATUS.RDY0 is hardware-owned */
    } else {
        w->regfile[0x14 / 4] &= ~UINT32_C(1);
    }
    if (line) {
        qemu_set_irq(line, !!((w->regfile[0x14 / 4] & 1) &&
                             (w->regfile[0x18 / 4] & 1)));
    }
}
static bool exesx_adc_explicit_sample(EXeSXProfileWindow *w, uint16_t *sample)
{
    const char *name = w->base == 0x41041000 ?
        "EXESX_ADC0_SAMPLE_RAW" : "EXESX_ADC1_SAMPLE_RAW";
    const char *s = g_getenv(name);
    char *end;
    uint64_t value;

    if (!s || !*s) {
        return false;
    }
    value = g_ascii_strtoull(s, &end, 0);
    if (*end || value > UINT16_MAX) {
        error_report("%s must be an unsigned 16-bit explicit raw sample", name);
        exit(1);
    }
    *sample = (uint16_t)value;
    return true;
}
static void exesx_adc_fifo_push(EXeSXProfileWindow *w, uint16_t sample,
                                 unsigned trig)
{
    uint32_t count = exesx_adc_fifo_count(w);

    if (count >= EXESX_ADC_FIFO_MAX) {
        w->regfile[0x14 / 4] |= 2; /* FIFO overflow */
        return;
    }
    /* Original ADC reports source command and trigger IDs in RESFIFO. */
    unsigned cmd = (w->regfile[(0xc0 + trig * 4) / 4] >> 24) & 0xf;
    w->regfile[(EXESX_ADC_FIFO_DATA / 4) + count] =
        UINT32_C(0x80000000) | ((cmd & 0xf) << 24) |
        ((trig & 0x7) << 16) | sample;
    w->regfile[0x30 / 4] = (w->regfile[0x30 / 4] & ~UINT32_C(0x1f)) |
                            (count + 1);
    exesx_adc_sync_fifo_irq(w);
}
static MemTxResult exesx_adc_read(EXeSXProfileWindow *w,
                                 hwaddr off, uint64_t *data, unsigned size)
{
    if (!exesx_adc_valid(w, off, size)) {
        return MEMTX_ERROR;
    }
    if (off == 0x300) {
        uint32_t count = exesx_adc_fifo_count(w);
        *data = count ? w->regfile[EXESX_ADC_FIFO_DATA / 4] : 0;
        if (count) {
            memmove(&w->regfile[EXESX_ADC_FIFO_DATA / 4],
                    &w->regfile[EXESX_ADC_FIFO_DATA / 4 + 1],
                    (count - 1) * sizeof(uint32_t));
            w->regfile[0x30 / 4] = (w->regfile[0x30 / 4] & ~UINT32_C(0x1f)) |
                                    (count - 1);
            exesx_adc_sync_fifo_irq(w);
        }
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
        if (word & 2) { /* reset controller, command buffers and FIFO */
            for (unsigned i = 0; i < 15; ++i) {
                w->regfile[(0x100 + i * 8) / 4] = 0;
                w->regfile[(0x104 + i * 8) / 4] = 0;
            }
            w->regfile[0x14 / 4] = 0;
            w->regfile[0x30 / 4] = 0;
        }
        if (word & 0x100) {
            w->regfile[0x30 / 4] &= ~UINT32_C(0x1f);
            w->regfile[0x14 / 4] &= ~UINT32_C(2);
        }
        w->regfile[off / 4] = word & ~UINT32_C(0x102);
        exesx_adc_sync_fifo_irq(w);
    } else if (off == 0x14) {
        /* READY is level driven by FIFO, not software-clearable. */
        w->regfile[off / 4] &= ~(word & ~UINT32_C(1));
        exesx_adc_sync_fifo_irq(w);
    } else if (off == 0x34) {
        if (word) {
            uint16_t sample;
            bool connected = exesx_adc_explicit_sample(w, &sample);
            qemu_log_mask(LOG_GUEST_ERROR,
                          "EXeSX ADC @0x%" HWADDR_PRIx
                          " SW trigger=0x%08x explicit_input=%d\n",
                          w->base, word, connected);
            if (connected && (w->regfile[0x10 / 4] & 1)) {
                for (unsigned trig = 0; trig < 4; ++trig) {
                    unsigned cmd = (w->regfile[(0xc0 + trig * 4) / 4] >> 24) & 0xf;
                    if ((word & (1U << trig)) && cmd) {
                        exesx_adc_fifo_push(w, sample, trig);
                    }
                }
            }
        }
        w->regfile[off / 4] = 0;
    } else if (off == 0x30) {
        /* FCOUNT0 is hardware-owned; watermark is guest-configurable. */
        w->regfile[off / 4] = (word & ~UINT32_C(0x1f)) |
                              exesx_adc_fifo_count(w);
        exesx_adc_sync_fifo_irq(w);
    } else {
        w->regfile[off / 4] = word;
        if (off == 0x18) {
            exesx_adc_sync_fifo_irq(w);
        }
    }
    qemu_log_mask(LOG_GUEST_ERROR,
                  "EXeSX ADC WRITE @0x%" HWADDR_PRIx " =0x%08x\n",
                  w->base + off, word);
    return MEMTX_OK;
}
