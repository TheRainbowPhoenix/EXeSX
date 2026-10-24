#!/usr/bin/env python3
"""Read-only original A7 QEMU -d exec cold-start milestone analysis.

Accepts private QEMU execution logs; only writes summary. No guest writes,
breakpoint perturbation, event injection, or source firmware publishing.
"""
import argparse
import json
from pathlib import Path
import re

MILESTONES = {
    "a7_main_initial_start": (0, 0x6004A0B4),
    "a7_initial_subsystem_init": (0, 0x60049C18),
    "a7_power_a004_callsite": (0, 0x60049C4C),
    "a7_power_a004_return_boundary": (0, 0x60049C50),
    "a7_power_init_helper": (0, 0x6000F688),
    "a7_power_a004_sender": (0, 0x60009284),
    "a7_ipc_sync_call": (0, 0x601782C8),
    "a7_ipc_wait_reply": (0, 0x60177CF8),
    "a7_ipc_wait_reply_alt": (0, 0x60177DFC),
    "a7_first_8800_service": (0, 0x60049C9C),
    "a7_first_9000_service": (0, 0x60049CC4),
    "a7_boot_activates_tasks": (0, 0x6004A124),
    "a7_boot_power_threshold": (0, 0x6004A180),
    "a7_boot_reinitialization": (0, 0x60011860),
    "a7_bios_startup_logic": (0, 0x60011CA4),
    "a7_version_event_wait": (0, 0x600108A8),
    "a7_factory_menu_entry": (0, 0x6003A878),
    "m4_a004_service_dispatch": (1, 0x1FFD9D44),
    "m4_a004_argument_2_handler": (1, 0x1FFDF49E),
    "m4_ipc_request_dispatch": (1, 0x1FFD5510),
    "m4_control_task_event_wait": (1, 0x1FFD635C),
    "m4_control_task_command_dispatch": (1, 0x1FFD5510),
    "m4_mu_notification_callback": (1, 0x1FFE479C),
    "m4_rtos_event_signal": (1, 0x1FFD53BA),
    "m4_ipc_mu_notification": (1, 0x1FFE479C),
}
PATTERN = re.compile(r'^Trace ([01]):.*?/([0-9a-fA-F]{16})/')

def summarize(path):
    by_pc = {(cpu, pc): name for name, (cpu, pc) in MILESTONES.items()}
    hits = {}
    line_number = 0
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line_number, line in enumerate(stream, 1):
            m = PATTERN.match(line)
            if m:
                name = by_pc.get((int(m.group(1)), int(m.group(2), 16)))
                if name is not None:
                    item = hits.setdefault(name, {"count": 0, "first_trace_line": line_number})
                    item["count"] += 1
    return {"input": str(path), "trace_lines": line_number,
            "hits": {name: hits.get(name, {"count": 0}) for name in MILESTONES},
            "a004_return_seen": "a7_power_a004_return_boundary" in hits,
            "boot_task_activations_seen": "a7_boot_activates_tasks" in hits,
            "factory_menu_seen": "a7_factory_menu_entry" in hits}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path, help="Private original-firmware QEMU -d exec trace")
    parser.add_argument("--output", type=Path, help="Optional private summary JSON")
    args = parser.parse_args()
    report = summarize(args.trace)
    result = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(result + "\n", encoding="utf-8")
    print(result)

if __name__ == "__main__":
    main()
