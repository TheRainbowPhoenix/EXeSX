/*
 * NXP i.MX7ULP LPIT0/LPIT1, simple four-channel interval timer.
 * PERI_LPIT.h: MCR +0x08, MSR +0x0c, MIER +0x10,
 * SETTEN/CLRTEN +0x14/+0x18, TVAL/CVAL/TCTRL 0x20+0x10*n.
 * LPIT1 retains the existing 1MHz provisional tick. Opt-in M4 LPIT0
 * runs at the original firmware's effective 12MHz timer source. Its
 * genuine interrupt is routed to Cortex-M4 NVIC IRQ49 when enabled via
 * EXESX_EXPERIMENTAL_M4_LPIT0_IRQ=1. LPIT1 continues to use GIC SPI25.
 * DMA outputs remain unimplemented.
 * Hidden per-channel timestamps are saved by board VMState regfile.
 */
static bool exesx_lpit_valid(EXeSXProfileWindow *w, hwaddr off)
{
    if ((w->base != 0x4102d000 && w->base != 0x40270000) ||
        off >= w->size || (off & 3)) {
        return false;
    }
    if (off <= 0x18) {
        return off == 0 || off == 4 || off == 8 ||
               off == 0xc || off == 0x10 ||
               off == 0x14 || off == 0x18;
    }
    return off >= 0x20 && off < 0x60 &&
           ((off - 0x20) % 0x10) <= 8;
}
static uint64_t exesx_lpit_epoch(EXeSXProfileWindow *w, unsigned n)
{
    return ((uint64_t)w->regfile[(0x204+0x10*n)/4] << 32) |
           w->regfile[(0x200+0x10*n)/4];
}
static void exesx_lpit_epoch_reset(EXeSXProfileWindow *w, unsigned n)
{
    uint64_t t = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    w->regfile[(0x200+0x10*n)/4] = (uint32_t)t;
    w->regfile[(0x204+0x10*n)/4] = (uint32_t)(t >> 32);
}
/*
 * Original M4 FUN_1FFD684A programs CH1.TVAL=12000 for a 1ms touch
 * timer, selecting an effective 12MHz LPIT0 clock. The existing A7
 * LPIT1 diagnostic source continues at 1MHz. Keep both derived from
 * QEMU virtual time; the original guest supplies period/MIER/TCTRL.
 *
 * With LPIT0 opt-in disabled preserve legacy 1MHz polling behavior.
 * 12MHz -> 12 ticks per microsecond, so values of 12000 are 1ms.
 */
static bool exesx_lpit_m4_clock(EXeSXProfileWindow *w)
{
    return w->base == UINT64_C(0x4102d000) &&
           !g_strcmp0(g_getenv("EXESX_EXPERIMENTAL_M4_LPIT0_IRQ"), "1");
}
static uint64_t exesx_lpit_elapsed_ticks(EXeSXProfileWindow *w,
                                         uint64_t delta_ns)
{
    if (exesx_lpit_m4_clock(w)) {
        return (delta_ns / 1000) * 12 + (delta_ns % 1000) * 12 / 1000;
    }
    return delta_ns / 1000;
}
static uint64_t exesx_lpit_duration_ns(EXeSXProfileWindow *w,
                                       uint64_t ticks)
{
    if (exesx_lpit_m4_clock(w)) {
        return (ticks * 1000 + 11) / 12;
    }
    return ticks * 1000;
}
static uint32_t exesx_lpit_cval(EXeSXProfileWindow *w, unsigned n)
{
    uint32_t ctrl = w->regfile[(0x28+0x10*n)/4];
    uint32_t tval = w->regfile[(0x20+0x10*n)/4];
    uint64_t t, period = (uint64_t)tval + 1;
    if (!(w->regfile[0x08/4] & 1) || !(ctrl & 1)) {
        return tval;
    }
    t = exesx_lpit_elapsed_ticks(
        w, qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) -
           exesx_lpit_epoch(w, n));
    return (uint32_t)(tval - (t % period));
}
static MemTxResult exesx_lpit_read(EXeSXProfileWindow *w, hwaddr off,
                                  uint64_t *value, unsigned size)
{
    unsigned n;
    if (size != 4 || !exesx_lpit_valid(w, off)) {
        return MEMTX_ERROR;
    }
    if (off == 0) {
        *value = 0x10000; /* Basic LPIT version */
        return MEMTX_OK;
    }
    if (off == 4) {
        *value = 4; /* Four channel implementation */
        return MEMTX_OK;
    }
    if (off == 0xc) {
        uint32_t status = w->regfile[0xc/4];
        for (n=0; n<4; n++) {
            if ((w->regfile[0x8/4] & 1) &&
                (w->regfile[(0x28+0x10*n)/4] & 1) &&
                exesx_lpit_elapsed_ticks(
                    w, qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) -
                       exesx_lpit_epoch(w,n)) >
                    w->regfile[(0x20+0x10*n)/4]) {
                status |= 1U << n;
            }
        }
        w->regfile[0xc/4] = status;
        *value = status;
        return MEMTX_OK;
    }
    if (off >= 0x20 && ((off-0x20)%0x10) == 4) {
        *value = exesx_lpit_cval(w,(off-0x20)/0x10);
        return MEMTX_OK;
    }
    if (off == 0x14 || off == 0x18) {
        *value = 0; /* Write-only enable strobes */
        return MEMTX_OK;
    }
    *value = w->regfile[off/4];
    return MEMTX_OK;
}
/*
 * Optional i.MX7ULP A7 LPIT1 asynchronous IRQ model, derived solely from
 * the programmed TVAL/CVAL/TCTRL, module enable and MIER. A WFI guest
 * cannot make progress with an MSR flag that only updates on reads.
 * Physical NXP A7 interrupt source LPIT1 is GIC SPI25 (board wiring).
 * Keep existing 1 MHz uncalibrated virtual tick model; do not fabricate
 * firmware event completion. The guest must handle and ACK the real IRQ.
 */
