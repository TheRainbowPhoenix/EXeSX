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
#define EXESX_LPSPI_GPIO_STATE   (0x320 / 4) /* bit0 valid, bit1 IRQ_N */


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

/*
 * Strict, loopback-only TCP transport for Python WINC1510 SPI slave.
 * No QEMU guest memory writes, no fake WLAN callbacks: electrical
 * transactions are derived exclusively from original TCR/TDR and PCS.
 * Protocol frame: PCS (1), flags BEGIN=1/END=2 (1), nbytes LE (2),
 * nbytes MOSI, exactly nbytes MISO. The Python process is localhost.
 */
/* Original DY357 TCR.BYSW swaps bytes inside each active FIFO word.
 * NXP PERI_LPSPI: TX and RX both swap, including partial final words.
 */
static uint32_t exesx_lpspi2_reverse_bytes(uint32_t value, unsigned bytes)
{
    uint32_t out = 0;
    for (unsigned i = 0; i < bytes; ++i) {
        out = (out << 8) | ((value >> (8 * i)) & 0xff);
    }
    return out;
}

static bool exesx_winc_gpio_pin_high(EXeSXProfileWindow *w,
                                       const char *env_name,
                                       bool default_high)
{
    const char *p = g_getenv(env_name);
    EXeSXProfileWindow *gpio = w->board ? w->board->m4_gpio_b : NULL;
    char *end;
    unsigned long bit;
    if (!p || !*p || !gpio) {
        return default_high;
    }
    bit = strtoul(p, &end, 0);
    if (*end || bit > 31) {
        qemu_log_mask(LOG_GUEST_ERROR, "EXeSX invalid WINC GPIOB pin %s\\n",
                      env_name);
        return default_high;
    }
    uint32_t mask = UINT32_C(1) << bit;
    if (!(gpio->regfile[0x14 / 4] & mask)) {
        /* Never override unconfigured direction or invent an output. */
        return default_high;
    }
    return !!(gpio->regfile[0] & mask);
}

