/*
 * Opt-in i.MX7ULP ChipIdea USB device endpoint-to-TCP fixture.
 * GIC SPI40; 0x40330000 controller (NXP i.MX7ULP / Linux imx7ulp.dtsi).
 *
 * The USB host is an external Python process on 127.0.0.1. It drives
 * genuine device-side SETUP, OUT and IN endpoints. Only an endpoint with
 * an original guest-programmed active dTD is allowed to move data.
 *
 * Request: [op:8, ep:8, n:16le, data[n] as appropriate].
 * 1=SETUP(8 bytes), 2=OUT(payload), 3=IN(n requested),
 * 4=CABLE_CONNECT(0), 5=DISCONNECT(0), 6=BUS_RESET(0).
 * Response: [status:8, ep:8, n:16le, data[n] for IN only].
 * 0=success, 1=NAK/unprimed, 2=STALL, 3=invalid.
 *
 * This is not a complete USB 2.0 wire model or a synthetic WLAN success
 * server. No guest endpoint, USB interrupt, or RAM write is faked without
 * an external host request and/or a real guest descriptor. The original
 * 0x400B firmware boot remains unaffected when opt-in is disabled.
 */
#define EXESX_USB_REQ_SETUP  1
#define EXESX_USB_REQ_OUT    2
#define EXESX_USB_REQ_IN     3
#define EXESX_USB_REQ_ATTACH 4
#define EXESX_USB_REQ_DETACH 5
#define EXESX_USB_REQ_RESET  6
#define EXESX_USB_MAX_PACKET 4096

static bool exesx_usb_enabled(EXeSXProfileWindow *w)
{
    return w && w->base == UINT64_C(0x40330000) &&
           !g_strcmp0(g_getenv("EXESX_EXPERIMENTAL_USB_ENDPOINTS"), "1");
}

static void exesx_usb_update_irq(EXeSXProfileWindow *w)
{
    if (w->board && w->board->usb1_irq) {
        qemu_set_irq(w->board->usb1_irq,
                     !!(w->regfile[0x144 / 4] &
                        w->regfile[0x148 / 4]));
    }
}

static bool exesx_usb_guest_mem(uint32_t pa, void *buffer,
                                unsigned size, bool write)
{
    /* No ROM, MMIO or unaligned descriptor overwrite by the host.
     * The guest supplies the dTD/dQH pointer. Supported mapped DDR
     * begins at 0x60000000 in this EXeSX board. */
    if (pa < 0x60000000 || size > EXESX_USB_MAX_PACKET ||
        (uint64_t)pa + size > UINT64_C(0x68000000)) {
        return false;
    }
    if (write) {
        return address_space_write(&address_space_memory, pa,
                                   MEMTXATTRS_UNSPECIFIED, buffer, size) ==
               MEMTX_OK;
    }
    return address_space_read(&address_space_memory, pa,
                              MEMTXATTRS_UNSPECIFIED, buffer, size) ==
           MEMTX_OK;
}
static bool exesx_usb_load32(uint32_t address, uint32_t *value)
{
    uint8_t data[4];
    if (!exesx_usb_guest_mem(address, data, 4, false)) {
        return false;
    }
    *value = ldl_le_p(data);
    return true;
}
static bool exesx_usb_store32(uint32_t address, uint32_t value)
{
    uint8_t data[4];
    stl_le_p(data, value);
    return exesx_usb_guest_mem(address, data, 4, true);
}

static void exesx_usb_signal(EXeSXProfileWindow *w, uint32_t bits)
{
    w->regfile[0x144 / 4] |= bits;
    exesx_usb_update_irq(w);
}

