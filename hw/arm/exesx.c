/* EXeSX proof-of-execution ARMv7-A research board. GPL-2.0-or-later.
 * No proprietary firmware. Incomplete hardware: no guest LCD/touch/IPC.
 */
#include "qemu/osdep.h"
#include "qapi/error.h"
#include "hw/boards.h"
#include "hw/arm/armv7m.h"
#include "hw/arm/boot.h"
#include "hw/intc/arm_gic.h"
#include "hw/sysbus.h"
#include "hw/irq.h"
#include "hw/qdev-clock.h"
#include "hw/clock.h"
#include "hw/qdev-properties.h"
#include "hw/sd/sdhci.h"
#include "hw/sd/sd.h"
#include "system/block-backend.h"
#include "system/memory.h"
#include "system/address-spaces.h"
#include "qemu/error-report.h"
#include "target/arm/cpu.h"
#include "qemu/units.h"
#include "qemu/module.h"
#include "qemu/log.h"
#include "qemu/timer.h"
#include "migration/vmstate.h"
#include <inttypes.h>

#define TYPE_EXESX_MACHINE MACHINE_TYPE_NAME("exesx")
OBJECT_DECLARE_SIMPLE_TYPE(EXeSXState, EXESX_MACHINE)
typedef struct EXeSXProfileWindow EXeSXProfileWindow;
typedef struct EXeSXState {
    MachineState parent_obj;
    ARMv7MState m4;
    Clock *m4cpuclk, *m4refclk;
    ARMCPU *a7cpu;
    EXeSXProfileWindow *mu_a, *mu_b, *lcd, *dmamux1, *m4_gpio_a, *m4_gpio_b;
    EXeSXProfileWindow *m4_port_a, *m4_port_b;
    uint16_t m4_keyboard_code;
    int m4_keyboard_row;
    int64_t m4_keyboard_next_poll_ns;
    uint64_t cp15_dacr_s_saved;
    uint64_t cp15_ttbr1_s_saved;
    bool m4_released;
    /* MU_A input is M4 NVIC IRQ22; MU_B is GIC SPI19 on A7. */
    qemu_irq mu_a_irq, mu_b_irq, lpit1_irq, lptmr0_irq, lptmr1_irq, tpm0_irq, m4_porta_irq, m4_portb_irq;
    MemoryRegion firmware, vectors, sram, ipc, provisional_writable;
} EXeSXState;


/*
 * Runtime memory-profile support. Deliberately data-driven so an experiment
 * can remap suspected RAM or provision diagnostic MMIO registers without
 * rebuilding QEMU. A read from an unconfigured register causes an abort,
 * rather than inventing a successful hardware handshake.
 *
 * EXESX_MEMORY_PROFILE=/absolute/path/profile.ini
 *
 * [extra-ram]
 * kind=ram
 * base=0x67100000
 * size=0x00500000
 *
 * [peripheral-probe]
 * kind=registers
 * base=0x410a3000
 * size=0x1000
 * reg.0x54=0x00000000
 */
struct EXeSXProfileWindow {
    MemoryRegion mr;
    char *name;
    uint64_t base;
    uint64_t size;
    GHashTable *registers;
    char *kind;
    EXeSXState *board;
    QEMUTimer *lpit_timer, *lptmr_timer, *tpm0_timer, *lcd_screenshot_timer, *m4_port_poll_timer;
    uint32_t m4_port_previous;
    bool m4_port_sampled;
    uint16_t *lcd_fb;
    unsigned lcd_x0, lcd_x1, lcd_y0, lcd_y1, lcd_x, lcd_y;
    unsigned lcd_param_count;
    uint16_t lcd_params[4];
    uint8_t lcd_cmd, lcd_madctl;
    bool lcd_dc, lcd_te_enabled, lcd_rgb565;
    uint64_t lcd_pixel_writes;
    /* Stable addresses; preserved by VMState on loadvm. */
    uint32_t regfile[0x10000 / sizeof(uint32_t)];
};

