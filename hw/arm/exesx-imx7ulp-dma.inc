/*
 * NXP i.MX7ULP Cortex-M4 DMA0 early-control subset.
 * Source: NXP MCIMX7U5_cm4_COMMON.h (DMA0_BASE=0x41008000),
 *         PERI_DMA.h (CR +0x00, ES +0x04, ERQ +0x0c,
 *         EEI +0x14, INT +0x24, ERR +0x2c, HRS +0x34).
 *
 * NO transfers, TCD descriptors, interrupts, or peripheral DMA requests
 * are emulated. Inaccessible offsets deliberately fault rather than
 * claiming the real DMA engine executed. State is VMState-backed.
 */
static bool exesx_dma0_early_reg(hwaddr off)
{
    switch (off) {
    case 0x00: case 0x04: case 0x0c: case 0x14:
    case 0x24: case 0x2c: case 0x34: case 0x44:
        return true;
    default:
        return false;
    }
}

/* DMA1 A7-side 32-channel TCD registers at +0x1000..+0x13ff.
 * Store descriptors for inspection only. No TCD engine or data copying.
 * Linux fsl,imx7ulp-edma binding documents this register window.
 */
static bool exesx_dma1_tcd_access(EXeSXProfileWindow *w, hwaddr off,
                                  unsigned size)
{
    return w->base == UINT64_C(0x40080000) &&
           off >= 0x1000 && off < 0x1400 &&
           (size == 1 || size == 2 || size == 4) &&
           (off & (size - 1)) == 0 &&
           ((off & 3) + size <= 4);
}

static MemTxResult exesx_dma0_read(EXeSXProfileWindow *w, hwaddr off,
                                  uint64_t *value, unsigned size)
{
    if (exesx_dma1_tcd_access(w, off, size)) {
        *value = (w->regfile[off / 4] >> ((off & 3) * 8)) &
                 ((UINT64_C(1) << (size * 8)) - 1);
        return MEMTX_OK;
    }
    if (w->base == UINT64_C(0x40080000) && size == 1 &&
        (off == 0x1a || off == 0x1b)) {
        /* Command registers are write-only and read as zero here. */
        *value = 0;
        return MEMTX_OK;
    }
    if ((w->base != UINT64_C(0x41008000) &&
         w->base != UINT64_C(0x40080000)) ||
        size != 4 || (off & 3) || off >= w->size ||
        !exesx_dma0_early_reg(off)) {
        return MEMTX_ERROR;
    }
    /* Without descriptors, no channel reports activity/error/interrupt. */
    if (off == 0x04 || off == 0x24 || off == 0x2c || off == 0x34) {
        *value = 0;
    } else {
        *value = w->regfile[off / 4];
    }
    return MEMTX_OK;
}

static MemTxResult exesx_dma0_write(EXeSXProfileWindow *w, hwaddr off,
                                   uint64_t value, unsigned size)
{
    uint32_t bits = (uint32_t)value;
    if (exesx_dma1_tcd_access(w, off, size)) {
        uint32_t shift = (off & 3) * 8;
        uint32_t mask = ((UINT64_C(1) << (size * 8)) - 1) << shift;
        w->regfile[off / 4] = (w->regfile[off / 4] & ~mask) |
                              (((uint32_t)value << shift) & mask);
        if (!g_strcmp0(g_getenv("EXESX_TRACE_DMA1_TCD"), "1")) {
            qemu_log_mask(LOG_UNIMP,
                          "EXeSX DMA1 TCD WRITE ch=%u field=0x%02" HWADDR_PRIx
                          " width=%u data=0x%08x (NO DMA execution)\n",
                          (unsigned)((off - 0x1000) / 32),
                          (off - 0x1000) % 32, size, (uint32_t)value);
        }
        return MEMTX_OK;
    }
    if (w->base == UINT64_C(0x40080000) && size == 1 &&
        (off == 0x1a || off == 0x1b)) {
        /* PERI_DMA.h: CERQ +0x1a and SERQ +0x1b are eight-bit
         * command registers; ERQ +0x0c has one bit per DMA channel.
         * Bit7 NOP, bit6 clear/set ALL requests, low five bits channel.
         * A request enable is NOT an executed TCD or DONE transition.
         */
        if (!(bits & 0x80)) {
            uint32_t channel_mask = (bits & 0x40) ?
                                    UINT32_MAX :
                                    (UINT32_C(1) << (bits & 0x1f));
            if (off == 0x1b) {
                w->regfile[0x0c / 4] |= channel_mask;
            } else {
                w->regfile[0x0c / 4] &= ~channel_mask;
            }
            if (!g_strcmp0(g_getenv("EXESX_TRACE_DMA1_TCD"), "1")) {
                qemu_log_mask(LOG_UNIMP,
                              "EXeSX DMA1 %s ch=%u ERQ=0x%08x "
                              "(NO DMA execution)\n",
                              off == 0x1b ? "SERQ" : "CERQ",
                              bits & 0x1f, w->regfile[0x0c / 4]);
            }
        }
        return MEMTX_OK;
    }
    if ((w->base != UINT64_C(0x41008000) &&
         w->base != UINT64_C(0x40080000)) ||
        size != 4 || (off & 3) || off >= w->size ||
        !exesx_dma0_early_reg(off) ||
        off == 0x04 || off == 0x34) {
        return MEMTX_ERROR;
    }
    if (off == 0x24 || off == 0x2c) {
        /* W1C interrupt/error status, initially zero. */
        w->regfile[off / 4] &= ~((uint32_t)value);
    } else {
        w->regfile[off / 4] = (uint32_t)value;
    }
    qemu_log_mask(LOG_GUEST_ERROR,
                  "EXeSX DMA EARLY_CONTROL @0x%" HWADDR_PRIx
                  " data=0x%08x (NO transfers modeled)\n",
                  w->base + off, (uint32_t)value);
    return MEMTX_OK;
}
