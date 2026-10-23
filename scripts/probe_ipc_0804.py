#!/usr/bin/env python3
"""Private read-only A7/M4 response provenance for original DY357 service 0x0804.

Requires a locally owned, validated OSUP and the experimental QEMU board.
Breakpoints and GDB write-watchpoints only; no guest RAM writes, IRQ injection,
forced GPIO state, or firmware bytes exported. Results MUST stay under private/.
"""
import json
import re
import subprocess
import time
from pathlib import Path

from probe_postdma_handoff import (
    RSP, choose_port, decode_registers, encode_packet,
)

REQUEST_CALLER = 0x6001D554
MILESTONES = {
    0x6017807C: "dispatcher_entry",
    0x60177FD8: "request_slot_index",
    0x60178048: "request_published",
    0x60178054: "response_copy",
    0x6001D558: "dispatcher_return",
    0x6001D564: "nonzero_response_return",
    0x60010898: "version_dialog_input_ready_result",
    0x600108A8: "keyboard_event_queue",
    0x60010974: "version_dialog_exit",
    0x6004A2B0: "startup_return",
    0x60400000: "os_entry",
}
SLOT_BASE = 0x2F028000
SLOT_STRIDE = 72
RESPONSE_OFFSET = 12


def response_word_address(index):
    """The original A7 transport uses 72-byte slots and word +12 for result."""
    if not isinstance(index, int) or not 0 <= index < 32:
        raise ValueError("Unexpected IPC slot index")
    return SLOT_BASE + index * SLOT_STRIDE + RESPONSE_OFFSET


def stopped_thread(reply):
    if not reply.startswith("T"):
        return None
    match = re.search(r"thread:0*([0-9a-fA-F]+);", reply)
    return int(match.group(1), 16) if match else None


