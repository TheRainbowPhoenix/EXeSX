/*
 * i.MX7ULP SNVS high-power EARLY BOOT subset, GPL-2.0-or-later.
 *
 * Source: NXP MCIMX7U5_cm4_COMMON.h (SNVS0_BASE = 0x41070000)
 *         NXP PERI_SNVS.h (HPCOMR +4, HPCR +8).
 *
 * This is not a security state machine or a wall-clock RTC. Never infer
 * trusted state from an accepted command. All security-violation commands
 * are rejected by default, unless explicitly in research diagnostic mode.
 * Readback of pulse/command bits is zero; undocumented registers fault.
 */
#define EXESX_SNVS_HPCOMR 0x04
#define EXESX_SNVS_HPCR   0x08
#define EXESX_SNVS_HPRTCMR 0x24
#define EXESX_SNVS_HPRTCLR 0x28
/* Internal, snapshot-backed RTC epoch and frozen tick accumulator.
 * These are not guest-visible SNVS register offsets. */
#define EXESX_SNVS_EPOCH_LO (0xb00 / 4)
#define EXESX_SNVS_EPOCH_HI (0xb04 / 4)
#define EXESX_SNVS_TICKS_LO (0xb08 / 4)
#define EXESX_SNVS_TICKS_HI (0xb0c / 4)
#define EXESX_SNVS_LP_SWR UINT32_C(0x00000010)
#define EXESX_SNVS_SW_SV UINT32_C(0x00000100)
#define EXESX_SNVS_SW_LPSV UINT32_C(0x00000400)
#define EXESX_SNVS_COMMANDS (EXESX_SNVS_LP_SWR | EXESX_SNVS_SW_SV | EXESX_SNVS_SW_LPSV)
/* Writable persistent command-register controls defined in PERI_SNVS.h. */
#define EXESX_SNVS_PERSISTENT UINT32_C(0x80012026)

static bool exesx_snvs_diagnostic_security(void)
{
    return g_strcmp0(g_getenv("EXESX_SNVS_DIAGNOSTIC_SECURITY_PULSES"), "1") == 0;
}

/* NXP SNVS HP counter uses 32768 counts per second (15 fraction bits).
 * VMState-backed epoch/base keep snapshots and RTC enable/disable coherent.
 * It starts at zero and does not claim real time/date or secure RTC sync.
 */
static uint64_t exesx_snvs_hp_ticks(EXeSXProfileWindow *w)
{
    uint64_t ticks = ((uint64_t)w->regfile[EXESX_SNVS_TICKS_HI] << 32) |
                       w->regfile[EXESX_SNVS_TICKS_LO];
    if (w->regfile[EXESX_SNVS_HPCR / 4] & UINT32_C(1)) {
        uint64_t epoch = ((uint64_t)w->regfile[EXESX_SNVS_EPOCH_HI] << 32) |
                           w->regfile[EXESX_SNVS_EPOCH_LO];
        uint64_t now = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
        if (now >= epoch) {
            ticks += muldiv64(now - epoch, 32768, NANOSECONDS_PER_SECOND);
        }
    }
    return ticks;
}

static MemTxResult exesx_snvs_hp_read(EXeSXProfileWindow *w, hwaddr off,
                                      uint64_t *value, unsigned size)
{
    if (size != 4 || (off & 3) || w->base != UINT64_C(0x41070000)) {
        return MEMTX_ERROR;
    }
    switch (off) {
    case EXESX_SNVS_HPCOMR:
    case EXESX_SNVS_HPCR:
        *value = w->regfile[off / 4];
        return MEMTX_OK;
    case EXESX_SNVS_HPRTCMR:
        *value = exesx_snvs_hp_ticks(w) >> 32;
        return MEMTX_OK;
    case EXESX_SNVS_HPRTCLR:
        *value = (uint32_t)exesx_snvs_hp_ticks(w);
        return MEMTX_OK;
    default:
        /* Unknown security, alarm, power, or RTC registers stay unmapped. */
        return MEMTX_ERROR;
    }
}

