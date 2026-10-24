/*
 * NXP i.MX7ULP SEMA42 hardware semaphore (A7/M4 shared gate ownership).
 * 16 byte-wide gate registers at +0..+0x0f, packed in descending groups:
 *  +0x03 Gate0, +0x02 Gate1, +0x01 Gate2, +0x00 Gate3, etc.
 * Gate values are zero=unlocked, 1..15=holding hardware domain ID.
 * A nonzero store atomically acquires an unlocked gate; a zero store from
 * its owner releases it. This early-boot model has no fairness/IRQ support.
 * User firmware is not included.
 */
static bool exesx_sema42_base(uint64_t base)
{
    return base == 0x4101b000 || base == 0x401b0000;
}
static MemTxResult exesx_sema42_read(EXeSXProfileWindow *w,
                                    hwaddr off, uint64_t *value,
                                    unsigned size)
{
    if (!exesx_sema42_base(w->base) || off + size > w->size) {
        return MEMTX_ERROR;
    }
    if (size == 1 && off < 16) {
        *value = w->regfile[off] & 0xf;
        return MEMTX_OK;
    }
    if (size == 2 && off == 0x42) {
        *value = w->regfile[0x100 / 4] & 0xffff;
        return MEMTX_OK;
    }
    return MEMTX_ERROR;
}
static MemTxResult exesx_sema42_write(EXeSXProfileWindow *w,
                                     hwaddr off, uint64_t value,
                                     unsigned size)
{
    uint32_t data = (uint32_t)value;
    uint32_t *gate;
    CPUState *requester = current_cpu;
    /* QEMU CPU index is diagnostic only until the A7/M4 domain
     * assignment has been cross-checked against original firmware.
     * Do not grant ownership merely because a CPU wrote an unlock.
     */
    int requester_index = requester ? requester->cpu_index : -1;
    if (!exesx_sema42_base(w->base) || off + size > w->size) {
        return MEMTX_ERROR;
    }
    if (size == 1 && off < 16) {
        gate = &w->regfile[off];
        uint32_t old_gate = *gate & 0xf;
        if (data > 15) {
            return MEMTX_ERROR;
        }
        if (*gate == 0 && data) {
            *gate = data; /* Atomic software-domain acquisition */
        } else if (*gate == data) {
            /* A same-domain nonzero attempt retains ownership. */
        } else if (data == 0) {
            /*
             * Gate 2 is shared by the original A7/M4 firmware. Domain 2
             * belongs to A7 (CPU0), domain 1 to M4 (CPU1). A zero write
             * is accepted only from the domain currently owning it.
             * The old unconditional release let A7 unlock M4's gate.
             *
             * Leave other gates on the preexisting model until their
             * original domain assignments are validated independently.
             */
            if (off != 1 ||
                (*gate == 2 && requester_index == 0) ||
                (*gate == 1 && requester_index == 1)) {
                *gate = 0;
            }
        }
        /*
         * Opt-in, unlimited gate-2 trace. Record every acquisition and
         * attempted release, including unsuccessful writes. Use the ARM guest execution PC from the running vCPU state.
         * Both mapping addresses are logged to detect alias divergence.
         * Run with -D private.log and EXESX_TRACE_SEMA42_GATE2=1.
         */
        if (off == 1 &&
            !g_strcmp0(g_getenv("EXESX_TRACE_SEMA42_GATE2"), "1")) {
            uint32_t before = old_gate;
            const char *action = data == 0 ?
                (!before ? "release-empty" :
                 (*gate == before ? "release-denied" : "release")) :
                (!before ? "acquire" :
                 (before == data ? "reacquire-own" : "blocked"));
            qemu_log("EXeSX SEMA42_GATE2 t_ns=%" PRIu64
                     " cpu=%d pc=0x%" PRIx64 " map=0x%" HWADDR_PRIx
                     " action=%s write=%u before=%u after=%u\n",
                     (uint64_t)qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL),
                     requester_index,
                     requester ? (uint64_t)ARM_CPU(requester)->env.regs[15] : 0,
                     w->base, action, data, before, *gate);
        }
        qemu_log_mask(LOG_GUEST_ERROR,
                      "EXeSX SEMA42 gate=%u domain=%u state=%u @0x%"
                      HWADDR_PRIx "\n",
                      (unsigned)((off & ~3U) + (3U-(off & 3U))),
                      data, *gate, w->base+off);
        return MEMTX_OK;
    }
    if (size == 2 && off == 0x42) {
        /* NXP reset sequence: 0xe2 then 0x1d as high-byte keys.
         * Explicitly temporary: gate domain access restrictions not wired. */
        uint32_t phase = w->regfile[0x104 / 4];
        if ((data >> 8) == 0xe2) {
            w->regfile[0x104 / 4] = 1;
            w->regfile[0x100 / 4] = 0x1000 | (data & 0xff);
        } else if (phase == 1 && (data >> 8) == 0x1d) {
            unsigned n = data & 0xff;
            if (n == 0xff) {
                for (unsigned j=0;j<16;j++) {
                    w->regfile[j] = 0;
                }
            } else if (n < 16) {
                w->regfile[(n & ~3U) + (3U-(n & 3U))] = 0;
            }
            w->regfile[0x104 / 4] = 0;
            w->regfile[0x100 / 4] = 0;
        } else {
            w->regfile[0x104 / 4] = 0;
            w->regfile[0x100 / 4] = 0;
        }
        return MEMTX_OK;
    }
    return MEMTX_ERROR;
}
