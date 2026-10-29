/*
 * i.MX7ULP LPSPI2 host controller: opt-in PIO transfer foundation.
 *
 * Register offsets from NXP i.MX7ULP LPSPI / Linux spi-fsl-lpspi.c:
 * CR 0x10, SR 0x14, CFGR1 0x24, CCR 0x40, FCR 0x58, FSR 0x5c,
 * TCR 0x60, TDR 0x64, RSR 0x70, RDR 0x74.
 *
 * Board wiring to ATWINC1510 is NOT confirmed on the original DY357.
 * Default mode preserves the original CR-only model. No WINC device
 * is attached in this commit. A diagnostic loopback is explicitly
 * synthetic; never interpret it as radio/association or factory success.
 *
 * Guest-visible FIFO data/state lives in VMState serialized regfile.
 * This is an eight-bit, immediate PIO-transfer subset; real shift timing,
 * DMA requests, IRQ routing and larger frame modes are not yet modeled.
 */

#define EXESX_LPSPI_RX_HEAD    (0x300 / 4)
#define EXESX_LPSPI_RX_COUNT   (0x304 / 4)
#define EXESX_LPSPI_RX_DATA    (0x310 / 4)
#define EXESX_LPSPI_RX_DEPTH   4

static bool exesx_lpspi2_pio_enabled(void)
{
    return !g_strcmp0(g_getenv("EXESX_EXPERIMENTAL_LPSPI2_FIFO"), "1");
}

static bool exesx_lpspi2_loopback_enabled(void)
{
    return !g_strcmp0(g_getenv("EXESX_DIAGNOSTIC_LPSPI2_LOOPBACK"), "1");
}

static uint32_t exesx_lpspi2_rx_count(EXeSXProfileWindow *w)
{
    return w->regfile[EXESX_LPSPI_RX_COUNT];
}

static void exesx_lpspi2_rx_reset(EXeSXProfileWindow *w)
{
    w->regfile[EXESX_LPSPI_RX_HEAD] = 0;
    w->regfile[EXESX_LPSPI_RX_COUNT] = 0;
}

static uint32_t exesx_lpspi2_status(EXeSXProfileWindow *w)
{
    uint32_t bits = w->regfile[0x14 / 4] | 1U; /* TDF, empty TX FIFO */
    uint32_t water = (w->regfile[0x58 / 4] >> 16) & 3;
    if (exesx_lpspi2_rx_count(w) > water) {
        bits |= 2U; /* RDF RX watermark reached */
    } else {
        bits &= ~2U;
    }
    return bits;
}

static MemTxResult exesx_lpspi2_read(EXeSXProfileWindow *w,
                                    hwaddr off, uint64_t *value,
                                    unsigned size)
{
    uint32_t count;
    if (w->base != UINT64_C(0x40290000) || size != 4) {
        return MEMTX_ERROR;
    }
    if (!exesx_lpspi2_pio_enabled()) {
        if (off != 0x10) {
            return MEMTX_ERROR;
        }
        *value = w->regfile[0x10 / 4];
        return MEMTX_OK;
    }
    switch (off) {
    case 0x00: *value = 0x01000003; return MEMTX_OK; /* VERID */
    case 0x04: *value = 0x00000202; return MEMTX_OK; /* PARAM: 4-word FIFOs */
    case 0x10: case 0x18: case 0x1c: case 0x20:
    case 0x24: case 0x30: case 0x34: case 0x40:
    case 0x58: case 0x60:
        *value = w->regfile[off / 4];
        return MEMTX_OK;
    case 0x14:
        *value = exesx_lpspi2_status(w);
        return MEMTX_OK;
    case 0x5c:
        *value = exesx_lpspi2_rx_count(w) << 16;
        return MEMTX_OK;
    case 0x70:
        *value = exesx_lpspi2_rx_count(w) ? 0U : 2U; /* RXEMPTY */
        return MEMTX_OK;
    case 0x74:
        count = exesx_lpspi2_rx_count(w);
        if (!count) {
            *value = 0;
            return MEMTX_OK;
        }
        *value = w->regfile[EXESX_LPSPI_RX_DATA +
                            w->regfile[EXESX_LPSPI_RX_HEAD]];
        w->regfile[EXESX_LPSPI_RX_HEAD] =
            (w->regfile[EXESX_LPSPI_RX_HEAD] + 1) %
            EXESX_LPSPI_RX_DEPTH;
        w->regfile[EXESX_LPSPI_RX_COUNT] = count - 1;
        return MEMTX_OK;
    default:
        return MEMTX_ERROR; /* do not silently accept reserved offsets */
    }
}

