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
/* PERI_USDHC.h PROT_CTRL: direction/endian/DMA/blockgap/wakeup/bursts;
 * undefined bits are read-as-zero and write-ignored. */
#define EXESX_USDHC1_PROT_CTRL_MASK UINT32_C(0x7f1f03ff)
/* Private snapshot-backed no-media command-deadline slots, not MMIO regs.
 * QEMU virtual time is used so pauses/snapshots do not use wall-clock time.
 * The timeout is an explicitly approximate controller-clock substitute.
 */
#define EXESX_USDHC1_NO_MEDIA_TS_LO (0xf00 / 4)
#define EXESX_USDHC1_NO_MEDIA_TS_HI (0xf04 / 4)
#define EXESX_USDHC1_NO_MEDIA_ARMED (0xf08 / 4)
#define EXESX_USDHC1_NO_MEDIA_TIMEOUT_NS UINT64_C(1000000)

static void exesx_usdhc1_update_no_media_timeout(EXeSXProfileWindow *w)
{
    uint64_t start;
    uint64_t now;

    if (!w->regfile[EXESX_USDHC1_NO_MEDIA_ARMED]) {
        return;
    }
    start = ((uint64_t)w->regfile[EXESX_USDHC1_NO_MEDIA_TS_HI] << 32) |
            w->regfile[EXESX_USDHC1_NO_MEDIA_TS_LO];
    now = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    if (now < start || now - start < EXESX_USDHC1_NO_MEDIA_TIMEOUT_NS) {
        return;
    }
    w->regfile[EXESX_USDHC1_NO_MEDIA_ARMED] = 0;
    /* No attached media can return an R1/R3/R7/etc response. The host
     * eventually reports a command timeout, not command completion.
     * INT_STATUS_EN controls whether this status flag is observable.
     * No GIC IRQ source has been connected by this limited model.
     */
    if (w->regfile[0x34 / 4] & UINT32_C(0x00010000)) {
        w->regfile[0x30 / 4] |= UINT32_C(0x00010000);
    }
}


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
    case 0x10: /* CMDRSP0: zero until a real medium is attached */
    case 0x14: /* CMDRSP1 */
    case 0x18: /* CMDRSP2 */
    case 0x1c: /* CMDRSP3 */
        *value = 0;
        return MEMTX_OK;
    case 0x30: /* INT_STATUS: host no-card timeout is evaluated lazily */
        exesx_usdhc1_update_no_media_timeout(w);
        *value = w->regfile[off / 4];
        return MEMTX_OK;
    case 0x08: /* CMD_ARG: argument from A7 to SD command wire */
    case 0x0c: /* CMD_XFR_TYP: most recently initiated command */
    case 0x28: /* PROT_CTRL: bus/endian/byte order configuration */
    case 0x2c:
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
    case 0x28: /* PROT_CTRL: no fake card-detect test-level change */
        w->regfile[off / 4] = bits & EXESX_USDHC1_PROT_CTRL_MASK;
        return MEMTX_OK;
    case 0x08: /* CMD_ARG: staging only; not a card response */
        w->regfile[off / 4] = bits;
        return MEMTX_OK;
    case 0x0c: { /* CMD_XFR_TYP: a write launches an SD/MMC command */
        unsigned index = (bits >> 24) & 0x3f;
        unsigned response_type = (bits >> 16) & 3;
        uint32_t argument = w->regfile[0x08 / 4];

        w->regfile[off / 4] = bits;
        /* Abandon any earlier no-response deadline whenever another
         * command is issued. A response-requiring command against an
         * empty slot must eventually raise CTOE, not remain pending
         * forever or claim successful card initialization.
         */
        w->regfile[EXESX_USDHC1_NO_MEDIA_ARMED] = 0;
        if (response_type != 0) {
            uint64_t now = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
            w->regfile[EXESX_USDHC1_NO_MEDIA_TS_LO] = (uint32_t)now;
            w->regfile[EXESX_USDHC1_NO_MEDIA_TS_HI] = now >> 32;
            w->regfile[EXESX_USDHC1_NO_MEDIA_ARMED] = 1;
        }
        /* NXP CMD0 (GO_IDLE_STATE) has no response and no data:
         * the HOST can finish sending its command without any medium.
         * This is NOT a card reply or proof that a card is inserted.
         * Do not fake completion for CMD8/CMD1/etc, which require
         * external media and have real response/timeout behavior.
         */
        if (index == 0 && argument == 0 && response_type == 0 &&
            !(bits & UINT32_C(0x00200000)) &&
            (w->regfile[0x34 / 4] & UINT32_C(1))) {
            w->regfile[0x30 / 4] |= UINT32_C(1); /* host CMD complete */
        }
        qemu_log_mask(LOG_UNIMP,
                      "EXeSX USDHC1 CMD%u ARG=0x%08x XFR=0x%08x "
                      "response=%u no-media (no card response)\n",
                      index, argument, bits, response_type);
        return MEMTX_OK;
    }
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