static int exesx_usb_ep_transfer(EXeSXProfileWindow *w,
                                 uint8_t ep, bool in,
                                 uint8_t *data, unsigned *size)
{
    uint32_t bit, list, qh, next, token, addr, remaining, amount;
    uint32_t flags = w->regfile[(0x1c0 + ep * 4) / 4];
    if (ep > 7 || !(w->regfile[0x140 / 4] & 1) ||
        (w->regfile[0x1a4 / 4] & 3) != 2) {
        return 1; /* not running as USB device */
    }
    /* Dedicated hardware STALL for each endpoint direction. */
    if (flags & (in ? UINT32_C(0x10000) : 1U)) {
        return 2;
    }
    bit = 1U << (ep + (in ? 16 : 0));
    if (!(w->regfile[0x1b8 / 4] & bit)) {
        return 1; /* original guest did not PRIME the endpoint */
    }
    list = w->regfile[0x158 / 4] & ~UINT32_C(0x7ff);
    if (list < 0x60000000) {
        return 3;
    }
    /* ChipIdea QH is 64 bytes for OUT and IN of each endpoint. */
    qh = list + (ep * 2U + (in ? 1U : 0U)) * 64U;
    if (!exesx_usb_load32(qh + 0x10, &next) ||
        (next & 1U)) {
        return 1; /* no active original guest dTD */
    }
    addr = next & ~UINT32_C(0x1f);
    if (!exesx_usb_load32(addr + 4, &token) ||
        !(token & 0x80U)) {
        return 1;
    }
    remaining = (token >> 16) & 0x7fffU;
    if (remaining > EXESX_USB_MAX_PACKET) {
        return 3;
    }
    amount = MIN(*size, remaining);
    uint32_t buffer_pa;
    if (!exesx_usb_load32(addr + 8, &buffer_pa)) {
        return 3;
    }
    /* dTD buffer pointer low 12 bits are valid for initial page offset;
     * the offset is already in the supplied physical first pointer. */
    if (amount && !exesx_usb_guest_mem(buffer_pa, data, amount, !in)) {
        return 3;
    }
    token &= ~(UINT32_C(0x7fff0000) | 0x80U);
    token |= (remaining - amount) << 16;
    if (!exesx_usb_store32(addr + 4, token) ||
        !exesx_usb_store32(qh + 0x14, token)) {
        return 3;
    }
    w->regfile[0x1b8 / 4] &= ~bit; /* ENDPTSTATUS */
    w->regfile[0x1bc / 4] |= bit;  /* ENDPTCOMPLETE */
    *size = amount;
    exesx_usb_signal(w, 1U);       /* USBSTS.UI on host transaction */
    return 0;
}

static void exesx_usb_reply(EXeSXProfileWindow *w, uint8_t status,
                            uint8_t ep, const uint8_t *payload,
                            unsigned size)
{
    uint8_t header[4] = { status, ep, size & 255, size >> 8 };
    int fd = w->usb_peer_fd;
    if (fd < 0) {
        return;
    }
    unsigned sent = 0;
    while (sent < 4) {
        int ret = send(fd, (const char *)header + sent, 4 - sent, 0);
        if (ret <= 0) {
            goto lost;
        }
        sent += ret;
    }
    sent = 0;
    while (sent < size) {
        int ret = send(fd, (const char *)payload + sent, size - sent, 0);
        if (ret <= 0) {
            goto lost;
        }
        sent += ret;
    }
    return;
lost:
    closesocket(fd);
    w->usb_peer_fd = -1;
}

