#!/usr/bin/env python3
"""External USB-factory host fixture over a future QEMU USB byte-stream bridge.

This is *host-side*, not the ATWINC1510 SPI slave. It sends original DY357
factory commands and consumes the original guest's response bytes. The
QEMU USBPHY/device/endpoint-to-socket bridge is NOT implemented yet:
a TCP listener alone cannot make the original A7's USB link connect.

Safe default: request command-1 HELLO only, report actual received bytes.
--full-plan additionally sends WLAN init and MAC query; command-2 EXIT is
sent ONLY if those operations genuinely replied successfully. It does
not invent a WLAN OK flag or a device response in the guest.
"""
import argparse
import json
import socket
import struct
import time

MAGIC = b"\xff\xff"
MAX_FRAME = 8192
STATUS = {0x80: "accepted", 0x81: "unsupported", 0x82: "device error"}


def packet(command, argument=0, payload=b""):
    if not 0 < command < 0x80 or not 0 <= argument <= 255:
        raise ValueError("invalid original factory command/argument")
    if not isinstance(payload, bytes) or len(payload) + 6 > MAX_FRAME:
        raise ValueError("invalid factory payload size")
    return struct.pack("<HBBH", 0xffff, command, argument,
                       len(payload) + 6) + payload


def decode_header(header):
    if len(header) != 6 or header[:2] != MAGIC:
        raise ValueError("unrecognized original USB factory response header")
    le = int.from_bytes(header[4:6], "little")
    be = int.from_bytes(header[4:6], "big")
    if 6 <= le <= MAX_FRAME:
        length, order = le, "little"
    elif 6 <= be <= MAX_FRAME:
        # Original ROM constructs some 64-byte replies as 00 40.
        # Keep the alternate endianness visible in logs.
        length, order = be, "big"
    else:
        raise ValueError("invalid factory response length")
    return {"code": header[2], "argument": header[3],
            "length": length, "length_endian": order}


def recv_exact(sock, size):
    chunks = bytearray()
    while len(chunks) < size:
        data = sock.recv(size - len(chunks))
        if not data:
            raise ConnectionError("original USB device disconnected mid-response")
        chunks.extend(data)
    return bytes(chunks)


def exchange(sock, command, argument=0, payload=b""):
    sock.sendall(packet(command, argument, payload))
    header = decode_header(recv_exact(sock, 6))
    body = recv_exact(sock, header["length"] - 6)
    result = {**header, "payload_hex": body.hex(),
              "status": STATUS.get(header["code"], "unexpected")}
    if header["code"] != 0x80:
        raise RuntimeError("original device rejected command {}:{}: {}"
                           .format(command, argument, result))
    return result


def plan(sock, full_plan=False):
    results = [{"request": "hello", "response": exchange(sock, 1)}]
    if full_plan:
        # Only original device-side responses can advance this plan.
        # Client-side "OK" is not a substitute for the A7 LCD result.
        results.append({"request": "wlan-init",
                        "response": exchange(sock, 3, 1)})
        results.append({"request": "mac-read",
                        "response": exchange(sock, 4, 2)})
        results.append({"request": "end-after-real-replies",
                        "response": exchange(sock, 2)})
    return results


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, required=True,
                   help="QEMU USB byte-stream bridge TCP listen port (future)")
    p.add_argument("--timeout", type=float, default=5.0)
    p.add_argument("--full-plan", action="store_true",
                   help="HELLO, WLAN init, MAC query, EXIT after genuine replies")
    p.add_argument("--report", help="local JSON transcript path")
    args = p.parse_args()
    if args.host != "127.0.0.1" or not 1024 <= args.port <= 65535:
        p.error("USB fixture connects to localhost ports 1024..65535 only")
    if not 0 < args.timeout <= 120:
        p.error("timeout must be in (0,120] seconds")
    try:
        with socket.create_connection((args.host, args.port),
                                      args.timeout) as sock:
            sock.settimeout(args.timeout)
            results = plan(sock, args.full_plan)
    except (OSError, ValueError, RuntimeError) as exc:
        p.exit(2, "Original USB device NOT verified: {}\n".format(exc))
    record = {"transport": "QEMU original USB endpoint stream",
              "original_rom_ok_screenshot_captured": False,
              "transactions": results}
    if args.report:
        from pathlib import Path
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(record, indent=2) + "\n",
                          encoding="utf-8")
    print(json.dumps(record, indent=2))
    print("Responses received; original WLAN OK/USB enumeration "
          "still require guest firmware confirmation.")


if __name__ == "__main__":
    main()
