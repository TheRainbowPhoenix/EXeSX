/*
 * i.MX7ULP M4 I2S0/I2S1 (SAI) register layout, NXP PERI_I2S.h.
 *
 * EXeSX original M4 firmware executes a TCSR read at 0x41037008
 * during the genuine factory 0x400B(2) service. Without I2S0 mapped
 * this is a precise bus fault (CFSR=0x8200 BFAR=0x41037008).
 *
 * Model control/configuration registers, FIFO reset auto-clear, and
 * W1C error flags only. The audio sample clock, waveform generation,
 * transfer requests, receive audio stream, and DMA are NOT invented.
 * Reserved holes intentionally MEMTX_ERROR. Not a generic register echo.
 *
 * Reference: NXP MCIMX7U5_cm4_COMMON.h:
 * I2S0_BASE 0x41037000, I2S1_BASE 0x410aa000.
 * NXP PERI_I2S.h: TCSR=0x08, TCR1..5=0x0c..0x1c,
 * TDR0..3=0x20..0x2c, TFR0..3=0x40..0x4c, TMR=0x60,
 * RCSR=0x88, RCR1..5=0x8c..0x9c, RDR0..3=0xa0..0xac,
 * RFR0..3=0xc0..0xcc, RMR=0xe0.
 */
static bool exesx_i2s_valid(EXeSXProfileWindow *w,
                            hwaddr off, unsigned size)
{
    if (size != 4 || (off & 3) || off >= w->size ||
        (w->base != 0x41037000 && w->base != 0x410aa000)) {
        return false;
    }
    return off == 0 || off == 4 ||
           (off >= 0x08 && off <= 0x2c) ||
           (off >= 0x40 && off <= 0x4c) ||
           off == 0x60 ||
           (off >= 0x88 && off <= 0xac) ||
           (off >= 0xc0 && off <= 0xcc) ||
           off == 0xe0;
}
static MemTxResult exesx_i2s_read(EXeSXProfileWindow *w, hwaddr off,
                                  uint64_t *result, unsigned size)
{
    if (!exesx_i2s_valid(w, off, size)) {
        return MEMTX_ERROR;
    }
    if (off == 0) {
        /* Hardware VERID is read-only; no fabricated silicon revision. */
        *result = 0;
    } else if (off == 4) {
        /* PARAM is read-only; unknown hardware line/FIFO capacities. */
        *result = 0;
    } else if (off >= 0xa0 && off <= 0xac) {
        /* No receiver/codec is connected: never echo stale TX/RX data. */
        qemu_log_mask(LOG_UNIMP,
                      "EXeSX I2S @0x%" HWADDR_PRIx
                      " RX FIFO read not implemented (no audio source)\n",
                      w->base + off);
        *result = 0;
    } else if ((off >= 0x40 && off <= 0x4c) ||
               (off >= 0xc0 && off <= 0xcc)) {
        /* No guest-configured audio clock, hence no data FIFO progress. */
        *result = 0;
    } else {
        *result = w->regfile[off / 4];
    }
    return MEMTX_OK;
}
static MemTxResult exesx_i2s_write(EXeSXProfileWindow *w, hwaddr off,
                                   uint64_t data, unsigned size)
{
    const uint32_t value = (uint32_t)data;
    if (!exesx_i2s_valid(w, off, size) ||
        off == 0 || off == 4 ||
        (off >= 0x40 && off <= 0x4c) ||
        (off >= 0xa0 && off <= 0xac) ||
        (off >= 0xc0 && off <= 0xcc)) {
        return MEMTX_ERROR;
    }
    if (off >= 0x20 && off <= 0x2c) {
        /* Register write is acknowledged, but no audio FIFO exists. */
        qemu_log_mask(LOG_UNIMP,
                      "EXeSX I2S @0x%" HWADDR_PRIx
                      " TX FIFO write not implemented (sample dropped)\n",
                      w->base + off);
        return MEMTX_OK;
    }
    if (off == 0x08 || off == 0x88) {
        /* TCSR/RCSR: 0x01000000 software reset and 0x02000000
         * FIFO reset are commands that self-clear. FEF, SEF and WSF
         * (bits18..20) are hardware-status W1C, not ordinary RW.
         * Do not assert FIFO-ready or fire an IRQ without a clock.
         */
        uint32_t old = w->regfile[off / 4];
        if ((value & UINT32_C(0x80000000)) &&
            !(old & UINT32_C(0x80000000))) {
            qemu_log_mask(LOG_UNIMP,
                          "EXeSX I2S @0x%" HWADDR_PRIx
                          " %s enabled: audio clock/FIFO/DMA/IRQ"
                          " not implemented\n",
                          w->base + off, off == 0x08 ? "TX" : "RX");
        }
        uint32_t status = (old & UINT32_C(0x001c0000)) &
                          ~(value & UINT32_C(0x001c0000));
        w->regfile[off / 4] = (value & ~UINT32_C(0x031c0000)) |
                              status;
        if (value & UINT32_C(0x01000000)) {
            /* Reset control/configuration register bank on SR. */
            hwaddr start = off == 0x08 ? 0x0c : 0x8c;
            for (hwaddr o = start; o <= start + 0x10; o += 4) {
                w->regfile[o / 4] = 0;
            }
        }
    } else {
        w->regfile[off / 4] = value;
    }
    return MEMTX_OK;
}
