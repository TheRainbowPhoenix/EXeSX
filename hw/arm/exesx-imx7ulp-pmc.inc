/*
 * i.MX7ULP PMC1 power management controller, early BIOS subset.
 * Peripheral base 0x40400000, offsets per NXP MCUXpresso PERI_PMC1.h.
 * Keeps programmed LDO mode/voltage words, including VLPS+0x14.
 * Power rails, thermal effects and voltage transition delays NOT modeled.
 */
static bool exesx_imx7ulp_pmc1_offset(hwaddr off)
{
    switch (off) {
    case 0x00: /* VERID, read-only */
    case 0x04: /* HSRUN */
    case 0x08: /* RUN */
    case 0x0c: /* VLPR */
    case 0x10: /* STOP */
    case 0x14: /* VLPS */
    case 0x18: /* LLS */
    case 0x1c: /* VLLS */
    case 0x20: /* STATUS, read-only */
    case 0x24: /* CTRL */
    case 0x34: /* BCTRL */
    case 0x44: /* SRAMCTRL */
        return true;
    default:
        return false;
    }
}

static MemTxResult exesx_imx7ulp_pmc1_read(EXeSXProfileWindow *w,
        hwaddr off, uint64_t *value, unsigned size)
{
    if (size != 4 || off >= w->size || w->base != 0x40400000 ||
        !exesx_imx7ulp_pmc1_offset(off)) {
        return MEMTX_ERROR;
    }
    if (off == 0x00) {
        *value = 0; /* Standard feature register, NXP PERI_PMC1.h */
    } else if (off == 0x20) {
        /* Power-good status is modeled as stable. Not analog fidelity. */
        *value = w->regfile[off / 4];
    } else {
        *value = w->regfile[off / 4];
    }
    return MEMTX_OK;
}

static MemTxResult exesx_imx7ulp_pmc1_write(EXeSXProfileWindow *w,
        hwaddr off, uint64_t value, unsigned size)
{
    if (size != 4 || off >= w->size || w->base != 0x40400000 ||
        !exesx_imx7ulp_pmc1_offset(off) ||
        off == 0x00 || off == 0x20) {
        return MEMTX_ERROR;
    }
    w->regfile[off / 4] = (uint32_t)value;
    qemu_log_mask(LOG_GUEST_ERROR,
                  "EXeSX PMC1 WRITE @0x%" HWADDR_PRIx " data=0x%08x\n",
                  w->base + off, (uint32_t)value);
    return MEMTX_OK;
}

/*
 * PMC0 is the M4-domain power controller at 0x410A1000.
 * Its register layout differs from A7-domain PMC1: VLPS is +0x18.
 */
static bool exesx_imx7ulp_pmc0_offset(hwaddr off)
{
    switch (off) {
    case 0x00: /* VERID read-only */
    case 0x04: /* PM_STAT read-only */
    case 0x08: /* HSRUN */
    case 0x0c: /* RUN */
    case 0x10: /* VLPR */
    case 0x14: /* STOP */
    case 0x18: /* VLPS */
    case 0x1c: /* LLS */
    case 0x20: /* VLLS */
    case 0x24: /* STATUS read-only */
    case 0x28: /* CTRL */
    case 0x30: /* ACTRL */
    case 0x38: /* BCTRL */
    case 0x48: /* SRAMCTRL_0 */
    case 0x4c: /* SRAMCTRL_1 */
    case 0x50: /* SRAMCTRL_2 */
        return true;
    default:
        return false;
    }
}

static MemTxResult exesx_imx7ulp_pmc0_read(EXeSXProfileWindow *w,
        hwaddr off, uint64_t *value, unsigned size)
{
    if (size != 4 || off >= w->size || w->base != 0x410a1000 ||
        !exesx_imx7ulp_pmc0_offset(off)) {
        return MEMTX_ERROR;
    }
    if (off == 0x00) {
        *value = 0; /* Standard feature revision */
    } else if (off == 0x04) {
        *value = 0x00010001; /* Both PMC0/PMC1 in RUN state */
    } else {
        *value = w->regfile[off / 4];
    }
    return MEMTX_OK;
}
static MemTxResult exesx_imx7ulp_pmc0_write(EXeSXProfileWindow *w,
        hwaddr off, uint64_t value, unsigned size)
{
    if (size != 4 || off >= w->size || w->base != 0x410a1000 ||
        !exesx_imx7ulp_pmc0_offset(off) ||
        off == 0 || off == 4 || off == 0x24) {
        return MEMTX_ERROR;
    }
    w->regfile[off / 4] = (uint32_t)value;
    qemu_log_mask(LOG_GUEST_ERROR,
                  "EXeSX PMC0 WRITE @0x%" HWADDR_PRIx
                  " data=0x%08x\n", w->base + off, (uint32_t)value);
    return MEMTX_OK;
}
