#!/usr/bin/env python3
"""Retryable, owner-local sweep of ORIGINAL DY357 factory menu paths.

No guest PC/memory/IPC injection. QEMU is tcg,thread=single; both media
snapshot=on. Every attempted path begins with a fresh original-ROM boot,
physical M4 test-chord keys, and read-only QMP LCD captures. A changed
screen is NOT a hardware PASS; only an owner-supplied golden can assert
a pixel-level match. Never upload logs, screenshots or proprietary ROMs.
"""
import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from auto_driver import profile_with_lcd
from ci_e2e_arm_pattern import (
    CHECKPOINTS, TRACE_PC, frame, m4_idle, navigate, physical, qemu_env,
    screenshot,
)
from ci_e2e_display_advanced import (
    HEADERS, native_header_fingerprint, screen_rgb,
)
from drive_factory_menu import QMP, choose_port, connect


@dataclass(frozen=True)
class MenuCase:
    key: str
    route: tuple
    kind: str = "menu"  # menu, diagnostic, unsafe, blocked
    requirement: str = ""
    # A known original LCD menu-header hash, not a fabricated guest PASS.
    known_header: str = ""


# A full registry also includes entries that must NOT be activated without
# an external peripheral or explicit operator consent. The scope=all report
# keeps them visible as SKIP rather than quietly calling them "passed".
CASES = (
    MenuCase("factory-manual-menu", (1,), known_header="manual-menu"),
    MenuCase("manual-display-menu", (1, 1), known_header="display-menu"),
    MenuCase("display-test-menu", (1, 1, 1),
             known_header="display-test-menu"),
    MenuCase("display-settings-menu", (1, 1, 2),
             known_header="display-settings-menu"),
    MenuCase("manual-wireless-menu", (1, 8)),
    MenuCase("wlan-communication-menu", (1, 8, 1)),
    MenuCase("wlan-battery-menu", (1, 8, 2)),
    MenuCase("wlan-power-save-menu", (1, 8, 3)),
    MenuCase("wlan-firmware-menu", (1, 8, 4)),
    MenuCase("wlan-mac-address-menu", (1, 8, 5)),
    MenuCase("wlan-version-check", (1, 8, 4, 2), "diagnostic",
             "winc"),
    MenuCase("wlan-get-mac", (1, 8, 5, 1), "diagnostic", "winc"),
    MenuCase("wlan-rssi", (1, 8, 1, 1), "diagnostic", "ap"),
    MenuCase("wlan-auto-deep-sleep", (1, 8, 3, 1), "diagnostic", "ap"),
    MenuCase("wlan-power-down", (1, 8, 3, 2), "blocked",
             "physical-key-assisted power-cycle test"),
    MenuCase("wlan-dhcp", (1, 8, 1, 1), "blocked",
             "DHCP fixture can be exercised through RSSI association; "
             "no independent DHCP LCD verdict established"),
    MenuCase("wlan-firmware-update", (1, 8, 4, 1), "unsafe",
             "OTA flash write, intentionally disabled"),
    MenuCase("factory-wifi-auto-usb", (8,), "blocked",
             "USB device controller / external 6-byte fixture absent"),
    MenuCase("factory-touch-e2", (13,), "blocked",
             "original touch electrode/IRQ pipeline not complete"),
    MenuCase("display-color-bar-1", (1, 1, 1, 2), "diagnostic"),
    MenuCase("display-color-bar-2", (1, 1, 1, 3), "diagnostic"),
    MenuCase("display-chidori", (1, 1, 1, 4), "diagnostic"),
    MenuCase("display-r-chidori", (1, 1, 1, 5), "diagnostic"),
    MenuCase("display-frame", (1, 1, 1, 6), "diagnostic"),
    MenuCase("display-gradation", (1, 1, 1, 7), "diagnostic"),
    MenuCase("display-menu-1", (1, 1, 1, 8), "diagnostic"),
    MenuCase("display-menu-2", (1, 1, 1, 9), "diagnostic"),
    MenuCase("display-menu-3", (1, 1, 1, 10), "diagnostic"),
    MenuCase("display-pattern-auto", (1, 1, 1, 11), "blocked",
             "multi-key completion requires separate pattern driver"),
)