static void exesx_usb_host_packet(EXeSXProfileWindow *w,
                                  const uint8_t *request, unsigned total)
{
    uint8_t op = request[0], ep = request[1];
    unsigned count = request[2] | ((unsigned)request[3] << 8);
    uint8_t payload[EXESX_USB_MAX_PACKET];
    uint32_t qh, list;
    unsigned amount = 0;
    int status = 3;
    if (total < 4 || count > EXESX_USB_MAX_PACKET ||
        (op != EXESX_USB_REQ_IN && total != 4U + count)) {
        exesx_usb_reply(w, 3, ep, NULL, 0);
        return;
    }
    switch (op) {
    case EXESX_USB_REQ_ATTACH:
        if (count || ep) {
            break;
        }
        w->regfile[0x184 / 4] |= (1U << 0) | (2U << 26);
        exesx_usb_signal(w, 4U); /* PORT_CHANGE */
        status = 0;
        break;
    case EXESX_USB_REQ_DETACH:
        if (count || ep) {
            break;
        }
        w->regfile[0x184 / 4] &= ~1U;
        exesx_usb_signal(w, 4U);
        status = 0;
        break;
    case EXESX_USB_REQ_RESET:
        if (count || ep) {
            break;
        }
        /* Hardware reset is host driven. Do NOT mark device enumerated. */
        w->regfile[0x1a8 / 4] = 0;
        w->regfile[0x1b0 / 4] = 0;
        w->regfile[0x1b8 / 4] = 0;
        w->regfile[0x1bc / 4] = 0;
        exesx_usb_signal(w, 1U << 6); /* URI */
        status = 0;
        break;
    case EXESX_USB_REQ_SETUP:
        if (ep || count != 8 ||
            (w->regfile[0x1a4 / 4] & 3) != 2 ||
            !(w->regfile[0x140 / 4] & 1)) {
            status = 1;
            break;
        }
        list = w->regfile[0x158 / 4] & ~UINT32_C(0x7ff);
        qh = list;
        if (list < 0x60000000 ||
            !exesx_usb_guest_mem(qh + 0x28, (void *)(request + 4), 8, true)) {
            status = 3;
            break;
        }
        w->regfile[0x1a8 / 4] |= 1; /* EP0 SETUPSTATUS */
        exesx_usb_signal(w, 1U);
        status = 0;
        break;
    case EXESX_USB_REQ_OUT:
        if (ep > 7) {
            break;
        }
        amount = count;
        memcpy(payload, request + 4, amount);
        status = exesx_usb_ep_transfer(w, ep, false, payload, &amount);
        break;
    case EXESX_USB_REQ_IN:
        if (ep > 7 || total != 4) {
            break;
        }
        amount = count;
        status = exesx_usb_ep_transfer(w, ep, true, payload, &amount);
        if (status != 0) {
            amount = 0;
        }
        break;
    default:
        break;
    }
    exesx_usb_reply(w, status, ep, payload,
                    op == EXESX_USB_REQ_IN && status == 0 ? amount : 0);
}

/* Only the explicit USB opt-in opens a localhost endpoint server.
 * All polling is bounded by select() with zero timeout; no blocking
 * accept or global pause of A7/M4 emulation is permitted.
 */
static void exesx_usb_tick(void *opaque)
{
    EXeSXProfileWindow *w = opaque;
    const char *portenv = g_getenv("EXESX_USB_FIXTURE_TCP_PORT");
    if (!exesx_usb_enabled(w) || !portenv) {
        return;
    }
    if (w->usb_listen_fd < 0) {
        char *stop;
        long port = strtol(portenv, &stop, 10);
        if (*stop || port < 1024 || port > 65535) {
            qemu_log_mask(LOG_GUEST_ERROR,
                          "EXeSX invalid USB fixture localhost port\n");
            return;
        }
        int fd = qemu_socket(AF_INET, SOCK_STREAM, 0);
        struct sockaddr_in addr = { 0 };
        if (fd < 0) {
            return;
        }
        addr.sin_family = AF_INET;
        addr.sin_port = htons((uint16_t)port);
        addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        if (bind(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0 ||
            listen(fd, 1) < 0) {
            closesocket(fd);
            return;
        }
        w->usb_listen_fd = fd;
    }
    fd_set fds;
    struct timeval zero = { 0, 0 };
    int fd = w->usb_peer_fd >= 0 ? w->usb_peer_fd : w->usb_listen_fd;
    FD_ZERO(&fds);
    FD_SET(fd, &fds);
    if (select(fd + 1, &fds, NULL, NULL, &zero) > 0) {
        if (w->usb_peer_fd < 0) {
            struct sockaddr_in peer;
            socklen_t peerlen = sizeof(peer);
            w->usb_peer_fd = accept(fd, (struct sockaddr *)&peer, &peerlen);
            w->usb_rx_have = 0;
        } else {
            unsigned cap = sizeof(w->usb_rxbuf) - w->usb_rx_have;
            int got = recv(fd, (char *)w->usb_rxbuf + w->usb_rx_have,
                           cap, 0);
            if (got <= 0) {
                closesocket(fd);
                w->usb_peer_fd = -1;
                w->usb_rx_have = 0;
            } else {
                w->usb_rx_have += got;
                while (w->usb_rx_have >= 4) {
                    unsigned n = w->usb_rxbuf[2] |
                                 ((unsigned)w->usb_rxbuf[3] << 8);
                    uint8_t op = w->usb_rxbuf[0];
                    unsigned total = 4 + (op == EXESX_USB_REQ_IN ? 0 : n);
                    if (n > EXESX_USB_MAX_PACKET) {
                        exesx_usb_reply(w, 3, w->usb_rxbuf[1], NULL, 0);
                        w->usb_rx_have = 0;
                        break;
                    }
                    if (w->usb_rx_have < total) {
                        break;
                    }
                    exesx_usb_host_packet(w, w->usb_rxbuf, total);
                    memmove(w->usb_rxbuf, w->usb_rxbuf + total,
                            w->usb_rx_have - total);
                    w->usb_rx_have -= total;
                }
            }
        }
    }
    timer_mod(w->usb_poll_timer,
              qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) + INT64_C(1000000));
}

