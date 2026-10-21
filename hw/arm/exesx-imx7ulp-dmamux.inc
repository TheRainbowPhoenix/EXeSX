/*
 * NXP i.MX7ULP A7 DMAMUX1 channel configuration, GPL-2.0-or-later.
 * Source: NXP MCIMX7U5_cm4_COMMON.h DMAMUX1_BASE=0x40210000;
 * Linux imx7ulp.dtsi eDMA1 has 32 channels and DMAMUX1 at this address.
 * Packed CHCFG0..31 can be accessed as bytes, halfwords, or words;
 * all accesses affect the same underlying bytes. Registers are only stored, never generate DMA requests.
 */
static MemTxResult exesx_dmamux1_read(EXeSXProfileWindow *w,
                                     hwaddr off, uint64_t *value,
                                     unsigned size)
{
    if (w->base != UINT64_C(0x40210000) || (size != 1 && size != 2 && size != 4) ||
        (off & (size - 1)) || off + size > 32) {
        return MEMTX_ERROR;
    }
    *value = (w->regfile[off / 4] >> ((off & 3) * 8)) &
             ((UINT64_C(1) << (size * 8)) - 1);
    return MEMTX_OK;
}
static MemTxResult exesx_dmamux1_write(EXeSXProfileWindow *w,
                                      hwaddr off, uint64_t value,
                                      unsigned size)
{
    uint32_t shift;
    uint32_t mask;
    if (w->base != UINT64_C(0x40210000) || (size != 1 && size != 2 && size != 4) ||
        (off & (size - 1)) || off + size > 32) {
        return MEMTX_ERROR;
    }
    shift = (off & 3) * 8;
    mask = (uint32_t)(((UINT64_C(1) << (size * 8)) - 1) << shift);
    w->regfile[off / 4] = (w->regfile[off / 4] & ~mask) |
                          (((uint32_t)value << shift) & mask);
    return MEMTX_OK;
}
