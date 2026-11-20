/* EXeSX runtime address access trace. GPL-2.0-or-later.
 * Compile ONLY this .so for new instrumentation; no QEMU rebuild required.
 * Logs successful accesses. Faulting bus cycles are NOT reported by the plugin:
 * also enable QEMU -d guest_errors to see rejected reads/writes.
 */
#include <glib.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <qemu-plugin.h>

QEMU_PLUGIN_EXPORT int qemu_plugin_version = QEMU_PLUGIN_VERSION;

typedef struct { uint64_t start, end; } Range;
static Range ranges[32];
static int nranges;
static guint64 seen, recorded;
static guint64 emitted_per_range[33];
static guint64 max_events = 128;
static bool virtual_only;
static bool show_values;
static GMutex output_lock;

/* Opt-in control-only capture of CPU0 LCD writes, never framebuffer bytes. */
static bool dcs_control_only, dcs_pin_known, dcs_data;
static uint8_t dcs_command;
static unsigned dcs_param_idx;
static guint64 dcs_n53, dcs_p53, dcs_n51, dcs_p51, dcs_toggles;
static bool dcs_prev_dd_valid, dcs_prev_dd;

static void dcs_access(unsigned cpu, qemu_plugin_meminfo_t info,
                       uint64_t addr, uint64_t pc)
{
    if (cpu != 0 || !qemu_plugin_mem_is_store(info) ||
        (addr != 0xb0000000 && addr != 0x400f0004 && addr != 0x400f0008)) {
        return;
    }
    qemu_plugin_mem_value m = qemu_plugin_mem_get_value(info);
    uint64_t v = m.type == QEMU_PLUGIN_MEM_VALUE_U8 ? m.data.u8 :
                 m.type == QEMU_PLUGIN_MEM_VALUE_U16 ? m.data.u16 :
                 m.type == QEMU_PLUGIN_MEM_VALUE_U32 ? m.data.u32 : m.data.u64;
    g_mutex_lock(&output_lock);
    if (addr == 0x400f0004 || addr == 0x400f0008) {
        if (v & 0x10000) {
            dcs_pin_known = true;
            dcs_data = addr == 0x400f0004;
        }
    } else if (dcs_pin_known && !dcs_data) {
        dcs_command = v & 255;
        dcs_param_idx = 0;
        if (dcs_command == 0x53 || dcs_command == 0x51) {
            if (dcs_command == 0x53) dcs_n53++; else dcs_n51++;
            g_autofree char *s = g_strdup_printf(
                "EXESX_DCS_CTRL command=0x%02x pc=0x%08" PRIx64 "\n",
                dcs_command, pc);
            qemu_plugin_outs(s);
        }
    } else if (dcs_pin_known && dcs_data && dcs_param_idx++ == 0) {
        if (dcs_command == 0x53) {
            bool dd = !!(v & 0x08);
            if (dcs_prev_dd_valid && dcs_prev_dd != dd) dcs_toggles++;
            dcs_prev_dd_valid = true;
            dcs_prev_dd = dd;
            dcs_p53++;
            g_autofree char *s = g_strdup_printf(
                "EXESX_DCS_CTRL parameter53_pc=0x%08" PRIx64
                " bctrl=%u dd=%u bl=%u\n", pc,
                (unsigned)!!(v & 0x20), (unsigned)dd,
                (unsigned)!!(v & 0x04));
            qemu_plugin_outs(s);
        } else if (dcs_command == 0x51) {
            dcs_p51++;
            g_autofree char *s = g_strdup_printf(
                "EXESX_DCS_CTRL parameter51_pc=0x%08" PRIx64
                " brightness_parameter_present=1 value=redacted\n", pc);
            qemu_plugin_outs(s);
        }
    }
    g_mutex_unlock(&output_lock);
}

