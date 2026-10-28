#!/usr/bin/env python3
"""Floating DY357 keyboard + live QEMU LCD. Tk UI; independent QEMU worker.

Windows: py -3 scripts/factory_control_panel.py C:\\Casio\\OSUP.BIN --qemu ...
No pygame/Pillow required. Optionally install Pillow for smoother rendering.
The live screen is obtained by QMP pmemsave of opt-in READ-ONLY RGB565 MMIO.
Only physical matrix contact closures are sent, never fake BIOS/IPC events.
"""
import argparse
import mmap
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time

from drive_factory_menu import QMP, choose_port, connect
from lcd_qmp import capture_frame, rgb565_to_rgb888
from auto_driver import BOOT, KEYS, prepare_media, profile_with_lcd, optional_qemu_path, convert_png

# Real M4 9x8 ROM table at 0x1FFD0E14; labels not inferred from photo.
ASCII_ROWS = ("QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM")
KNOWN = [("POWER", 0x80), ("0x90", 0x90), ("DOWN", 0x91),
         ("0x92", 0x92), ("0x93", 0x93), ("0x94", 0x94),
         ("0x95", 0x95), ("0x96", 0x96), ("BOOT", 0x9c)]
LABELS = set("".join(ASCII_ROWS))
TIMESTAMP = re.compile(r"^Trace \d+:.*?/00000000([0-9a-fA-F]{8})/", re.M)
M4_400B_PATH = {
    0x1ffe3e38: "M4 event7 dispatcher selected group",
    0x1ffe4174: "M4 event7 group handler",
    0x1ffe42bc: "M4 event7 bit24 path",
    0x1ffe42c8: "M4 event7 bit24 guard allowed",
    0x1ffe4438: "M4 shared power-state writer",
    0x1ffe42fa: "M4 event10 semaphore released",
    0x1ffe4780: "M4 event10 wait entered",
    0x1ffe478a: "M4 event10 wait returned",
}

A7_MILESTONES = {
    0x60010868: "Version popup entered",
    0x600108a8: "Version popup event wait",
    0x60010910: "First menu key check",
    0x60010928: "Final menu key check",
    0x60010930: "0x94 accepted",
    0x6003a878: "TEST MENU code entered",
    0x60006240: "IPC 0x400B invoked",
    0x60006268: "IPC 0x400B returned",
    0x60057668: "Menu painter executed",
}


def original_menu_highlight(rgb):
    """Find original full-width inverse-highlight bar, or None.

    Works on both TEST MENU and its 14-row MANUAL MENU; does not depend
    on the title header color (the original menu inverts that header).
    Reads only exported RGB pixels, never guest MMIO or RAM.
    """
    if len(rgb) != 864 * 480 * 3:
        return None
    run_start, run_len = None, 0
    for y in range(25, 410):
        black = True
        for x in (610, 720, 820, 850):
            i = (864 * y + x) * 3
            if rgb[i:i+3] != b"\\x00\\x00\\x00":
                black = False
                break
        if black:
            if run_start is None:
                run_start = y
            run_len += 1
            if run_len >= 12:
                return run_start
        else:
            run_start, run_len = None, 0
    return None


def pure_rgb565_lcd(mm):
    """Read the host QMP RGB565 file through mmap, without guest writes."""
    if len(mm) != 864 * 480 * 2:
        raise ValueError("bad shared frame length")
    return rgb565_to_rgb888(mm[:])


def e2_debug_options(environment):
    """Explicit loopback-only guest debugging; completely disabled normally.

    The original-A7 diagnostic needs two independent connections so the
    factory worker can retain its QMP monitor and LCD frame thread.
    """
    ports = []
    for name in ("EXESX_E2_HMP_PORT", "EXESX_E2_GDB_PORT"):
        raw = environment.get(name, "")
        if not raw:
            ports.append(None)
            continue
        if not raw.isascii() or not raw.isdecimal():
            raise ValueError(name + " must be a decimal TCP port")
        port = int(raw)
        if not 1 <= port <= 65535:
            raise ValueError(name + " outside TCP port range")
        ports.append(port)
    hmp_port, gdb_port = ports
    if hmp_port is not None and hmp_port == gdb_port:
        raise ValueError("E2 GDB and HMP ports must differ")
    hmp = ("tcp:127.0.0.1:{},server=on,wait=off".format(hmp_port)
           if hmp_port else "none")
    gdb = (["-gdb", "tcp:127.0.0.1:{}".format(gdb_port)]
           if gdb_port else [])
    trace = ("exec,guest_errors,unimp"
             if environment.get("EXESX_E2_TRACE_I2C", "") == "1"
             else "exec")
    return hmp, gdb, trace


