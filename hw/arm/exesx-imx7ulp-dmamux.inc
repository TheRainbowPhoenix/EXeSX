/*
 * NXP MCIMX7U5 i.MX7ULP M4 DMAMUX0 (0x41020000) and A7 DMAMUX1 (0x40210000): 32 CHCFG registers, uint32_t stride 4.
 * PERI_DMAMUX.h: CHCFG[n] offset n*4, SOURCE[6:0], A_ON[29],
 * TRIG[30], ENBL[31]. Undocumented/reserved bits are RAZ/WI.
 *
 * This is configuration storage only. Source selection and TRIG do not
 * synthesize DMA data requests; an actual DMA engine remains necessary.
 * Underlying profile regfile is snapshottable by EXeSX.
 */
#define EXESX_DMAMUX1_CHCFG_COUNT 32
#define EXESX_DMAMUX1_CHCFG_MASK UINT32_C(0xe000007f)

static bool exesx_dmamux1_access(EXeSXProfileWindow *w,
                                hwaddr off, unsigned size)
{
    return (w->base == UINT64_C(0x41020000) ||
            w->base == UINT64_C(0x40210000)) &&
           (size == 1 || size == 2 || size == 4) &&
           !(off & (size - 1)) &&
           off + size <= 4 * EXESX_DMAMUX1_CHCFG_COUNT &&
           ((off & 3) + size <= 4);
}

static MemTxResult exesx_dmamux1_read(EXeSXProfileWindow *w,
                                     hwaddr off, uint64_t *value,
                                     unsigned size)
{
    uint32_t word;
    if (!exesx_dmamux1_access(w, off, size)) {
        return MEMTX_ERROR;
    }
    word = w->regfile[off / 4] & EXESX_DMAMUX1_CHCFG_MASK;
    *value = (word >> ((off & 3) * 8)) &
             ((UINT64_C(1) << (size * 8)) - 1);
    return MEMTX_OK;
}

static MemTxResult exesx_dmamux1_write(EXeSXProfileWindow *w,
                                      hwaddr off, uint64_t value,
                                      unsigned size)
{
    uint32_t shift;
    uint32_t mask;
    if (!exesx_dmamux1_access(w, off, size)) {
        return MEMTX_ERROR;
    }
    shift = (off & 3) * 8;
    mask = (uint32_t)(((UINT64_C(1) << (size * 8)) - 1) << shift);
    uint32_t old_cfg = w->regfile[off / 4];
    w->regfile[off / 4] = ((old_cfg & ~mask) |
                          (((uint32_t)value << shift) & mask)) &
                         EXESX_DMAMUX1_CHCFG_MASK;
    if (w->base == UINT64_C(0x41020000) &&
        !(old_cfg & UINT32_C(0x80000000)) &&
        (w->regfile[off / 4] & UINT32_C(0x80000000))) {
        qemu_log_mask(LOG_UNIMP,
                      "EXeSX M4 DMAMUX0 channel %u enabled"
                      " (source=%u): peripheral DMA requests"
                      " not implemented\n",
                      (unsigned)(off / 4),
                      w->regfile[off / 4] & 0x7f);
    }
    if (!g_strcmp0(g_getenv("EXESX_TRACE_M4_DMAMUX0"), "1") &&
        w->base == UINT64_C(0x41020000) &&
        old_cfg != w->regfile[off / 4]) {
        uint32_t cfg = w->regfile[off / 4];
        qemu_log("EXeSX DMAMUX0 M4 CHCFG%u old=0x%08x new=0x%08x source=%u A_ON=%u TRIG=%u ENBL=%u\n",
                 (unsigned)(off / 4), old_cfg, cfg, cfg & 0x7f,
                 !!(cfg & (1U << 29)), !!(cfg & (1U << 30)),
                 !!(cfg & (1U << 31)));
    }
    return MEMTX_OK;
}