# Root factory menu has 16 items. The other 12 entries need confirmed
# labels/hardware classification before any automatic ENTER. Do not try
# unknown firmware-modifying tests speculatively.
FACTORY_KNOWN_ROWS = {1, 8, 13}
# Reference fingerprints are measured from the owner-original A7 LCD,
# not inferred from a changed frame. Prevent stale M4 ENTER keys from
# silently navigating back into DISPLAY instead of the WLAN menu.
# The first two are original MANUAL MENU -> WLAN CHECK MENU;
# the third is the genuine "****< Wi-Fi MENU >****" with RSSI TEST row 1.
# The original root TEST MENU and nested MANUAL CHECK share the literal
# header "MANUAL MENU". A title-only fingerprint is insufficient: the
# nested menu has row2 MEMORY MENU and row3 eMMC MENU, whereas the root
# has ARM PATTERN entries. Golden is derived only from the original LCD
# row2-4 *caption ink*, not guest state or synthetic text injection.
ORIGINAL_MANUAL_CHECK_ROWS_SHA256 = (
    "880467b96e315f0f46957098e2ba6ed17ce2faa257e139d9672001650bd7cf38"
)


def original_menu_rows_fingerprint(rgb):
    ink = bytearray()
    for row in (2, 3, 4):
        y0 = round(25 + (row - 1) * 24.3)
        ink.extend(int(rgb[3 * (y * 864 + x)] < 127)
                   for y in range(y0, y0 + 20)
                   for x in range(20, 430))
    return hashlib.sha256(ink).hexdigest()


ORIGINAL_WLAN_ROUTE_HEADERS = {
    (1, 8): "252dd05d8034ae95fce3ad729a483efba2eda65c9bca9a6972f516eb9c1eb721",
    (1, 8, 1): "c4ad1600bca91a11754d3b74f1fe04dcb91bc35231cc276bcc1f20a069706d54",
}


ROOT_UNMAPPED = tuple(
    MenuCase("factory-row-%02d-unmapped" % row, (row,), "blocked",
             "root row action not yet audited; no automatic ENTER")
    for row in range(1, 17) if row not in FACTORY_KNOWN_ROWS
)


def require_original_menu_header(route, observed, rgb=None):
    """Reject wrong navigation even when the native LCD changed.

    A stale M4 ENTER once went from WLAN CHECK MENU into DISPLAY MENU.
    Generic frame-change checks misreported it as RSSI screen coverage.
    Only source-captured authentic heading fingerprints count here.
    """
    display = {
        (1,): "manual-menu",
        (1, 1): "display-menu",
        (1, 1, 1): "display-test-menu",
        (1, 1, 2): "display-settings-menu",
    }
    known = display.get(tuple(route))
    expected = (HEADERS[known] if known else
                ORIGINAL_WLAN_ROUTE_HEADERS.get(tuple(route)))
    if expected and observed != expected:
        raise RuntimeError("original factory route heading mismatch: " +
                           ",".join(map(str, route)))
    if tuple(route) == (1,):
        if rgb is None or original_menu_rows_fingerprint(rgb) != (
                ORIGINAL_MANUAL_CHECK_ROWS_SHA256):
            raise RuntimeError(
                "root and nested MANUAL MENU have identical titles; "
                "original row-caption evidence does not match nested menu")


def all_cases():
    return CASES + ROOT_UNMAPPED


def skip_reason(case, args):
    if case.kind in ("unsafe", "blocked"):
        return case.requirement
    if case.requirement == "winc" and args.winc_port is None:
        return "WINC simulator not configured (--winc-port)"
    if case.requirement == "ap" and not (args.winc_port and args.fixture_ssid):
        return "explicit AP fixture required (--winc-port --fixture-ssid)"
    return ""


def press_and_open(qmp, contact, out, stage, attempts=6):
    """Pulse actual M4 ENTER briefly, release, THEN sample original LCD.

    QMP frame captures can take long periods under single-threaded TCG.
    Previously holding ENTER until the framebuffer changed caused repeated
    electrical key events and even reentered the *previous* menu's handler.
    Each bounded physical pulse now runs independently of QMP operations.
    """
    before = frame(qmp, out, stage + "-before")
    old_title = native_header_fingerprint(screen_rgb(out, stage + "-before"))
    old_hash = before["sha256"]
    for i in range(attempts):
        physical(contact, "0x94")
        try:
            time.sleep(.19)
        finally:
            physical(contact, "0")
        # The original M4 GPIO scan/debounce and A7 menu handler need
        # physical key release before the next input or LCD inspection.
        time.sleep(.65)
        for _ in range(10):
            if m4_idle(qmp):
                break
            time.sleep(.045)
        opened = frame(qmp, out, stage + "-probe")
        new_title = native_header_fingerprint(
            screen_rgb(out, stage + "-probe"))
        if new_title != old_title and opened["sha256"] != old_hash:
            time.sleep(.75)
            frame(qmp, out, stage + "-opened")
            confirmed = native_header_fingerprint(
                screen_rgb(out, stage + "-opened"))
            if confirmed != old_title:
                return confirmed
        time.sleep(.22)
    raise RuntimeError(
        "physical ENTER did not change original LCD title: " + stage)


