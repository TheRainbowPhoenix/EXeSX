#!/usr/bin/env python3
"""Actual USB host-side transaction driver for the EXeSX ChipIdea socket.

This is not a USB gadget, and it never writes guest memory or invents
USB descriptors. Real original A7 must program device mode, QHs and dTDs.
The host asks the original device for descriptors, sends SET_ADDRESS and
SET_CONFIGURATION, then exchanges original factory bytes on bulk EPs.

Wire: QEMU requests [op:u8, ep:u8, length:u16le, payload for SETUP/OUT];
reply [status:u8, ep:u8, length:u16le, payload only for IN].
0=ACK, 1=NAK (original guest not ready), 2=STALL, 3=bridge error.
"""
import argparse
import socket
import struct
import time

from usb_factory_host import packet, decode_header, recv_exact

SETUP, OUT, IN, ATTACH, DETACH, RESET = 1, 2, 3, 4, 5, 6
USB_TIMEOUT = 12
MAX_PACKET = 4096


class USBEndpointHost:
    def __init__(self, sock, timeout=USB_TIMEOUT):
        self.sock = sock
        self.timeout = timeout
        self.config = None
        self.ep_out = self.ep_in = None
        self.max_packet = 64

    def transaction(self, opcode, ep=0, data=b"", request_length=None,
                    retry=True):
        n = len(data) if request_length is None else request_length
        if n > MAX_PACKET or ep > 7 or ep < 0 or opcode not in (
                SETUP, OUT, IN, ATTACH, DETACH, RESET):
            raise ValueError("invalid USB host endpoint transaction")
        if opcode in (IN,) and data:
            raise ValueError("IN has no outbound payload")
        if opcode not in (IN,) and n != len(data):
            raise ValueError("OUT/SETUP data count mismatch")
        deadline = time.monotonic() + self.timeout
        while True:
            self.sock.sendall(struct.pack("<BBH", opcode, ep, n) + data)
            reply = recv_exact(self.sock, 4)
            status, reply_ep, count = struct.unpack("<BBH", reply)
            if reply_ep != ep or count > MAX_PACKET:
                raise RuntimeError("invalid QEMU USB endpoint response")
            body = recv_exact(self.sock, count)
            if status == 0:
                return body
            if status != 1 or not retry or time.monotonic() > deadline:
                raise RuntimeError("USB endpoint {}:{} status {}".format(
                    ep, opcode, status))
            time.sleep(.025)

    def enumerate(self):
        self.transaction(ATTACH, retry=False)
        self.transaction(RESET, retry=False)
        # The original A7 receives this SETUP in its QH+0x28, handles
        # USBSTS.UI and primes the requested EP0 dTD.
        self.transaction(SETUP, data=bytes.fromhex("8006000100001200"))
        desc = self.transaction(IN, request_length=18)
        if len(desc) < 18 or desc[1] != 1:
            raise RuntimeError("original guest has not supplied USB device descriptor")
        self.transaction(OUT, data=b"")  # control status stage
        self.transaction(SETUP, data=bytes.fromhex("0005010000000000"))
        self.transaction(IN, request_length=0)  # ADDRESS status stage
        self.transaction(SETUP, data=bytes.fromhex("8006000200000900"))
        head = self.transaction(IN, request_length=9)
        if len(head) < 9 or head[1] != 2:
            raise RuntimeError("USB configuration header invalid")
        self.transaction(OUT, data=b"")
        total = int.from_bytes(head[2:4], "little")
        if total > MAX_PACKET or total < 9:
            raise RuntimeError("USB configuration total length is invalid")
        self.transaction(SETUP, data=bytes((0x80, 6, 0, 2, 0, 0,
                                             total & 255, total >> 8)))
        config = self.transaction(IN, request_length=total)
        if len(config) < total or config[1] != 2:
            raise RuntimeError("USB config data incomplete")
        self.transaction(OUT, data=b"")
        cfg_value = config[5]
        self.transaction(SETUP, data=bytes((0, 9, cfg_value, 0, 0, 0, 0, 0)))
        self.transaction(IN, request_length=0)
        out_ep = in_ep = None
        i = 0
        max_packet = 64
        while i + 2 <= len(config):
            size, dtype = config[i:i+2]
            if size < 2 or i + size > len(config):
                raise RuntimeError("broken USB config descriptor")
            if dtype == 5 and size >= 7 and config[i+3] & 3 == 2:
                number = config[i+2] & 15
                if number > 7:
                    raise RuntimeError("unsupported USB bulk endpoint number")
                if config[i+2] & 0x80:
                    in_ep = number
                else:
                    out_ep = number
                max_packet = max(max_packet, int.from_bytes(config[i+4:i+6], "little"))
            i += size
        if out_ep is None or in_ep is None:
            raise RuntimeError("original USB device exposed no bulk IN+OUT endpoints")
        self.config, self.ep_out, self.ep_in = config, out_ep, in_ep
        self.max_packet = min(max_packet, MAX_PACKET)
        return {"device_descriptor": desc.hex(), "config_descriptor": config.hex(),
                "bulk_out": out_ep, "bulk_in": in_ep, "max_packet": self.max_packet}

    def bulk_write(self, payload):
        if self.ep_out is None:
            raise RuntimeError("USB enumeration not completed")
        # The original gadget queues its own dTD. Never inject the
        # factory commands directly into shared RAM or RTOS buffers.
        for pos in range(0, len(payload), self.max_packet):
            self.transaction(OUT, self.ep_out,
                             payload[pos:pos+self.max_packet])

    def bulk_read(self, requested):
        if self.ep_in is None:
            raise RuntimeError("USB enumeration not completed")
        return self.transaction(IN, self.ep_in,
                                request_length=min(requested, self.max_packet))


class EndpointFactoryStream:
    """Socket-like adapter for unmodified usb_factory_host.exchange()."""
    def __init__(self, bridge):
        self.bridge = bridge
        self.buffer = bytearray()

    def sendall(self, data):
        self.bridge.bulk_write(data)

    def recv(self, n):
        if not self.buffer:
            self.buffer.extend(self.bridge.bulk_read(max(n, 1)))
        chunk = self.buffer[:n]
        del self.buffer[:n]
        return bytes(chunk)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--timeout", type=float, default=USB_TIMEOUT)
    p.add_argument("--factory-hello", action="store_true",
                   help="after actual enumeration request original factory HELLO")
    p.add_argument("--full-plan", action="store_true",
                   help="only after original replies: init, MAC, EXIT")
    a = p.parse_args()
    if not 1024 <= a.port <= 65535 or not 0 < a.timeout <= 120:
        p.error("localhost port or timeout out of range")
    with socket.create_connection(("127.0.0.1", a.port), a.timeout) as s:
        s.settimeout(a.timeout)
        host = USBEndpointHost(s, a.timeout)
        print("Original USB descriptors:", host.enumerate(), flush=True)
        if a.factory_hello or a.full_plan:
            from usb_factory_host import plan
            print("Original factory responses:",
                  plan(EndpointFactoryStream(host), a.full_plan), flush=True)
        else:
            print("Original guest USB enumeration succeeded, no WLAN claim.")


if __name__ == "__main__":
    main()