static MemTxResult exesx_snvs_hp_write(EXeSXProfileWindow *w, hwaddr off,
                                       uint64_t value, unsigned size)
{
    uint32_t bits = value;
    uint32_t secure = bits & (EXESX_SNVS_SW_SV | EXESX_SNVS_SW_LPSV);
    if (size != 4 || (off & 3) || w->base != UINT64_C(0x41070000)) {
        return MEMTX_ERROR;
    }
    switch (off) {
    case EXESX_SNVS_HPCOMR:
        /*
         * Reject undocumented or currently unmodeled controls.
         * LP_SWR is a WRITE-ONLY reset command (NXP). It does not stick
         * in HPCOMR and it must not spin forever in the M4's poll loop.
         * We have no modeled LP state to actually reset.
         */
        if (bits & ~(EXESX_SNVS_PERSISTENT | EXESX_SNVS_COMMANDS)) {
            qemu_log_mask(LOG_GUEST_ERROR,
                          "EXeSX SNVS unsupported HPCOMR 0x%08x\n", bits);
            return MEMTX_ERROR;
        }
        /*
         * SW_SV/SW_LPSV are documented HPCOMR write-only command strobes.
         * The unmodified M4 ROM invokes them in its B000 boot service.
         * A legal command write must not create a Cortex-M precise
         * BusFault; that previously trapped the M4 in HardFault and
         * prevented all later A7<->M4 control IPC. We acknowledge the
         * register transaction and keep the command bits self-clearing.
         * No security-state transition, alarm, or trusted status is
         * invented. Diagnostic mode controls verbose trace ONLY.
         */
        if (secure && !exesx_snvs_diagnostic_security()) {
            qemu_log_mask(LOG_UNIMP,
                          "EXeSX SNVS security command 0x%08x accepted "
                          "without modeled security-state transition\n",
                          secure);
        }
        /* LP reset is disabled by persistent HPCOMR.LP_SWR_DIS bit5.
         * Even in that case the command is never stored/readable.
         */
        if ((bits & EXESX_SNVS_LP_SWR) &&
            !(w->regfile[EXESX_SNVS_HPCOMR / 4] & UINT32_C(0x20))) {
            qemu_log_mask(LOG_GUEST_ERROR,
                          "EXeSX SNVS LP_SWR requested; no LP state yet\n");
        }
        if (secure) {
            qemu_log_mask(LOG_GUEST_ERROR,
                          "EXeSX SNVS DIAGNOSTIC security command pulse "
                          "0x%08x ignored, status NOT authenticated\n", secure);
        }
        /* Pulse bits clear; other documented writable bits retain state. */
        w->regfile[EXESX_SNVS_HPCOMR / 4] = bits & EXESX_SNVS_PERSISTENT;
        return MEMTX_OK;
    case EXESX_SNVS_HPCR:
        /* Only HP RTC_EN bit0. No calendar/alarms/secure RTC sync.
         * Preserve counter across disable/re-enable; enable time is
         * stored in VMState-backed private slots for snapshot replay.
         */
        if (bits & ~UINT32_C(1)) {
            return MEMTX_ERROR;
        }
        if ((w->regfile[EXESX_SNVS_HPCR / 4] & 1) && !(bits & 1)) {
            uint64_t ticks = exesx_snvs_hp_ticks(w);
            w->regfile[EXESX_SNVS_TICKS_LO] = (uint32_t)ticks;
            w->regfile[EXESX_SNVS_TICKS_HI] = ticks >> 32;
        } else if (!(w->regfile[EXESX_SNVS_HPCR / 4] & 1) && (bits & 1)) {
            uint64_t now = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
            w->regfile[EXESX_SNVS_EPOCH_LO] = (uint32_t)now;
            w->regfile[EXESX_SNVS_EPOCH_HI] = now >> 32;
        }
        w->regfile[EXESX_SNVS_HPCR / 4] = bits;
        return MEMTX_OK;
    default:
        return MEMTX_ERROR;
    }
}