class EmulatorWorker(threading.Thread):
    def __init__(self, args, actions, updates):
        super().__init__(daemon=True, name="EXeSX-QEMU-monitor")
        self.args, self.actions, self.updates = args, actions, updates
        self.proc = self.qmp = self.sock = self.trace_stream = None
        self.contact_file = self.framefile = self.output = None
        self.start_time = 0
        self.mode = "off"
        self.pressed = None
        self.wait_seen = False
        self.menu_seen = False
        self.hit = set()
        self.sequence = []
        self.seq_stage = None
        self.seq_deadline = 0
        self.next_capture = 0
        self.frame_count = 0
        self.stopping = False
        self.boot_attempt = 0
        self.last_menu_keys_at = None
        self.prepared_inputs = None
        self.last_heartbeat = 0
        self.safe_down_held = False
        self.safe_down_since = None
        self.safe_down_before = None
        self.last_frame_selection = None

    def post(self, *items):
        self.updates.put(items)

    def physical(self, code):
        if self.contact_file is not None:
            self.contact_file.write_text(
                (",".join(hex(k) for k in code) if isinstance(code, tuple)
                 else ("0" if code is None else hex(code))) + "\n",
                encoding="ascii")

    def stop_vm(self):
        if self.contact_file is not None:
            try: self.physical(None)
            except OSError: pass
        if self.sock:
            try: self.sock.close()
            except OSError: pass
            self.sock = None
        if self.trace_stream:
            self.trace_stream.close()
            self.trace_stream = None
        if self.proc:
            self.proc.terminate()
            try: self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
            self.proc = None
        self.qmp = None
        if hasattr(self, "console") and self.console:
            self.console.close()
            self.console = None
        self.mode = "off"

    def start_vm(self, mode):
        self.stop_vm()
        self.boot_attempt += 1
        args = self.args
        self.chord_released = False
        self.safe_down_held = False
        self.safe_down_since = None
        self.safe_down_before = None
        self.last_frame_selection = None
        # Hold the genuine startup chord through the original M4/A7 CA05
        # handshake; 1.2 s was flaky under single-thread TCG.
        self.boot_chord_seconds = args.release_at
        self.menu_macro_fired = False
        self.last_menu_keys_at = None
        self.output = args.output_dir.resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        if self.prepared_inputs is None:
            self.post("status", "Preparing private OSUP / synthetic eMMC (first run may take time on Windows)")
            self.prepared_inputs = prepare_media(args, self.output)
        elf, emmc = self.prepared_inputs
        profile = profile_with_lcd(args.profile, self.output)
        self.post("status", "Starting QEMU: {} (no separate display window)".format(args.qemu.name))
        self.contact_file = self.output / "gui-contact.txt"
        self.framefile = self.output / "gui-lcd-rgb565.raw"
        trace = self.output / "gui-execution-private.log"
        self.physical((0x9c, 0x90) if mode in ("popup", "menu") else None)
        env = os.environ.copy()
        env.update(
            EXESX_MEMORY_PROFILE=str(profile),
            EXESX_EXPERIMENTAL_M4_BOOT="1",
            EXESX_EXPERIMENTAL_MU_IRQ="1",
            EXESX_EXPERIMENTAL_LPIT1_IRQ="1",
            # M4 LPIT0 external IRQ33 (exception 49): original 1ms touch timer.
            # Guest firmware still programs LPIT0/NVIC and posts RTOS
            # events itself. No synthetic touch messages are generated.
            EXESX_EXPERIMENTAL_M4_LPIT0_IRQ="1",
            EXESX_EXPERIMENTAL_LPTMR_IRQ="1",
            EXESX_EXPERIMENTAL_LPTMR_PCS_CLOCKS="1",
            EXESX_EXPERIMENTAL_M4_PORT_IRQ="1",
            EXESX_EXPERIMENTAL_M4_TPM0_IRQ="1",
            EXESX_EXPERIMENTAL_M4_TPM0_INPUT_MHZ="48",
            EXESX_DIAGNOSTIC_A7_TPM6_KHZ="32",
            EXESX_EXPERIMENTAL_LCD="1",
            EXESX_LCD_FRAMEBUFFER_EXPORT="1",
            EXESX_EXPERIMENTAL_DMA1_M2M="1",
            EXESX_USDHC1_EMMC="1",
            EXESX_USDHC0_SD="1" if args.sd else "0",
            EXESX_USDHC0_SD_DETECT_GPIO="1" if args.sd else "0",
            EXESX_I2C4B_REGISTER_MIRROR="1",
            EXESX_I2C40_REGISTER_MIRROR="1",
            EXESX_SNVS_DIAGNOSTIC_SECURITY_PULSES="1",
            EXESX_GPIOA_INPUT_MASK="0x808c6008",
            EXESX_GPIOB_INPUT_MASK="0xc8",
            EXESX_M4_KEY_MATRIX_FILE=str(self.contact_file.resolve()))
        # Optional source-driven ADC completion investigation. The M4 CPU
        # still issues each original SW trigger; no guest event is injected.
        for index in (0, 1):
            sample = getattr(args, "adc{}_sample".format(index), None)
            envvar = "EXESX_ADC{}_SAMPLE_RAW".format(index)
            if sample is None:
                env.pop(envvar, None)
            else:
                env[envvar] = hex(sample)
        lib = args.qemu.resolve().parent / "lib"
        if lib.is_dir():
            env["LD_LIBRARY_PATH"] = str(lib) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
        port = choose_port()
        monitor_spec, gdb_options, qemu_log_categories = e2_debug_options(env)
        # Passive guest-TB checkpoints for original M4 touch acquisition.
        # No CPU breakpoints, IRQ injections, RAM patches or touch events.
        # Keep OFF by default: logging changes TCG wall-time behavior.
        touch_trace = (
            ",0x1ffdba48+0x10,0x1ffdbcde+0x10,0x1ffdc2be+0x10"
            ",0x1ffdff08+0x10,0x1ffdff2e+0x10,0x1ffdfeea+0x10"
            ",0x1ffdbfb4+0x20,0x1ffdbfd6+0x58"
            ",0x1ffd53ba+0x20,0x1ffd6bac+0x10"
            ",0x1ffe02a0+0x10,0x1ffdc1c6+0x10"
            ",0x1ffd684a+0x4a,0x1ffd6988+0x55"
            ",0x1ffd69f2+0x40"
            if env.get("EXESX_TRACE_TOUCH_WORKER") == "1" else ""
        )
        command = [
            str(args.qemu.resolve()), "-machine", "exesx", "-m", "64M",
            "-accel", "tcg,thread={}".format(getattr(args, "tcg_thread", "single")), "-display", "none", "-serial", "none",
            "-monitor", monitor_spec, "-no-reboot",
            "-S", "-qmp", "tcp:127.0.0.1:{},server=on,wait=off".format(port),
            "-drive", "if=none,id=exesx-emmc,file={},format=raw,snapshot=on".format(emmc),
            "-device", "loader,file={},cpu-num=0".format(elf),
            "-d", qemu_log_categories, "-dfilter",
            ("0x60010868+0x140,0x6003a878+0x500,0x60006240+0x60,0x60057668+0x30,"
             "0x1ffe3e1e+0x24,0x1ffe4126+0x24,0x1ffe4174+0x18,"
             "0x1ffe42bc+0x44,0x1ffe4438+0x12,0x1ffe4776+0x18,"
             "0x1ffd635c+0x8,0x1ffd6450+0x8"
             if getattr(args, "trace_m4_400b", False) else
             "0x60010868+0x140,0x6003a878+0x500,0x60006240+0x60,0x60057668+0x30")
            + touch_trace,
            "-D", str(trace),
        ]
        command += gdb_options
        if args.sd:
            command += ["-drive", "if=none,id=exesx-sd,file={},format=raw,snapshot=on".format(args.sd)]
        self.console = (self.output / "gui-console-private.log").open("wb")
        try:
            self.proc = subprocess.Popen(command, env=env, stdout=self.console,
                                         stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        except OSError as error:
            raise RuntimeError("Cannot launch {}: {}. Check extracted DLLs / antivirus quarantine.".format(args.qemu, error)) from error
        self.post("status", "QEMU PID {} running; connecting QMP monitor".format(self.proc.pid))
        self.sock = connect(port, self.proc)
        self.qmp = QMP(self.sock)
        self.qmp.execute("cont")
        self.post("status", "QEMU PID {} running; original A7/M4 firmware started".format(self.proc.pid))
        self.trace_stream = trace.open("r", encoding="utf-8", errors="replace")
        self.start_time = time.monotonic()
        self.mode = mode
        self.wait_seen = self.menu_seen = False
        self.hit.clear()
        self.sequence.clear()
        self.seq_stage = None
        self.pressed = None
        self.next_capture = time.monotonic() + .5
        self.post("status", "Booting {} attempt {}/{} — QEMU PID {} (headless, LCD shown here)".format(
            mode, self.boot_attempt, self.args.retries, self.proc.pid))
        self.last_heartbeat = time.monotonic()
        self.frame_count = 0

    def trace_step(self):
        text = self.trace_stream.read()
        if not text:
            return
        for raw in TIMESTAMP.findall(text):
            pc = int(raw, 16)
            if (getattr(self.args, "trace_m4_400b", False) and
                    self.menu_seen and pc in M4_400B_PATH and pc not in self.hit):
                self.hit.add(pc)
                self.post("m4_400b", {"pc": "0x{:08x}".format(pc),
                                       "step": M4_400B_PATH[pc]})
            if pc in A7_MILESTONES and pc not in self.hit:
                self.hit.add(pc)
                self.post("milestone", A7_MILESTONES[pc])
                if pc == 0x600108a8:
                    self.wait_seen = True
                if pc == 0x6003a878:
                    self.menu_seen = True
        if self.mode == "menu" and self.wait_seen and not self.sequence and not self.menu_seen and not getattr(self, "menu_macro_fired", False):
            self.menu_macro_fired = True
            self.sequence = list(KEYS)
            self.seq_stage = "press"
            self.seq_deadline = time.monotonic()
            self.post("status", "Sending genuine 0x93 -> 0x93 -> 0x94")

    def sequence_step(self):
        if not self.sequence or time.monotonic() < self.seq_deadline:
            return
        if self.seq_stage == "press":
            code = int(self.sequence[0], 0)
            self.physical(code)
            self.seq_stage = "release"
            self.seq_deadline = time.monotonic() + self.args.hold
        elif self.seq_stage == "release":
            self.physical(None)
            self.sequence.pop(0)
            self.seq_stage = "press" if self.sequence else None
            self.seq_deadline = time.monotonic() + self.args.gap
            if not self.sequence and self.mode == "menu" and not self.menu_seen:
                self.last_menu_keys_at = time.monotonic()

    def frame_step(self):
        if getattr(self.args, "no_screenshots", False):
            return
        if time.monotonic() < self.next_capture or self.sequence:
            return
        # Don't disturb the sensitive original CA05 boot/key event timing
        # with a megabyte QMP dump before the dialog is ready.
        if self.mode in ("popup","menu") and not self.wait_seen:
            return
        self.next_capture = time.monotonic() + max(.20, 1 / self.args.fps)
        raw = capture_frame(self.qmp, self.framefile)
        # mmap is file-backed and read-only; no shared guest memory is modified.
        with self.framefile.open("rb") as f:
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as memory:
                rgb = pure_rgb565_lcd(memory)
        self.last_frame_selection = original_menu_highlight(rgb)
        if (self.safe_down_held and self.last_frame_selection is not None and
                self.last_frame_selection != self.safe_down_before):
            self.physical(None)
            self.safe_down_held = False
            self.safe_down_since = None
            self.post("status", "Original menu navigation confirmed: "
                      "physical DOWN moved the inverse-highlighted row "
                      "to LCD y={}".format(self.last_frame_selection))
        ppm = self.output / "gui-screen.ppm"
        staging = ppm.with_suffix(".ppm.tmp")
        staging.write_bytes(b"P6\n864 480\n255\n" + rgb)
        os.replace(staging, ppm)
        self.frame_count += 1
        self.post("frame", str(ppm), self.frame_count)

    def handle_action(self, action):
        what, value = action
        if what == "quit":
            self.stopping = True
        elif what == "start":
            self.boot_attempt = 0
            self.start_vm(value)
        elif what == "press" and self.proc and not self.sequence:
            self.pressed = value
            self.physical(value)
        elif what == "release" and self.proc and not self.sequence:
            self.pressed = None
            self.physical(None)
        elif what == "pulse" and self.proc and not self.sequence:
            self.sequence = [hex(value)]
            self.seq_stage = "press"
            self.seq_deadline = time.monotonic()
        elif what == "menu_keys" and self.proc and self.wait_seen and not self.sequence:
            self.sequence = list(KEYS)
            self.seq_stage = "press"
            self.seq_deadline = time.monotonic()
            self.post("status", "Sending 0x93 0x93 0x94 at the original event wait")
        elif what == "read_ipc" and self.proc and self.qmp:
            # Read original shared control request on the sole QMP owner thread.
            self.post("ipc", self.qmp.hmp("xp /12wx 0x2f028000"))
        elif what == "read_400b_flow" and self.proc and self.qmp:
            # Post-menu read-only M4 guard + original A7/M4 control slot.
            # Object 7 bit24 handler at 0x1FFE42BC uses
            # *(uint8_t*)0x1FFECD58 & 0x5 to decide whether to give
            # semaphore object 10 (0x1FFE42FA). Do NOT write those bits.
            guard = self.qmp.hmp("xp /1wx 0x1ffecd58")
            state = self.qmp.hmp("xp /4wx 0x1ffecd58")
            ipc = self.qmp.hmp("xp /6wx 0x2f028000")
            # HMP cpu 1 in separate calls silently resets to CPU0.
            # info registers 1 explicitly selects the actual M4 vCPU.
            self.qmp.execute("stop")
            try:
                m4_regs = self.qmp.hmp("info registers 1")
            finally:
                self.qmp.execute("cont")
            self.post("400b_flow", {"m4_guard": guard, "m4_state": state,
                                    "shared_ipc": ipc, "m4_registers": m4_regs})
        elif what == "read_adc" and self.proc and self.qmp:
            # ADC MMIO has RESERVED holes (+0x08/+0x0c), so a bulk
            # xp /16wx fails even though all the real registers are mapped.
            # Read only valid offsets; no trigger, sample, or IRQ injection.
            offsets = {"ctrl": 0x10, "stat": 0x14,
                       "ie": 0x18, "fctrl": 0x30}
            samples = {}
            for name, base in (("adc0", 0x41041000),
                               ("adc1", 0x410ad000)):
                samples[name] = {
                    reg: self.qmp.hmp("xp /1wx 0x{:x}".format(base + off))
                    for reg, off in offsets.items()
                }
            self.post("adc", samples)
        elif what == "safe_check" and self.proc:
            if 0x60057668 not in self.hit:
                self.post("status", "SAFE CHECK BLOCKED: TEST MENU painter has not executed; IPC 0x400B still pending")
            elif not self.sequence and not self.safe_down_held:
                # A short synthetic pulse was too fast under single-thread
                # TCG. Hold REAL M4 electrical contact until the firmware
                # paints a different selected row, then release in frame_step.
                if self.frame_count == 0 or getattr(self.args, "no_screenshots", False):
                    self.post("status", "Safe navigation requires a painted LCD frame")
                else:
                    self.safe_down_before = self.last_frame_selection
                    self.safe_down_held = True
                    self.safe_down_since = time.monotonic()
                    self.physical(0x91)
                    self.post("status", "Safe navigation: holding genuine M4 DOWN "
                              "until LCD selection moves (bounded 4.5s)")
        elif what == "screenshot" and self.proc:
            frame = self.output / "gui-screen.ppm"
            if frame.exists():
                stamped = self.output / "manual-lcd-{}.png".format(int(time.time()))
                convert_png(frame, stamped)
                self.post("status", "Saved {}".format(stamped.name))
        elif what == "shutdown":
            self.stop_vm()
            self.post("status", "QEMU stopped")

    def run(self):
        while not self.stopping:
            try:
                try:
                    command = self.actions.get(timeout=.02)
                    self.handle_action(command)
                except queue.Empty:
                    pass
                if self.proc and self.proc.poll() is not None:
                    self.post("status", "QEMU exited unexpectedly: code {}".format(self.proc.returncode))
                    self.stop_vm()
                if self.proc:
                    if time.monotonic() - self.last_heartbeat >= 3.0:
                        self.last_heartbeat = time.monotonic()
                        age = int(self.last_heartbeat - self.start_time)
                        step = ("original A7 event-wait seen" if self.wait_seen else
                                "waiting for original A7 dialog")
                        self.post("status", "QEMU PID {} alive ({} s); {}. {} frames.".format(
                            self.proc.pid, age, step, self.frame_count))
                    if (self.mode in ("popup","menu") and not self.chord_released
                            and time.monotonic() - self.start_time >= self.boot_chord_seconds):
                        self.physical(None)
                        self.chord_released = True
                    self.trace_step()
                    self.sequence_step()
                    self.frame_step()
                    if (self.safe_down_held and self.safe_down_since is not None and
                            time.monotonic() - self.safe_down_since > 4.5):
                        self.physical(None)
                        self.safe_down_held = False
                        self.safe_down_since = None
                        self.post("status", "Original DOWN timed out without a "
                                  "confirmed selected-row change")
                    if (self.mode in ("popup", "menu") and
                            ((not self.wait_seen and
                              time.monotonic() - self.start_time > self.args.retry_after) or
                             (self.last_menu_keys_at and not self.menu_seen and
                              time.monotonic() - self.last_menu_keys_at > 4))):
                        if self.boot_attempt < self.args.retries:
                            old_mode = self.mode
                            self.post("status", "Retrying original cold boot; prior attempt did not reach expected guest PC")
                            self.start_vm(old_mode)
                        else:
                            self.post("status", "No native dialog/menu after {} boots; leaving QEMU running for manual diagnosis".format(self.args.retries))
                            self.mode = "manual"
            except Exception as exc:
                self.post("status", "Worker error: {}: {}".format(type(exc).__name__, exc))
                self.stop_vm()
        self.stop_vm()


def headless_check(args):
    """Run the same worker as Tk, without a display server or UI."""
    actions, updates = queue.Queue(), queue.Queue()
    worker = EmulatorWorker(args, actions, updates)
    worker.start()
    actions.put(("start", args.check_mode))
    deadline = time.monotonic() + args.check_seconds
    saw_process = False
    saw_monitor = False
    try:
        while time.monotonic() < deadline:
            if worker.proc and worker.proc.poll() is None:
                saw_process = True
            try:
                event = updates.get(timeout=.4)
            except queue.Empty:
                continue
            if event[0] in ("status", "milestone"):
                print("[{}] {}".format(event[0], event[1]), flush=True)
                if event[0] == "status" and ("original A7/M4 firmware started" in event[1] or
                                            "Booting " in event[1] and "QEMU PID" in event[1]):
                    saw_monitor = True
                if event[0] == "status" and ("Worker error:" in event[1] or
                                             "QEMU exited unexpectedly" in event[1]):
                    break
        print("HEADLESS RESULT: QEMU spawned={}, QMP ready={}, "
              "A7 dialog wait={}, factory menu={}, frames={}".format(
                  saw_process, saw_monitor, worker.wait_seen,
                  worker.menu_seen, worker.frame_count), flush=True)
        if worker.output:
            print("Private console:", worker.output / "gui-console-private.log", flush=True)
            print("Private trace:", worker.output / "gui-execution-private.log", flush=True)
        return 0 if saw_process and saw_monitor else 2
    finally:
        actions.put(("quit", None))
        worker.join(timeout=10)


def show_window(args):
    import tkinter as tk
    from tkinter import ttk
    root = tk.Tk()
    root.title("EXeSX - Floating Casio keyboard / TEST MENU")
    root.geometry("995x780")
    root.attributes("-topmost", True)
    actions, updates = queue.Queue(), queue.Queue()
    worker = EmulatorWorker(args, actions, updates)
    worker.start()
    frame = ttk.Frame(root, padding=8)
    frame.pack(fill="both", expand=True)
    controls = ttk.Frame(frame)
    controls.pack(fill="x")
    def cmd(mode):
        actions.put(("start", mode))
    ttk.Button(controls, text="POWER / NORMAL", command=lambda:cmd("normal")).pack(side="left")
    ttk.Button(controls, text="Version popup [9C+90]", command=lambda:cmd("popup")).pack(side="left")
    ttk.Button(controls, text="AUTO TEST MENU [93 93 94]", command=lambda:cmd("menu")).pack(side="left")
    ttk.Button(controls, text="Manual 93→93→94", command=lambda:actions.put(("menu_keys",None))).pack(side="left")
    ttk.Button(controls, text="Safe DOWN check", command=lambda:actions.put(("safe_check",None))).pack(side="left")
    ttk.Button(controls, text="Save screenshot", command=lambda:actions.put(("screenshot", None))).pack(side="left")
    ttk.Button(controls, text="Stop", command=lambda:actions.put(("shutdown", None))).pack(side="left")
    status = tk.StringVar(value="Choose a boot macro. All key contacts are original ROM codes.")
    ttk.Label(frame, textvariable=status).pack(anchor="w", pady=(5,2))
    screen = tk.Label(frame, bg="#181818", fg="white", text="LCD frame appears here\n864 x 480", width=96, height=30)
    screen.pack(pady=3, fill="x")
    screen.photo = None
    board = tk.Frame(frame, bg="#171717", padx=9, pady=9)
    board.pack(fill="both", expand=True)
    def make_key(parent, label, key, width=6):
        b = tk.Button(parent, text=label, width=width, height=2,
                      bg="#343434", fg="#ffffff", activebackground="#686868",
                      activeforeground="white", relief="raised", bd=2)
        b.bind("<ButtonPress-1>", lambda e,k=key:actions.put(("press",k)))
        b.bind("<ButtonRelease-1>", lambda e,k=key:actions.put(("release",k)))
        b.pack(side="left", padx=2, pady=2)
        return b
    make_row = lambda: tk.Frame(board, bg="#171717")
    row = make_row();row.pack(anchor="w")
    for label, code in KNOWN:
        make_key(row, label, code, width=7)
    for i, letters in enumerate(ASCII_ROWS):
        row = make_row(); row.pack(anchor="w", padx=(i*25,0))
        for label in letters:
            make_key(row, label, ord(label.lower()), width=6)
    row=make_row();row.pack(anchor="w")
    for label, code in [("0xC0",0xc0), ("0xC1",0xc1), ("0xC2",0xc2),
                        ("0xC3",0xc3), ("0xC4",0xc4), ("0xC5",0xc5),
                        ("0xC6",0xc6), ("0xD2",0xd2)]:
        make_key(row,label,code,width=7)
    ttk.Label(frame, text="Hold mouse button to hold a physical key; release to send key-up. "
                          "Codes 0x90-0x96 are shown numerically where the printed legend "
                          "is not independently verified. No SD FORMAT/WRITE keys are automated.",
              wraplength=980).pack(anchor="w", pady=(4,0))
    def keyboard_down(event):
        if event.char and event.char.lower() in "".join(ASCII_ROWS).lower():
            actions.put(("press", ord(event.char.lower())))
    def keyboard_up(event):
        if event.char and event.char.lower() in "".join(ASCII_ROWS).lower():
            actions.put(("release", None))
    root.bind("<KeyPress>", keyboard_down)
    root.bind("<KeyRelease>", keyboard_up)
    def poll():
        # All Tk operations stay on main thread; worker owns QEMU and QMP.
        try:
            while True:
                event = updates.get_nowait()
                if event[0] == "frame":
                    try:
                        img = tk.PhotoImage(file=event[1])
                        screen.configure(image=img, text="")
                        screen.photo = img
                    except tk.TclError as e:
                        status.set("Frame loading: {}".format(e))
                elif event[0] in ("milestone","status"):
                    status.set(event[1])
        except queue.Empty:
            pass
        root.after(110, poll)
    def close():
        actions.put(("quit", None))
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", close)
    poll()
    root.mainloop()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("osup", nargs="?", type=Path, help="Original OSUP; prepared locally")
    p.add_argument("--elf", type=Path)
    p.add_argument("--emmc", type=Path)
    p.add_argument("--qemu", type=Path)
    p.add_argument("--sd", type=Path, help="Disposable image; all writes snapshot-on")
    p.add_argument("--profile", type=Path)
    p.add_argument("--output-dir", type=Path, default=Path("private/floating-keyboard"))
    p.add_argument("--fps", type=float, default=2., help="Host LCD refresh limit, 0.1-4 advised")
    p.add_argument("--no-screenshots", action="store_true",
                   help="Disable all QMP framebuffer reads and image generation during boot")
    p.add_argument("--tcg-thread", choices=("single", "multi"), default="single",
                   help="Compare A7/M4 interprocessor scheduling without guest patching")
    p.add_argument("--adc0-sample", type=lambda s:int(s,0), default=None,
                   help="Explicit 16-bit ADC0 result for opt-in original M4 IRQ experiment")
    p.add_argument("--adc1-sample", type=lambda s:int(s,0), default=None,
                   help="Explicit 16-bit ADC1 result for opt-in original M4 IRQ experiment")
    p.add_argument("--trace-m4-400b", action="store_true",
                   help="Trace original M4 event7 semaphore wait and MU callback")
    p.add_argument("--hold", type=float, default=.080)
    p.add_argument("--gap", type=float, default=.060)
    p.add_argument("--release-at", type=float, default=4.0)
    p.add_argument("--retries", type=int, default=3, help="Fresh boot retries on missed original firmware checkpoints")
    p.add_argument("--retry-after", type=float, default=24, help="Host seconds allowed for the A7 version-event wait")
    p.add_argument("--headless-check", action="store_true",
                   help="Test the exact floating keyboard/QEMU worker without Tk")
    p.add_argument("--check-mode", choices=("normal", "popup", "menu"), default="menu")
    p.add_argument("--check-seconds", type=float, default=25,
                   help="Wall-time duration for headless worker verification")
    a = p.parse_args()
    a.qemu = optional_qemu_path(a.qemu)
    if a.profile is None:
        a.profile = Path(__file__).resolve().parent.parent / "profiles/imx7ulp-early-boot.ini"
    a.profile = a.profile.resolve()
    if not a.profile.exists():
        p.error("Profile does not exist")
    if not a.osup and not (a.elf and a.emmc):
        p.error("OSUP or --elf and --emmc required")
    if a.sd and (not a.sd.is_file() or a.sd.stat().st_size < 2 * 1024**3):
        p.error("SD must be disposable raw image >=2GiB")
    if any(sample is not None and not (0 <= sample <= 0xffff)
           for sample in (a.adc0_sample, a.adc1_sample)):
        p.error("ADC raw sample must be 0..0xffff")
    if (a.fps <= 0 or a.hold <= 0 or a.release_at < 0 or a.gap < 0 or
            a.retries < 1 or a.retry_after <= 0 or a.check_seconds <= 0):
        p.error("Invalid timing")
    if a.headless_check:
        return headless_check(a)
    show_window(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
