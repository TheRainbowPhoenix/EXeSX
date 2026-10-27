/* ROHM BU21029MUV: 4-wire resistive touch controller on M4 LPI2C2.
 * The original M4 (0x1ffdb9xx) addresses slave 0x40 and receives 14
 * coordinate/pressure bytes, then samples PTB3 for active-low PEN_INT.
 * Separate from BU26154 audio CODEC at slave 0x1a.
 * Device is opt-in pending board-level confirmation:
 * EXESX_BU21029_LPI2C_BUS=2; EXESX_BU21029_TOUCH_FILE="down x y [z1 z2]".
 * All coordinates are RAW 12-bit, NOT screen pixels or IPC messages.
 */
static bool exesx_bu21029_enabled(uint64_t i2c_base)
{
    /* Read immutable launch configuration ONCE, not millions of times
     * in the M4 GPIO PDIR hot loop. Codes 1..4 select bus 0..3;
     * 5 means disabled. g_once is safe with multi-threaded TCG. */
    static gsize configured_bus = 0;
    if (g_once_init_enter(&configured_bus)) {
        const char *bus = g_getenv("EXESX_BU21029_LPI2C_BUS");
        gsize code = bus && bus[0] >= '0' && bus[0] <= '3' &&
                     !bus[1] ? (gsize)(bus[0] - '0') + 1 : 5;
        g_once_init_leave(&configured_bus, code);
    }
    return configured_bus <= 4 &&
           i2c_base == UINT64_C(0x41033000) +
                       (configured_bus - 1) * 0x1000;
}

static bool exesx_bu21029_contact(EXeSXState *board,
                                  uint16_t *x, uint16_t *y,
                                  uint16_t *z1, uint16_t *z2)
{
    int64_t now = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);

    if (!board) {
        return false;
    }
    if (now >= board->m4_touch_next_poll_ns) {
        const char *path = g_getenv("EXESX_BU21029_TOUCH_FILE");
        gchar *contents = NULL;
        unsigned down = 0, ix = 0, iy = 0, iz1 = 800, iz2 = 1200;
        int parsed = 0;
        board->m4_touch_next_poll_ns = now + INT64_C(5000000);
        board->m4_touch_down = false;
        if (path && *path &&
            g_file_get_contents(path, &contents, NULL, NULL)) {
            parsed = sscanf(contents, "%u %u %u %u %u",
                            &down, &ix, &iy, &iz1, &iz2);
            if ((parsed == 3 || parsed == 5) && down == 1 &&
                ix <= 4095 && iy <= 4095 && iz1 > 0 &&
                iz1 <= 4095 && iz2 >= iz1 && iz2 <= 4095) {
                board->m4_touch_down = true;
                board->m4_touch_x = ix;
                board->m4_touch_y = iy;
                board->m4_touch_z1 = iz1;
                board->m4_touch_z2 = iz2;
            }
            g_free(contents);
        }
    }
    if (board->m4_touch_down) {
        if (x) { *x = board->m4_touch_x; }
        if (y) { *y = board->m4_touch_y; }
        if (z1) { *z1 = board->m4_touch_z1; }
        if (z2) { *z2 = board->m4_touch_z2; }
    }
    return board->m4_touch_down;
}

/* BU21029 scan and pen-INT state, stored in the existing migration-safe
 * LPI2C2 register file. CF=0 autoscan must precede an IRQ; a raw host
 * electrode alone must not impersonate a completed measurement.
 *
 * State @0x208: bit0 touch scanned/interval started, bit1 INT asserted.
 * Deadline @0x20c: unsigned guest-virtual microseconds (wrap-safe).
 * The first conversion is modeled as 2ms, later conversions as 20.48ms
 * interval + 2ms conversion. Analog filters are not modeled.
 *
 * Per ROHM Auto Mode sequence, INT is initially HIGH. It goes LOW
 * only after the first full X/Y/Z scan; reading the conversion result
 * deasserts it until the next interval. No M4 NVIC or IPC event is
 * created here: the original PORTB IRQC and M4 firmware own both. */
static bool exesx_bu21029_pen_irq_asserted(EXeSXState *board)
{
    EXeSXProfileWindow *w = board ? board->m4_lpi2c2 : NULL;
    uint32_t state, now_us, deadline;
    bool down;
    if (!w || !exesx_bu21029_enabled(w->base)) {
        return false;
    }
    down = exesx_bu21029_contact(board, NULL, NULL, NULL, NULL);
    state = w->regfile[0x208 / 4];
    if (!down || (w->regfile[0x1fc / 4] & 0xfc) != 0x80) {
        /* Pen release or explicit stop/conversion mode: idle, INT HIGH. */
        if (state && !g_strcmp0(g_getenv("EXESX_TRACE_BU21029"), "1")) {
            qemu_log("EXeSX BU21029 PEN_IRQ idle: down=%u command=0x%02x prior=%u\n",
                     down, w->regfile[0x1fc / 4] & 0xff, state);
        }
        w->regfile[0x208 / 4] = 0;
        return false;
    }
    now_us = (uint32_t)(qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) / 1000);
    if (!(state & 1)) {
        w->regfile[0x20c / 4] = now_us + 2000;
        state = 1;
    } else {
        deadline = w->regfile[0x20c / 4];
        if (!(state & 2) && (int32_t)(now_us - deadline) >= 0) {
            state |= 2;
        }
    }
    if (state != w->regfile[0x208 / 4] &&
        !g_strcmp0(g_getenv("EXESX_TRACE_BU21029"), "1")) {
        qemu_log("EXeSX BU21029 PEN_IRQ state=%u (old=%u) now_us=%u next_us=%u\n",
                 state, w->regfile[0x208 / 4], now_us,
                 w->regfile[0x20c / 4]);
    }
    w->regfile[0x208 / 4] = state;
    return (state & 2) != 0;
}

static uint32_t exesx_bu21029_gpio_b_levels(EXeSXState *board,
                                               uint32_t levels)
{
    if (!exesx_bu21029_enabled(UINT64_C(0x41035000))) {
        return levels;
    }
    /* PTB3 is an active-low physical input, sampled by genuine M4 GPIO.
     * The PORTB/IRQ57 hardware model handles flag and NVIC delivery. */
    return exesx_bu21029_pen_irq_asserted(board) ?
           levels & ~UINT32_C(0x8) : levels | UINT32_C(0x8);
}