static void access_cb(unsigned int cpu, qemu_plugin_meminfo_t info,
                      uint64_t vaddr, void *userdata)
{
    uint64_t pc = (uintptr_t)userdata;
    if (dcs_control_only) {
        dcs_access(cpu, info, vaddr, pc);
        return;
    }
    /* Some QEMU 10.1 system-mode RAM callbacks have no valid hwaddr
     * accessor context. In explicit virtual-only mode never query it;
     * report only virtual addresses rather than asserting identity maps.
     */
    struct qemu_plugin_hwaddr *hw =
        virtual_only ? NULL : qemu_plugin_get_hwaddr(info, vaddr);
    uint64_t physical = hw ? qemu_plugin_hwaddr_phys_addr(hw) : vaddr;
    const char *device = virtual_only ? "virtual-only" :
                         (hw ? qemu_plugin_hwaddr_device_name(hw) : "untranslated");
    const char *kind = qemu_plugin_mem_is_store(info) ? "WRITE" : "READ";
    bool emit;
    int i, range_index = 32;
    bool hit = nranges == 0;
    for (i = 0; i < nranges; i++) {
        if ((physical >= ranges[i].start && physical < ranges[i].end) ||
            (vaddr >= ranges[i].start && vaddr < ranges[i].end)) {
            hit = true;
            range_index = i;
            break;
        }
    }
    if (!hit) {
        return;
    }
    g_mutex_lock(&output_lock);
    seen++;
    emit = emitted_per_range[range_index] < max_events;
    if (emit) {
        emitted_per_range[range_index]++;
        recorded++;
    }
    g_mutex_unlock(&output_lock);
    if (emit) {
        g_autofree char *line = g_strdup_printf(
            "EXESX_ACCESS cpu=%u pc=0x%08" PRIx64 " kind=%s"
            " virtual=0x%08" PRIx64 " physical=0x%08" PRIx64
            " width=%u backing=%s\n",
            cpu, pc, kind, vaddr, physical,
            1u << qemu_plugin_mem_size_shift(info),
            device ? device : "(unknown)");
        qemu_plugin_outs(line);
        if (show_values) {
            /* QEMU 10.1 plugin memory-value API: only owner-opted traces.
             * NEVER enable in CI with private Casio binaries or commit
             * the resulting raw command/pixel values.
             */
            qemu_plugin_mem_value mv = qemu_plugin_mem_get_value(info);
            uint64_t val = mv.type == QEMU_PLUGIN_MEM_VALUE_U8 ? mv.data.u8 :
                           mv.type == QEMU_PLUGIN_MEM_VALUE_U16 ? mv.data.u16 :
                           mv.type == QEMU_PLUGIN_MEM_VALUE_U32 ? mv.data.u32 :
                           mv.data.u64;
            g_autofree char *value_line = g_strdup_printf(
                "EXESX_VALUE cpu=%u pc=0x%08" PRIx64
                " kind=%s virtual=0x%08" PRIx64
                " width=%u value=0x%08" PRIx64 "\n",
                cpu, pc, kind, vaddr,
                1u << qemu_plugin_mem_size_shift(info), val);
            qemu_plugin_outs(value_line);
        }
    }
}

static void translated(qemu_plugin_id_t id, struct qemu_plugin_tb *tb)
{
    size_t i, count = qemu_plugin_tb_n_insns(tb);
    for (i = 0; i < count; i++) {
        struct qemu_plugin_insn *insn = qemu_plugin_tb_get_insn(tb, i);
        uintptr_t pc = (uintptr_t)qemu_plugin_insn_vaddr(insn);
        qemu_plugin_register_vcpu_mem_cb(insn, access_cb,
                                         QEMU_PLUGIN_CB_NO_REGS,
                                         QEMU_PLUGIN_MEM_RW, (void *)pc);
    }
}

static void finished(qemu_plugin_id_t id, void *userdata)
{
    if (dcs_control_only) {
        g_autofree char *s = g_strdup_printf(
            "EXESX_DCS_SUMMARY cmd53=%" G_GUINT64_FORMAT
            " params53=%" G_GUINT64_FORMAT
            " dd_transitions=%" G_GUINT64_FORMAT
            " cmd51=%" G_GUINT64_FORMAT
            " params51=%" G_GUINT64_FORMAT "\n",
            dcs_n53, dcs_p53, dcs_toggles, dcs_n51, dcs_p51);
        qemu_plugin_outs(s);
        return;
    }
    g_autofree char *s = g_strdup_printf(
        "EXESX_SUMMARY tracked_accesses=%" G_GUINT64_FORMAT
        " emitted=%" G_GUINT64_FORMAT
        " dropped=%" G_GUINT64_FORMAT "\n",
        seen, recorded, seen - recorded);
    qemu_plugin_outs(s);
}

QEMU_PLUGIN_EXPORT int qemu_plugin_install(qemu_plugin_id_t id,
                                           const qemu_info_t *info,
                                           int argc, char **argv)
{
    int i;
    if (!info->system_emulation) {
        return -1;
    }
    for (i = 0; i < argc; i++) {
        if (g_str_equal(argv[i], "dcs_control_only=1")) {
            dcs_control_only = true;
            virtual_only = true;
        } else if (g_str_equal(argv[i], "values=1")) {
            show_values = true;
        } else if (g_str_equal(argv[i], "virtual_only=1")) {
            virtual_only = true;
        } else if (g_str_has_prefix(argv[i], "max=")) {
            max_events = g_ascii_strtoull(argv[i] + 4, NULL, 0);
            if (max_events > 100000) {
                fprintf(stderr, "EXeSX plugin max limit exceeded\n");
                return -1;
            }
        } else if (g_str_has_prefix(argv[i], "range=")) {
            char *colon;
            char *part = argv[i] + 6;
            uint64_t a, b;
            if (nranges >= 32 || !(colon = strchr(part, ':'))) {
                fprintf(stderr, "EXeSX plugin expected range=START:END\n");
                return -1;
            }
            a = g_ascii_strtoull(part, NULL, 0);
            b = g_ascii_strtoull(colon + 1, NULL, 0);
            if (a >= b) {
                fprintf(stderr, "EXeSX plugin reversed/empty range\n");
                return -1;
            }
            ranges[nranges++] = (Range){a,b};
        } else {
            fprintf(stderr, "EXeSX plugin unknown option: %s\n", argv[i]);
            return -1;
        }
    }
    g_mutex_init(&output_lock);
    qemu_plugin_register_vcpu_tb_trans_cb(id, translated);
    qemu_plugin_register_atexit_cb(id, finished, NULL);
    return 0;
}
