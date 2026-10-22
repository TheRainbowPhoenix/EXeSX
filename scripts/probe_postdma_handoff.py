#!/usr/bin/env python3
"""Private, read-only original A7 boot milestones via QEMU GDB RSP.

Never sends firmware bytes, alters RAM, forces an IRQ or jumps to OS. Captures
only selected CPU0 registers and status addresses; keep logs/results private.
"""
import json
from pathlib import Path
import re
import socket
import subprocess
import time

MILESTONES = {
    0x60048878: "nested_boot_service",
    0x600488a0: "timer25_return",
    0x600488b8: "timer125_request",
    0x600488e0: "nested_service_return",
    0x60048918: "outer_elapsed_check",
    0x60048924: "outer_retry_decision",
    0x60048938: "outer_timeout_branch",
    0x601b82bc: "dma_csr_poll",
    0x601b4504: "dma_csr_return",
    0x601b450c: "dma_wait_exit",
    0x6004a2b0: "startup_service_return",
    0x6004a2cc: "callback_loop",
    0x60049bcc: "callback_dispatcher",
    0x60049c04: "callback_blx",
    0x60400000: "os_trampoline",
    0x605e3ad0: "os_main_entry",
}
STATE = {
    "component_bits": (0x622e6fc4, 4),
    "os_callback_recorded": (0x6232da18, 4),
    "callback_cache": (0x622e6fbc, 4),
    "service_ready_byte": (0x62413241, 1),
    "timer_wait": (0x6232e35c, 4),
    "sdhc_argument": (0x40380008, 4),
}


def encode_packet(payload):
    b = payload.encode("ascii")
    return b"$" + b + b"#" + f"{sum(b) & 255:02x}".encode()


def decode_registers(hex_payload):
    """QEMU ARM remote-g packet: R0..R15, 32-bit little-endian."""
    if len(hex_payload) < 128:
        raise ValueError("short ARM RSP register reply")
    return {f"r{i}": int.from_bytes(bytes.fromhex(hex_payload[i*8:i*8+8]), "little")
            for i in range(16)}


class RSP:
    def __init__(self, conn):
        self.conn = conn

    def receive(self, seconds=2):
        deadline = time.monotonic() + seconds
        in_packet = False
        payload = bytearray()
        while time.monotonic() < deadline:
            self.conn.settimeout(min(0.35, max(.01, deadline - time.monotonic())))
            try:
                b = self.conn.recv(1)
            except socket.timeout:
                continue
            if not b:
                raise ConnectionError("QEMU GDB stub closed")
            if not in_packet:
                if b == b"$":
                    in_packet = True
                continue
            if b == b"#":
                checksum = self.conn.recv(2)
                if len(checksum) != 2 or int(checksum, 16) != (sum(payload) & 255):
                    self.conn.sendall(b"-")
                    raise ValueError("invalid GDB RSP checksum")
                self.conn.sendall(b"+")
                return payload.decode("ascii")
            payload.extend(b)
        raise TimeoutError("waiting for RSP stop/reply")

    def command(self, payload):
        self.conn.sendall(encode_packet(payload))
        return self.receive(4)

    def memory(self, addr, count):
        response = self.command(f"m{addr:x},{count:x}")
        if response.startswith("E"):
            return None
        return int.from_bytes(bytes.fromhex(response), "little")


