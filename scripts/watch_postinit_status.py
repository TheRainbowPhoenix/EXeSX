#!/usr/bin/env python3
"""Attach to paused QEMU gdbstub, set post-initialization A7 RAM write watch.

QEMU must be launched with -S -gdb tcp:127.0.0.1:1234 and a *private*
user-provided firmware loaded locally. Does not modify RAM, flash or ROM.
Avoids confusing the BIOS's startup BSS zeroer with a later status writer.
Default observation runs for 12 wall-clock seconds; metadata-only output.
"""
import argparse
import json
import socket
import struct
import time


def packet(sock):
    while sock.recv(1) != b"$":
        pass
    result = bytearray()
    while True:
        ch = sock.recv(1)
        if ch == b"#":
            sock.recv(2)
            sock.sendall(b"+")
            return result.decode()
        result.extend(ch)


def command(sock, payload):
    payload = payload.encode()
    sock.sendall(b"$" + payload + b"#" +
                 f"{sum(payload) & 255:02x}".encode())
    if payload == b"c":
        return None
    return packet(sock)


def regs_from_g_reply(reply):
    """R0..R15 of QEMU's standard A7 GDB register packet."""
    if len(reply) < 128:
        raise ValueError("Truncated ARM GDB register packet")
    return [struct.unpack("<I", bytes.fromhex(reply[i:i+8]))[0]
            for i in range(0, 128, 8)]


def audit(sock, seconds):
    command(sock, "qSupported:multiprocess+;swbreak+;hwbreak+")
    if command(sock, "Z0,6001000c,4") != "OK":
        raise RuntimeError("Could not install BIOS status-accessor breakpoint")
    command(sock, "c")
    first = packet(sock)
    r = regs_from_g_reply(command(sock, "g"))
    if r[15] != 0x6001000c:
        raise RuntimeError(f"Stopped before status accessor at {r[15]:#x}")
    # Remove accessor breakpoint before continuing or it immediately
    # re-triggers. Installing the write watchpoint now excludes BSS init.
    if command(sock, "z0,6001000c,4") != "OK":
        raise RuntimeError("Could not remove status-accessor breakpoint")
    if command(sock, "Z2,62413241,1") != "OK":
        raise RuntimeError("Could not install one-byte RAM write watchpoint")
    initial = command(sock, "m62413241,1")
    events = []
    command(sock, "c")
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            sock.settimeout(min(1., max(.01, end-time.monotonic())))
            stop = packet(sock)
        except socket.timeout:
            continue
        r = regs_from_g_reply(command(sock, "g"))
        events.append(dict(stop=stop, pc=f"0x{r[15]:08x}",
                           lr=f"0x{r[14]:08x}",
                           byte=command(sock, "m62413241,1")))
        if len(events) >= 16:
            break
        command(sock, "c")
    return dict(first_status_accessor=f"0x{r[15]:08x}" if not events
                else "0x6001000c",
                first_accessor_lr=f"0x{regs_from_g_reply(command(sock,'g'))[14]:08x}"
                if events else None,
                initial_flag=initial, watchpoint_events=events,
                watch_after_bss=True,
                zero_events_means_no_observed_later_write=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", type=int, default=1234)
    p.add_argument("--seconds", type=float, default=12.)
    a = p.parse_args()
    with socket.create_connection(("127.0.0.1", a.port), timeout=10) as sock:
        result = audit(sock, a.seconds)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
