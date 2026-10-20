/*
 * i.MX7ULP PORT A..F pin-control / GPIO interrupt status.
 * NXP PERI_PORT.h:
 * PCR[0..31] @0x00..0x7c, GPCLR/GPCHR @0x80/84,
 * GICLR/GICHR @0x88/8c and ISFR @0xa0.
 * Non-routed pins remain quiet; no IRQ assertions or electrical modeling.
 *
 * The register data is VMState-serialized by the EXeSX profile board.
 */
static bool exesx_port_known_base(uint64_t base)
{
    switch (base) {
    case 0x4103f000: case 0x41040000:
    case 0x40ae0000: case 0x40af0000:
    case 0x40b00000: case 0x40b10000:
        return true;
    default: return false;
    }
}
static bool exesx_port_offset(hwaddr off)
{
    return !(off & 3) &&
           (off < 0x80 || off == 0x80 || off == 0x84 ||
            off == 0x88 || off == 0x8c || off == 0xa0);
}
static MemTxResult exesx_port_read(EXeSXProfileWindow *w, hwaddr off,
                                   uint64_t *value, unsigned size)
{
    if (size != 4 || off >= w->size || !exesx_port_known_base(w->base) ||
        !exesx_port_offset(off)) {
        return MEMTX_ERROR;
    }
    *value = w->regfile[off / 4];
    return MEMTX_OK;
}
static MemTxResult exesx_port_write(EXeSXProfileWindow *w, hwaddr off,
                                    uint64_t value, unsigned size)
{
    uint32_t bits = (uint32_t)value;
    if (size != 4 || off >= w->size || !exesx_port_known_base(w->base) ||
        !exesx_port_offset(off)) {
        return MEMTX_ERROR;
    }
    if (off < 0x80) {
        /* PCR[n] bit24 ISF is hardware state with write-one-to-clear. */
        w->regfile[off / 4] = (bits & ~UINT32_C(0x01000000)) |
            (w->regfile[off / 4] & UINT32_C(0x01000000) &
             ~bits);
    } else if (off == 0xa0) {
        /* ISFR is a bitmap of sticky pin flags, write-one-to-clear. */
        w->regfile[off / 4] &= ~bits;
    } else if (off == 0x80 || off == 0x84) {
        /* Global pin write data GPWD applied to pins selected by GPWE. */
        unsigned n;
        unsigned first = (off == 0x80) ? 0 : 16;
        uint32_t select = bits >> 16;
        for (n = 0; n < 16; ++n) {
            if (select & (1U << n)) {
                uint32_t old = w->regfile[(first+n)];
                uint32_t newbits = bits & 0xffff;
                w->regfile[first+n] = (old & ~UINT32_C(0xffff)) |
                                       newbits;
            }
        }
        w->regfile[off / 4] = bits;
    } else {
        w->regfile[off / 4] = bits;
    }
    qemu_log_mask(LOG_GUEST_ERROR,
                  "EXeSX PORT WRITE @0x%" HWADDR_PRIx
                  " data=0x%08x\n", w->base+off, bits);
    return MEMTX_OK;
}
