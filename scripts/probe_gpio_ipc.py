#!/usr/bin/env python3
"""Snapshot-checked single-input M4 GPIO/IPC differential, against private firmware.

Only a single PDIR read at M4 Thumb PC 0x1FFD85C6 is substituted per case.
Never patches ROM, IPC, a QEMU device model, or an actual device. Both
opt-in I2C diagnostic register mirrors are used; results are not hardware truth.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
from fuzz_mmio import RSP, QMP, make_qcow2

SCAN = 0x1FFD85C6
ERROR_STORE = 0x1FFD5B60
ALTERNATE_STORE = 0x1FFD5B68
A7_COMPARE = 0x601786D4
A7_HOLD = 0x60179A7C
TARGETS = {"code9c": 0x00080000, "code90": 0x00800000}


def read32(rsp, address):
    raw = rsp.request(f"m{address:x},4")
    if len(raw) != 8 or any(c not in "0123456789abcdefABCDEF" for c in raw):
        raise RuntimeError(f"GDB read failed at {address:#x}: {raw}")
    return int.from_bytes(bytes.fromhex(raw), "little")


def wait_for_socket(address, process, unix=False):
    for _ in range(400):
        if process.poll() is not None:
            raise RuntimeError(f"QEMU exited early ({process.returncode})")
        try:
            if unix:
                sock = socket.socket(socket.AF_UNIX)
                sock.connect(address)
            else:
                sock = socket.create_connection(address, 0.15)
            return sock
        except OSError:
            time.sleep(0.025)
    raise TimeoutError("QEMU debugger/monitor unavailable")


class Session:
    def __init__(self, args):
        self.args = args

    def __enter__(self):
        args = self.args
        self.tmp = tempfile.TemporaryDirectory(prefix="exesx-gpio-")
        scratch = Path(self.tmp.name)
        probe_socket = socket.socket()
        probe_socket.bind(("127.0.0.1", 0))
        port = probe_socket.getsockname()[1]
        probe_socket.close()
        qcow = scratch / "rollback.qcow2"
        make_qcow2(qcow)
        qemu = args.qemu.resolve()
        env = os.environ.copy()
        env.update(EXESX_MEMORY_PROFILE=str(args.profile.resolve()),
                   EXESX_EXPERIMENTAL_M4_BOOT="1",
                   EXESX_I2C4B_REGISTER_MIRROR="1",
                   EXESX_I2C40_REGISTER_MIRROR="1")
        env.pop("EXESX_I2C4B_REPLY_HEX", None)
        lib = qemu.parent / "lib"
        if lib.is_dir():
            env["LD_LIBRARY_PATH"] = str(lib) + ":" + env.get("LD_LIBRARY_PATH", "")
        cmd = [str(qemu), "-machine", "exesx", "-m", "64M", "-accel", "tcg",
               "-display", "none", "-serial", "none", "-S",
               "-gdb", f"tcp:127.0.0.1:{port}",
               "-qmp", f"unix:{scratch}/qmp.sock,server=on,wait=off",
               "-monitor", "none", "-no-reboot",
               "-device", f"loader,file={args.elf.resolve()},cpu-num=0",
               "-drive", f"file={qcow},if=none,format=qcow2,id=vmstate",
               "-d", "guest_errors,int", "-D", str((args.out / "qemu.log").resolve())]
        self.console = (args.out / "qemu-console.log").open("w")
        self.proc = subprocess.Popen(cmd, env=env, stdout=self.console,
                                     stderr=subprocess.STDOUT)
        try:
            self.gdb_socket = wait_for_socket(("127.0.0.1", port), self.proc)
            self.rsp = RSP(self.gdb_socket)
            self.rsp.request("qSupported:multiprocess+;qXfer:features:read+")
            self.rsp.request("?")
            self.qmp_socket = wait_for_socket(str(scratch / "qmp.sock"), self.proc, True)
            self.qmp = QMP(self.qmp_socket)
            for pc in (SCAN, ERROR_STORE, ALTERNATE_STORE):
                if self.rsp.request(f"Z0,{pc:x},2") != "OK":
                    raise RuntimeError(f"Breakpoint rejected at {pc:#x}")
            if not self.rsp.request("c").startswith("T05thread:p01.02;"):
                raise RuntimeError("Expected Cortex-M4 input scan breakpoint")
            self.select_m4()
            if self.rsp.reg(15) != SCAN:
                raise RuntimeError("Unexpected first M4 PC")
            self.checkpoint()
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        for name in ("gdb_socket", "qmp_socket"):
            sock = getattr(self, name, None)
            if sock:
                sock.close()
        if hasattr(self, "proc") and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        if hasattr(self, "console"):
            self.console.close()
        self.tmp.cleanup()

    def select_m4(self):
        if self.rsp.request("Hgp01.02") != "OK":
            raise RuntimeError("Cannot select M4 registers")

    def select_a7(self):
        if self.rsp.request("Hgp01.01") != "OK":
            raise RuntimeError("Cannot select A7 registers")

    def state(self):
        self.select_m4()
        return {"pc": self.rsp.reg(15), "sp": self.rsp.reg(13),
                "pdir": read32(self.rsp, 0x4100F010),
                "pdor": read32(self.rsp, 0x4100F000),
                "ipc": read32(self.rsp, 0x2F028000)}

    def checkpoint(self):
        self.saved = self.state()
        self.qmp.hmp("savevm before_gpio")
        if "before_gpio" not in self.qmp.hmp("info snapshots"):
            raise RuntimeError("Missing QEMU VM snapshot")
        # Verify a deliberate GPIO MMIO mutation and an M4 CPU PC change both rollback.
        changed = self.saved["pdor"] ^ 1
        data = changed.to_bytes(4, "little").hex()
        if self.rsp.request("M4100f000,4:" + data) != "OK":
            raise RuntimeError("Cannot dirty GPIO MMIO for rollback check")
        if read32(self.rsp, 0x4100F000) != changed:
            raise RuntimeError("GPIO dirty readback failed")
        self.rsp.setreg(15, SCAN + 2)
        self.restore()

    def restore(self):
        self.qmp.hmp("loadvm before_gpio")
        actual = self.state()
        if actual != self.saved:
            raise RuntimeError(f"Unsafe snapshot: {actual} != {self.saved}")

    def trial(self, case, max_scan_hits=16):
        self.restore()
        source, state = case.split(":", 1)
        if source not in TARGETS or state not in ("high", "low", "pass"):
            raise ValueError("Use code9c|code90 : high|low|pass")
        target = TARGETS[source]
        events = []
        for _ in range(max_scan_hits):
            self.select_m4()
            if self.rsp.reg(15) != SCAN:
                raise RuntimeError("Unexpected M4 PC before GPIO read")
            r6, r5, r8 = [self.rsp.reg(reg) for reg in (6, 5, 8)]
            if r6 not in (0x4100F000, 0x4100F040,
                          0x400F0000, 0x400F0040, 0x400F0080, 0x400F00C0):
                raise RuntimeError(f"Unexpected GPIO bank {r6:#x}")
            pdir = read32(self.rsp, r6 + 0x10)
            pddr = read32(self.rsp, r6 + 0x14)
            valid_input = r8 & r5 & ~pddr & 0xFFFFFFFF
            if r8 == target:
                if valid_input != target:
                    raise RuntimeError("Target is not a firmware-selected GPIO input")
                value = (pdir | target if state == "high" else
                         pdir & ~target if state == "low" else pdir)
            else:
                value = pdir  # replay original value while approaching the second scan
            events.append({"pc": hex(SCAN), "bit": hex(r8), "gpio_base": hex(r6),
                           "pdir": hex(pdir), "pddr": hex(pddr),
                           "substituted_read": hex(value)})
            self.rsp.setreg(0, value)
            self.rsp.setreg(15, SCAN + 2)  # Skip only the verified 16-bit Thumb LDR.
            if r8 == target and self.rsp.request(f"z0,{SCAN:x},2") != "OK":
                raise RuntimeError("Could not disarm M4 input breakpoint")
            stop = self.rsp.request("c")
            if not stop.startswith("T05thread:p01.02;"):
                raise RuntimeError(f"Unexpected M4 continuation {stop}")
            if r8 == target:
                if self.rsp.request(f"Z0,{SCAN:x},2") != "OK":
                    raise RuntimeError("Could not rearm input breakpoint")
                break
        else:
            raise RuntimeError("Target input scan not reached within bounded iterations")
        self.select_m4()
        store_pc = self.rsp.reg(15)
        if store_pc not in (ERROR_STORE, ALTERNATE_STORE):
            raise RuntimeError(f"No actual M4 IPC writer observed: {store_pc:#x}")
        ipc_before = read32(self.rsp, 0x2F028000)
        if self.rsp.request(f"z0,{store_pc:x},2") != "OK":
            raise RuntimeError("Could not step M4 IPC writer")
        self.rsp.request("s")  # Actual guest STR writes the mailbox; host does NOT.
        ipc_after = read32(self.rsp, 0x2F028000)
        if self.rsp.request(f"Z0,{store_pc:x},2") != "OK":
            raise RuntimeError("Could not restore M4 IPC breakpoint")
        if self.rsp.request(f"Z0,{A7_COMPARE:x},4") != "OK":
            raise RuntimeError("Cannot break on A7 IPC comparison")
        stop = self.rsp.request("c")
        if not stop.startswith("T05thread:p01.01;"):
            raise RuntimeError(f"Expected A7 IPC compare: {stop}")
        self.select_a7()
        if self.rsp.reg(15) != A7_COMPARE:
            raise RuntimeError("A7 did not reach expected IPC compare")
        lhs, rhs = self.rsp.reg(0), self.rsp.reg(1)
        self.rsp.request("s")  # Let actual ARM BNE decide whether to skip diagnostic handler.
        next_pc = self.rsp.reg(15)
        if self.rsp.request(f"z0,{A7_COMPARE:x},4") != "OK":
            raise RuntimeError("Could not disarm A7 breakpoint")
        self.qmp.command("cont")
        time.sleep(self.args.follow_seconds)
        self.qmp.command("stop")
        self.select_a7()
        later_a7 = self.rsp.reg(15)
        a7_r4 = self.rsp.reg(4)
        callback_address = a7_r4 + 0x8c if later_a7 == A7_HOLD else None
        callback_value = read32(self.rsp, callback_address) if callback_address is not None else None
        self.select_m4()
        later_m4 = self.rsp.reg(15)
        return {"case": case, "read_interceptions": events,
                "m4_store_instruction": hex(store_pc),
                "ipc_before": hex(ipc_before), "ipc_after": hex(ipc_after),
                "a7_compare_pc": hex(A7_COMPARE),
                "a7_lhs": hex(lhs), "a7_rhs": hex(rhs),
                "a7_next_pc_after_real_bne": hex(next_pc),
                "a7_pc_after_follow_up": hex(later_a7),
                "m4_pc_after_follow_up": hex(later_m4),
                "a7_in_holding_loop": later_a7 == A7_HOLD,
                "a7_r4_at_sample": hex(a7_r4),
                "a7_hold_callback_slot": hex(callback_address) if callback_address is not None else None,
                "a7_hold_callback_value": hex(callback_value) if callback_value is not None else None,
                "firmware_boot_verified": False, "physical_gpio_state_known": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("elf", type=Path, help="user-owned, locally extracted private A7 ELF")
    parser.add_argument("--qemu", type=Path, default=Path("build/qemu-system-arm"))
    parser.add_argument("--profile", type=Path, default=Path("profiles/imx7ulp-early-boot.ini"))
    parser.add_argument("--out", type=Path, default=Path("private/gpio-ipc-differential"))
    parser.add_argument("--follow-seconds", type=float, default=0.25)
    parser.add_argument("--cases", default="code9c:pass,code9c:low,code9c:high,code90:high")
    args = parser.parse_args()
    if not 0.05 <= args.follow_seconds <= 5:
        parser.error("Follow-up observation must be 0.05 to 5 seconds")
    for path in (args.elf, args.qemu, args.profile):
        if not path.is_file():
            parser.error(f"Missing required file: {path}")
    cases = args.cases.split(",")
    if not cases or any(":" not in case for case in cases):
        parser.error("Expected comma-separated code9c:pass,code9c:high,code90:high")
    args.out.mkdir(parents=True, exist_ok=True)
    with Session(args) as guest:
        results = []
        for case in cases:
            row = guest.trial(case)
            results.append(row)
            print(json.dumps({k: v for k, v in row.items() if k != "read_interceptions"}), flush=True)
        report = {"source": str(args.elf.resolve()),
                  "snapshot_restores_cpu_and_dirtied_gpio": True,
                  "source_checkpoint": {k: hex(v) for k, v in guest.saved.items()},
                  "diagnostic_i2c_mirrors": ["0x4b", "0x40"],
                  "results": results,
                  "note": "Hypothetical single GPIO input transition, not real board wiring or boot"}
    path = args.out / "results.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    print("Saved private results:", path)


if __name__ == "__main__":
    main()
