/*
 * TPM6/TPM7: early-boot Timer/PWM counter and control registers.
 * NXP MCIMX7U5 PERI_TPM.h and fsl_clock.h (TPM6 @0x40a10000).
 * Experimental clock period: QEMU virtual microseconds, not board-calibrated.
 * Internal epoch is kept in spare regfile indexes >0x100 and serialized with
 * all other board registers for snapshot rollback. No IRQ output yet.
 */
static bool exesx_tpm_offset(hwaddr off)
{
    return off == 0 || off == 4 || off == 8 ||
           off == 0x10 || off == 0x14 || off == 0x18 ||
           off == 0x1c ||
           (off >= 0x20 && off <= 0x4c && !(off & 3)) ||
           off == 0x64 || off == 0x6c || off == 0x70 ||
           off == 0x78 || off == 0x80 || off == 0x84;
}
static uint64_t exesx_tpm_epoch(EXeSXProfileWindow *w)
{
    return ((uint64_t)w->regfile[0x104 / 4] << 32) |
           w->regfile[0x100 / 4];
}
static void exesx_tpm_set_epoch(EXeSXProfileWindow *w)
{
    uint64_t ns = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    w->regfile[0x100 / 4] = (uint32_t)ns;
    w->regfile[0x104 / 4] = (uint32_t)(ns >> 32);
}
static uint32_t exesx_tpm_counter(EXeSXProfileWindow *w)
{
    uint32_t sc = w->regfile[0x10 / 4];
    uint32_t base = w->regfile[0x108 / 4];
    uint64_t elapsed, period = (uint64_t)w->regfile[0x18 / 4] + 1;
    if ((sc & 0x18) != 0x08) {
        return base;
    }
    elapsed = (qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) -
               exesx_tpm_epoch(w)) / 1000;
    elapsed >>= sc & 7;
    return (uint32_t)((base + elapsed) % period);
}
static MemTxResult exesx_tpm_read(EXeSXProfileWindow *w, hwaddr off,
                                  uint64_t *value, unsigned size)
{
    if (size != 4 || !exesx_tpm_offset(off) || off >= w->size ||
        (w->base != 0x40a10000 && w->base != 0x40a20000)) {
        return MEMTX_ERROR;
    }
    if (off == 0x14) {
        *value = exesx_tpm_counter(w);
    } else if (off == 0x00) {
        *value = 3; /* NXP TPM standard feature set with filter/combiner */
    } else if (off == 0x04) {
        *value = 6; /* Six compare/capture channels */
    } else {
        *value = w->regfile[off / 4];
    }
    return MEMTX_OK;
}
static MemTxResult exesx_tpm_write(EXeSXProfileWindow *w, hwaddr off,
                                   uint64_t value, unsigned size)
{
    uint32_t bits = (uint32_t)value;
    if (size != 4 || !exesx_tpm_offset(off) || off >= w->size ||
        (w->base != 0x40a10000 && w->base != 0x40a20000) ||
        off == 0 || off == 4) {
        return MEMTX_ERROR;
    }
    if (off == 0x10) {
        /* Snapshot the old count before changing divider / CMOD. */
        w->regfile[0x108 / 4] = exesx_tpm_counter(w);
        exesx_tpm_set_epoch(w);
        w->regfile[0x10 / 4] = bits & ~UINT32_C(0x80);
    } else if (off == 0x14) {
        /* Counter write: resets CNT as described in the TPM SDK. */
        w->regfile[0x108 / 4] = 0;
        w->regfile[0x14 / 4] = 0;
        exesx_tpm_set_epoch(w);
    } else if (off == 0x18) {
        w->regfile[0x18 / 4] = bits;
    } else if (off == 0x08 && (bits & 2)) {
        /* Module soft reset bit self clears. */
        w->regfile[0x10 / 4] = 0;
        w->regfile[0x108 / 4] = 0;
        w->regfile[0x18 / 4] = 0xffff;
        exesx_tpm_set_epoch(w);
        w->regfile[0x08 / 4] = bits & ~2U;
    } else {
        w->regfile[off / 4] = bits;
    }
    qemu_log_mask(LOG_GUEST_ERROR,
                  "EXeSX TPM WRITE @0x%" HWADDR_PRIx
                  " data=0x%08x\\n", w->base + off, bits);
    return MEMTX_OK;
}
