/*
 * TPM0..TPM7: early-boot Timer/PWM counter and control registers.
 * NXP MCIMX7U5 PERI_TPM.h and fsl_clock.h (TPM6 @0x40a10000).
 * Experimental clock period: QEMU virtual microseconds, not board-calibrated.
 * Internal epoch is kept in spare regfile indexes >0x100 and serialized with
 * all other board registers for snapshot rollback. An opt-in TPM0 overflow
 * IRQ38 model follows the original M4 timer's TOIE, TOF and clock mode.
 */
/* All eight TPM instances from NXP MCIMX7U5_cm4_COMMON.h. */
static bool exesx_tpm_base(uint64_t base)
{
    switch (base) {
    case 0x41030000: /* TPM0 */
    case 0x41031000: /* TPM1 */
    case 0x410a8000: /* TPM2 */
    case 0x410a9000: /* TPM3 */
    case 0x40250000: /* TPM4 */
    case 0x40260000: /* TPM5 */
    case 0x40a10000: /* TPM6 */
    case 0x40a20000: /* TPM7 */
        return true;
    default:
        return false;
    }
}
static bool exesx_tpm_offset(hwaddr off)
{
    return off == 0 || off == 4 || off == 8 ||
           off == 0x10 || off == 0x14 || off == 0x18 ||
           off == 0x1c ||
           (off >= 0x20 && off <= 0x4c && !(off & 3)) ||
           off == 0x64 || off == 0x6c || off == 0x70 ||
           off == 0x78 || off == 0x80 || off == 0x84;
}
static uint64_t exesx_tpm_epoch(EXeSXProfileWindow *w)
{
    return ((uint64_t)w->regfile[0x104 / 4] << 32) |
           w->regfile[0x100 / 4];
}
static void exesx_tpm_set_epoch(EXeSXProfileWindow *w)
{
    uint64_t ns = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    w->regfile[0x100 / 4] = (uint32_t)ns;
    w->regfile[0x104 / 4] = (uint32_t)(ns >> 32);
}
/*
 * DIAGNOSTIC CLOCK ONLY. The original EXeSX TPM model assumes 1MHz,
 * not the real i.MX7ULP PCC-selected input clock. For a controlled
 * physical-key timing experiment, permit a private TPM0-only source
 * frequency override; do NOT apply it to A7 LPIT or to other TPMs.
 * The default is bit-identical to the old virtual-time model.
 */
static unsigned exesx_tpm0_input_mhz(EXeSXProfileWindow *w)
{
    const char *s;
    uint64_t mhz;
    if (!w->tpm0_timer || w->base != 0x41030000) {
        return 1;
    }
    s = g_getenv("EXESX_EXPERIMENTAL_M4_TPM0_INPUT_MHZ");
    if (!s || !*s) {
        return 1;
    }
    mhz = g_ascii_strtoull(s, NULL, 0);
    return mhz >= 1 && mhz <= 120 ? (unsigned)mhz : 1;
}
static uint32_t exesx_tpm_counter(EXeSXProfileWindow *w)
{
    uint32_t sc = w->regfile[0x10 / 4];
    uint32_t base = w->regfile[0x108 / 4];
    uint64_t elapsed, period = (uint64_t)w->regfile[0x18 / 4] + 1;
    if ((sc & 0x18) != 0x08) {
        return base;
    }
    elapsed = (qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) -
               exesx_tpm_epoch(w)) / 1000;
    elapsed *= exesx_tpm0_input_mhz(w);
    elapsed >>= sc & 7;
    return (uint32_t)((base + elapsed) % period);
}
/*
 * Original relocated M4 firmware installs vector 0x36 (external IRQ38)
 * with handler at 0x1FFDB68C. It checks TPM0.SC.TOF (bit7), invokes
 * original keyboard debounce callback 0x1FFD7D5A, then clears TOF W1C.
 * The original firmware starts TPM0 via FUN_1FFDB7C2(0) with SC=0x48,
 * CNT=0, MOD=0x5DC. Do not synthesize any RTOS flag or A7 key event:
 * let the firmware service the real NVIC interrupt.
 */
static void exesx_tpm0_update_irq(EXeSXProfileWindow *w)
{
    if (w->tpm0_timer && w->board && w->board->tpm0_irq) {
        qemu_set_irq(w->board->tpm0_irq,
                     (w->regfile[0x10 / 4] & 0xc0) == 0xc0);
    }
}

