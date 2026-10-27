#!/usr/bin/env python3
"""Safe original-firmware TEST MENU headless regression (not fake menu events).

Runs the same real M4 physical contacts + A7 trace worker as the floating
controller. QMP only READS original IPC. If the native menu painter has not
executed, DO NOT select unknown factory items or destructive SD tests.
This tool returns 3 for menu entry with blocked 0x400B/menu paint.
"""
import argparse
import hashlib
import json
from pathlib import Path
import queue
import re
import time

from factory_control_panel import EmulatorWorker
from auto_driver import optional_qemu_path


def parse_ipc_dump(value):
    words = []
    for line in value.splitlines():
        if ":" in line:
            words += [int(n, 16) for n in
                      re.findall(r"0x[0-9a-fA-F]+", line.split(":", 1)[1])]
    return {
        "request": "0x{:08x}".format(words[3]) if len(words) > 3 else None,
        "argument": words[4] if len(words) > 4 else None,
        "status": "0x{:08x}".format(words[2]) if len(words) > 2 else None,
    }


def parse_m4_event10_guard(text):
    """Decode an *original read-only RAM* sample of M4 control bit0/bit2.

    0x1FFE42C4 checks (state_byte & 0x5) != 0; if true it skips
    original event10 semaphore release at 0x1FFE42FA. This is an
    observation-only classifier, not a command to overwrite the state.
    """
    words = re.findall(r"0x([0-9a-fA-F]{1,8})", text.split(":", 1)[-1])
    if not words:
        return {"accessible": False, "raw": None,
                "bit0_or_bit2_blocks_event10": None}
    value = int(words[0], 16)
    return {"accessible": True, "raw": "0x{:08x}".format(value),
            "bit0_or_bit2_blocks_event10": bool(value & 5)}


def check(name, condition, blocked=None):
    return {"name": name, "status": "PASS" if condition else
            ("BLOCKED" if blocked else "FAIL"),
            "blocked_by": None if condition else blocked}