ORIGINAL_CHORD_CHECKPOINTS = ("first", None, "accepted")


def factory_boot(qmp, contact, trace, proc, timeout):
    """CI-proven 0x93,0x93,0x94 chord, with real A7 PC acknowledgment."""
    hits = Counter()
    started = time.monotonic()
    while not trace.exists() and time.monotonic()-started < 5:
        time.sleep(.02)
    if not trace.exists():
        raise RuntimeError("QEMU original A7 execution trace missing")
    with trace.open("r", errors="replace") as stream:
        # Exact original-ROM entry pacing from ci_e2e_arm_pattern.py:
        # the second press of 0x93 may execute the same translated A7
        # basic block and is not guaranteed a second -d exec marker.
        # Therefore release on 280 ms upper bound; acceptance of the
        # entire chord is still checked using the original A7 PC.
        released = False
        index = 0
        down = False
        pressed = 0.0
        next_at = 0.0
        up_at = 0.0
        ack_before = 0
        buffered = ""
        while time.monotonic() - started < timeout and proc.poll() is None:
            now = time.monotonic() - started
            if not released and now >= 4:
                physical(contact, "0")
                released = True
            buffered += stream.read()
            if "\n" in buffered:
                complete, buffered = buffered.rsplit("\n", 1)
            else:
                complete = ""
            for pc in TRACE_PC.findall(complete):
                for label, addr in CHECKPOINTS.items():
                    if pc.lower() == addr:
                        hits[label] += 1
            if released and hits["wait"] and index < 3:
                desired = ("first", "first", "accepted")[index]
                if not down and now >= next_at:
                    if index == 0 or m4_idle(qmp) or now-up_at > 1.25:
                        physical(contact, ("0x93", "0x93", "0x94")[index])
                        ack_before = hits[desired]
                        pressed = now
                        down = True
                elif down and (hits[desired] > ack_before or now-pressed > .28):
                    physical(contact, "0")
                    index += 1
                    down = False
                    up_at = now
                    next_at = now + .012
            if hits["paint"]:
                break
            time.sleep(.018)
    required = ("wait", "first", "accepted", "factory",
                "ipc_call", "ipc_return", "paint")
    missing = [key for key in required if not hits[key]]
    if missing:
        raise RuntimeError("original factory checkpoints missing: " +
                           ",".join(missing))
    physical(contact, "0")
    time.sleep(1.3)
    return dict(hits)


