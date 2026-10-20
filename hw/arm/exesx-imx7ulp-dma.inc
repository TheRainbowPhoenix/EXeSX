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

static MemTxResult exesx_dma0_read(EXeSXProfileWindow *w, hwaddr off,
                                  uint64_t *value, unsigned size)
{
    if (w->base != 0x41008000 || size != 4 || (off & 3) ||
        off >= w->size || !exesx_dma0_early_reg(off)) {
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
    if (w->base != 0x41008000 || size != 4 || (off & 3) ||
        off >= w->size || !exesx_dma0_early_reg(off) ||
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
                  "EXeSX DMA0 EARLY_CONTROL @0x%" HWADDR_PRIx
                  " data=0x%08x (NO transfers modeled)\n",
                  w->base + off, (uint32_t)value);
    return MEMTX_OK;
}
