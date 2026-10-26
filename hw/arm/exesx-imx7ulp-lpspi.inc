/*
 * i.MX7ULP LPSPI2 early-control subset, GPL-2.0-or-later.
 * NXP MCIMX7U5_cm4_COMMON.h LPSPI2_BASE 0x40290000; CR at +0x10.
 * Only the enable/reset FIFO control word is stored. No SPI clocks,
 * packet exchange, attached peripherals or transfer-completion flags.
 */
static MemTxResult exesx_lpspi2_read(EXeSXProfileWindow *w,
                                    hwaddr off, uint64_t *value,
                                    unsigned size)
{
    if (w->base != UINT64_C(0x40290000) || size != 4 || off != 0x10) {
        return MEMTX_ERROR;
    }
    *value = w->regfile[0x10 / 4];
    return MEMTX_OK;
}
static MemTxResult exesx_lpspi2_write(EXeSXProfileWindow *w,
                                     hwaddr off, uint64_t value,
                                     unsigned size)
{
    if (w->base != UINT64_C(0x40290000) || size != 4 || off != 0x10) {
        return MEMTX_ERROR;
    }
    /* MEN and reset/FIFO command control bits are recorded only.
     * Hardware reset semantics and SPI transfers are not yet emulated.
     */
    if (((uint32_t)value & 1) && !(w->regfile[0x10 / 4] & 1)) {
        qemu_log_mask(LOG_UNIMP,
                      "EXeSX LPSPI2 MEN enabled @0x40290010:"
                      " SPI TX/RX FIFO, clock/chip-select and IRQ"
                      " not implemented (ATWINC15x0 host wiring unverified)\n");
    }
    w->regfile[0x10 / 4] = (uint32_t)value;
    return MEMTX_OK;
}