def run_case(args, case, attempt, goldens):
    root = args.output / case.key / ("attempt-%d" % attempt)
    root.mkdir(parents=True, exist_ok=True)
    contact = root / "m4-physical-contact.txt"
    physical(contact, "0x9c,0x90")
    profile = profile_with_lcd(args.profile, root)
    env = qemu_env(profile.resolve(), contact.resolve())
    env.update({
        "EXESX_EXPERIMENTAL_LPSPI2_FIFO": "1",
        "EXESX_EXPERIMENTAL_LPSPI2_DMA": "1",
        "EXESX_ORIGINAL_LPSPI2_UPPER_LANE": "1",
        "EXESX_WINC1510_GPIO_PROTOCOL": "1",
        "EXESX_TRACE_WLAN_SPI": "1",
    })
    lib = args.qemu.parent / "lib"
    if lib.is_dir():
        env["LD_LIBRARY_PATH"] = str(lib.resolve()) + os.pathsep + env.get(
            "LD_LIBRARY_PATH", "")
    backend = None
    backend_command = None
    if args.winc_port:
        backend_command = [
            sys.executable, str(Path(__file__).with_name(
                "winc1510_spi_backend.py")), "--port", str(args.winc_port),
            "--gpio-status", "--hif-mailbox", "--fixture-identity",
            "--trace-events",
            "--command-crc", "--frame-spanning-cs",
        ]
        if args.fixture_ssid:
            backend_command.extend(("--fixture-ssid", args.fixture_ssid))
        if args.fixture_ipv4:
            backend_command.extend(("--fixture-ipv4", args.fixture_ipv4))
        env["EXESX_WINC1510_TCP_PORT"] = str(args.winc_port)
        if args.winc_start_early:
            backend = subprocess.Popen(
                backend_command, stdin=subprocess.DEVNULL,
                stdout=(root / "private-winc.log").open("wb"),
                stderr=subprocess.STDOUT)
            time.sleep(.25)
            if backend.poll() is not None:
                raise RuntimeError("WINC backend exited before QEMU startup")
    qport = choose_port()
    command = [
        str(args.qemu), "-machine", "exesx", "-m", "64M",
        "-accel", "tcg,thread=single", "-display", "none",
        "-serial", "none", "-monitor", "none", "-no-reboot", "-S",
        "-qmp", "tcp:127.0.0.1:%d,server=on,wait=off" % qport,
        "-drive", "if=none,id=exesx-emmc,file=%s,format=raw,snapshot=on"
        % args.emmc,
        "-drive", "if=none,id=exesx-sd,file=%s,format=raw,snapshot=on"
        % args.sd,
        "-device", "loader,file=%s,cpu-num=0" % args.elf,
        "-d", "exec", "-dfilter",
        "0x60010868+0x130,0x6003a878+0x500,"
        "0x60006240+0x70,0x60057668+0x40",
        "-D", str(root / "private-execution.log"),
    ]
    proc = None
    sock = None
    try:
        with (root / "private-qemu-console.log").open("wb") as console:
            proc = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL,
                                    stdout=console, stderr=subprocess.STDOUT)
            sock = connect(qport, proc)
            qmp = QMP(sock)
            qmp.execute("cont")
            checkpoints = factory_boot(
                qmp, contact, root / "private-execution.log",
                proc, args.boot_timeout)
            first = frame(qmp, root, "factory-menu")
            if len(first["histogram"]) != 2:
                raise RuntimeError("original factory LCD is not monochrome")
            screenshot(root / "factory-menu.ppm", root / "factory-menu.png")
            entered = []
            for depth, row in enumerate(case.route):
                stage = "route-%d-row-%d" % (depth + 1, row)
                navigate(qmp, contact, root, row)
                if (backend_command and backend is None and
                        depth == len(case.route) - 1):
                    # A live synchronous GPIO/IRQ socket during earlier
                    # M4 factory-key scanning can perturb the original
                    # keypad debounce. Keep the QEMU port configured,
                    # but attach the simulated WINC only once the A7 is
                    # about to enter the requested WLAN test. Real guest
                    # SPI bytes, not this host action, still initiate
                    # every WINC transaction or HIF callback.
                    backend = subprocess.Popen(
                        backend_command, stdin=subprocess.DEVNULL,
                        stdout=(root / "private-winc.log").open("wb"),
                        stderr=subprocess.STDOUT)
                    time.sleep(.25)
                    if backend.poll() is not None:
                        raise RuntimeError("WINC backend exited before test")
                title = press_and_open(
                    qmp, contact, root, stage,
                    attempts=args.entry_attempts)
                entered.append({"row": row, "header_sha256": title})
                require_original_menu_header(
                    case.route[:depth + 1], title,
                    screen_rgb(root, stage + "-opened"))
            # A native WLAN OK/NG can appear briefly before the A7
            # returns to the previous menu. Preserve distinct real LCD
            # screenshots throughout observation; never infer an OK
            # merely from a different frame/hash.
            intermediate = []
            seen = set()
            sample = 0
            observed_start = time.monotonic()
            while time.monotonic() - observed_start < args.settle:
                name = "observation-%03d" % sample
                sample += 1
                picture = frame(qmp, root, name)
                if picture["sha256"] not in seen:
                    seen.add(picture["sha256"])
                    screenshot(root / (name + ".ppm"),
                               root / (name + ".png"))
                    intermediate.append({
                        "screenshot": name + ".png",
                        "original_lcd_sha256": picture["sha256"]})
                time.sleep(.3)
            final = frame(qmp, root, "final-screen")
            screenshot(root / "final-screen.ppm", root / "final-screen.png")
            title = native_header_fingerprint(
                screen_rgb(root, "final-screen"))
            if case.known_header and title != HEADERS[case.known_header]:
                raise RuntimeError("original final menu header mismatch")
            expected = goldens.get(case.key)
            # No automatic WLAN PASS based on merely reaching a screen.
            verdict = ("PIXEL_GOLDEN_MATCH" if expected and
                       final["sha256"] == expected else
                       "PIXEL_GOLDEN_MISMATCH" if expected else
                       "MENU_VERIFIED" if case.known_header else
                       "SCREEN_OBSERVED_NOT_HARDWARE_VERDICT")
            events = []
            if args.winc_port:
                log = root / "private-winc.log"
                if log.exists():
                    for line in log.read_text(errors="replace").splitlines():
                        if line.startswith("WINC_EVENT "):
                            try:
                                events.append(json.loads(line[11:]))
                            except json.JSONDecodeError:
                                pass
            event_counts = dict(Counter(e["event"] for e in events))
            opcodes = sorted(set(
                e.get("opcode", "") for e in events
                if e["event"] == "hif-request"))
            return {
                "status": verdict, "route": list(case.route),
                "intermediate_lcd_captures": intermediate,
                "winc_event_counts": event_counts,
                "original_hif_request_opcodes": opcodes,
                "winc_private_event_log": ("private-winc.log"
                                           if args.winc_port else None),
                "actual_a7_checkpoints": checkpoints, "entered": entered,
                "original_lcd_ppm_sha256": final["sha256"],
                "original_lcd_header_sha256": title,
                "screenshot": str((root / "final-screen.png").relative_to(
                    args.output)),
                "original_firmware_modified": False,
                "tcg": "single", "media_snapshot": True,
            }
    finally:
        physical(contact, "0")
        if sock:
            sock.close()
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=4)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        if backend:
            backend.terminate()
            try:
                backend.wait(timeout=4)
            except subprocess.TimeoutExpired:
                backend.kill()
                backend.wait()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true",
                        help="print full coverage/skip manifest without ROM")
    parser.add_argument("--scope", choices=("menus", "diagnostics", "all"),
                        default="menus")
    parser.add_argument("--only", action="append", default=[],
                        help="case name or substring; repeatable")
    for name in ("qemu", "profile", "elf", "emmc", "sd", "output"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--entry-attempts", type=int, default=6)
    parser.add_argument("--boot-timeout", type=float, default=90)
    parser.add_argument("--settle", type=float, default=2)
    parser.add_argument("--winc-port", type=int)
    parser.add_argument("--winc-start-early", action="store_true",
                        help="legacy: attach Python WINC before QEMU boot; "
                             "default defers it until selected test entry")
    parser.add_argument("--fixture-ssid")
    parser.add_argument("--fixture-ipv4")
    parser.add_argument("--goldens", type=Path,
                        help="private JSON mapping case name to PPM SHA256")
    args = parser.parse_args(argv)
    if args.fixture_ipv4 and not args.fixture_ssid:
        parser.error("--fixture-ipv4 requires --fixture-ssid")
    if args.winc_port and not 1024 <= args.winc_port <= 65535:
        parser.error("--winc-port must be 1024..65535")
    if args.attempts < 1 or args.entry_attempts < 1:
        parser.error("retry counts must be positive")
    cases = [
        c for c in all_cases()
        if (args.scope == "all" or
            (args.scope == "menus" and c.kind == "menu") or
            (args.scope == "diagnostics" and c.kind != "menu"))
        and (not args.only or any(x in c.key for x in args.only))
    ]
    if args.list:
        print(json.dumps([
            {"case": c.key, "route": c.route, "kind": c.kind,
             "skip": skip_reason(c, args)} for c in cases
        ], indent=2))
        return 0
    if not cases:
        parser.error("no selected cases")
    for key in ("qemu", "profile", "elf", "emmc", "sd", "output"):
        if getattr(args, key) is None:
            parser.error("--%s required unless --list" % key)
    for key in ("qemu", "profile", "elf", "emmc", "sd"):
        setattr(args, key, getattr(args, key).resolve(strict=True))
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    goldens = json.loads(args.goldens.read_text()) if args.goldens else {}
    report = {"scope": args.scope, "cases": {},
              "firmware_modified": False,
              "tcg": "single", "snapshot": True}
    for case in cases:
        reason = skip_reason(case, args)
        if reason:
            report["cases"][case.key] = {
                "status": "SKIPPED_DEPENDENCY_OR_SAFETY",
                "reason": reason, "route": case.route}
            continue
        for n in range(1, args.attempts + 1):
            try:
                result = run_case(args, case, n, goldens)
                result["attempt"] = n
                report["cases"][case.key] = result
                break
            except Exception as exc:
                # Private error text/trace stays in owner-local output.
                owner_only = args.output / case.key / (
                    "attempt-%d" % n)
                owner_only.mkdir(parents=True, exist_ok=True)
                (owner_only / "private-error.txt").write_text(
                    repr(exc) + "\n")
                report["cases"][case.key] = {
                    "status": "NOT_REACHED", "attempt": n,
                    "exception_type": type(exc).__name__,
                    "private_diagnostic": str(
                        (owner_only / "private-error.txt").relative_to(
                            args.output)),
                }
        args.output.joinpath("summary.json").write_text(
            json.dumps(report, indent=2) + "\n")
        print("%s: %s" % (case.key, report["cases"][case.key]["status"]),
              flush=True)
    return int(any(v["status"] in ("NOT_REACHED", "PIXEL_GOLDEN_MISMATCH")
                   for v in report["cases"].values()))


if __name__ == "__main__":
    sys.exit(main())