/*
 * i.MX7ULP Single Boot, NXP description:
 * CM4 ROM waits on SIM0_DGO_GP7; CA7 copies the CM4 image to SRAM,
 * writes the CM4 entrypoint to SIM0_DGO_GP7, then ROM transfers control.
 *
 * We do NOT ship the SoC ROM, so this opt-in release starts the real
 * firmware's M4 reset vector at the firmware-provided SRAM vector table.
 * This is the ROM boot handoff, NOT an invented mailbox response.
 * Must be gated behind EXESX_EXPERIMENTAL_M4_BOOT=1 while the rest of
 * hardware (M4 peripherals, IPC, external flash) is incomplete.
 */
static void exesx_m4_rom_handoff(EXeSXState *s, uint32_t entry)
{
    ARMCPU *m4 = s->m4.cpu;
    CPUState *cs;
    uint32_t vector_entry, vector_sp;

    if (g_strcmp0(g_getenv("EXESX_EXPERIMENTAL_M4_BOOT"), "1") ||
        !m4 || s->m4_released) {
        return;
    }

    vector_sp = ldl_phys(&address_space_memory, 0x1ffd0000);
    vector_entry = ldl_phys(&address_space_memory, 0x1ffd0004);
    if ((entry & 1) == 0 || entry != vector_entry ||
        vector_sp < 0x1ffd0000 || vector_sp >= 0x20010000) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "EXeSX M4 handoff deferred: GP7=0x%08x,"
                      " vector SP=0x%08x PC=0x%08x\\n",
                      entry, vector_sp, vector_entry);
        return;
    }

    cs = CPU(m4);
    cs->start_powered_off = false;
    cpu_reset(cs);
    cs->halted = 0;
    s->m4_released = true;
    qemu_cpu_kick(cs);
    error_report("EXeSX EXPERIMENTAL M4 ROM handoff: MSP=0x%08x PC=0x%08x",
                 vector_sp, vector_entry);
}

#include "exesx-lcd.inc"
#include "exesx-imx7ulp-keyboard.inc"
#include "exesx-imx7ulp.inc"

static int exesx_registers_post_load(void *opaque, int version_id)
{
    EXeSXProfileWindow *w = opaque;
    if (w->lptmr_timer) {
        /* Device flags/epoch are saved in regfile; rearm this
         * host QEMU timer after loading a private VM checkpoint. */
        exesx_lptmr_schedule(w);
    }
    if (w->tpm0_timer) {
        /* TPM0 phase/overflow flag live in saved regfile. Recompute the
         * upcoming original M4 IRQ38 delivery after loadvm. */
        exesx_tpm0_schedule(w);
    }
    if (w->m4_port_poll_timer) {
        /* The saved PORT regfile is authoritative, external host inputs are
         * reread. Avoid manufacturing an edge across process restarts. */
        w->m4_port_sampled = false;
        timer_mod(w->m4_port_poll_timer,
                  qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) + 20000000);
    }
    return 0;
}
static const VMStateDescription exesx_registers_vmstate = {
    .name = "exesx-experimental-registers",
    .post_load = exesx_registers_post_load,
    .version_id = 1,
    .minimum_version_id = 1,
    .fields = (const VMStateField[]) {
        VMSTATE_UINT32_ARRAY(regfile, EXeSXProfileWindow, 0x10000 / 4),
        VMSTATE_END_OF_LIST()
    },
};

/*
 * Cortex-A7 in our experimental machine executes secure AArch32 CP15
 * startup code. QEMU 10.1's generic CPU loadvm currently fails to
 * preserve secure-side DACR and TTBR1 in this configuration.
 * Register an EXeSX-only supplementary VMState; no guest behavior is faked.
 */
static int exesx_cp15_pre_save(void *opaque)
{
    EXeSXState *s = opaque;
    s->cp15_dacr_s_saved = s->a7cpu->env.cp15.dacr_s;
    s->cp15_ttbr1_s_saved = s->a7cpu->env.cp15.ttbr1_s;
    return 0;
}

static int exesx_cp15_post_load(void *opaque, int version_id)
{
    EXeSXState *s = opaque;
    s->a7cpu->env.cp15.dacr_s = s->cp15_dacr_s_saved;
    s->a7cpu->env.cp15.ttbr1_s = s->cp15_ttbr1_s_saved;
    return 0;
}

