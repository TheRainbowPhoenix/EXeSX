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

/*
 * USDHC1 A7 host clock bring-up only, NXP USDHC_Type:
 * base 0x40380000; SYS_CTRL +0x2c, PRES_STATE +0x24,
 * MIX_CTRL +0x48 and VEND_SPEC +0xc0.
 * No inserted card, SD command response or transfer is emulated.
 */
#define EXESX_USDHC1_BASE UINT64_C(0x40380000)
#define EXESX_USDHC1_VEND_SPEC_MASK UINT32_C(0x8000810e)
#define EXESX_USDHC1_SYS_CTRL_MASK UINT32_C(0x1f8ffff0)
/* Explicit NXP PERI_USDHC.h INT_STATUS valid bits; no virtual card
 * means no command completion, transfer completion, or insertion events.
 */
#define EXESX_USDHC1_IRQ_VALID UINT32_C(0x157f51ff)

static MemTxResult exesx_usdhc1_read(EXeSXProfileWindow *w,
                                    hwaddr off, uint64_t *value,
                                    unsigned size)
{
    if (w->base != EXESX_USDHC1_BASE || size != 4 || (off & 3)) {
        return MEMTX_ERROR;
    }
    switch (off) {
    case 0x24:
        /* Host SD clock stable, but NO card present and NO data ready. */
        *value = UINT32_C(0x00000008);
        return MEMTX_OK;
    case 0x2c:
    case 0x30: /* INT_STATUS, no event sources implemented */
    case 0x34: /* INT_STATUS_EN */
    case 0x38: /* INT_SIGNAL_EN */
    case 0x44: /* WTMK_LVL: read/write FIFO watermark parameters */
    case 0x48:
    case 0xc0:
        *value = w->regfile[off / 4];
        return MEMTX_OK;
    default:
        return MEMTX_ERROR;
    }
}

static MemTxResult exesx_usdhc1_write(EXeSXProfileWindow *w,
                                     hwaddr off, uint64_t value,
                                     unsigned size)
{
    uint32_t bits = (uint32_t)value;
    if (w->base != EXESX_USDHC1_BASE || size != 4 || (off & 3)) {
        return MEMTX_ERROR;
    }
    switch (off) {
    case 0x2c:
        /* NXP SYS_CTRL RSTA/RSTC/RSTD/RSTT are reset command bits
         * that self-clear. Other enabled clock divisors remain stored.
         * We have no attached card, buffer or command FSM to reset.
         */
        if (bits & ~EXESX_USDHC1_SYS_CTRL_MASK) {
            /* Software may write an entire register including reserved
             * low bits. In this device model they are RAZ/WI rather
             * than a fabricated bus fault. No transfer is started.
             */
            qemu_log_mask(LOG_GUEST_ERROR,
                          "EXeSX USDHC1 ignored reserved SYS_CTRL bits "
                          "0x%08x\n", bits & ~EXESX_USDHC1_SYS_CTRL_MASK);
        }
        w->regfile[off / 4] =
            bits & EXESX_USDHC1_SYS_CTRL_MASK & ~UINT32_C(0x17000000);
        return MEMTX_OK;
    case 0x30: /* INT_STATUS W1C; no card/command event to set flags */
        w->regfile[off / 4] &= ~(bits & EXESX_USDHC1_IRQ_VALID);
        return MEMTX_OK;
    case 0x34: /* INT_STATUS_EN: mask documented status source bits */
    case 0x38: /* INT_SIGNAL_EN: mask documented IRQ source bits */
        w->regfile[off / 4] = bits & EXESX_USDHC1_IRQ_VALID;
        return MEMTX_OK;
    case 0x44: /* WTMK_LVL: RD/WR_WML 8-bit, RD/WR_BRST_LEN 5-bit */
        w->regfile[off / 4] =
            bits & UINT32_C(0x1fff1fff);
        return MEMTX_OK;
    case 0x48:
        /* MIX_CTRL carries SD card transfer mixing flags, stored for
         * introspection only. No card command or data transfer occurs.
         */
        w->regfile[off / 4] = bits;
        return MEMTX_OK;
    case 0xc0:
        /* NXP VEND_SPEC.FRC_SDCLK_ON bit8, voltage selection and vendor
         * controls. No fabricated host clock/card state transitions. */
        if (bits & ~EXESX_USDHC1_VEND_SPEC_MASK) {
            return MEMTX_ERROR;
        }
        w->regfile[off / 4] = bits;
        return MEMTX_OK;
    default:
        return MEMTX_ERROR;
    }
}
