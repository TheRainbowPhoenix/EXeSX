/* EXeSX proof-of-execution ARMv7-A research board. GPL-2.0-or-later.
 * No proprietary firmware. Incomplete hardware: no guest LCD/touch/IPC.
 */
#include "qemu/osdep.h"
#include "qapi/error.h"
#include "hw/boards.h"
#include "hw/arm/armv7m.h"
#include "hw/arm/boot.h"
#include "hw/qdev-clock.h"
#include "hw/clock.h"
#include "hw/qdev-properties.h"
#include "system/memory.h"
#include "system/address-spaces.h"
#include "qemu/error-report.h"
#include "target/arm/cpu.h"
#include "qemu/units.h"
#include "qemu/module.h"
#include "qemu/log.h"
#include <inttypes.h>

#define TYPE_EXESX_MACHINE MACHINE_TYPE_NAME("exesx")
OBJECT_DECLARE_SIMPLE_TYPE(EXeSXState, EXESX_MACHINE)
typedef struct EXeSXState {
    MachineState parent_obj;
    ARMv7MState m4;
    Clock *m4cpuclk, *m4refclk;
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
typedef struct EXeSXProfileWindow {
    MemoryRegion mr;
    char *name;
    uint64_t base;
    uint64_t size;
    GHashTable *registers;
} EXeSXProfileWindow;

static MemTxResult exesx_reg_read(void *opaque, hwaddr offset, uint64_t *data,
                                  unsigned size, MemTxAttrs attrs)
{
    EXeSXProfileWindow *w = opaque;
    uint32_t *v = NULL;
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
    .valid.min_access_size = 4,
    .valid.max_access_size = 4,
    .impl.min_access_size = 4,
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

static void exesx_load_profile(MemoryRegion *sysmem)
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
    if (ngroups > 32) {
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
        if (!w->size || w->size > 256 * MiB ||
            w->base + w->size > UINT64_C(0x100000000) ||
            (w->base & 3) || (w->size & 3)) {
            error_report("EXeSX profile %s has invalid window", group);
            exit(1);
        }
        if (g_strcmp0(kind, "ram") == 0) {
            memory_region_init_ram(&w->mr, NULL, w->name, w->size,
                                   &error_fatal);
        } else if (g_strcmp0(kind, "registers") == 0) {
            if (w->size > 0x10000) {
                error_report("EXeSX register window %s too large", group);
                exit(1);
            }
            w->registers = g_hash_table_new_full(g_direct_hash, g_direct_equal,
                                                  NULL, g_free);
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
                    p = g_new(uint32_t, 1);
                    *p = (uint32_t)value;
                    g_hash_table_insert(w->registers,
                        GUINT_TO_POINTER((unsigned)off + 1), p);
                }
            }
            memory_region_init_io(&w->mr, NULL, &exesx_reg_ops, w,
                                  w->name, w->size);
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
    qdev_realize(DEVICE(a7), NULL, &error_fatal);
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
    exesx_load_profile(mem);

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
    object_property_set_bool(OBJECT(&s->m4), "start-powered-off", true,
                             &error_fatal);
    object_property_set_link(OBJECT(&s->m4), "memory", OBJECT(mem),
                             &error_abort);
    qdev_connect_clock_in(m4dev, "cpuclk", s->m4cpuclk);
    qdev_connect_clock_in(m4dev, "refclk", s->m4refclk);
    sysbus_realize(SYS_BUS_DEVICE(&s->m4), &error_fatal);
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