static bool exesx_lpspi2_tcp_exchange(EXeSXProfileWindow *w, uint32_t pcs,
                                     uint32_t nbits, uint32_t bits,
                                     bool high_partial, bool byte_swap,
                                     bool begin, bool end, uint32_t *response)
{
    const char *portstr = g_getenv("EXESX_WINC1510_TCP_PORT");
    char *stop;
    long port;
    uint8_t packet[8] = {0}, reply[5] = {0};
    bool gpio_proto = !g_strcmp0(
        g_getenv("EXESX_WINC1510_GPIO_PROTOCOL"), "1");
    int fd, nbytes;
    size_t sent = 0, received = 0;
    if (!portstr || !*portstr) {
        return false;
    }
    port = strtol(portstr, &stop, 10);
    if (*stop || port < 1024 || port > 65535) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "EXeSX WINC1510 invalid loopback port; not connected\n");
        return false;
    }
    nbytes = (nbits + 7) / 8;
    if ((nbits & 7) || nbytes < 1 || nbytes > 4) {
        qemu_log_mask(LOG_UNIMP,
                      "EXeSX WINC1510 unsupported partial-byte SPI clocks\n");
        return false;
    }
    if (w->lpspi_backend_fd < 0) {
        struct sockaddr_in address = {0};
        fd = qemu_socket(AF_INET, SOCK_STREAM, 0);
        if (fd < 0) {
            return false;
        }
        address.sin_family = AF_INET;
        address.sin_port = htons((uint16_t)port);
        address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        if (connect(fd, (struct sockaddr *)&address, sizeof(address)) < 0) {
            closesocket(fd);
            qemu_log_mask(LOG_GUEST_ERROR,
                          "EXeSX WINC1510 Python backend absent on localhost\n");
            return false;
        }
        w->lpspi_backend_fd = fd;
        begin = true; /* snapshot/reconnect must start a fresh CS */
    }
    packet[0] = pcs;
    packet[1] = (begin ? 1 : 0) | (end ? 2 : 0);
    if (gpio_proto) {
        /* Pins are actual original M4 GPIOB output latches, if a
         * researcher has explicitly mapped their pin numbers.
         * Default disconnected/unmapped control lines are deasserted.
         * RESET_N active high, WAKE_N active low, CHIP_EN active high. */
        if (exesx_winc_gpio_pin_high(w, "EXESX_WINC_RESET_GPIOB_PIN", true)) {
            packet[1] |= 4;
        }
        if (exesx_winc_gpio_pin_high(w, "EXESX_WINC_WAKE_GPIOB_PIN", false)) {
            packet[1] |= 8;
        }
        if (exesx_winc_gpio_pin_high(w, "EXESX_WINC_ENABLE_GPIOB_PIN", true)) {
            packet[1] |= 16;
        }
    }
    packet[2] = nbytes;
    packet[3] = 0;
    /* 'bits' is the already-extracted active 1..4 bytes of TDR.
     * Hardware BYSW reverses their order before clocking SPI. */
    uint32_t wire = byte_swap ?
                    exesx_lpspi2_reverse_bytes(bits, nbytes) : bits;
    for (int i = 0; i < nbytes; ++i) {
        packet[4 + i] = wire >> (8 * (nbytes - 1 - i));
    }
    while (sent < (size_t)(4 + nbytes)) {
        int ret = send(w->lpspi_backend_fd,
                       (const char *)packet + sent, 4 + nbytes - sent, 0);
        if (ret <= 0) {
            goto failed;
        }
        sent += ret;
    }
    /* Extended socket mode adds one sampled IRQ_N byte after MISO.
     * Legacy backend remains byte-for-byte compatible. */
    size_t reply_len = nbytes + (gpio_proto ? 1 : 0);
    while (received < reply_len) {
        int ret = recv(w->lpspi_backend_fd,
                       (char *)reply + received, reply_len - received, 0);
        if (ret <= 0) {
            goto failed;
        }
        received += ret;
    }
    if (gpio_proto) {
        /* 1 = IRQ_N high/idle; 0 = interrupt pending, active low.
         * Drives only the modeled electrical input; no guest event. */
        w->regfile[EXESX_LPSPI_GPIO_STATE] =
            1U | ((reply[nbytes] & 1U) << 1);
    }
    *response = 0;
    for (int i = 0; i < nbytes; ++i) {
        *response = (*response << 8) | reply[i];
    }
    if (byte_swap) {
        *response = exesx_lpspi2_reverse_bytes(*response, nbytes);
    }
    if (high_partial) {
        *response <<= 32 - nbits;
    }
    return true;

failed:
    /* Disconnected backend electrically deasserts IRQ_N, never leaves
     * a stale pending interrupt or fake WLAN completion behind. */
    w->regfile[EXESX_LPSPI_GPIO_STATE] = 0;
    closesocket(w->lpspi_backend_fd);
    w->lpspi_backend_fd = -1;
    qemu_log_mask(LOG_GUEST_ERROR,
                  "EXeSX WINC1510 backend dropped SPI segment; not ACKed\n");
    return false;
}

/*
 * Read the WINC's *physical* IRQ_N state when M4 PORTB is polled.
 * A zero-clock special RPC keeps CS untouched and does not fabricate
 * any SPI response, HIF callback, A7 interrupt, or guest RAM data.
 * The RPC is opt-in to prevent latency/regressions on normal boots.
 * A bounded select() avoids a permanently wedged Python backend.
 */
