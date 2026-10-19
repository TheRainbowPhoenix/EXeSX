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
#include "target/arm/cpu.h"
#include "qemu/units.h"
#include "qemu/module.h"

#define TYPE_EXESX_MACHINE MACHINE_TYPE_NAME("exesx")
OBJECT_DECLARE_SIMPLE_TYPE(EXeSXState, EXESX_MACHINE)
typedef struct EXeSXState {
    MachineState parent_obj;
    ARMv7MState m4;
    Clock *m4cpuclk, *m4refclk;
    MemoryRegion firmware, vectors, sram, ipc;
} EXeSXState;

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
    memory_region_init_ram(&s->firmware, OBJECT(ms), "exesx.rom-loading",
                           16 * MiB, &error_fatal);
    memory_region_add_subregion(mem, 0x60000000, &s->firmware);
    /* Provisional low-vector alias, NOT confirmed hardware behavior. */
    memory_region_init_alias(&s->vectors, OBJECT(ms), "exesx.vectors",
                             &s->firmware, 0, 1 * MiB);
    memory_region_add_subregion(mem, 0x0, &s->vectors);
    memory_region_init_ram(&s->sram, OBJECT(ms), "exesx.sram",
                           256 * KiB, &error_fatal);
    memory_region_add_subregion(mem, 0x1ffd0000, &s->sram);
    memory_region_init_ram(&s->ipc, OBJECT(ms), "exesx.ipc",
                           8 * MiB, &error_fatal);
    memory_region_add_subregion(mem, 0x2f000000, &s->ipc);
    memory_region_add_subregion(mem, 0x62000000, ms->ram);

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
    mc->max_cpus = 1;
    mc->default_cpus = 1;
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