def run(a):
    actions, updates = queue.Queue(), queue.Queue()
    worker = EmulatorWorker(a, actions, updates)
    worker.start()
    actions.put(("start", "menu"))
    observed = []
    ipc = None
    menu_at = painter_at = None
    requested_ipc = did_down = False
    adc_samples = []
    flow_samples = []
    m4_execution = []
    last_flow_at = 0
    last_adc_at = 0
    before_down = None
    t0 = time.monotonic()
    try:
        while time.monotonic() - t0 < a.seconds:
            try:
                event = updates.get(timeout=.30)
            except queue.Empty:
                event = None
            if event is not None:
                kind, value, *_ = event
                if kind == "milestone":
                    observed.append(value)
                    print("ORIGINAL ARM:", value, flush=True)
                    if value == "TEST MENU code entered":
                        menu_at = time.monotonic()
                    if value == "Menu painter executed":
                        painter_at = time.monotonic()
                elif kind == "ipc":
                    ipc = parse_ipc_dump(value)
                    print("ORIGINAL IPC:", ipc, flush=True)
                elif kind == "m4_400b":
                    m4_execution.append({"host_elapsed": round(time.monotonic()-t0, 2),
                                         **value})
                    print("ORIGINAL M4:", value, flush=True)
                elif kind == "400b_flow":
                    original = parse_m4_event10_guard(value["m4_guard"])
                    registers = value.get("m4_registers", "")
                    m4_cpu = {}
                    for name in ("R13", "R14", "R15", "xPSR", "MSP", "PSP"):
                        match = re.search(r"\b" + name +
                                          r"=([0-9a-fA-F]{8})", registers)
                        if match:
                            m4_cpu[name.lower()] = "0x" + match.group(1)
                    flow = {"host_elapsed": round(time.monotonic()-t0, 2),
                            "original_m4_state": original,
                            "m4_original_state_registers": value.get("m4_state"),
                            "m4_cpu1_registers": m4_cpu,
                            "original_a7_m4_ipc": parse_ipc_dump(value["shared_ipc"])}
                    flow_samples.append(flow)
                    print("EVENT10 GUARD:", flow, flush=True)
                elif kind == "adc":
                    sample = {"host_elapsed": round(time.monotonic()-t0, 2)}
                    for bank, registers in value.items():
                        decoded = {}
                        errors = {}
                        for reg, text in registers.items():
                            line = text.split(":", 1)[-1]
                            match = re.search(r"0x[0-9a-fA-F]+", line)
                            decoded[reg] = match.group(0) if match else None
                            if not match:
                                errors[reg] = text.strip()
                        sample[bank] = {
                            **decoded, "accessible": all(
                                decoded[name] is not None
                                for name in ("ctrl", "stat", "ie", "fctrl")),
                            "read_errors": errors or None}
                    adc_samples.append(sample)
                    print("PASSIVE ADC:", sample, flush=True)
                elif kind == "status" and (
                        "Worker error:" in value or
                        "QEMU exited unexpectedly:" in value):
                    print(value, flush=True)
                    break
            if (menu_at is not None and not requested_ipc and
                    time.monotonic() - menu_at >= 1):
                actions.put(("read_ipc", None))
                requested_ipc = True
            if (getattr(a, "sample_400b_flow", False) and menu_at is not None and
                    time.monotonic() - last_flow_at >= 7):
                last_flow_at = time.monotonic()
                actions.put(("read_400b_flow", None))
            if (getattr(a, "sample_adc", False) and menu_at is not None and
                    time.monotonic() - last_adc_at >= 20):
                last_adc_at = time.monotonic()
                actions.put(("read_adc", None))
            if painter_at is not None and not did_down and worker.frame_count:
                frame = a.output_dir / "gui-screen.ppm"
                before_down = (hashlib.sha256(frame.read_bytes()).hexdigest()
                               if frame.is_file() else None)
                # Physically close/release DOWN (ROM key 0x91). NEVER Enter.
                actions.put(("safe_check", None))
                did_down = True
            if (menu_at is not None and painter_at is None and
                    time.monotonic() - menu_at >= a.post_menu_seconds):
                break
            if painter_at is not None and did_down and time.monotonic()-painter_at > 4:
                break

        hits = set(observed)
        menu = "TEST MENU code entered" in hits
        painter = "Menu painter executed" in hits
        image = a.output_dir / "gui-screen.ppm"
        final_sha = (hashlib.sha256(image.read_bytes()).hexdigest()
                     if image.is_file() else None)
        checks = [
            check("version dialog reached", "Version popup entered" in hits),
            check("original A7 keyboard event wait", "Version popup event wait" in hits),
            check("0x93 key checker", "First menu key check" in hits),
            check("0x94 accepted", "0x94 accepted" in hits),
            check("original factory-menu code entry", menu),
            check("0x400B IPC service invoked", "IPC 0x400B invoked" in hits),
            check("0x400B service returned", "IPC 0x400B returned" in hits,
                  "0x400B(2) pending" if menu else None),
            check("original TEST MENU painter", painter,
                  "0x400B did not return" if menu else None),
            check("safe DOWN navigation", did_down,
                  "no menu painter; unsafe to navigate blindly" if not painter else
                  ("LCD intentionally disabled; no verified selection" if a.no_screenshots else None)),
            check("selection changes real LCD", bool(before_down and final_sha != before_down),
                  "LCD intentionally disabled for IPC soak" if a.no_screenshots else
                  ("no painted menu to compare" if not did_down else None)),
        ]
        a.output_dir.mkdir(parents=True, exist_ok=True)
        report = {
            "no_screenshots": a.no_screenshots,
            "tcg_thread": a.tcg_thread,
            "m4_400b_trace_enabled": a.trace_m4_400b,
            "diagnostic_raw_adc0": a.adc0_sample,
            "diagnostic_raw_adc1": a.adc1_sample,
            "method": "unchanged OSUP guest, original physical GPIO keys, executed ARM TBs and read-only QMP",
            "original_checkpoints": observed,
            "shared_ipc": ipc,
            "passive_adc_samples": adc_samples,
            "event10_guard_samples": flow_samples,
            "m4_original_post_menu_execution": m4_execution,
            "frames": worker.frame_count,
            "lcd_sha256": final_sha,
            "qemu_running_during_check": bool(worker.proc and worker.proc.poll() is None),
            "checks": checks,
            "destructive_sd_tests_executed": False,
            "private_trace": "gui-execution-private.log",
        }
        outfile = a.output_dir / "menu-checks-private.json"
        outfile.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
        for item in checks:
            print("{:7} {}{}".format(
                item["status"], item["name"],
                " ({})".format(item["blocked_by"]) if item["blocked_by"] else ""),
                flush=True)
        print("PRIVATE REPORT:", outfile, flush=True)
        return (0 if (menu and painter and did_down and
                       before_down and final_sha != before_down) else
                (3 if menu else 2))
    finally:
        actions.put(("quit", None))
        worker.join(timeout=12)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("osup", type=Path, nargs="?")
    p.add_argument("--qemu", type=Path)
    p.add_argument("--elf", type=Path)
    p.add_argument("--emmc", type=Path)
    p.add_argument("--sd", type=Path, help="Disposable SD image; snapshot=on")
    p.add_argument("--profile", type=Path)
    p.add_argument("--output-dir", type=Path, default=Path("private/menu-tests"))
    p.add_argument("--seconds", type=float, default=85)
    p.add_argument("--post-menu-seconds", type=float, default=8)
    p.add_argument("--retries", type=int, default=3)
    p.add_argument("--retry-after", type=float, default=24)
    p.add_argument("--release-at", type=float, default=1.2)
    p.add_argument("--hold", type=float, default=.060)
    p.add_argument("--gap", type=float, default=.025)
    p.add_argument("--fps", type=float, default=2)
    p.add_argument("--adc0-sample", type=lambda s:int(s,0), default=None,
                   help="Explicit raw 16-bit ADC0 analog source; diagnostic, default disconnected")
    p.add_argument("--adc1-sample", type=lambda s:int(s,0), default=None,
                   help="Explicit raw 16-bit ADC1 analog source; diagnostic, default disconnected")
    p.add_argument("--sample-400b-flow", action="store_true",
                   help="Read-only M4 bit0/bit2 event10 guard and 0x400B shared IPC")
    p.add_argument("--sample-adc", action="store_true",
                   help="Sample genuine ADC0/ADC1 CTRL/STAT/IE/FCTRL via read-only QMP")
    p.add_argument("--no-screenshots", action="store_true",
                   help="No LCD QMP reads, mmap or PPM; investigate IPC independent of capture")
    p.add_argument("--tcg-thread", choices=("single","multi"), default="single",
                   help="A7/M4 scheduling A/B test")
    p.add_argument("--trace-m4-400b", action="store_true",
                   help="Include native M4 event7 wait/producer PCs in private execution trace")
    a = p.parse_args()
    a.qemu = optional_qemu_path(a.qemu)
    if a.profile is None:
        here = Path(__file__).resolve().parent
        locations = [here.parent / "profiles" / "imx7ulp-early-boot.ini",
                     here / "profiles" / "imx7ulp-early-boot.ini"]
        a.profile = next((candidate for candidate in locations if candidate.is_file()),
                         locations[0])
    a.profile = a.profile.resolve()
    a.output_dir = a.output_dir.resolve()
    if (not a.profile.is_file() or
            not (a.osup or a.elf and a.emmc) or
            a.seconds <= 0 or a.post_menu_seconds < 0 or a.retries < 1):
        p.error("Missing original private OSUP/ELF/eMMC/profile or invalid duration")
    if any(x is not None and not (0 <= x <= 0xffff)
           for x in (a.adc0_sample, a.adc1_sample)):
        p.error("Explicit raw ADC sample must be 0..0xffff")
    if a.sd and (not a.sd.is_file() or a.sd.stat().st_size < 2 * 1024**3):
        p.error("SD must be disposable raw image >=2GiB")
    return run(a)


if __name__ == "__main__":
    raise SystemExit(main())
