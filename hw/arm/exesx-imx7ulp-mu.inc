/*
 * i.MX7ULP Messaging Unit v1, MUA + MUB, two-sided mailbox channels.
 * NXP PERI_MU.h and Linux drivers/mailbox/imx-mailbox.c:
 * MUA=0x41022000, MUB=0x40220000
 * TR0..3 +0x20..0x2c, RR0..3 +0x40..0x4c, SR +0x60, CR +0x64.
 *
 * Four slot mailboxes are shared between the two profile windows.
 * TR write changes the other side's RF status; RR read returns the
 * actual word and releases the sender's TE. GP flags and doorbells
 * are reflected across sides. Snapshot state is saved in the regular
 * per-window regfile. Wiring MU IRQ into NVIC/GIC is not yet done.
 */
#define EXESX_MU_TE_INDEX (0x200 / 4)
#define EXESX_MU_RF_INDEX (0x204 / 4)
#define EXESX_MU_GIP_INDEX (0x208 / 4)

static bool exesx_mu_valid_base(uint64_t base)
{
    return base == UINT64_C(0x41022000) ||
           base == UINT64_C(0x40220000);
}
static EXeSXProfileWindow *exesx_mu_peer(EXeSXProfileWindow *w)
{
    if (!w->board) {
        return NULL;
    }
    return w->base == UINT64_C(0x41022000) ?
        w->board->mu_b : w->board->mu_a;
}
/*
 * Experimental IRQ delivery for NXP MU_A (M4 IRQ22) and MU_B (GIC SPI19).
 * Enable EXESX_EXPERIMENTAL_MU_IRQ=1. Default keeps historical behavior.
 * NXP MU.CR TIEn/RIEn/GIEn masks match SR TE/RF/GIP status nibbles.
 */
static void exesx_mu_update_irq(EXeSXProfileWindow *w)
{
    EXeSXState *board = w->board;
    qemu_irq line;
    uint32_t cr, pending;
    if (!board ||
        g_strcmp0(g_getenv("EXESX_EXPERIMENTAL_MU_IRQ"), "1")) {
        return;
    }
    line = w->base == 0x41022000 ? board->mu_a_irq : board->mu_b_irq;
    if (!line) {
        return;
    }
    cr = w->regfile[0x64 / 4];
    pending = ((cr >> 20) & w->regfile[EXESX_MU_TE_INDEX]) |
              ((cr >> 24) & w->regfile[EXESX_MU_RF_INDEX]) |
              ((cr >> 28) & w->regfile[EXESX_MU_GIP_INDEX]);
    qemu_set_irq(line, (pending & 15) != 0);
}

static MemTxResult exesx_mu_read(EXeSXProfileWindow *w, hwaddr off,
                                uint64_t *value, unsigned size)
{
    EXeSXProfileWindow *peer;
    unsigned chan;
    if (size != 4 || (off & 3) || off >= w->size ||
        !exesx_mu_valid_base(w->base)) {
        return MEMTX_ERROR;
    }
    peer = exesx_mu_peer(w);
    if (off == 0) {
        *value = 0x0100000f; /* MU version 1.0, 4 registers, features */
    } else if (off == 4) {
        *value = 0x00040404; /* 4 TX and RX registers each */
    } else if (off >= 0x20 && off <= 0x2c) {
        /* NXP MU TRn are write-only; reads return zero. */
        *value = 0;
    } else if (off >= 0x40 && off <= 0x4c) {
        chan = (off - 0x40) / 4;
        *value = w->regfile[off / 4];
        if (w->regfile[EXESX_MU_RF_INDEX] & (1U << chan)) {
            w->regfile[EXESX_MU_RF_INDEX] &= ~(1U << chan);
            if (peer) {
                peer->regfile[EXESX_MU_TE_INDEX] |= 1U << chan;
            }
            exesx_mu_update_irq(w);
            if (peer) {
                exesx_mu_update_irq(peer);
            }
        }
    } else if (off == 0x60) {
        uint32_t status =
            (w->regfile[EXESX_MU_TE_INDEX] & 15) << 20 |
            (w->regfile[EXESX_MU_RF_INDEX] & 15) << 24 |
            (w->regfile[EXESX_MU_GIP_INDEX] & 15) << 28;
        if (peer) {
            status |= peer->regfile[0x64 / 4] & 7;
        }
        *value = status;
    } else if (off == 0x64) {
        *value = w->regfile[off / 4];
    } else {
        return MEMTX_ERROR;
    }
    return MEMTX_OK;
}
static MemTxResult exesx_mu_write(EXeSXProfileWindow *w, hwaddr off,
                                 uint64_t value, unsigned size)
{
    EXeSXProfileWindow *peer;
    uint32_t bits = (uint32_t)value;
    unsigned chan;
    if (size != 4 || (off & 3) || off >= w->size ||
        !exesx_mu_valid_base(w->base)) {
        return MEMTX_ERROR;
    }
    peer = exesx_mu_peer(w);
    if (off >= 0x20 && off <= 0x2c) {
        chan = (off - 0x20) / 4;
        if (!(w->regfile[EXESX_MU_TE_INDEX] & (1U << chan))) {
            /*
             * TE=0: no room for another message. Do not convert a
             * non-ready TX write into a synchronous ARM Data Abort.
             * Drop the unaccepted word and preserve existing mailbox
             * data; model does not fabricate a peer acknowledgement.
             */
            qemu_log_mask(LOG_GUEST_ERROR,
                          "EXeSX MU busy TR%u at 0x%" HWADDR_PRIx
                          " ignored data=0x%08x\\n",
                          chan, w->base + off, bits);
            return MEMTX_OK;
        }
        w->regfile[off / 4] = bits;
        w->regfile[EXESX_MU_TE_INDEX] &= ~(1U << chan);
        if (peer) {
            peer->regfile[(0x40 + 4 * chan) / 4] = bits;
            peer->regfile[EXESX_MU_RF_INDEX] |= 1U << chan;
        }
    } else if (off == 0x60) {
        /* Pending general-purpose interrupt flags are write-one-to-clear. */
        w->regfile[EXESX_MU_GIP_INDEX] &= ~((bits >> 28) & 15);
    } else if (off == 0x64) {
        if (bits & 0x20) {
            /* MUR: software MU reset self-clears. */
            w->regfile[EXESX_MU_TE_INDEX] = 15;
            w->regfile[EXESX_MU_RF_INDEX] = 0;
            w->regfile[EXESX_MU_GIP_INDEX] = 0;
        }
        if (peer) {
            peer->regfile[EXESX_MU_GIP_INDEX] |= (bits >> 16) & 15;
        }
        /* GIR strobes and MUR/flag-update commands self clear. */
        w->regfile[0x64 / 4] = bits &
                              ~UINT32_C(0x000f0120);
    } else {
        return MEMTX_ERROR;
    }
    exesx_mu_update_irq(w);
    if (peer) {
        exesx_mu_update_irq(peer);
    }
    qemu_log_mask(LOG_GUEST_ERROR,
                  "EXeSX MU WRITE @0x%" HWADDR_PRIx
                  " data=0x%08x\n", w->base + off, bits);
    return MEMTX_OK;
}
