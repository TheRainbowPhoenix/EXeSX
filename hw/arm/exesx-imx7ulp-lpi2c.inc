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

/* Diagnostic-only 8-bit register echo; do not confuse with a real chip.
 * Preserve all registers in the existing serialized QEMU regfile.
 */
static bool exesx_lpi2c_register_mirror(EXeSXProfileWindow *w)
{
    const char *v = g_getenv("EXESX_I2C4B_REGISTER_MIRROR");
    return w->base == 0x41035000 && v && !strcmp(v, "1") &&
           !exesx_lpi2c_probe_reply(w);
}

/* Separate diagnostic hypothesis at I2C 0x40. This is NOT a chip model. */
static bool exesx_lpi2c_register_mirror40(EXeSXProfileWindow *w)
{
    const char *v = g_getenv("EXESX_I2C40_REGISTER_MIRROR");
    return w->base == 0x41035000 && v && !strcmp(v, "1");
}

/* State for the currently ACKed slave, kept in VMState-backed regfile. */
static bool exesx_lpi2c_active_mirror(EXeSXProfileWindow *w)
{
    unsigned addr = w->regfile[0x1c0 / 4] & 0xfe;
    return (addr == 0x96 && exesx_lpi2c_register_mirror(w)) ||
           (addr == 0x80 && exesx_lpi2c_register_mirror40(w) &&
            !exesx_bu21029_enabled(w->base));
}


/* Opt-in ROHM BU26154 touch digital interface (DY890 board candidate).
 * Not assigned to DY357: EXESX_BU26154_LPI2C_BUS=0..3 explicitly selects
 * M4 I2C port. Address 0x1a is the documented ROHM 2-wire slave.
 * MAPCON switch: read=0x1c, write=0x1d, select map0/1/2.
 * Touch controller registers are ONLY on MAP1; on MAP0 0x0c/0x0d
 * is clock enable, where TCLKEN bit7 must be asserted for conversion.
 * MAP1: TCHCTRL read=0x60 write=0x61; 12-bit ADC=0x62/0x64.
 * Touch input file "down x y" provides 12-bit RAW 0..4095 samples;
 * default disconnected. Pen IRQ/codec/pressure/clock NOT emulated.
 */
