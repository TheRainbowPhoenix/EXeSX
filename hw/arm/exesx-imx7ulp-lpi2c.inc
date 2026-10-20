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
/*
 * Optional black-box diagnostic ONLY, not a maXTouch implementation:
 *
 * EXESX_I2C4B_REPLY_HEX=001122... enables a synthetic slave on the
 * real M4 LPI2C2 bus at 7-bit address 0x4b.
 * The bytes are repeated on each read transaction; no hardware identity
 * is claimed. Disabling the variable restores real NACK-on-missing-slave.
 *
 * This lets us compare genuine firmware branches after one ACK + scripted
 * read response. All mutable transaction fields live in the VMState-backed
 * regfile (starting at +0x1c0), and we never intercept other buses/IDs.
 */
static const char *exesx_lpi2c_probe_reply(EXeSXProfileWindow *w)
{
    const char *hex = g_getenv("EXESX_I2C4B_REPLY_HEX");
    gsize n, i;
    if (w->base != 0x41035000 || !hex || !hex[0]) {
        return NULL;
    }
    n = strlen(hex);
    if ((n & 1) || n > 128) {
        return NULL;
    }
    for (i = 0; i < n; i++) {
        if (g_ascii_xdigit_value(hex[i]) < 0) {
            return NULL;
        }
    }
    return hex;
}

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
    case 0x14: /* MSR: TDF/RDF plus sticky errors */
        *value = w->regfile[0x14 / 4] |
                 ((w->regfile[0x10 / 4] & 1) ? 1U : 0U) |
                 ((w->regfile[0x1c4 / 4] && exesx_lpi2c_probe_reply(w))
                  ? 2U : 0U);
        return MEMTX_OK;
    case 0x5c: /* MFSR RXCOUNT [18:16] */
        *value = (w->regfile[0x1c4 / 4] &&
                  exesx_lpi2c_probe_reply(w)) ? (1U << 16) : 0;
        return MEMTX_OK;
    case 0x70: { /* MRDR; RXEMPTY if no byte pending */
        const char *hex = exesx_lpi2c_probe_reply(w);
        uint32_t remaining = w->regfile[0x1c4 / 4];
        if (hex && remaining) {
            size_t len = strlen(hex) / 2;
            uint32_t cursor = w->regfile[0x1c8 / 4]++;
            size_t pos = (cursor % len) * 2;
            unsigned hi = g_ascii_xdigit_value(hex[pos]);
            unsigned lo = g_ascii_xdigit_value(hex[pos + 1]);
            w->regfile[0x1c4 / 4] = remaining - 1;
            *value = (hi << 4) | lo;
            qemu_log_mask(LOG_GUEST_ERROR,
                          "EXeSX DIAGNOSTIC I2C4B READ byte=0x%02x"
                          " remaining=%u\\n",
                          (unsigned)*value, remaining - 1);
        } else {
            *value = 0x4000;
        }
        return MEMTX_OK;
    }
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
            const char *probe = exesx_lpi2c_probe_reply(w);
            unsigned address_byte = bits & 0xff;
            if (probe && (address_byte == 0x96 || address_byte == 0x97)) {
                w->regfile[0x1c0 / 4] = address_byte; /* active */
                w->regfile[0x1c4 / 4] = 0; /* pending RX */
                w->regfile[0x1c8 / 4] = 0; /* read cursor */
                if (address_byte == 0x96) {
                    w->regfile[0x1cc / 4] = 0; /* pointer byte index */
                }
                qemu_log_mask(LOG_GUEST_ERROR,
                              "EXeSX DIAGNOSTIC I2C4B ACK @0x%"
                              HWADDR_PRIx " rw=%s (not chip-validated)\\n",
                              w->base, (address_byte & 1) ? "read" : "write");
            } else {
                w->regfile[0x14 / 4] |= 0x400; /* NDF, no slave */
                qemu_log_mask(LOG_GUEST_ERROR,
                              "EXeSX LPI2C @0x%" HWADDR_PRIx
                              " address=0x%02x: NACK (no slave attached)\\n",
                              w->base, address_byte);
            }
        } else if (cmd == 1 && exesx_lpi2c_probe_reply(w) &&
                   w->regfile[0x1c0 / 4] == 0x97) {
            w->regfile[0x1c4 / 4] = (bits & 0xff) + 1;
            w->regfile[0x1c8 / 4] = 0;
            qemu_log_mask(LOG_GUEST_ERROR,
                          "EXeSX DIAGNOSTIC I2C4B RX_REQUEST count=%u\\n",
                          (unsigned)((bits & 0xff) + 1));
        } else if (cmd == 0 && exesx_lpi2c_probe_reply(w) &&
                   w->regfile[0x1c0 / 4] == 0x96) {
            unsigned index = w->regfile[0x1cc / 4]++;
            if (index < 2) {
                w->regfile[(0x1d0 + 4*index) / 4] = bits & 0xff;
                if (index == 1) {
                    unsigned ptr = w->regfile[0x1d0 / 4] |
                                   ((bits & 0xff) << 8);
                    qemu_log_mask(LOG_GUEST_ERROR,
                                  "EXeSX DIAGNOSTIC I2C4B pointer=0x%04x"
                                  " (unidentified slave)\\n", ptr);
                }
            }
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
