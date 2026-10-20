/*
 * i.MX7ULP LPI2C controller: explicit early-boot master register model.
 * NXP MCIMX7U5 PERI_LPI2C.h; LPI2C0..3 at 0x41033000..0x41036000.
 *
 * Model handles control reset/enable, timing configuration, FIFO status,
 * W1C status flags and MTDR start/stop commands. There is no attached I2C
 * slave: a START attempts an address and produces NACK, not a fake device
 * response. No clock-stretching, RX FIFO, GPIO pinmux linkage or NVIC IRQ.
 * State resides in the existing VMState-backed register file.
 */
static bool exesx_lpi2c_valid_base(uint64_t base)
{
    return base == 0x41033000 || base == 0x41034000 ||
           base == 0x41035000 || base == 0x41036000;
}
static bool exesx_lpi2c_offset(hwaddr off)
{
    if (off >= 0x110 && off <= 0x170 && !(off & 3)) {
        switch (off) {
        case 0x110: case 0x114: case 0x118: case 0x11c:
        case 0x124: case 0x128: case 0x140:
        case 0x150: case 0x154: case 0x160: case 0x170:
            return true;
        }
    }
    switch (off) {
    case 0x00: case 0x04:
    case 0x10: case 0x14: case 0x18: case 0x1c:
    case 0x20: case 0x24: case 0x28: case 0x2c:
    case 0x40: case 0x48: case 0x50:
    case 0x58: case 0x5c: case 0x60: case 0x70:
        return true;
    }
    return false;
}
static MemTxResult exesx_lpi2c_read(EXeSXProfileWindow *w, hwaddr off,
                                    uint64_t *value, unsigned size)
{
    if (size != 4 || off >= w->size || !exesx_lpi2c_offset(off) ||
        !exesx_lpi2c_valid_base(w->base)) {
        return MEMTX_ERROR;
    }
    switch (off) {
    case 0x00: *value = 0x01000003; return MEMTX_OK; /* VERID */
    case 0x04: *value = 0x00000202; return MEMTX_OK; /* PARAM: 4 x TX/RX */
    case 0x14: /* MSR: TDF when module enabled, plus sticky errors */
        *value = w->regfile[0x14 / 4] |
                 ((w->regfile[0x10 / 4] & 1) ? 1U : 0U);
        return MEMTX_OK;
    case 0x5c: *value = 0; return MEMTX_OK; /* MFSR: FIFOs empty */
    case 0x70: *value = 0x4000; return MEMTX_OK; /* MRDR: RXEMPTY */
    default:
        *value = w->regfile[off / 4];
        return MEMTX_OK;
    }
}
static MemTxResult exesx_lpi2c_write(EXeSXProfileWindow *w, hwaddr off,
                                     uint64_t value, unsigned size)
{
    uint32_t bits = (uint32_t)value;
    if (size != 4 || off >= w->size || !exesx_lpi2c_offset(off) ||
        !exesx_lpi2c_valid_base(w->base)) {
        return MEMTX_ERROR;
    }
    if (off == 0 || off == 4 || off == 0x5c || off == 0x70 ||
        off == 0x150 || off == 0x170) {
        return MEMTX_ERROR; /* Strictly read-only. */
    }
    if (off == 0x10) {
        if (bits & 2) {
            /* RST is self-clearing; FIFO and sticky status reset. */
            w->regfile[0x14 / 4] = 0;
            w->regfile[0x10 / 4] = 0;
        }
        w->regfile[0x10 / 4] = bits & ~2U;
    } else if (off == 0x14 || off == 0x114) {
        /* MSR/SSR sticky flag bits, write 1 to clear. */
        w->regfile[off / 4] &= ~bits;
    } else if (off == 0x60) {
        /* MTDR: COMMAND bits 10:8, DATA bits 7:0. */
        unsigned cmd = (bits >> 8) & 7;
        if (cmd == 4 || cmd == 5) {
            /* Address phase: no guest I2C slaves registered yet. */
            w->regfile[0x14 / 4] |= 0x400; /* NDF: unexpected NACK */
            qemu_log_mask(LOG_GUEST_ERROR,
                          "EXeSX LPI2C @0x%" HWADDR_PRIx
                          " address=0x%02x: NACK (no slave attached)\n",
                          w->base, (unsigned)(bits & 0xff));
        } else if (cmd == 2) {
            w->regfile[0x14 / 4] |= 0x300; /* EPF + SDF */
        }
        w->regfile[off / 4] = bits;
    } else {
        w->regfile[off / 4] = bits;
    }
    qemu_log_mask(LOG_GUEST_ERROR,
                  "EXeSX LPI2C WRITE @0x%" HWADDR_PRIx
                  " data=0x%08x\n", w->base + off, bits);
    return MEMTX_OK;
}