static bool exesx_bu26154_present(EXeSXProfileWindow *w)
{
    const char *bus = g_getenv("EXESX_BU26154_LPI2C_BUS");
    return bus && bus[0] >= '0' && bus[0] <= '3' && !bus[1] &&
           w->base == UINT64_C(0x41033000) + (bus[0] - '0') * 0x1000;
}
static bool exesx_bu26154_active(EXeSXProfileWindow *w)
{
    return exesx_bu26154_present(w) &&
           (w->regfile[0x1c0 / 4] & 0xfe) == 0x34;
}
static uint32_t exesx_bu26154_map(EXeSXProfileWindow *w)
{
    return w->regfile[0x1ec / 4] & 3;
}
static uint32_t exesx_bu26154_touch_clock(EXeSXProfileWindow *w)
{
    return w->regfile[0x1f0 / 4] & 0x80;
}
static uint32_t exesx_bu26154_ctrl(EXeSXProfileWindow *w)
{
    return w->regfile[0x1e4 / 4] ? w->regfile[0x1e0 / 4] : 0x78;
}
static uint16_t exesx_bu26154_adc(EXeSXProfileWindow *w)
{
    const char *path = g_getenv("EXESX_BU26154_TOUCH_FILE");
    gchar *src = NULL;
    unsigned down, x, y;
    uint32_t ctrl = exesx_bu26154_ctrl(w);
    uint16_t result = 0;
    if (!(ctrl & 0x80) || !exesx_bu26154_touch_clock(w) || !path || !*path ||
        !g_file_get_contents(path, &src, NULL, NULL)) {
        return 0;
    }
    if (sscanf(src, "%u %u %u", &down, &x, &y) == 3 &&
        down == 1 && x <= 4095 && y <= 4095) {
        switch ((ctrl >> 4) & 3) {
        case 0: result = x; break;
        case 1: result = y; break;
        default:
            qemu_log_mask(LOG_UNIMP,
                          "EXeSX BU26154 pressure conversion not implemented\n");
        }
    }
    g_free(src);
    return result;
}
static uint32_t exesx_bu26154_read_byte(EXeSXProfileWindow *w)
{
    uint32_t reg = w->regfile[0x1e8 / 4] & 255;
    uint32_t bank = exesx_bu26154_map(w), value = 0;
    if (reg == 0x1c) {
        value = bank;
    } else if (bank == 0 && reg == 0x0c) {
        value = w->regfile[0x1f0 / 4];
    } else if (bank == 1 && reg == 0x60) {
        value = exesx_bu26154_ctrl(w);
    } else if (bank == 1 && (reg == 0x62 || reg == 0x64)) {
        value = reg == 0x62 ? exesx_bu26154_adc(w) >> 4 :
                              exesx_bu26154_adc(w) & 15;
    } else {
        qemu_log_mask(LOG_UNIMP,
                      "EXeSX BU26154 unsupported read MAP%u reg 0x%02x\n",
                      bank, reg);
    }
    w->regfile[0x1e8 / 4] = (reg + 2) & 255;
    return value;
}
static void exesx_bu26154_tx_byte(EXeSXProfileWindow *w,
                                 unsigned index, uint32_t data)
{
    uint32_t reg;
    if (!index) {
        w->regfile[0x1e8 / 4] = data & 255;
        return;
    }
    reg = w->regfile[0x1e8 / 4] & 255;
    uint32_t bank = exesx_bu26154_map(w);
    if (reg == 0x1d && (data & 255) < 3) {
        /* MAPCON is the actual ROHM register-bank selector. */
        w->regfile[0x1ec / 4] = data & 255;
    } else if (bank == 0 && reg == 0x0d) {
        /* Preserve CLK.EN bits while gating touch ADC on TCLKEN. */
        w->regfile[0x1f0 / 4] = data & 255;
    } else if (bank == 1 && reg == 0x61) {
        w->regfile[0x1e0 / 4] = data & 255;
        w->regfile[0x1e4 / 4] = 1;
        qemu_log_mask(LOG_UNIMP,
                      "EXeSX BU26154 MAP1 touch control=0x%02x"
                      " pen IRQ/analog conversion timing not implemented\n",
                      data & 255);
    } else {
        qemu_log_mask(LOG_UNIMP,
                      "EXeSX BU26154 unsupported MAP%u write"
                      " reg=0x%02x data=0x%02x\n",
                      bank, reg, data & 255);
    }
    w->regfile[0x1e8 / 4] = (reg + 2) & 255;
}

/*
 * ROHM BU21029 4-wire resistive touchscreen (not BU26154 CODEC).
 * Original M4 calls 0x1ffdb9dc, 0x1ffdba12 and reads PORTB3 low.
 * I2C slave 0x40: register command byte (index << 3 | bank << 2),
 * then data; conversion commands 0x84/0x8d and 14-byte report.
 * All mutable state below is in the existing VMState-backed regfile.
 */
static bool exesx_bu21029_active(EXeSXProfileWindow *w)
{
    return exesx_bu21029_enabled(w->base) &&
           (w->regfile[0x1c0 / 4] & 0xfe) == 0x80;
}

static uint8_t exesx_bu21029_read_byte(EXeSXProfileWindow *w)
{
    unsigned cmd = w->regfile[0x1f4 / 4] & 0xff;
    unsigned pos = w->regfile[0x1c8 / 4]++;
    uint16_t x = 0, y = 0, z1 = 0, z2 = 0;
    bool down = exesx_bu21029_contact(&x, &y, &z1, &z2);
    unsigned reg, bank;
    if (cmd & 0x80) {
        /* M4 FUN_1FFDba12 decodes seven big-endian 16-bit words.
         * First two are raw 12-bit coordinates shifted left by four.
         * Other slots are Z readings / optional dual-touch metadata;
         * never report a second contact without a second host input. */
        uint16_t words[7] = {
            (uint16_t)(x << 4), (uint16_t)(y << 4),
            (uint16_t)(z1 << 4), (uint16_t)(z2 << 4),
            (uint16_t)(z1 << 4), 0, 0
        };
        uint16_t v = (down && pos < 14) ? words[pos / 2] : 0;
        return (pos & 1) ? (v & 0xff) : (v >> 8);
    }
    reg = (cmd >> 3) & 15;
    bank = (cmd >> 2) & 1;
    if (bank == 0 && reg == 0x0d) {
        /* STATUS: AUTO + BUSY + TOUCH; no invented calibration done. */
        return 0x48 | (down ? 1U : 0U);
    }
    if (bank == 0 && reg == 0x0e) {
        return 0x02; /* ROHM silicon ID 0x0229 */
    }
    if (bank == 0 && reg == 0x0f) {
        return 0x29;
    }
    return w->regfile[0x300 / 4 + bank * 16 + reg] & 0xff;
}