static const VMStateDescription exesx_cp15_vmstate = {
    .name = "exesx-extra-secure-cp15",
    .version_id = 1,
    .minimum_version_id = 1,
    .pre_save = exesx_cp15_pre_save,
    .post_load = exesx_cp15_post_load,
    .fields = (const VMStateField[]) {
        VMSTATE_UINT64(cp15_dacr_s_saved, EXeSXState),
        VMSTATE_UINT64(cp15_ttbr1_s_saved, EXeSXState),
        VMSTATE_BOOL(m4_released, EXeSXState),
        VMSTATE_END_OF_LIST()
    },
};

static MemTxResult exesx_reg_read(void *opaque, hwaddr offset, uint64_t *data,
                                  unsigned size, MemTxAttrs attrs)
{
    EXeSXProfileWindow *w = opaque;
    uint32_t *v = NULL;
    if (!strcmp(w->kind, "exesx-lcd")) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "EXeSX LCD unmodeled READ addr=0x%" HWADDR_PRIx
                      " width=%u command=0x%02x DC=%u param_count=%u "
                      "pixel_writes=%" PRIu64 " -- abort (no guessed response)\\n",
                      w->base + offset, size, w->lcd_cmd, w->lcd_dc,
                      w->lcd_param_count, w->lcd_pixel_writes);
        *data = 0;
        return MEMTX_ERROR;
    }
    if (exesx_imx7ulp_kind(w->kind)) {
        return exesx_imx7ulp_read(w, offset, data, size);
    }
    if (size == 4 && !(offset & 3) && offset <= UINT32_MAX - 1) {
        v = g_hash_table_lookup(w->registers,
                                GUINT_TO_POINTER((unsigned)offset + 1));
    }
    if (!v) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "EXeSX unconfigured MMIO READ @0x%" HWADDR_PRIx
                      " size=%u (%s): ABORT\\n", w->base + offset, size,
                      w->name);
        return MEMTX_ERROR;
    }
    *data = *v;
    qemu_log_mask(LOG_GUEST_ERROR,
                  "EXeSX diagnostic MMIO READ @0x%" HWADDR_PRIx
                  " =0x%08x (%s)\\n", w->base + offset, *v, w->name);
    return MEMTX_OK;
}

static MemTxResult exesx_reg_write(void *opaque, hwaddr offset, uint64_t data,
                                   unsigned size, MemTxAttrs attrs)
{
    EXeSXProfileWindow *w = opaque;
    uint32_t *v = NULL;
    if (!strcmp(w->kind, "exesx-lcd")) {
        return exesx_lcd_write(w, offset, data, size);
    }
    if (exesx_imx7ulp_kind(w->kind)) {
        return exesx_imx7ulp_write(w, offset, data, size);
    }
    if (size == 4 && !(offset & 3) && offset <= UINT32_MAX - 1) {
        v = g_hash_table_lookup(w->registers,
                                GUINT_TO_POINTER((unsigned)offset + 1));
    }
    if (!v) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "EXeSX unconfigured MMIO WRITE @0x%" HWADDR_PRIx
                      " data=0x%" PRIx64 " size=%u (%s): ABORT\\n",
                      w->base + offset, data, size, w->name);
        return MEMTX_ERROR;
    }
    *v = (uint32_t)data;
    qemu_log_mask(LOG_GUEST_ERROR,
                  "EXeSX diagnostic MMIO WRITE @0x%" HWADDR_PRIx
                  " =0x%08x (%s)\\n", w->base + offset, *v, w->name);
    return MEMTX_OK;
}

static const MemoryRegionOps exesx_reg_ops = {
    .read_with_attrs = exesx_reg_read,
    .write_with_attrs = exesx_reg_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid.min_access_size = 1,
    .valid.max_access_size = 4,
    .impl.min_access_size = 1,
    .impl.max_access_size = 4,
};

static uint64_t exesx_config_number(GKeyFile *cfg, const char *group,
                                     const char *key)
{
    g_autofree char *s = g_key_file_get_string(cfg, group, key, NULL);
    char *end;
    uint64_t v;
    if (!s || !*s || *s == '-') {
        error_report("EXeSX profile %s.%s: missing/invalid number",
                     group, key);
        exit(1);
    }
    v = g_ascii_strtoull(s, &end, 0);
    if (*end) {
        error_report("EXeSX profile %s.%s: trailing number characters",
                     group, key);
        exit(1);
    }
    return v;
}

