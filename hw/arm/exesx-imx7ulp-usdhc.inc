/*
 * NXP i.MX7ULP USDHC0 pre-card-init status, GPL-2.0-or-later.
 * Linux arch/arm/boot/dts/imx7ulp.dtsi: USDHC0=0x40370000
 * NXP PERI_USDHC.h: PRES_STATE (+0x24), SDSTB bit3, CINST bit16.
 * No storage image, command handling, SD/eMMC responses or data transfers.
 */
static MemTxResult exesx_usdhc0_read(EXeSXProfileWindow *w,
                                    hwaddr off, uint64_t *value,
                                    unsigned size)
{
    if (w->base != UINT64_C(0x40370000) || off != 0x24 || size != 4) {
        return MEMTX_ERROR;
    }
    /* Simplified stable host clock after board clock setup; no card.
     * CINST, RTA, WTA, CIHB, CDIHB, DLA and BREN/BWEN remain zero.
     */
    *value = UINT32_C(0x00000008);
    return MEMTX_OK;
}
static MemTxResult exesx_usdhc0_write(EXeSXProfileWindow *w,
                                     hwaddr off, uint64_t value,
                                     unsigned size)
{
    /* PRES_STATE is read only; unsupported command/control regs fault. */
    return MEMTX_ERROR;
}
