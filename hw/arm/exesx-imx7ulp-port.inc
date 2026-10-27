/*
 * i.MX7ULP PORT A..F pin-control / GPIO interrupt status.
 * NXP PERI_PORT.h:
 * PCR[0..31] @0x00..0x7c, GPCLR/GPCHR @0x80/84,
 * GICLR/GICHR @0x88/8c and ISFR @0xa0.
 * Non-routed pins remain quiet; no IRQ assertions or electrical modeling.
 *
 * The register data is VMState-serialized by the EXeSX profile board.
 */
/*
 * Register-derived M4 PORT edge/level interrupt model.
 * Original M4 IRQ vector 72 -> external NVIC IRQ56/PCTLA;
 * vector 73 -> IRQ57/PCTLB (NXP i.MX7ULP RM Table 3-1).
 * Off unless EXESX_EXPERIMENTAL_M4_PORT_IRQ=1.
 */
static qemu_irq exesx_m4_port_irq(EXeSXProfileWindow *w)
{
    if (!w->board) {
        return NULL;
    }
    return w->base == UINT64_C(0x4103f000) ?
           w->board->m4_porta_irq :
           w->base == UINT64_C(0x41040000) ?
           w->board->m4_portb_irq : NULL;
}
static bool exesx_port_irqc_enabled(uint32_t pcr)
{
    unsigned irqc = (pcr >> 16) & 15;
    return irqc >= 8 && irqc <= 12;
}
static void exesx_m4_port_irq_update(EXeSXProfileWindow *w)
{
    qemu_irq irq;
    unsigned pin;
    bool pending = false;
    if (!w->m4_port_poll_timer || !(irq = exesx_m4_port_irq(w))) {
        return;
    }
    for (pin = 0; pin < 32; ++pin) {
        if ((w->regfile[0xa0 / 4] & (UINT32_C(1) << pin)) &&
            exesx_port_irqc_enabled(w->regfile[pin])) {
            pending = true;
            break;
        }
    }
    qemu_set_irq(irq, pending);
}
static void exesx_m4_port_observe_inputs(EXeSXProfileWindow *w,
                                          uint32_t levels)
{
    uint32_t before = w->m4_port_previous;
    /*
     * Opt-in diagnostic A/B only: suppress repeated level-trigger ISF
     * assertion while a pin is held. This is NOT the default silicon
     * behavior; use only to determine whether M4 IRQ56 repetition can
     * starve the original key-IPC worker after its RTOS flag posts.
     */
    bool edge_only = !g_strcmp0(
        g_getenv("EXESX_DIAGNOSTIC_M4_PORT_EDGE_ONLY"), "1");
    unsigned pin;
    w->m4_port_previous = levels;
    if (!w->m4_port_sampled) {
        w->m4_port_sampled = true; /* sample reference, not a fake edge */
        return;
    }
    for (pin = 0; pin < 32; ++pin) {
        uint32_t bit = UINT32_C(1) << pin;
        uint32_t pcr = w->regfile[pin];
        unsigned irqc = (pcr >> 16) & 15;
        bool oldhigh = (before & bit) != 0;
        bool newhigh = (levels & bit) != 0;
        bool trigger = (irqc == 8 && !newhigh &&
                        (!edge_only || oldhigh)) ||
                       (irqc == 9 && !oldhigh && newhigh) ||
                       (irqc == 10 && oldhigh && !newhigh) ||
                       (irqc == 11 && oldhigh != newhigh) ||
                       (irqc == 12 && newhigh &&
                        (!edge_only || !oldhigh));
        if (trigger) {
            w->regfile[pin] |= UINT32_C(0x01000000); /* PCR.ISF */
            w->regfile[0xa0 / 4] |= bit;             /* PORT.ISFR */
        }
    }
    exesx_m4_port_irq_update(w);
}

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
        if (bits & UINT32_C(0x01000000)) {
            w->regfile[0xa0 / 4] &= ~(UINT32_C(1) << (off / 4));
        }
    } else if (off == 0xa0) {
        /* ISFR is a bitmap of sticky pin flags, write-one-to-clear. */
        w->regfile[off / 4] &= ~bits;
        for (unsigned pin = 0; pin < 32; pin++) {
            if (bits & (UINT32_C(1) << pin)) {
                w->regfile[pin] &= ~UINT32_C(0x01000000);
            }
        }
    } else if (off == 0x88 || off == 0x8c) {
        /*
         * PORT.GICLR/GICHR differs from GPCLR/GPCHR:
         * GIWE = low 16 bits select PCR[0..15] / PCR[16..31],
         * GIWD = upper 16 bits become PCR[n][31:16].
         * The original M4 uses GICLR=0x00086008 and GICHR=0x0008808c
         * to arm IRQC=8 (interrupt on logic zero) on keyboard columns.
         * Previously these writes were only mirrored, leaving all
         * PORTA.PCR interrupts disabled; M4 IRQ56 never woke the
         * keyboard event producer.
         */
        unsigned first = off == 0x88 ? 0 : 16;
        uint32_t select = bits & 0xffff;
        uint32_t irq_data = bits & UINT32_C(0xffff0000);
        for (unsigned n = 0; n < 16; n++) {
            if (select & (UINT32_C(1) << n)) {
                unsigned pin = first + n;
                w->regfile[pin] = (w->regfile[pin] & 0xffff) | irq_data;
            }
        }
        w->regfile[off / 4] = bits;
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
    if (w->m4_port_poll_timer) {
        exesx_m4_port_irq_update(w);
    }
    if (w->base == UINT64_C(0x41040000) && off == 0x0c &&
        !g_strcmp0(g_getenv("EXESX_TRACE_BU21029"), "1")) {
        qemu_log("EXeSX BU21029 PORTB.PCR3 write=0x%08x effective=0x%08x ISFR=0x%08x\n",
                 bits, w->regfile[off / 4], w->regfile[0xa0 / 4]);
    }
    qemu_log_mask(LOG_GUEST_ERROR,
                  "EXeSX PORT WRITE @0x%" HWADDR_PRIx
                  " data=0x%08x\n", w->base+off, bits);
    return MEMTX_OK;
}