static void exesx_load_profile(MemoryRegion *sysmem, EXeSXState *board)
{
    const char *filename = g_getenv("EXESX_MEMORY_PROFILE");
    g_autoptr(GKeyFile) cfg = g_key_file_new();
    g_autoptr(GError) error = NULL;
    gsize ngroups;
    g_auto(GStrv) groups = NULL;
    unsigned int k;

    if (!filename || !*filename) {
        return;
    }
    if (!g_key_file_load_from_file(cfg, filename, G_KEY_FILE_NONE, &error)) {
        error_report("EXeSX profile '%s': %s", filename, error->message);
        exit(1);
    }
    groups = g_key_file_get_groups(cfg, &ngroups);
    if (ngroups > 64) {
        error_report("EXeSX: too many profile windows");
        exit(1);
    }
    for (k = 0; k < ngroups; k++) {
        const char *group = groups[k];
        g_autofree char *kind = g_key_file_get_string(cfg, group, "kind", NULL);
        EXeSXProfileWindow *w = g_new0(EXeSXProfileWindow, 1);
        gsize nkeys;
        g_auto(GStrv) keys = NULL;
        gsize i;

        w->base = exesx_config_number(cfg, group, "base");
        w->size = exesx_config_number(cfg, group, "size");
        w->name = g_strdup_printf("exesx.profile.%s", group);
        w->kind = g_strdup(kind);
        w->board = board;
        if (!w->size || w->size > 256 * MiB ||
            w->base + w->size > UINT64_C(0x100000000) ||
            (w->base & 3) || (w->size & 3)) {
            error_report("EXeSX profile %s has invalid window", group);
            exit(1);
        }
        if (g_strcmp0(kind, "exesx-lcd") == 0) {
            if (w->base != 0xb0000000 || w->size != 0x1000 ||
                board->lcd || g_strcmp0(g_getenv("EXESX_EXPERIMENTAL_LCD"), "1")) {
                error_report("EXeSX LCD invalid profile/opt-in");
                exit(1);
            }
            board->lcd = w;
            w->lcd_fb = g_new0(uint16_t, EXESX_LCD_W * EXESX_LCD_H);
            w->lcd_x1 = EXESX_LCD_W - 1;
            w->lcd_y1 = EXESX_LCD_H - 1;
            w->lcd_rgb565 = true;
            if (g_getenv("EXESX_LCD_SCREENSHOT")) {
                w->lcd_screenshot_timer = timer_new_ns(
                    QEMU_CLOCK_VIRTUAL, exesx_lcd_snapshot_tick, w);
                timer_mod(w->lcd_screenshot_timer,
                          qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) + 500000000);
            }
            memory_region_init_io(&w->mr, NULL, &exesx_reg_ops, w,
                                  w->name, w->size);
        } else if (g_strcmp0(kind, "ram") == 0) {
            memory_region_init_ram(&w->mr, NULL, w->name, w->size,
                                   &error_fatal);
        } else if (exesx_imx7ulp_kind(kind)) {
            if (w->size > 0x10000 ||
                (!strcmp(kind, "imx7ulp-tstmr") && w->size != 8)) {
                error_report("EXeSX i.MX7ULP model window %s invalid size", group);
                exit(1);
            }
            if (g_strcmp0(kind, "imx7ulp-dmamux") == 0 && w->base == 0x40210000) {
                board->dmamux1 = w;
            }
            if (!strcmp(kind, "imx7ulp-port") &&
                (w->base == 0x4103f000 || w->base == 0x41040000)) {
                if (w->base == 0x4103f000) {
                    board->m4_port_a = w;
                } else {
                    board->m4_port_b = w;
                }
                if (!g_strcmp0(g_getenv("EXESX_EXPERIMENTAL_M4_PORT_IRQ"), "1")) {
                    w->m4_port_poll_timer = timer_new_ns(
                        QEMU_CLOCK_VIRTUAL, exesx_m4_port_tick, w);
                    timer_mod(w->m4_port_poll_timer,
                              qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) + 20000000);
                }
            }
            if (!strcmp(kind, "imx7ulp-gpio")) {
                if (w->base == 0x4100f000) {
                    board->m4_gpio_a = w;
                } else if (w->base == 0x4100f040) {
                    board->m4_gpio_b = w;
                }
            }
            if (g_strcmp0(kind, "imx7ulp-mu") == 0) {
                if (w->base == 0x41022000) {
                    board->mu_a = w;
                } else if (w->base == 0x40220000) {
                    board->mu_b = w;
                } else {
                    error_report("EXeSX MU base unknown: 0x%" PRIx64, w->base);
                    exit(1);
                }
                w->regfile[0x200 / 4] = 15; /* all four TX empty */
            }
            if (g_strcmp0(kind, "imx7ulp-scg0") == 0) {
                /*
                 * This emulator enters at the A7 BIOS, bypassing M4 ROM.
                 * The real M4 expects FIRC CSR.VLD (bit24) already set
                 * before configuring its SCG0 divider registers.
                 * Provide enabled oscillator reset state, not an
                 * unconditional read override. Status tracks CSR.EN.
                 */
                w->regfile[0x14 / 4] = 0x03000000; /* RUN: FIRC */
                w->regfile[0x200 / 4] = 1; /* SIRCEN */
                w->regfile[0x300 / 4] = 1; /* FIRCEN */
            }
            if (g_strcmp0(kind, "imx7ulp-scg1") == 0) {
                /*
                 * This image starts at the BIOS entry, not the silicon ROM.
                 * Supply enabled oscillator defaults normally set by ROM.
                 */
                w->regfile[0x14 / 4] = 0x03000000; /* RCCR FIRC */
                w->regfile[0x100 / 4] = 1; /* SOSCEN */
                w->regfile[0x200 / 4] = 1; /* SIRCEN */
                w->regfile[0x300 / 4] = 1; /* FIRCEN */
            }
            if (w->base == 0x40270000 &&
                !g_strcmp0(g_getenv("EXESX_EXPERIMENTAL_LPIT1_IRQ"), "1")) {
                w->lpit_timer = timer_new_ns(QEMU_CLOCK_VIRTUAL,
                                             exesx_lpit_timer_tick, w);
            }
            if (g_strcmp0(kind, "imx7ulp-lptmr") == 0 &&
                (w->base == 0x4102e000 || w->base == 0x4102f000) &&
                !g_strcmp0(g_getenv("EXESX_EXPERIMENTAL_LPTMR_IRQ"), "1")) {
                w->lptmr_timer = timer_new_ns(QEMU_CLOCK_VIRTUAL,
                                                 exesx_lptmr_timer_tick, w);
            }
            if (!strcmp(kind, "imx7ulp-tpm") && w->base == 0x41030000 &&
                !g_strcmp0(g_getenv("EXESX_EXPERIMENTAL_M4_TPM0_IRQ"), "1")) {
                w->tpm0_timer = timer_new_ns(QEMU_CLOCK_VIRTUAL,
                                              exesx_tpm0_timer_tick, w);
            }
            memory_region_init_io(&w->mr, NULL, &exesx_reg_ops, w,
                                  w->name, w->size);
            if (vmstate_register(NULL, k, &exesx_registers_vmstate, w)) {
                error_report("EXeSX i.MX7ULP model migration registration failed");
                exit(1);
            }
        } else if (g_strcmp0(kind, "registers") == 0) {
            if (w->size > 0x10000) {
                error_report("EXeSX register window %s too large", group);
                exit(1);
            }
            w->registers = g_hash_table_new(g_direct_hash, g_direct_equal);
            keys = g_key_file_get_keys(cfg, group, &nkeys, NULL);
            for (i = 0; i < nkeys; i++) {
                if (g_str_has_prefix(keys[i], "reg.")) {
                    uint64_t off = g_ascii_strtoull(keys[i] + 4, NULL, 0);
                    uint64_t value = exesx_config_number(cfg, group, keys[i]);
                    uint32_t *p;
                    if (off >= w->size || (off & 3) || value > UINT32_MAX) {
                        error_report("EXeSX register offset invalid: %s", keys[i]);
                        exit(1);
                    }
                    p = &w->regfile[off / 4];
                    *p = (uint32_t)value;
                    g_hash_table_insert(w->registers,
                        GUINT_TO_POINTER((unsigned)off + 1), p);
                }
            }
            memory_region_init_io(&w->mr, NULL, &exesx_reg_ops, w,
                                  w->name, w->size);
            if (vmstate_register(NULL, k, &exesx_registers_vmstate, w)) {
                error_report("EXeSX register window VMState registration failed");
                exit(1);
            }
        } else {
            error_report("EXeSX profile %s: unknown kind '%s'",
                         group, kind ? kind : "(null)");
            exit(1);
        }
        memory_region_add_subregion(sysmem, w->base, &w->mr);
        error_report("EXeSX diagnostic profile %s: %s @0x%" PRIx64
                     " +0x%" PRIx64 " (not hardware-validated)",
                     group, kind, w->base, w->size);
    }
}