static void exesx_tpm0_schedule(EXeSXProfileWindow *w)
{
    uint32_t sc, modulo, count;
    uint64_t remaining, ns_per_tick;
    int64_t now;

    if (!w->tpm0_timer) {
        return;
    }
    sc = w->regfile[0x10 / 4];
    exesx_tpm0_update_irq(w);
    if ((sc & 0x18) != 0x08) { /* timer counts only when CMOD=01 */
        timer_del(w->tpm0_timer);
        return;
    }
    now = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    modulo = w->regfile[0x18 / 4];
    count = exesx_tpm_counter(w);
    remaining = (uint64_t)modulo + 1 - count;
    ns_per_tick = UINT64_C(1000) << (sc & 7);
    /* Always progress at least one virtual nanosecond. */
    timer_mod(w->tpm0_timer, now +
              MAX(UINT64_C(1),
                  (remaining * ns_per_tick +
                   exesx_tpm0_input_mhz(w) - 1) /
                  exesx_tpm0_input_mhz(w)));
}

static void exesx_tpm0_timer_tick(void *opaque)
{
    EXeSXProfileWindow *w = opaque;
    uint32_t sc = w->regfile[0x10 / 4];

    if ((sc & 0x18) != 0x08) {
        return;
    }
    /* Overflow flag is sticky until the guest explicitly clears it. */
    w->regfile[0x10 / 4] = sc | 0x80;
    w->regfile[0x108 / 4] = 0; /* counter wraps */
    exesx_tpm_set_epoch(w);
    exesx_tpm0_update_irq(w);
    exesx_tpm0_schedule(w);
}

static MemTxResult exesx_tpm_read(EXeSXProfileWindow *w, hwaddr off,
                                  uint64_t *value, unsigned size)
{
    if (size != 4 || !exesx_tpm_offset(off) || off >= w->size ||
        !exesx_tpm_base(w->base)) {
        return MEMTX_ERROR;
    }
    if (off == 0x14) {
        *value = exesx_tpm_counter(w);
    } else if (off == 0x00) {
        *value = 3; /* NXP TPM standard feature set with filter/combiner */
    } else if (off == 0x04) {
        *value = 6; /* Six compare/capture channels */
    } else {
        *value = w->regfile[off / 4];
    }
    return MEMTX_OK;
}
static MemTxResult exesx_tpm_write(EXeSXProfileWindow *w, hwaddr off,
                                   uint64_t value, unsigned size)
{
    uint32_t bits = (uint32_t)value;
    if (size != 4 || !exesx_tpm_offset(off) || off >= w->size ||
        !exesx_tpm_base(w->base) ||
        off == 0 || off == 4) {
        return MEMTX_ERROR;
    }
    if (off == 0x10) {
        /* Snapshot the old count before changing divider / CMOD. */
        w->regfile[0x108 / 4] = exesx_tpm_counter(w);
        exesx_tpm_set_epoch(w);
        /* TPM0.SC.TOF is write-one-to-clear, not cleared by
         * unrelated control writes (firmware writes SC|0x80). */
        w->regfile[0x10 / 4] =
            (bits & ~UINT32_C(0x80)) |
            (w->regfile[0x10 / 4] & UINT32_C(0x80) &
             ~(bits & UINT32_C(0x80)));
    } else if (off == 0x14) {
        /* Counter write: resets CNT as described in the TPM SDK. */
        w->regfile[0x108 / 4] = 0;
        w->regfile[0x14 / 4] = 0;
        exesx_tpm_set_epoch(w);
    } else if (off == 0x18) {
        w->regfile[0x18 / 4] = bits;
    } else if (off == 0x08 && (bits & 2)) {
        /* Module soft reset bit self clears. */
        w->regfile[0x10 / 4] = 0;
        w->regfile[0x108 / 4] = 0;
        w->regfile[0x18 / 4] = 0xffff;
        exesx_tpm_set_epoch(w);
        w->regfile[0x08 / 4] = bits & ~2U;
    } else {
        w->regfile[off / 4] = bits;
    }
    if (w->tpm0_timer &&
        (off == 0x10 || off == 0x14 || off == 0x18 ||
         (off == 0x08 && (bits & 2)))) {
        exesx_tpm0_schedule(w);
    }
    qemu_log_mask(LOG_GUEST_ERROR,
                  "EXeSX TPM WRITE @0x%" HWADDR_PRIx
                  " data=0x%08x\\n", w->base + off, bits);
    return MEMTX_OK;
}
