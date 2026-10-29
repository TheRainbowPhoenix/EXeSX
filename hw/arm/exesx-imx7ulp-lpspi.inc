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
 * Multiword frames are shifted as little-endian RX FIFO *words*. The
 * selected PCS is derived from TCR, not guessed from a Wi-Fi command.
 * DMA0 peripheral requests, interrupt routing, and real shift timing
 * still require independent validation against original guest traces.
 */

#define EXESX_LPSPI_RX_HEAD     (0x300 / 4)
#define EXESX_LPSPI_RX_COUNT    (0x304 / 4)
#define EXESX_LPSPI_RX_DATA     (0x340 / 4)
#define EXESX_LPSPI_RX_DEPTH    16
#define EXESX_LPSPI_FRAME_LEFT  (0x310 / 4)
#define EXESX_LPSPI_ACTIVE_PCS  (0x314 / 4)
#define EXESX_LPSPI_PCS_ASSERT  (0x318 / 4)
#define EXESX_LPSPI_FRAME_COUNT (0x31c / 4)

static void exesx_lpspi2_deassert_pcs(EXeSXProfileWindow *w)
{
    if (w->regfile[EXESX_LPSPI_PCS_ASSERT] &&
        !g_strcmp0(g_getenv("EXESX_TRACE_WLAN_SPI"), "1")) {
        qemu_log("EXeSX LPSPI2 PCS%u deassert after genuine frame\n",
                 w->regfile[EXESX_LPSPI_ACTIVE_PCS]);
    }
    w->regfile[EXESX_LPSPI_PCS_ASSERT] = 0;
    w->regfile[EXESX_LPSPI_FRAME_LEFT] = 0;
}

static void exesx_lpspi2_assert_pcs(EXeSXProfileWindow *w, unsigned pcs)
{
    if (w->regfile[EXESX_LPSPI_PCS_ASSERT] &&
        w->regfile[EXESX_LPSPI_ACTIVE_PCS] != pcs) {
        exesx_lpspi2_deassert_pcs(w);
    }
    if (!w->regfile[EXESX_LPSPI_PCS_ASSERT]) {
        w->regfile[EXESX_LPSPI_ACTIVE_PCS] = pcs;
        w->regfile[EXESX_LPSPI_PCS_ASSERT] = 1;
        if (!g_strcmp0(g_getenv("EXESX_TRACE_WLAN_SPI"), "1")) {
            qemu_log("EXeSX LPSPI2 PCS%u assert (hardware host)\n", pcs);
        }
    }
}


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
    for (unsigned i = 0; i < EXESX_LPSPI_RX_DEPTH; ++i) {
        w->regfile[EXESX_LPSPI_RX_DATA + i] = 0;
    }
}

static uint32_t exesx_lpspi2_status(EXeSXProfileWindow *w)
{
    uint32_t bits = w->regfile[0x14 / 4] | 1U; /* TDF: TX shifter idle */
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
    case 0x04: *value = 0x00000404; return MEMTX_OK; /* PARAM: 16 words */
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
        if (!(bits & 1U) || (bits & 2U)) {
            exesx_lpspi2_deassert_pcs(w);
        }
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
        w->regfile[off / 4] = bits;
        return MEMTX_OK;
    case 0x60: { /* TCR: PCS bits 24-25, FRAMESZ bits 0-11 */
        uint32_t old = w->regfile[0x60 / 4];
        if ((w->regfile[EXESX_LPSPI_PCS_ASSERT] != 0) &&
            !(old & (1U << 21))) {
            exesx_lpspi2_deassert_pcs(w);
        }
        w->regfile[0x60 / 4] = bits;
        w->regfile[EXESX_LPSPI_FRAME_LEFT] = (bits & 0xfffU) + 1;
        w->regfile[EXESX_LPSPI_FRAME_COUNT]++;
        w->regfile[0x14 / 4] &= ~((1U << 10) | (1U << 9));
        return MEMTX_OK;
    }
    case 0x64: { /* TDR shifts 1..32 bits from each packed 32-bit word */
        uint32_t left, nbits, shifted, rxword;
        if (!(w->regfile[0x10 / 4] & 1) ||
            !(w->regfile[0x24 / 4] & 1)) {
            qemu_log_mask(LOG_GUEST_ERROR,
                          "EXeSX LPSPI2 TDR without enabled host\n");
            return MEMTX_OK; /* no clock edges without MEN+MASTER */
        }
        left = w->regfile[EXESX_LPSPI_FRAME_LEFT];
        if (!left) {
            qemu_log_mask(LOG_GUEST_ERROR,
                          "EXeSX LPSPI2 TDR outside a programmed frame\n");
            return MEMTX_OK;
        }
        nbits = MIN(left, 32U);
        /*
         * Full 32-bit words retain their byte order. In the original
         * driver a *terminal partial word* of a multiword transfer is
         * placed in the upper byte lanes (FUN_601c2580), whereas a
         * standalone 8-bit LPSPI frame uses low lane 0 as normal.
         */
        bool high_partial = nbits < 32U &&
                            ((w->regfile[0x60 / 4] & 0xfffU) + 1U) > 32U;
        uint32_t mask = nbits == 32U ? UINT32_MAX :
                        (1U << nbits) - 1U;
        shifted = high_partial ? (bits >> (32U - nbits)) & mask :
                   bits & mask;
        exesx_lpspi2_assert_pcs(w, (w->regfile[0x60 / 4] >> 24) & 3);
        /*
         * Disconnected MISO uses pulled-up all-one bits. A *synthetic*
         * loopback returns shifted MOSI, never a guessed Wi-Fi ID.
         * The native firmware writes full words then drains RX words.
         * For a shorter terminal word, unused bits are zero-filled.
         */
        rxword = exesx_lpspi2_loopback_enabled() ? shifted : mask;
        if (high_partial) {
            rxword <<= (32U - nbits);
        }
        count = exesx_lpspi2_rx_count(w);
        if (count >= EXESX_LPSPI_RX_DEPTH) {
            qemu_log_mask(LOG_GUEST_ERROR,
                          "EXeSX LPSPI2 RX FIFO overrun; no fake success\n");
            w->regfile[0x14 / 4] |= (1U << 11); /* REF */
            return MEMTX_OK;
        }
        if (!(w->regfile[0x60 / 4] & (1U << 19))) {
            uint32_t tail =
                (w->regfile[EXESX_LPSPI_RX_HEAD] + count) %
                EXESX_LPSPI_RX_DEPTH;
            w->regfile[EXESX_LPSPI_RX_DATA + tail] = rxword;
            w->regfile[EXESX_LPSPI_RX_COUNT] = count + 1;
        }
        if (!g_strcmp0(g_getenv("EXESX_TRACE_WLAN_SPI"), "1")) {
            qemu_log("EXeSX LPSPI2 PIO PCS%u shift %u bits"
                     " MOSI=0x%08x MISO=0x%08x left=%u\n",
                     w->regfile[EXESX_LPSPI_ACTIVE_PCS], nbits,
                     shifted, rxword, left - nbits);
        }
        w->regfile[EXESX_LPSPI_FRAME_LEFT] = left - nbits;
        if (left == nbits) {
            w->regfile[0x14 / 4] |= (1U << 10) | (1U << 9);
            if (!(w->regfile[0x60 / 4] & (1U << 21))) {
                exesx_lpspi2_deassert_pcs(w);
            }
        }
        return MEMTX_OK;
    }
    default:
        return MEMTX_ERROR;
    }
}