static void exesx_lpit_irq_update(EXeSXProfileWindow *w)
{
    qemu_irq irq = NULL;
    if (!w->lpit_timer || !w->board) {
        return;
    }
    irq = w->base == UINT64_C(0x4102d000) ?
          w->board->lpit0_irq : w->board->lpit1_irq;
    if (irq) {
        qemu_set_irq(irq,
                     (w->regfile[0xc / 4] &
                      w->regfile[0x10 / 4] & 0xf) != 0);
    }
}
static void exesx_lpit_timer_update(EXeSXProfileWindow *w)
{
    uint64_t now, nearest = UINT64_MAX;
    if (!w->lpit_timer) {
        return;
    }
    now = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    for (unsigned n = 0; n < 4; ++n) {
        uint64_t period, epoch, due;
        if (!(w->regfile[0x8 / 4] & 1) ||
            !(w->regfile[(0x28 + 0x10 * n) / 4] & 1)) {
            continue;
        }
        period = exesx_lpit_duration_ns(
            w, (uint64_t)w->regfile[(0x20 + 0x10 * n) / 4] + 1);
        epoch = exesx_lpit_epoch(w, n);
        if (now >= epoch && now - epoch >= period) {
            uint64_t cycles = (now - epoch) / period;
            uint64_t advanced = epoch + cycles * period;
            w->regfile[0xc / 4] |= 1U << n;
            w->regfile[(0x200 + 0x10 * n) / 4] = (uint32_t)advanced;
            w->regfile[(0x204 + 0x10 * n) / 4] = (uint32_t)(advanced >> 32);
            epoch = advanced;
        }
        due = epoch + period;
        if (due < nearest) {
            nearest = due;
        }
    }
    if (nearest == UINT64_MAX) {
        timer_del(w->lpit_timer);
    } else {
        timer_mod(w->lpit_timer, nearest);
    }
    exesx_lpit_irq_update(w);
}
static void exesx_lpit_timer_tick(void *opaque)
{
    exesx_lpit_timer_update(opaque);
}
static MemTxResult exesx_lpit_write(EXeSXProfileWindow *w, hwaddr off,
                                   uint64_t value, unsigned size)
{
    uint32_t bits = (uint32_t)value;
    unsigned n;
    if (size != 4 || !exesx_lpit_valid(w, off) ||
        off == 0 || off == 4 ||
        (off >= 0x20 && ((off-0x20)%0x10) == 4)) {
        return MEMTX_ERROR;
    }
    switch (off) {
    case 0x08:
        w->regfile[off/4] = bits & ~2U; /* SW_RST self-clears */
        if (bits & 2) {
            for (n=0;n<4;n++) {
                w->regfile[(0x28+0x10*n)/4] = 0;
                exesx_lpit_epoch_reset(w,n);
            }
            w->regfile[0xc/4] = 0;
        }
        break;
    case 0x0c:
        w->regfile[off/4] &= ~(bits & 0x0f); /* W1C */
        break;
    case 0x14: case 0x18:
        for (n=0; n<4; n++) {
            if (bits & (1U << n)) {
                uint32_t *ctrl = &w->regfile[(0x28+0x10*n)/4];
                if (off == 0x14) {
                    *ctrl |= 1;
                    exesx_lpit_epoch_reset(w,n);
                } else {
                    *ctrl &= ~1U;
                }
            }
        }
        break;
    default:
        w->regfile[off/4] = bits;
        if (off >= 0x20 && ((off-0x20)%0x10) == 8 &&
            (bits & 1)) {
            exesx_lpit_epoch_reset(w,(off-0x20)/0x10);
        }
        break;
    }
    exesx_lpit_timer_update(w);
    qemu_log_mask(LOG_GUEST_ERROR,
                  "EXeSX LPIT WRITE @0x%" HWADDR_PRIx
                  " data=0x%08x\n", w->base+off, bits);
    return MEMTX_OK;
}
