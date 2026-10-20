/*
 * i.MX7ULP low-power LPTMR0/1 timer: early-boot implementation.
 * Register map from NXP MCIMX7U5 PERI_LPTMR.h:
 * CSR +0, PSR +4, CMR +8, CNR +0xC.
 *
 * A monotonic QEMU-virtual 1 MHz source represents one selected internal
 * timer clock until the M4 clock-tree inputs are modeled. Counter/compare
 * status and prescale follow register configuration. No external pulses,
 * NVIC assertion or DMA yet. Epoch stored in VMState-backed regfile so
 * savevm/loadvm replays the same timer state.
 */
static bool exesx_lptmr_addr(EXeSXProfileWindow *w, hwaddr off)
{
    return (w->base == 0x4102e000 || w->base == 0x4102f000) &&
           off <= 0xc && !(off & 3) && off + 4 <= w->size;
}
static uint64_t exesx_lptmr_start_ns(EXeSXProfileWindow *w)
{
    return ((uint64_t)w->regfile[0x104 / 4] << 32) |
           w->regfile[0x100 / 4];
}
static void exesx_lptmr_restart(EXeSXProfileWindow *w)
{
    uint64_t now = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    w->regfile[0x100 / 4] = (uint32_t)now;
    w->regfile[0x104 / 4] = (uint32_t)(now >> 32);
}
static uint64_t exesx_lptmr_ticks(EXeSXProfileWindow *w)
{
    uint32_t csr = w->regfile[0];
    uint32_t psr = w->regfile[1];
    uint64_t ticks;
    if (!(csr & 1) || (csr & 2)) {
        return 0; /* Off, or pulse mode without an external pulse source. */
    }
    ticks = (qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) -
             exesx_lptmr_start_ns(w)) / 1000;
    if (!(psr & 4)) {
        unsigned shift = ((psr >> 3) & 15) + 1;
        ticks >>= shift; /* divide by 2,4,...,65536 */
    }
    return ticks;
}
static uint32_t exesx_lptmr_counter(EXeSXProfileWindow *w)
{
    uint64_t ticks = exesx_lptmr_ticks(w);
    uint32_t csr = w->regfile[0];
    uint32_t compare = w->regfile[2] & 0xffff;
    if (!compare) {
        compare = 0xffff;
    }
    if (ticks >= compare) {
        w->regfile[0] |= 0x80; /* hardware compare flag TCF */
    }
    if (csr & 4) {
        return (uint32_t)(ticks & 0xffff); /* free-running */
    }
    return (uint32_t)(ticks % ((uint64_t)compare + 1));
}
static MemTxResult exesx_lptmr_read(EXeSXProfileWindow *w, hwaddr off,
                                   uint64_t *value, unsigned size)
{
    if (size != 4 || !exesx_lptmr_addr(w, off)) {
        return MEMTX_ERROR;
    }
    if (off == 0x0) {
        exesx_lptmr_counter(w);
    }
    *value = off == 0xc ? exesx_lptmr_counter(w) : w->regfile[off / 4];
    return MEMTX_OK;
}
static MemTxResult exesx_lptmr_write(EXeSXProfileWindow *w, hwaddr off,
                                    uint64_t value, unsigned size)
{
    uint32_t bits = (uint32_t)value;
    if (size != 4 || !exesx_lptmr_addr(w, off)) {
        return MEMTX_ERROR;
    }
    switch (off) {
    case 0:
        if ((bits & 1) != (w->regfile[0] & 1)) {
            exesx_lptmr_restart(w);
        }
        /* TCF bit7: write 1 to clear; other CSR bits are writable. */
        w->regfile[0] = (bits & ~UINT32_C(0x80)) |
            ((w->regfile[0] & UINT32_C(0x80)) & ~bits);
        break;
    case 4:
        w->regfile[1] = bits & 0x7f;
        exesx_lptmr_restart(w);
        break;
    case 8:
        w->regfile[2] = bits & 0xffff;
        break;
    case 0xc:
        /* NXP: CNR write latches/reset synchronizes the counter. */
        exesx_lptmr_restart(w);
        break;
    }
    qemu_log_mask(LOG_GUEST_ERROR,
                  "EXeSX LPTMR WRITE @0x%" HWADDR_PRIx
                  " data=0x%08x\n", w->base + off, bits);
    return MEMTX_OK;
}