static MemTxResult exesx_lpspi2_write(EXeSXProfileWindow *w,
                                     hwaddr off, uint64_t value,
                                     unsigned size)
{
    uint32_t bits = (uint32_t)value;
    uint32_t count;
    if (w->base != UINT64_C(0x40290000) || size != 4) {
        return MEMTX_ERROR;
    }
    if (!exesx_lpspi2_pio_enabled()) {
        if (off != 0x10) {
            return MEMTX_ERROR;
        }
        if ((bits & 1) && !(w->regfile[0x10 / 4] & 1)) {
            qemu_log_mask(LOG_UNIMP,
                          "EXeSX LPSPI2 MEN enabled @0x40290010: "
                          "SPI TX/RX FIFO, clock/chip-select and IRQ "
                          "not implemented (WLAN wiring unverified)\n");
        }
        w->regfile[0x10 / 4] = bits;
        return MEMTX_OK;
    }

    switch (off) {
    case 0x10: /* CR: RST, RTF, RRF are self-clearing */
        if (bits & (2U | 0x100U | 0x200U)) {
            if (bits & (2U | 0x200U)) {
                exesx_lpspi2_rx_reset(w);
            }
            if (bits & 2U) {
                w->regfile[0x14 / 4] = 0;
            }
        }
        w->regfile[0x10 / 4] = bits & ~(2U | 0x100U | 0x200U);
        return MEMTX_OK;
    case 0x14: /* SR TCF/FCF/WCF W1C */
        w->regfile[0x14 / 4] &= ~(bits & ~3U);
        return MEMTX_OK;
    case 0x18: case 0x1c: case 0x20: case 0x24:
    case 0x30: case 0x34: case 0x40: case 0x58:
    case 0x60:
        w->regfile[off / 4] = bits;
        return MEMTX_OK;
    case 0x64: /* PIO TX data: shift a single 8-bit frame */
        if (!(w->regfile[0x10 / 4] & 1) ||
            !(w->regfile[0x24 / 4] & 1)) {
            qemu_log_mask(LOG_GUEST_ERROR,
                          "EXeSX LPSPI2 TDR without enabled host\n");
            return MEMTX_OK; /* no clock edges without MEN+MASTER */
        }
        if ((w->regfile[0x60 / 4] & 0xfff) != 7) {
            qemu_log_mask(LOG_UNIMP,
                          "EXeSX LPSPI2 unsupported frame width=%u "
                          "(only 8-bit PIO modeled)\n",
                          (w->regfile[0x60 / 4] & 0xfff) + 1);
            return MEMTX_OK;
        }
        /*
         * No confirmed slave wired on this original DY357 bus.
         * Open MISO is not assumed to be a WINC chip ID. Only an
         * EXPLICIT opt-in diagnostic physical loopback returns MOSI.
         * Without it RX data is 0xff (pulled-up disconnected line).
         */
        count = exesx_lpspi2_rx_count(w);
        if (count < EXESX_LPSPI_RX_DEPTH &&
            !(w->regfile[0x60 / 4] & (1U << 19))) {
            uint32_t tail =
                (w->regfile[EXESX_LPSPI_RX_HEAD] + count) %
                EXESX_LPSPI_RX_DEPTH;
            w->regfile[EXESX_LPSPI_RX_DATA + tail] =
                exesx_lpspi2_loopback_enabled() ? (bits & 0xffU) : 0xffU;
            w->regfile[EXESX_LPSPI_RX_COUNT] = count + 1;
        } else if (count >= EXESX_LPSPI_RX_DEPTH) {
            qemu_log_mask(LOG_UNIMP,
                          "EXeSX LPSPI2 RX overrun; cannot drop FIFO "
                          "frames silently\n");
        }
        /* Hardware transfer-complete status; no IRQ/DMA routed yet. */
        w->regfile[0x14 / 4] |= (1U << 10) | (1U << 9);
        return MEMTX_OK;
    default:
        return MEMTX_ERROR;
    }
}
