/*
 * i.MX7ULP SNVS high-power EARLY BOOT subset, GPL-2.0-or-later.
 *
 * Source: NXP MCIMX7U5_cm4_COMMON.h (SNVS0_BASE = 0x41070000)
 *         NXP PERI_SNVS.h (HPCOMR +4, HPCR +8).
 *
 * This is not a security state machine or a working RTC. Never infer
 * trusted state from an accepted command. All security-violation commands
 * are rejected by default, unless explicitly in research diagnostic mode.
 * Readback of pulse/command bits is zero; undocumented registers fault.
 */
#define EXESX_SNVS_HPCOMR 0x04
#define EXESX_SNVS_HPCR   0x08
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
        if (secure && !exesx_snvs_diagnostic_security()) {
            qemu_log_mask(LOG_GUEST_ERROR,
                          "EXeSX SNVS security command 0x%08x requires "
                          "explicit diagnostic mode; no secure-state engine\n",
                          secure);
            return MEMTX_ERROR;
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
        /* Only HP RTC_EN bit0 is verified by this firmware.
         * No fabricated RTC ticks, counter, alarm or security flags.
         */
        if (bits & ~UINT32_C(1)) {
            return MEMTX_ERROR;
        }
        w->regfile[EXESX_SNVS_HPCR / 4] = bits;
        return MEMTX_OK;
    default:
        return MEMTX_ERROR;
    }
}