static MemTxResult exesx_usb_read(EXeSXProfileWindow *w, hwaddr off,
                                 uint64_t *data, unsigned size)
{
    if (!exesx_usb_enabled(w) || size != 4 || (off & 3) ||
        off >= 0x200) {
        return MEMTX_ERROR;
    }
    switch (off) {
    case 0x100: *data = 0x01000040; return MEMTX_OK; /* CAPLENGTH=0x40 */
    case 0x124: *data = 0x00000108; return MEMTX_OK; /* DCCPARAMS: 8 EP */
    case 0x140: case 0x144: case 0x148: case 0x154:
    case 0x158: case 0x178: case 0x17c: case 0x184:
    case 0x1a4: case 0x1a8: case 0x1b0: case 0x1b4:
    case 0x1b8: case 0x1bc:
        *data = w->regfile[off / 4];
        return MEMTX_OK;
    default:
        if (off >= 0x1c0 && off <= 0x1dc) {
            *data = w->regfile[off / 4];
            return MEMTX_OK;
        }
        return MEMTX_ERROR;
    }
}

static MemTxResult exesx_usb_write(EXeSXProfileWindow *w, hwaddr off,
                                  uint64_t value, unsigned size)
{
    uint32_t bits = (uint32_t)value;
    if (!exesx_usb_enabled(w) || size != 4 || (off & 3) ||
        off >= 0x200) {
        return MEMTX_ERROR;
    }
    switch (off) {
    case 0x140:
        if (bits & 2) { /* USBCMD.RST auto-clears */
            w->regfile[0x1b0 / 4] = 0;
            w->regfile[0x1b8 / 4] = 0;
            w->regfile[0x1bc / 4] = 0;
        }
        w->regfile[off / 4] = bits & ~2U;
        break;
    case 0x144: case 0x1a8: case 0x1bc:
        w->regfile[off / 4] &= ~bits; /* W1C */
        break;
    case 0x148: case 0x154: case 0x158:
    case 0x178: case 0x17c: case 0x184:
    case 0x1a4:
        w->regfile[off / 4] = bits;
        break;
    case 0x1b0: /* ENDPTPRIME */
        w->regfile[0x1b8 / 4] |= bits;
        w->regfile[0x1b0 / 4] = 0; /* prime handshake completes */
        break;
    case 0x1b4: /* FLUSH */
        w->regfile[0x1b8 / 4] &= ~bits;
        w->regfile[0x1b4 / 4] = 0;
        break;
    default:
        if (off >= 0x1c0 && off <= 0x1dc) {
            w->regfile[off / 4] = bits;
        } else {
            return MEMTX_ERROR;
        }
    }
    exesx_usb_update_irq(w);
    return MEMTX_OK;
}
