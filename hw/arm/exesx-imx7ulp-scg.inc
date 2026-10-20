/*
 * SCG1 system clock generation, deliberately bounded early-boot subset.
 * Register offsets and status bits: NXP i.MX7ULP PERI_SCG.h.
 * The external 24MHz SOSC and internal IRC sources are considered already
 * stable when BIOS is entered (ROM-stage clock initialization is absent).
 * PLL lock is presently immediate when enabled: no frequency model yet.
 * GPL-2.0-or-later; no proprietary firmware.
 */
static bool exesx_scg1_offset(hwaddr off)
{
    switch (off) {
    case 0x00: case 0x04: case 0x10: case 0x14:
    case 0x18: case 0x1c: case 0x20: case 0x30:
    case 0x40: case 0x44: case 0x100: case 0x104:
    case 0x200: case 0x204: case 0x300: case 0x304:
    case 0x500: case 0x504: case 0x508: case 0x50c:
    case 0x510: case 0x514: case 0x518: case 0x5f8:
    case 0x600: case 0x604: case 0x608: case 0x60c:
    case 0x610: case 0x614: case 0x618: case 0x6f8:
        return true;
    default:
        return false;
    }
}

static uint32_t exesx_scg1_pfd_status(uint32_t raw, bool pll_enabled)
{
    unsigned i;
    uint32_t result = raw & ~UINT32_C(0x40404040);
    if (!pll_enabled) {
        return result;
    }
    for (i = 0; i < 4; i++) {
        uint32_t pfd = (raw >> (i * 8)) & 0xff;
        uint32_t fraction = pfd & 0x3f;
        /* Clock active only if ungated with a legal divide fraction. */
        if (!(pfd & 0x80) && fraction >= 12 && fraction <= 35) {
            result |= UINT32_C(0x40) << (i * 8);
        }
    }
    return result;
}

static MemTxResult exesx_scg1_read(EXeSXProfileWindow *w,
                                    hwaddr off, uint64_t *value,
                                    unsigned size)
{
    uint32_t raw;
    if (size != 4 || (off & 3) || off >= w->size ||
        w->base != 0x403e0000 || !exesx_scg1_offset(off)) {
        return MEMTX_ERROR;
    }
    raw = w->regfile[off / 4];
    switch (off) {
    case 0x10: /* CSR, reflects RCCR selected source in RUN mode */
        raw = w->regfile[0x14 / 4];
        break;
    case 0x100: case 0x200: case 0x300: /* SOSC/SIRC/FIRC CSR */
    case 0x500: case 0x600: /* Auxiliary/System PLL CSR */
        raw = (raw & ~UINT32_C(0x01000000)) |
              ((raw & 1) ? UINT32_C(0x01000000) : 0);
        break;
    case 0x50c: /* APLL PFD */
        raw = exesx_scg1_pfd_status(raw, w->regfile[0x500 / 4] & 1);
        break;
    case 0x60c: /* SPLL PFD */
        raw = exesx_scg1_pfd_status(raw, w->regfile[0x600 / 4] & 1);
        break;
    default:
        break;
    }
    *value = raw;
    return MEMTX_OK;
}

static MemTxResult exesx_scg1_write(EXeSXProfileWindow *w,
                                     hwaddr off, uint64_t value,
                                     unsigned size)
{
    uint32_t raw = (uint32_t)value;
    if (size != 4 || (off & 3) || off >= w->size ||
        w->base != 0x403e0000 || !exesx_scg1_offset(off)) {
        return MEMTX_ERROR;
    }
    /* Read-only identity and status controls. */
    if (off == 0x00 || off == 0x04 || off == 0x10 || off == 0x44) {
        return MEMTX_ERROR;
    }
    if (off == 0x100 || off == 0x200 || off == 0x300 ||
        off == 0x500 || off == 0x600) {
        if (w->regfile[off / 4] & 0x00800000) { /* LK */
            return MEMTX_ERROR;
        }
        /* Valid/selected/error are hardware status, not writable. */
        raw &= ~UINT32_C(0x07000000);
    }
    if (off == 0x50c || off == 0x60c) {
        /* PFDx_VALID flags are read-only; recomputed from divider/gate. */
        raw &= ~UINT32_C(0x40404040);
    }
    w->regfile[off / 4] = raw;
    qemu_log_mask(LOG_GUEST_ERROR,
                  "EXeSX SCG1 WRITE @0x%" HWADDR_PRIx
                  " =0x%08x\\n", w->base + off, raw);
    return MEMTX_OK;
}
