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
        if (data > 15) {
            return MEMTX_ERROR;
        }
        if (*gate == 0 && data) {
            *gate = data; /* Atomic software-domain acquisition */
        } else if (*gate == data) {
            /* A same-domain nonzero attempt retains ownership. */
        } else if (data == 0) {
            /* Only the currently executing domain may release.
             * For now, the A7 domain is the one that acquired the gate. */
            *gate = 0;
        }
        static unsigned int trace_sample_count;
        if (!g_strcmp0(g_getenv("EXESX_TRACE_SEMA42_CPU"), "1") &&
            trace_sample_count++ < 128) {
            qemu_log_mask(LOG_UNIMP,
                          "EXeSX SEMA42 CPU=%d guest-pc=%08x gate=%u write=%u state=%u @0x%"
                          HWADDR_PRIx "\n",
                          requester_index,
                          requester ? (uint32_t)ARM_CPU(requester)->env.regs[15] : 0,
                          (unsigned)((off & ~3U) + (3U - (off & 3U))),
                          data, *gate, w->base + off);
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