static void exesx_bu21029_write_byte(EXeSXProfileWindow *w,
                                    unsigned index, uint32_t data)
{
    if (index == 0) {
        w->regfile[0x1f4 / 4] = data & 0xff; /* command/address */
        if ((data & 0x80) && data != 0x80 && data != 0x84 &&
            data != 0x8d && data != 0xa8) {
            qemu_log_mask(LOG_UNIMP,
                          "EXeSX BU21029 unimplemented command 0x%02x\n",
                          data & 0xff);
        }
        return;
    }
    if (index == 1) {
        unsigned cmd = w->regfile[0x1f4 / 4] & 0xff;
        unsigned reg = (cmd >> 3) & 15;
        unsigned bank = (cmd >> 2) & 1;
        if (cmd & 0x80) {
            qemu_log_mask(LOG_UNIMP,
                          "EXeSX BU21029 unexpected data after command"
                          " 0x%02x\n", cmd);
        } else if (bank == 0 && (reg == 0x0d || reg == 0x0e || reg == 0x0f)) {
            qemu_log_mask(LOG_UNIMP,
                          "EXeSX BU21029 read-only register write 0x%02x\n",
                          reg);
        } else {
            w->regfile[0x300 / 4 + bank * 16 + reg] = data & 0xff;
        }
    } else {
        qemu_log_mask(LOG_UNIMP,
                      "EXeSX BU21029 unsupported %u-byte control write\n",
                      index + 1);
    }
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
                 ((w->regfile[0x1c4 / 4] && (exesx_lpi2c_probe_reply(w) || exesx_lpi2c_active_mirror(w) ||
                   exesx_bu26154_active(w) ||
                   exesx_bu21029_active(w)))
                  ? 2U : 0U);
        return MEMTX_OK;
    case 0x5c: /* MFSR RXCOUNT [18:16] */
        *value = (w->regfile[0x1c4 / 4] &&
                  (exesx_lpi2c_probe_reply(w) || exesx_lpi2c_active_mirror(w) ||
                   exesx_bu26154_active(w) ||
                   exesx_bu21029_active(w))) ? (1U << 16) : 0;
        return MEMTX_OK;
    case 0x70: { /* MRDR; RXEMPTY if no byte pending */
        const char *hex = exesx_lpi2c_probe_reply(w);
        uint32_t remaining = w->regfile[0x1c4 / 4];
        if (exesx_bu21029_active(w) && remaining) {
            *value = exesx_bu21029_read_byte(w);
            w->regfile[0x1c4 / 4] = remaining - 1;
        } else if (exesx_bu26154_active(w) && remaining) {
            *value = exesx_bu26154_read_byte(w);
            w->regfile[0x1c4 / 4] = remaining - 1;
        } else if (exesx_lpi2c_active_mirror(w) && remaining) {
            unsigned ptr = w->regfile[0x1d8 / 4] & 0xff;
            unsigned addr = w->regfile[0x1c0 / 4] & 0xfe;
            unsigned bank = addr == 0x80 ? 0x2000 / 4 : 0x1000 / 4;
            *value = w->regfile[bank + ptr] & 0xff;
            w->regfile[0x1d8 / 4] = (ptr + 1) & 0xff;
            w->regfile[0x1c4 / 4] = remaining - 1;
            qemu_log_mask(LOG_GUEST_ERROR,
                          "EXeSX DIAGNOSTIC %s MIRROR READ"
                          " reg=0x%02x byte=0x%02x remaining=%u\n",
                          addr == 0x80 ? "I2C40" : "I2C4B",
                          ptr, (unsigned)*value, remaining - 1);
        } else if (hex && remaining) {
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
            bool accept4b = (probe || exesx_lpi2c_register_mirror(w)) &&
                            (address_byte == 0x96 || address_byte == 0x97);
            bool accept40 = exesx_lpi2c_register_mirror40(w) &&
                            (address_byte == 0x80 || address_byte == 0x81);
            bool accept_ts = exesx_bu21029_enabled(w->base) &&
                             (address_byte == 0x80 || address_byte == 0x81);
            bool accept_bu = exesx_bu26154_present(w) &&
                             (address_byte == 0x34 || address_byte == 0x35);
            if (accept4b || accept40 || accept_bu || accept_ts) {
                w->regfile[0x1c0 / 4] = address_byte; /* active */
                w->regfile[0x1c4 / 4] = 0; /* pending RX */
                w->regfile[0x1c8 / 4] = 0; /* read cursor */
                if (!(address_byte & 1)) {
                    w->regfile[0x1cc / 4] = 0; /* pointer byte index */
                }
                qemu_log_mask(LOG_GUEST_ERROR,
                              "EXeSX DIAGNOSTIC %s ACK @0x%"
                              HWADDR_PRIx " rw=%s (not chip-validated)\\n",
                              accept_ts ? "BU21029" :
                              (accept_bu ? "BU26154" :
                              (accept40 ? "I2C40" : "I2C4B")),
                              w->base, (address_byte & 1) ? "read" : "write");
            } else {
                w->regfile[0x14 / 4] |= 0x400; /* NDF, no slave */
                qemu_log_mask(LOG_GUEST_ERROR,
                              "EXeSX LPI2C @0x%" HWADDR_PRIx
                              " address=0x%02x: NACK (no slave attached)\\n",
                              w->base, address_byte);
            }
        } else if (cmd == 1 &&
                   (exesx_lpi2c_probe_reply(w) ||
                    exesx_lpi2c_active_mirror(w) ||
                    exesx_bu26154_active(w) ||
                    exesx_bu21029_active(w)) &&
                   (w->regfile[0x1c0 / 4] == 0x97 ||
                    w->regfile[0x1c0 / 4] == 0x81 ||
                    w->regfile[0x1c0 / 4] == 0x35)) {
            w->regfile[0x1c4 / 4] = (bits & 0xff) + 1;
            w->regfile[0x1c8 / 4] = 0;
            qemu_log_mask(LOG_GUEST_ERROR,
                          "EXeSX DIAGNOSTIC %s RX_REQUEST count=%u\\n",
                          exesx_bu21029_active(w) ? "BU21029" :
                          (w->regfile[0x1c0 / 4] == 0x35 ? "BU26154" :
                          (w->regfile[0x1c0 / 4] == 0x81 ? "I2C40" : "I2C4B")),
                          (unsigned)((bits & 0xff) + 1));
        } else if (cmd == 0 &&
                   (exesx_lpi2c_probe_reply(w) ||
                    exesx_lpi2c_active_mirror(w) ||
                    exesx_bu26154_active(w) ||
                    exesx_bu21029_active(w)) &&
                   (w->regfile[0x1c0 / 4] == 0x96 ||
                    w->regfile[0x1c0 / 4] == 0x80 ||
                    w->regfile[0x1c0 / 4] == 0x34)) {
            unsigned index = w->regfile[0x1cc / 4]++;
            if (exesx_bu21029_active(w)) {
                exesx_bu21029_write_byte(w, index, bits & 255);
            } else if (exesx_bu26154_active(w)) {
                exesx_bu26154_tx_byte(w, index, bits & 255);
            } else if (exesx_lpi2c_active_mirror(w)) {
                if (index == 0) {
                    w->regfile[0x1d8 / 4] = bits & 0xff;
                } else {
                    unsigned reg = w->regfile[0x1d8 / 4] & 0xff;
                    unsigned address = w->regfile[0x1c0 / 4] & 0xfe;
                    unsigned bank = address == 0x80 ? 0x2000 / 4 : 0x1000 / 4;
                    w->regfile[bank + reg] = bits & 0xff;
                    w->regfile[0x1d8 / 4] = (reg + 1) & 0xff;
                    qemu_log_mask(LOG_GUEST_ERROR,
                                  "EXeSX DIAGNOSTIC %s MIRROR WRITE"
                                  " reg=0x%02x byte=0x%02x\n",
                                  address == 0x80 ? "I2C40" : "I2C4B",
                                  reg, bits & 0xff);
                }
            } else if (index < 2) {
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