static void exesx_lpspi2_poll_gpio_irq(EXeSXProfileWindow *w)
{
    uint8_t request[4] = { 0xff, 0x20, 0, 0 };
    uint8_t status = 1;
    fd_set readfds;
    struct timeval deadline = { 0, 20000 };
    if (!w ||
        g_strcmp0(g_getenv("EXESX_WINC1510_GPIO_PROTOCOL"), "1")) {
        return;
    }
    /*
     * The original host may sample IRQ_N before issuing its first SPI
     * command. Do not require an earlier TDR write to connect the slave:
     * that creates a circular dependency when initialization waits for
     * IRQ_N. The zero-clock query preserves CS and never generates a
     * guest-visible completion or synthetic SPI byte.
     */
    if (w->lpspi_backend_fd < 0) {
        const char *portstr = g_getenv("EXESX_WINC1510_TCP_PORT");
        char *stop;
        long port;
        struct sockaddr_in address = {0};
        int conn;
        if (!portstr || !*portstr) {
            return;
        }
        port = strtol(portstr, &stop, 10);
        if (*stop || port < 1024 || port > 65535) {
            return;
        }
        conn = qemu_socket(AF_INET, SOCK_STREAM, 0);
        if (conn < 0) {
            return;
        }
        address.sin_family = AF_INET;
        address.sin_port = htons((uint16_t)port);
        address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        if (connect(conn, (struct sockaddr *)&address,
                    sizeof(address)) < 0) {
            closesocket(conn);
            return;
        }
        w->lpspi_backend_fd = conn;
    }
    int fd = w->lpspi_backend_fd;
    int sent = send(fd, (const char *)request, sizeof(request), 0);
    if (sent != sizeof(request)) {
        goto disconnected;
    }
    FD_ZERO(&readfds);
    FD_SET(fd, &readfds);
    if (select(fd + 1, &readfds, NULL, NULL, &deadline) <= 0 ||
        recv(fd, (char *)&status, 1, 0) != 1) {
        goto disconnected;
    }
    w->regfile[EXESX_LPSPI_GPIO_STATE] =
        1U | ((status & 1U) << 1);
    return;
disconnected:
    closesocket(fd);
    w->lpspi_backend_fd = -1;
    w->regfile[EXESX_LPSPI_GPIO_STATE] = 0;
    qemu_log_mask(LOG_GUEST_ERROR,
                  "EXeSX WINC1510 IRQ_N backend poll unavailable\\n");
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

/* Triggered only by real guest DER/SERQ and a fully programmed pair of
 * eDMA1 descriptors. No PC, RTOS flag, DMA event or guest buffer injection.
 * A7 WLAN original host uses SADDR RAM -> LPSPI2.TDR (TX) and
 * LPSPI2.RDR -> DADDR RAM (RX) for full-duplex DMA transfers.
 */
static void exesx_lpspi2_dma_kick(EXeSXProfileWindow *w);

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
    case 0x1c: /* DER TDDE/RDDE requests, not a success signal */
        w->regfile[off / 4] = bits;
        exesx_lpspi2_dma_kick(w);
        return MEMTX_OK;
    case 0x18: case 0x20: case 0x24:
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
        bool beginning = !w->regfile[EXESX_LPSPI_PCS_ASSERT];
        unsigned pcs = (w->regfile[0x60 / 4] >> 24) & 3U;
        exesx_lpspi2_assert_pcs(w, pcs);
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
        if (g_getenv("EXESX_WINC1510_TCP_PORT")) {
            uint32_t backend_rx;
            bool ending = left == nbits &&
                          !(w->regfile[0x60 / 4] & (1U << 21));
            if (exesx_lpspi2_tcp_exchange(
                    w, pcs, nbits, shifted, high_partial,
                    !!(w->regfile[0x60 / 4] & (1U << 22)),
                    beginning, ending, &backend_rx)) {
                rxword = backend_rx;
            } else {
                /* A disconnected card cannot reply with a fabricated
                 * chip ID, ACK, HIF response or WLAN success value. */
                rxword = high_partial ? mask << (32U - nbits) : mask;
            }
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

/*
 * Guest-originated eDMA1 LPSPI2 transfers. The original DY357 WLAN driver
 * queues scatter/gather TCDs (FUN_601c2740 / FUN_601b82e8), including TX
 * writes to TCR between 512-byte TX/RX segments. Rejecting CSR.ESG on the
 * initial TCD previously prevented those transfers from ever reaching SPI.
 *
 * Deliberately bounded: only genuine DMA1/DMAMUX1 requests for the observed
 * LPSPI2 TX/RX sources, 32-bit transfers, RAM-backed TCD links and <=8192
 * clocked bytes are accepted. No guest RAM, HIF callback or success flag is
 * fabricated: all bytes are moved through the real modeled TDR and RDR.
 */
static bool exesx_lpspi2_dma_advance(EXeSXProfileWindow *w,
                                      EXeSXProfileWindow *dma,
                                      unsigned channel, uint32_t moved)
{
    uint32_t *t = &dma->regfile[(0x1000 + channel * 32) / 4];
    uint16_t csr = t[7] & 0xffff;
    bool link = !!(csr & 0x10); /* eDMA CSR.ESG */
    uint32_t next = t[6];
    uint8_t bytes[32];
    MemTxResult status;

    if (t[0] != UINT32_C(0x40290074)) {
        t[0] += moved;
    }
    if (t[4] != UINT32_C(0x40290064) &&
        t[4] != UINT32_C(0x40290060)) {
        t[4] += moved;
    }
    t[5] &= 0xffff; /* CITER exhausted, preserve DOFF */
    if (csr & 2) { /* INTMAJOR: original DMA completion callback */
        dma->regfile[0x24 / 4] |= 1U << channel;
        qemu_set_irq(w->board->dma1_group_irqs[channel & 15], 1);
    }
    if (link) {
        /* Never follow arbitrary MMIO, ROM or unaligned guest pointers. */
        if ((next & 31) || next < UINT32_C(0x60000000) ||
            next >= UINT32_C(0x70000000)) {
            qemu_log_mask(LOG_GUEST_ERROR,
                          "EXeSX WLAN eDMA invalid linked TCD address\n");
            return false;
        }
        status = address_space_read(&address_space_memory, next,
                                    MEMTXATTRS_UNSPECIFIED,
                                    bytes, sizeof(bytes));
        if (status != MEMTX_OK) {
            qemu_log_mask(LOG_GUEST_ERROR,
                          "EXeSX WLAN eDMA unreadable linked TCD\n");
            return false;
        }
        for (unsigned i = 0; i < 8; ++i) {
            t[i] = ldl_le_p(bytes + 4 * i);
        }
        return true;
    }
    t[7] |= 0x80; /* DONE only for the terminal TCD */
    if (csr & 8) { /* DREQ */
        dma->regfile[0x0c / 4] &= ~(1U << channel);
    }
    return true;
}

static void exesx_lpspi2_dma_kick(EXeSXProfileWindow *w)
{
    EXeSXProfileWindow *dma = w->board->wlan_dma1;
    EXeSXProfileWindow *mux = w->board->dmamux1;
    int tx = -1, rx = -1;
    uint32_t clocked = 0;
    bool tx_done = false, rx_done = false;
    unsigned steps;
    MemTxResult status;

    if (g_strcmp0(g_getenv("EXESX_EXPERIMENTAL_LPSPI2_DMA"), "1") ||
        !exesx_lpspi2_pio_enabled() || !dma || !mux ||
        !(w->regfile[0x10 / 4] & 1) ||
        !(w->regfile[0x24 / 4] & 1) ||
        (w->regfile[0x1c / 4] & 3) != 3) {
        return;
    }

    for (unsigned channel = 0; channel < 32; ++channel) {
        uint32_t *t = &dma->regfile[(0x1000 + channel * 32) / 4];
        uint32_t cfg = mux->regfile[channel];
        uint32_t attr = t[1];
        unsigned ssize = (attr >> 24) & 7, dsize = (attr >> 16) & 7;
        int16_t soff = (int16_t)(attr & 0xffff);
        int16_t doff = (int16_t)(t[5] & 0xffff);
        uint16_t csr = t[7] & 0xffff;
        uint32_t citer = t[5] >> 16;
        uint32_t minor = t[2];

        if (!(dma->regfile[0x0c / 4] & (1U << channel)) ||
            !(cfg & (1U << 31)) ||
            !citer || minor != 4 || citer > 2048 ||
            (csr & 0x80) || ssize != 2 || dsize != 2 ||
            t[3] != 0) {
            continue;
        }
        /* DY357 FUN_601c2f04: DMA1 ch2 TX source 0x1a, ch3 RX
         * source 0x19. Both are actual programmed guest registers. */
        if (t[4] == UINT32_C(0x40290064) &&
            soff == 4 && doff == 0 &&
            (cfg & 0x7f) == 0x1a &&
            t[0] >= UINT32_C(0x60000000)) {
            if (tx < 0) tx = channel;
        } else if (t[0] == UINT32_C(0x40290074) &&
                   soff == 0 && doff == 4 &&
                   (cfg & 0x7f) == 0x19 &&
                   t[4] >= UINT32_C(0x60000000)) {
            if (rx < 0) rx = channel;
        }
    }
    if (tx < 0 || rx < 0) {
        return;
    }

    for (steps = 0; steps < 64 && !tx_done; ++steps) {
        uint32_t *td = &dma->regfile[(0x1000 + tx * 32) / 4];
        uint32_t *rd = &dma->regfile[(0x1000 + rx * 32) / 4];
        uint32_t txcount = td[5] >> 16;
        uint32_t txbytes, rxbytes = 0;
        uint32_t txsrc = td[0], txdest = td[4];
        uint8_t data[4];

        if (td[2] != 4 || !txcount || txcount > 2048 ||
            (td[7] & 0x80)) {
            break;
        }
        txbytes = txcount * 4;
        if (txdest == UINT32_C(0x40290060)) {
            /* A genuine chained TX descriptor reprograms TCR between
             * original 512-byte frames. It clocks no MOSI bytes. */
            uint32_t value;
            if (txbytes != 4 || txsrc < UINT32_C(0x60000000)) {
                break;
            }
            status = address_space_read(&address_space_memory, txsrc,
                                        MEMTXATTRS_UNSPECIFIED, data, 4);
            if (status != MEMTX_OK) break;
            value = ldl_le_p(data);
            if (exesx_lpspi2_write(w, 0x60, value, 4) != MEMTX_OK) {
                break;
            }
        } else if (txdest == UINT32_C(0x40290064) && !rx_done &&
                   rd[0] == UINT32_C(0x40290074) &&
                   td[1] >> 24 == 2 && rd[1] >> 24 == 2 &&
                   txsrc >= UINT32_C(0x60000000) &&
                   rd[4] >= UINT32_C(0x60000000)) {
            uint32_t rxcnt = rd[5] >> 16;
            if (rd[2] != 4 || !rxcnt || rxcnt > 2048) {
                break;
            }
            rxbytes = rxcnt * 4;
            if (txbytes != rxbytes ||
                clocked + txbytes > 8192 ||
                w->regfile[EXESX_LPSPI_FRAME_LEFT] <
                    txbytes * 8U) {
                break;
            }
            for (uint32_t i = 0; i < txbytes; i += 4) {
                uint64_t word;
                status = address_space_read(&address_space_memory,
                                            txsrc + i,
                                            MEMTXATTRS_UNSPECIFIED, data, 4);
                if (status != MEMTX_OK ||
                    exesx_lpspi2_write(w, 0x64,
                                        ldl_le_p(data), 4) != MEMTX_OK ||
                    exesx_lpspi2_read(w, 0x74, &word, 4) != MEMTX_OK) {
                    return;
                }
                stl_le_p(data, (uint32_t)word);
                status = address_space_write(&address_space_memory,
                                             rd[4] + i,
                                             MEMTXATTRS_UNSPECIFIED, data, 4);
                if (status != MEMTX_OK) {
                    qemu_log_mask(LOG_GUEST_ERROR,
                                  "EXeSX WLAN eDMA RX RAM bus error\n");
                    return;
                }
            }
            clocked += txbytes;
            if (!exesx_lpspi2_dma_advance(w, dma, rx, rxbytes)) {
                return;
            }
            rx_done = !(rd[5] >> 16);
        } else {
            /* Unsupported peripheral descriptor: don't produce a
             * successful guest DMA interrupt without real clocks. */
            break;
        }
        bool was_link = !!(td[7] & 0x10);
        if (!exesx_lpspi2_dma_advance(w, dma, tx, txbytes)) {
            return;
        }
        tx_done = !was_link;
        if (rxbytes && rx_done) {
            /* RX descriptor's successor may have been loaded above. */
            rx_done = !!(rd[7] & 0x80);
        }
    }
    if (clocked && !g_strcmp0(g_getenv("EXESX_TRACE_WLAN_SPI"), "1")) {
        qemu_log("EXeSX WINC guest-originated linked eDMA "
                 "%u bytes, %u TCD steps, TX ch%d RX ch%d\n",
                 clocked, steps, tx, rx);
    }
}