def run_probe(command, environment, seconds, output_dir):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    port = choose_port()
    report = {
        "scope": "Private, original-ROM 0x0804 A7/M4 request/response",
        "timeout_seconds": seconds,
        "gpio_a_input_mask": environment.get("EXESX_GPIOA_INPUT_MASK"),
        "gpio_b_input_mask": environment.get("EXESX_GPIOB_INPUT_MASK"),
        "events": [],
        "limit": "Bounded observations, not real GPIO wiring or a complete OS boot",
    }
    cmd = list(command) + ["-S", "-gdb", f"tcp:127.0.0.1:{port}"]
    out = output / "ipc0804-qemu-console-private.log"
    with out.open("w") as console:
        proc = subprocess.Popen(cmd, env=environment, stdout=console,
                                stderr=subprocess.STDOUT)
        conn = None
        try:
            for _ in range(100):
                if proc.poll() is not None:
                    raise RuntimeError("QEMU exited before GDB connection")
                try:
                    import socket
                    conn = socket.create_connection(("127.0.0.1", port), timeout=0.35)
                    break
                except OSError:
                    time.sleep(0.1)
            if conn is None:
                raise TimeoutError("QEMU GDB socket not ready")
            rsp = RSP(conn)
            rsp.command("?")
            if rsp.command("Hg1") != "OK" or rsp.command("Hc-1") != "OK":
                raise RuntimeError("Unable to select A7 CPU0 and continue both cores")
            if rsp.command(f"Z0,{REQUEST_CALLER:x},4") != "OK":
                raise RuntimeError("Unable to break at original service 0x0804 call")
            breakpoints = {REQUEST_CALLER: "original_request"}
            slot = None
            watched = False
            deadline = time.monotonic() + seconds
            conn.sendall(encode_packet("c"))
            while time.monotonic() < deadline and proc.poll() is None:
                try:
                    stop = rsp.receive(min(1.25, max(0.05, deadline-time.monotonic())))
                except TimeoutError:
                    continue
                thread = stopped_thread(stop)
                if thread not in (1, 2):
                    report["unhandled_stop"] = stop[:100]
                    break
                if rsp.command(f"Hg{thread}") != "OK":
                    raise RuntimeError("Cannot select stopping CPU")
                regs = decode_registers(rsp.command("g"))
                pc = regs["r15"]
                kind = breakpoints.get(pc, "m4_response_write" if watched and "watch:" in stop else "unexpected_stop")
                item = {
                    "kind": kind, "thread": thread, "pc": hex(pc),
                    "r0": hex(regs["r0"]), "r1": hex(regs["r1"]),
                    "lr": hex(regs["r14"]),
                    "slot": slot,
                }
                if slot is not None:
                    item["response_word_at_stop"] = (
                        None if (v := rsp.memory(response_word_address(slot), 4)) is None else hex(v)
                    )
                if kind == "original_request":
                    if thread != 1 or regs["r1"] != 0x0804:
                        raise RuntimeError("Breakpoint did not contain expected A7 service ID 0x0804")
                    if rsp.command(f"z0,{REQUEST_CALLER:x},4") != "OK":
                        raise RuntimeError("Cannot remove service caller breakpoint")
                    breakpoints.pop(pc)
                    for address, label in MILESTONES.items():
                        if rsp.command(f"Z0,{address:x},4") != "OK":
                            raise RuntimeError(f"Cannot insert breakpoint {address:#x}")
                        breakpoints[address] = label
                elif kind == "request_slot_index":
                    if thread != 1:
                        raise RuntimeError("Request allocator did not execute on A7")
                    slot = regs["r0"]
                    response_word_address(slot)  # refuse unexpected allocation
                    if rsp.command(f"z0,{pc:x},4") != "OK":
                        raise RuntimeError("Cannot remove slot-index breakpoint")
                    breakpoints.pop(pc)
                elif kind == "request_published":
                    if thread != 1 or slot is None:
                        raise RuntimeError("No A7 request slot before publication")
                    # A7 has copied the original request ID into slot+12.
                    # Watch the eventual response word, not the A7 byte9
                    # publication store, which would be a false producer hit.
                    address = response_word_address(slot)
                    if rsp.command(f"Z2,{address:x},4") != "OK":
                        raise RuntimeError("Unable to watch M4 response word")
                    watched = True
                    if rsp.command(f"z0,{pc:x},4") != "OK":
                        raise RuntimeError("Cannot remove publication breakpoint")
                    breakpoints.pop(pc)
                elif kind == "m4_response_write":
                    item["expected_m4_thread"] = thread == 2
                    item["m4_gpio_a_pdir"] = (
                        None if (v := rsp.memory(0x4100F010, 4)) is None else hex(v)
                    )
                    item["m4_gpio_a_pddr"] = (
                        None if (v := rsp.memory(0x4100F014, 4)) is None else hex(v)
                    )
                    item["m4_gpio_b_pdir"] = (
                        None if (v := rsp.memory(0x4100F050, 4)) is None else hex(v)
                    )
                    if rsp.command(f"z2,{response_word_address(slot):x},4") != "OK":
                        raise RuntimeError("Cannot remove response watchpoint")
                    watched = False
                elif pc in breakpoints:
                    if rsp.command(f"z0,{pc:x},4") != "OK":
                        raise RuntimeError("Cannot remove executed breakpoint")
                    breakpoints.pop(pc)
                else:
                    report["unexpected_stop"] = stop[:100]
                    report["events"].append(item)
                    break
                report["events"].append(item)
                print(kind, "thread", thread, "pc", hex(pc), "r0", item["r0"], flush=True)
                if rsp.command("Hg1") != "OK":
                    raise RuntimeError("Cannot restore A7 selection")
                conn.sendall(encode_packet("c"))
            if proc.poll() is None:
                conn.sendall(b"\x03")
                try:
                    stop = rsp.receive(3)
                    if stopped_thread(stop) is not None:
                        rsp.command("Hg1")
                        regs = decode_registers(rsp.command("g"))
                        report["final_a7_pc"] = hex(regs["r15"])
                except (TimeoutError, OSError, ValueError):
                    pass
        finally:
            if conn:
                conn.close()
            proc.kill()
            proc.wait(timeout=5)
            (output / "ipc0804-summary.json").write_text(
                json.dumps(report, indent=2) + "\n"
            )
    return report