def choose_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def run_probe(command, environment, seconds, output_dir, milestones=MILESTONES,
              repeat_retry=5):
    """Start paused native QEMU; remove each guest breakpoint after first hit."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    port = choose_port()
    cmd = list(command) + ["-S", "-gdb", f"tcp:127.0.0.1:{port}"]
    report = {"model": "original-firmware/private", "timeout_seconds": seconds,
              "breakpoints": [dict(pc=hex(pc), name=name)
                              for pc, name in milestones.items()],
              "hits": [], "final_cpu0": None,
              "caveat": "One-shot guest-PC breakpoints; absence of a hit is bounded only. No RAM, IRQ or firmware modifications."}
    started = time.monotonic()
    with (out / "qemu-console-private.log").open("w") as console:
        proc = subprocess.Popen(cmd, env=environment, stdout=console,
                                stderr=subprocess.STDOUT)
        conn = None
        try:
            while time.monotonic() - started < 10:
                if proc.poll() is not None:
                    raise RuntimeError("QEMU exited before GDB connection")
                try:
                    conn = socket.create_connection(("127.0.0.1", port),
                                                    timeout=0.4)
                    break
                except OSError:
                    time.sleep(.1)
            if conn is None:
                raise TimeoutError("QEMU GDB socket not ready")
            rsp = RSP(conn)
            rsp.command("?")
            if rsp.command("Hg1") != "OK":  # CPU0 A7 register selection
                raise RuntimeError("cannot select A7 CPU0")
            if rsp.command("Hc-1") != "OK":  # resume both QEMU cores
                raise RuntimeError("cannot continue both cores")
            for pc in milestones:
                if rsp.command(f"Z0,{pc:x},4") != "OK":
                    raise RuntimeError(f"could not set breakpoint {pc:#x}")
            deadline = time.monotonic() + seconds
            rsp.conn.sendall(encode_packet("c"))
            while time.monotonic() < deadline and proc.poll() is None:
                try:
                    stopped = rsp.receive(min(1.25, deadline-time.monotonic()))
                except TimeoutError:
                    continue
                if not stopped.startswith("T") or not re.search(r"thread:0*1;", stopped):
                    report["other_stop"] = stopped[:100]
                    break
                regs = decode_registers(rsp.command("g"))
                pc = regs["r15"]
                entry = {"pc": hex(pc), "name": milestones.get(pc, "unexpected"),
                         "r0": hex(regs["r0"]), "r4": hex(regs["r4"]),
                         "lr": hex(regs["r14"]),
                         "seconds_elapsed": round(time.monotonic()-started, 3),
                         "state": {k: (None if (v := rsp.memory(addr, length)) is None else hex(v))
                                   for k, (addr, length) in STATE.items()}}
                report["hits"].append(entry)
                print("HIT", entry["name"], entry["pc"],
                      "R0", entry["r0"], flush=True)
                if pc not in milestones:
                    break
                if rsp.command(f"z0,{pc:x},4") != "OK":
                    raise RuntimeError("failed to remove guest breakpoint")
                # Follow repeated outer BIOS service retries without patching RAM.
                # Step once past the breakpoint before rearming it, otherwise
                # the stub would immediately stop at the same instruction.
                if pc == 0x60048924 and sum(h["pc"] == hex(pc) for h in report["hits"]) < repeat_retry:
                    rsp.conn.sendall(encode_packet("s"))
                    stepped = rsp.receive(4)
                    if not stepped.startswith("T") or not re.search(r"thread:0*1;", stepped):
                        raise RuntimeError("CPU0 retry single-step did not complete")
                    stepped_pc = decode_registers(rsp.command("g"))["r15"]
                    if stepped_pc == pc or rsp.command(f"Z0,{pc:x},4") != "OK":
                        raise RuntimeError("unable to re-arm BIOS retry breakpoint")
                rsp.conn.sendall(encode_packet("c"))
            # Sample the CPU on interrupt; don't mistake the last new translated
            # TB address in -d in_asm for the CPU's current program counter.
            if proc.poll() is None:
                conn.sendall(b"\x03")
                try:
                    stop = rsp.receive(3)
                    if stop.startswith("T"):
                        regs = decode_registers(rsp.command("g"))
                        report["final_cpu0"] = {
                            "pc": hex(regs["r15"]), "lr": hex(regs["r14"]),
                            "r0": hex(regs["r0"]),
                            "state": {k: (None if (v := rsp.memory(a, n)) is None else hex(v))
                                      for k, (a, n) in STATE.items()}}
                except (TimeoutError, OSError, ValueError):
                    pass
        finally:
            if conn:
                conn.close()
            proc.kill()
            proc.wait(timeout=4)
            (out / "handoff-summary.json").write_text(
                json.dumps(report, indent=2) + "\n")
    return report