static void exesx_init(MachineState *ms)
{
    EXeSXState *s = EXESX_MACHINE(ms);
    MemoryRegion *mem = get_system_memory();
    Object *a7 = object_new(ARM_CPU_TYPE_NAME("cortex-a7"));
    DeviceState *m4dev;

    if (ms->ram_size != 64 * MiB) {
        error_report("exesx requires -m 64M");
        exit(1);
    }
    object_property_add_child(OBJECT(ms), "cortex-a7", a7);
    /*
     * Cortex-A7 CBAR/PERIPHBASE identifies the cluster private peripheral
     * region. The Casio BIOS reads CBAR using MRC p15,4,...,c15,c0,0
     * and derives GICD=CBAR+0x1000 and GICC=CBAR+0x2000.
     * i.MX7ULP Linux DTS gives 0x40021000/0x40022000, hence 0x40020000.
     * Leaving QEMU's reset-cbar at zero sends the BIOS to ROM VA 0x2000
     * after the MMU maps that VA to 0x60002000; a physical 0x2000
     * alias does not fix the virtual address.
     */
    object_property_set_int(a7, "reset-cbar", 0x40020000, &error_fatal);
    qdev_realize(DEVICE(a7), NULL, &error_fatal);
    s->a7cpu = ARM_CPU(a7);
    if (vmstate_register(NULL, 0, &exesx_cp15_vmstate, s)) {
        error_report("EXeSX secure-CP15 migration registration failed");
        exit(1);
    }
    /* Real ARMv7-A CP15, barriers, and MMU are provided by QEMU TCG. */
    memory_region_init_ram(&s->firmware, NULL, "exesx.rom-loading",
                           16 * MiB, &error_fatal);
    memory_region_add_subregion(mem, 0x60000000, &s->firmware);
    /*
     * User-firmware trace: first DFSR=0x808, DFAR=0x61080000, on the
     * zero-initializer's STR at 0x60254714. The physical memory kind
     * is NOT confirmed. Map 0x61000000..0x61ffffff to experimental
     * RAM so later firmware faults/peripheral dependencies can be traced.
     * This mapping is intentionally not presented as faithful silicon.
     */
    memory_region_init_ram(&s->provisional_writable, NULL,
                           "exesx.provisional-writable", 16 * MiB,
                           &error_fatal);
    memory_region_add_subregion(mem, 0x61000000, &s->provisional_writable);
    /* Provisional low-vector alias, NOT confirmed hardware behavior. */
    memory_region_init_alias(&s->vectors, NULL, "exesx.vectors",
                             &s->firmware, 0, 1 * MiB);
    memory_region_add_subregion(mem, 0x0, &s->vectors);
    memory_region_init_ram(&s->sram, NULL, "exesx.sram",
                           256 * KiB, &error_fatal);
    memory_region_add_subregion(mem, 0x1ffd0000, &s->sram);
    memory_region_init_ram(&s->ipc, NULL, "exesx.ipc",
                           8 * MiB, &error_fatal);
    memory_region_add_subregion(mem, 0x2f000000, &s->ipc);
    memory_region_add_subregion(mem, 0x62000000, ms->ram);
    exesx_load_profile(mem, s);

    /*
     * Real QEMU GICv2: A7 secure distributor/CPU interface plus IRQ/FIQ.
     * The CBAR-derived physical addresses are defined in imx7ulp.dtsi.
     */
    {
        DeviceState *gic = qdev_new(TYPE_ARM_GIC);
        SysBusDevice *gicsbd = SYS_BUS_DEVICE(gic);

        qdev_prop_set_uint32(gic, "num-cpu", 1);
        qdev_prop_set_uint32(gic, "num-irq", 160);
        qdev_prop_set_uint32(gic, "revision", 2);
        qdev_prop_set_bit(gic, "has-security-extensions", true);
        sysbus_realize_and_unref(gicsbd, &error_fatal);
        sysbus_mmio_map(gicsbd, 0, 0x40021000);
        sysbus_mmio_map(gicsbd, 1, 0x40022000);
        sysbus_connect_irq(gicsbd, 0,
                           qdev_get_gpio_in(DEVICE(a7), ARM_CPU_IRQ));
        sysbus_connect_irq(gicsbd, 1,
                           qdev_get_gpio_in(DEVICE(a7), ARM_CPU_FIQ));
        /* GIC qdev input indices are 0-based SPIs (GIC ID=32+index). */
        s->mu_b_irq = qdev_get_gpio_in(gic, 19);
        /* NXP i.MX7ULP A7 GIC SPI 25 = LPIT1. */
        s->lpit1_irq = qdev_get_gpio_in(gic, 25);

        /*
         * Explicitly opt-in real SD/eMMC device path. This is QEMU's
         * actual i.MX USDHC host + actual eMMC command/data state machine,
         * not an MMIO table that invents card replies. By default the
         * existing verified no-media model remains active underneath.
         *
         * Use -drive if=none,id=exesx-emmc,file=...,format=raw,snapshot=on
         * and EXESX_USDHC1_EMMC=1. The user-area image must match the
         * Samsung KLMAG1JETD-B041 reference geometry exactly. The QEMU
         * eMMC model has its own implementation-specific limitations:
         * do not assume its CID/EXT_CSD matches physical Samsung hardware.
         */
        if (!g_strcmp0(g_getenv("EXESX_USDHC1_EMMC"), "1")) {
            BlockBackend *blk = blk_by_name("exesx-emmc");
            int64_t bytes;
            DeviceState *host;
            DeviceState *card;
            SysBusDevice *host_sbd;

            if (!blk) {
                error_report("EXeSX eMMC: EXESX_USDHC1_EMMC=1 requires "
                             "-drive if=none,id=exesx-emmc,file=IMAGE,"
                             "format=raw,snapshot=on");
                exit(1);
            }
            bytes = blk_getlength(blk);
            /* QEMU TYPE_EMMC carves boot0 and boot1 from the FIRST
             * 8 MiB of the backing file. Its ext_csd SEC_COUNT is the
             * remaining USER area only (Samsung reference: 0x01d1f000
             * 512-byte sectors). No authenticated RPMB is supported.
             */
            if (bytes != INT64_C(15642656768)) {
                error_report("EXeSX eMMC: Samsung candidate backing must "
                             "contain boot0 (4 MiB) + boot1 (4 MiB) + "
                             "user area (15634268160 bytes): expected "
                             "15642656768 total bytes, got %" PRId64,
                             bytes);
                exit(1);
            }
            host = qdev_new(TYPE_IMX_USDHC);
            object_property_add_child(OBJECT(ms), "usdhc1-card-host",
                                      OBJECT(host));
            qdev_prop_set_uint8(host, "sd-spec-version", 3);
            /* i.MX7ULP USDHC input comes from SCG1/PCC2, not from the
             * reserved SYS_CTRL low nibble. This opt-in assumption models
             * a supplied root clock; 0 explicitly tests the gated case.
             * PCC2/SCG1 gate-to-clock wiring remains a future task.
             */
            qdev_prop_set_bit(host, "imx7ulp-input-clock",
                              g_strcmp0(g_getenv("EXESX_USDHC1_INPUT_CLOCK"),
                                        "0") != 0);
            /* 3.0V+1.8V, 4/8-bit capable, 512/2048-byte blocks, DMA.
             * This is a guest test-controller capability mask, NOT a
             * measured DY357 i.MX7ULP hardware register reset value.
             */
            qdev_prop_set_uint64(host, "capareg", UINT64_C(0x05e80080));
            host_sbd = SYS_BUS_DEVICE(host);
            sysbus_realize(host_sbd, &error_fatal);
            /* The existing exesx-profile window is lower priority, so
             * default no-media mode is byte-for-byte unchanged.
             * Only this opt-in process sees real QEMU USDHC MMIO.
             */
            memory_region_add_subregion_overlap(
                mem, UINT64_C(0x40380000),
                sysbus_mmio_get_region(host_sbd, 0), 1);
            /* Linux imx7ulp.dtsi: USDHC1 is A7 GIC_SPI 43. */
            sysbus_connect_irq(host_sbd, 0, qdev_get_gpio_in(gic, 43));

            card = qdev_new(TYPE_EMMC);
            qdev_prop_set_uint64(card, "boot-partition-size", 4 * MiB);
            qdev_prop_set_drive_err(card, "drive", blk, &error_fatal);
            qdev_realize_and_unref(card, qdev_get_child_bus(host, "sd-bus"),
                                   &error_fatal);
            error_report("EXeSX experimental eMMC: QEMU i.MX USDHC1 host "
                         "+ QEMU eMMC card, Samsung-class 16GB image "
                         "(boot0/boot1/user; RPMB unsupported); "
                         "guest data is synthetic unless provided by user");
        }
    }

    /* Independent M-profile CPU and NVIC, powered off pending IPC model. */
    s->m4cpuclk = clock_new(OBJECT(ms), "m4cpuclk");
    s->m4refclk = clock_new(OBJECT(ms), "m4refclk");
    clock_set_hz(s->m4cpuclk, 48000000); /* provisional */
    clock_set_hz(s->m4refclk, 1000000); /* provisional */
    object_initialize_child(OBJECT(ms), "cortex-m4-nvic", &s->m4, TYPE_ARMV7M);
    m4dev = DEVICE(&s->m4);
    qdev_prop_set_string(m4dev, "cpu-type", ARM_CPU_TYPE_NAME("cortex-m4"));
    qdev_prop_set_uint32(m4dev, "num-irq", 128);
    qdev_prop_set_uint32(m4dev, "init-svtor", 0x1ffd0000);
    /* ARMv7-M without TrustZone resets through M_REG_NS vector base. */
    qdev_prop_set_uint32(m4dev, "init-nsvtor", 0x1ffd0000);
    object_property_set_bool(OBJECT(&s->m4), "start-powered-off", true,
                             &error_fatal);
    object_property_set_link(OBJECT(&s->m4), "memory", OBJECT(mem),
                             &error_abort);
    qdev_connect_clock_in(m4dev, "cpuclk", s->m4cpuclk);
    qdev_connect_clock_in(m4dev, "refclk", s->m4refclk);
    sysbus_realize(SYS_BUS_DEVICE(&s->m4), &error_fatal);
    /* MCIMX7U5_cm4_COMMON.h: MU_A_IRQn = 22 (external NVIC line). */
    s->mu_a_irq = qdev_get_gpio_in(DEVICE(&s->m4), 22);
    /* NXP i.MX7ULP NVIC: LPTMR0_IRQn=36, LPTMR1_IRQn=37. */
    s->lptmr0_irq = qdev_get_gpio_in(DEVICE(&s->m4), 36);
    s->lptmr1_irq = qdev_get_gpio_in(DEVICE(&s->m4), 37);
    /* Original M4 binary: vector 0x36 (54) -> external IRQ38 TPM0,
     * whose handler @0x1FFDB68C invokes keyboard debounce callback. */
    s->tpm0_irq = qdev_get_gpio_in(DEVICE(&s->m4), 38);
    /* Reference manual: vectors 72/73 = M4 external IRQ56/57, PORT A/B. */
    s->m4_porta_irq = qdev_get_gpio_in(DEVICE(&s->m4), 56);
    s->m4_portb_irq = qdev_get_gpio_in(DEVICE(&s->m4), 57);

    armv7m_load_kernel(s->m4.cpu, NULL, 0x1ffd0000, 0x40000);
}
static void exesx_class_init(ObjectClass *oc, const void *data)
{
    MachineClass *mc = MACHINE_CLASS(oc);
    mc->desc = "EXeSX Cortex-A7/M4 experimental (incomplete)";
    mc->init = exesx_init;
    /* One A7 plus one independent M4: TCG must allocate two contexts. */
    mc->min_cpus = 2;
    mc->max_cpus = 2;
    mc->default_cpus = 2;
    mc->default_ram_size = 64 * MiB;
    mc->default_ram_id = "exesx.ram";
    mc->no_floppy = true;
    mc->no_cdrom = true;
}
static const TypeInfo exesx_info = {
    .name = TYPE_EXESX_MACHINE,
    .parent = TYPE_MACHINE,
    .instance_size = sizeof(EXeSXState),
    .class_init = exesx_class_init,
};
static void exesx_register(void) { type_register_static(&exesx_info); }
type_init(exesx_register)
