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


def pure_rgb565_lcd(mm):
    """Read the host QMP RGB565 file through mmap, without guest writes."""
    if len(mm) != 864 * 480 * 2:
        raise ValueError("bad shared frame length")
    return rgb565_to_rgb888(mm[:])


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
        args = self.args
        self.output = args.output_dir.resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        elf, emmc = prepare_media(args, self.output)
        profile = profile_with_lcd(args.profile, self.output)
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
        lib = args.qemu.resolve().parent / "lib"
        if lib.is_dir():
            env["LD_LIBRARY_PATH"] = str(lib) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
        port = choose_port()
        command = [
            str(args.qemu.resolve()), "-machine", "exesx", "-m", "64M",
            "-accel", "tcg", "-display", "none", "-serial", "none",
            "-monitor", "none", "-no-reboot",
            "-S", "-qmp", "tcp:127.0.0.1:{},server=on,wait=off".format(port),
            "-drive", "if=none,id=exesx-emmc,file={},format=raw,snapshot=on".format(emmc),
            "-device", "loader,file={},cpu-num=0".format(elf),
            "-d", "exec", "-dfilter",
            "0x60010868+0x140,0x6003a878+0x500,0x60006240+0x60,0x60057668+0x30",
            "-D", str(trace),
        ]
        if args.sd:
            command += ["-drive", "if=none,id=exesx-sd,file={},format=raw,snapshot=on".format(args.sd)]
        self.console = (self.output / "gui-console-private.log").open("wb")
        self.proc = subprocess.Popen(command, env=env, stdout=self.console,
                                     stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        self.sock = connect(port, self.proc)
        self.qmp = QMP(self.sock)
        self.qmp.execute("cont")
        self.trace_stream = trace.open("r", encoding="utf-8", errors="replace")
        self.start_time = time.monotonic()
        self.mode = mode
        self.wait_seen = self.menu_seen = False
        self.hit.clear()
        self.sequence.clear()
        self.seq_stage = None
        self.pressed = None
        self.next_capture = time.monotonic() + .5
        self.post("status", "Booting: {}".format(mode))
        self.frame_count = 0

    def trace_step(self):
        text = self.trace_stream.read()
        if not text:
            return
        for raw in TIMESTAMP.findall(text):
            pc = int(raw, 16)
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

    def frame_step(self):
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
            self.chord_released = False
            self.menu_macro_fired = False
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
        elif what == "safe_check" and self.proc:
            if 0x60057668 not in self.hit:
                self.post("status", "SAFE CHECK BLOCKED: TEST MENU painter has not executed; IPC 0x400B still pending")
            elif not self.sequence:
                # Navigation only: original M4 code 0x91 is DOWN.
                # No SD read/write/FORMAT option is activated automatically.
                self.sequence = ["0x91"]
                self.seq_stage = "press"
                self.seq_deadline = time.monotonic()
                self.post("status", "Safe navigation: DOWN key only")
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
                    if (self.mode in ("popup","menu") and not self.chord_released
                            and time.monotonic() - self.start_time >= self.args.release_at):
                        self.physical(None)
                        self.chord_released = True
                    self.trace_step()
                    self.sequence_step()
                    self.frame_step()
            except Exception as exc:
                self.post("status", "Worker error: {}: {}".format(type(exc).__name__, exc))
                self.stop_vm()
        self.stop_vm()


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
    p.add_argument("--fps", type=float, default=2., help="Host LCD refresh limit, 1-4 advised")
    p.add_argument("--hold", type=float, default=.060)
    p.add_argument("--gap", type=float, default=.025)
    p.add_argument("--release-at", type=float, default=1.2)
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
    if a.fps <= 0 or a.hold <= 0 or a.release_at < 0 or a.gap < 0:
        p.error("Invalid timing")
    show_window(a)


if __name__ == "__main__":
    main()
