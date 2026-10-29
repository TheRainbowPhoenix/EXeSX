#!/usr/bin/env python3
"""Microchip ATWINC1510 SPI-slave protocol experiment, localhost only.

The host (QEMU LPSPI2) owns all clocking, PCS, DMA and GPIO. This backend
answers the documented WINC command framing and provides a register/RAM
image. A ROM chip ID is grounded in original DY357 A7 FUN_601c0f78.
It does NOT simulate RF association, external AP, HIF firmware or pass
a factory result. Use --flash to attach an owner-supplied PRIVATE dump.

Transport: TCP loopback, repeated [pcs:u8, flags:u8, n:u16le, TX[n]]
followed by exactly RX[n]. Flags 1=CS assert, 2=CS deassert.
"""
import argparse
from collections import deque
import json
from pathlib import Path
import socket
import struct

READ = {0xc4: 4, 0xca: 4}
WRITE = {0xc3: 7, 0xc9: 8}
DMA_READ = {0xc2: 6, 0xc8: 7}
DMA_WRITE = {0xc1: 6, 0xc7: 7}
SPECIAL = {0xc5: 4, 0xc6: 4, 0xcf: 4}
RECOGNIZED = {**READ, **WRITE, **DMA_READ, **DMA_WRITE, **SPECIAL}
MAX_FRAME = 8192
MAX_FLASH = 1024 * 1024


class Winc1510SPI:
    def __init__(self, flash=None, chip_id=0x1002b0, crc=False,
                 hif_mailbox=False):
        if flash is not None and len(flash) > MAX_FLASH:
            raise ValueError("WINC SPI flash image larger than documented 1 MiB")
        self.flash = bytes(flash) if flash is not None else None
        self.chip_id = chip_id
        self.crc = crc
        # Explicit opt-in. This is the real HIF register handshake, not
        # automatic Wi-Fi association, DHCP or firmware-version success.
        self.hif_mailbox = hif_mailbox
        self.hif_outbound_addr = 0x30000
        self.hif_inbound_addr = 0x32000
        self.hif_requests = []
        self.hif_notifications = []
        self.registers = {0x1000: chip_id, 0x13f4: 3,
                          0x1070: 0, 0x1078: 0, 0x1084: 0,
                          0x108c: 0, 0x106c: 0, 0x150400: 0}
        self.memory = {}
        self.events = []
        self.selected_pcs = None
        self._reset_transaction()

    def _reset_transaction(self):
        self.header = bytearray()
        self.pending = deque()
        self.payload_size = 0
        self.payload_addr = None
        self.payload = bytearray()
        self.completed = False

    def begin(self, pcs):
        if not 0 <= pcs <= 3:
            raise ValueError("LPSPI2 PCS out of range")
        if self.selected_pcs is not None:
            raise ValueError("PCS asserted twice without END")
        self.selected_pcs = pcs
        self._reset_transaction()
        self.events.append(("cs", pcs, "assert"))

    def end(self):
        if self.selected_pcs is not None:
            self.events.append(("cs", self.selected_pcs, "deassert"))
        self.selected_pcs = None
        self._reset_transaction()

    @staticmethod
    def _address(header, internal=False):
        if internal:
            return ((header[1] & 0x7f) << 8) | header[2]
        return (header[1] << 16) | (header[2] << 8) | header[3]

    def _read_reg(self, addr):
        if addr in self.registers:
            return self.registers[addr]
        if self.flash is not None and 0x400000 <= addr < 0x400000 + len(self.flash):
            pos = addr - 0x400000
            return int.from_bytes(self.flash[pos:pos+4].ljust(4, b"\xff"), "big")
        return self.memory.get(addr, 0)

    def _write_reg(self, addr, word):
        if self.hif_mailbox:
            if addr == 0x1078 and (word & 2):
                # Actual original A7 FUN_601C0708 writes bit1, polls
                # until cleared, then reads the WINC buffer pointer.
                self.registers[0x150400] = self.hif_outbound_addr
                self.registers[0x1078] = word & ~2
                self.events.append(("hif-outbound-grant",
                                    self.hif_outbound_addr))
                return
            if addr == 0x106c and (word & 2):
                self._take_hif_request(word >> 2)
            if addr == 0x1070:
                # A7 acknowledges bit0 only after FUN_601C0970 sees
                # a real HIF callback. Never generate one on W1C.
                self.registers[0x1070] = word
                return
        if addr == 0x1000:
            self.events.append(("blocked-chip-id-write", addr, word))
            return
        self.registers[addr] = word & 0xffffffff
        self.events.append(("register-write", addr, word & 0xffffffff))

    def _take_hif_request(self, address):
        # A7 original DMA/FUN_601C0E24 wrote the complete 8-byte
        # request header into WINC RAM before writing 0x106C.
        # Format from owner decomp FUN_601C0708, little-endian HIF len.
        if not self.hif_mailbox or not 0x10000 <= address <= 0x7fff8:
            self.events.append(("invalid-hif-notification", address))
            return
        header = self._dma_get(address, 8)
        group, opcode = header[:2]
        length = int.from_bytes(header[2:4], "little")
        if not (8 <= length <= 0x63c and 0 < group <= 7):
            self.events.append(("malformed-hif-request", address,
                                header.hex()))
            return
        payload = self._dma_get(address + 8, length - 8)
        request = {"group": group, "opcode": opcode,
                   "length": length, "payload": payload,
                   "ram": address}
        self.hif_requests.append(request)
        self.events.append(("hif-request", group, opcode, length))
        # No callback fabricated here. The genuine device firmware or
        # explicit emulated AP/socket fixture must produce a response.

    def queue_hif_callback(self, group, opcode, payload=b""):
        """Explicitly inject a *device-side* HIF callback for a fixture.

        This is a Python-device test entry point, never a guest RAM
        write or unsolicited host startup success. The original A7 still
        must poll WINC SPI registers and dispatch the callback itself.
        """
        if not self.hif_mailbox or not 0 < group <= 7 or not 0 <= opcode <= 255:
            raise ValueError("HIF mailbox not enabled or bad callback header")
        if not isinstance(payload, bytes) or len(payload) + 8 > 0x63c:
            raise ValueError("HIF callback body too large")
        if self.registers.get(0x1070, 0) & 1:
            raise RuntimeError("previous HIF callback not yet acknowledged")
        raw = bytes((group, opcode)) + (len(payload)+8).to_bytes(2, "little")
        raw += bytes(4) + payload
        for i, byte in enumerate(raw):
            self.memory[self.hif_inbound_addr + i] = byte
        self.registers[0x1084] = self.hif_inbound_addr
        self.registers[0x1070] = len(raw) << 2 | 1
        self.hif_notifications.append((group, opcode, len(raw)))
        self.events.append(("hif-device-callback", group, opcode,
                            len(raw)))

    def _dma_get(self, addr, size):
        if size > MAX_FRAME:
            raise ValueError("oversize DMA read")
        return bytes(self.memory.get(addr + i, 0) & 0xff for i in range(size))

    def _dma_put(self, addr, payload):
        if len(payload) > MAX_FRAME:
            raise ValueError("oversize DMA write")
        for i, v in enumerate(payload):
            self.memory[addr + i] = v
        self.events.append(("dma-write", addr, len(payload)))

    def _finish_command(self):
        h = self.header
        cmd = h[0]
        internal = cmd in (0xc3, 0xc4)
        addr = self._address(h, internal)
        self.events.append(("spi-command", self.selected_pcs, cmd, addr))
        if cmd == 0xcf:
            self.registers.clear()
            self.registers.update({0x1000: self.chip_id, 0x13f4: 3,
                                   0x1070: 0, 0x1078: 0, 0x1084: 0,
                                   0x108c: 0, 0x106c: 0, 0x150400: 0})
            self.pending.extend((cmd, 0))
        elif cmd in (0xc5, 0xc6):
            self.pending.extend((cmd, 0))
        elif cmd in READ:
            self.pending.extend((cmd, 0, 0xf3))
            self.pending.extend(self._read_reg(addr).to_bytes(4, "big"))
        elif cmd in WRITE:
            data = int.from_bytes(h[3:7] if internal else h[4:8], "big")
            self._write_reg(addr, data)
            self.pending.extend((cmd, 0))
        elif cmd in DMA_READ or cmd in DMA_WRITE:
            width = 3 if cmd in (0xc7, 0xc8) else 2
            length = int.from_bytes(h[4:4+width], "big")
            if length > MAX_FRAME:
                raise ValueError("requested WINC SPI DMA size too large")
            self.pending.extend((cmd, 0, 0xf3))
            if cmd in DMA_READ:
                self.pending.append(0xf3)
                self.pending.extend(self._dma_get(addr, length))
            else:
                self.payload_addr = addr
                self.payload_size = length
        self.completed = True

    def _clock_byte(self, byte):
        response = self.pending.popleft() if self.pending else 0xff
        if self.payload_size:
            if byte == 0xf3 and not self.payload:
                return response  # optional data-block start marker
            self.payload.append(byte)
            if len(self.payload) == self.payload_size:
                self._dma_put(self.payload_addr, self.payload)
                self.payload_size = 0
                self.payload_addr = None
                self.payload.clear()
                self.pending.extend((0,))  # data packet acknowledged
            return response
        if self.completed:
            return response
        if not self.header:
            if byte not in RECOGNIZED:
                self.events.append(("unknown-spi-opcode", byte))
                self.completed = True
                return 0xff
        self.header.append(byte)
        needed = RECOGNIZED[self.header[0]] + int(self.crc)
        if len(self.header) == needed:
            self._finish_command()
        return response

    def shift(self, pcs, tx, begin=False, end=False):
        if len(tx) > MAX_FRAME:
            raise ValueError("oversized SPI clock segment")
        if begin:
            self.begin(pcs)
        if self.selected_pcs != pcs:
            raise ValueError("SPI transfer without active matching PCS")
        rx = bytes(self._clock_byte(x) for x in tx)
        if end:
            self.end()
        return rx


def recv_exact(sock, n):
    data = bytearray()
    while len(data) < n:
        part = sock.recv(n - len(data))
        if not part:
            raise ConnectionError("short WINC backend request")
        data.extend(part)
    return bytes(data)


def serve(host, port, chip):
    if host != "127.0.0.1":
        raise ValueError("WINC backend intentionally binds localhost only")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((host, port))
        srv.listen(1)
        print("WINC1510 SPI register backend on {}:{}; Wi-Fi HIF/radio "
              "not yet implemented".format(host, port), flush=True)
        while True:
            conn, _ = srv.accept()
            with conn:
                conn.settimeout(5)
                try:
                    while True:
                        header = conn.recv(4)
                        if not header:
                            break
                        while len(header) < 4:
                            header += recv_exact(conn, 4-len(header))
                        pcs, flags, count = struct.unpack("<BBH", header)
                        if count > MAX_FRAME or flags & ~3:
                            raise ValueError("invalid QEMU SPI segment")
                        tx = recv_exact(conn, count)
                        rx = chip.shift(pcs, tx, bool(flags & 1),
                                        bool(flags & 2))
                        conn.sendall(rx)
                except (ConnectionError, OSError, ValueError) as error:
                    print("WINC SPI disconnected:", error, flush=True)
                    chip.end()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--listen", default="127.0.0.1")
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--flash", type=Path, help="owner-private optional flash dump")
    p.add_argument("--chip-id", type=lambda s: int(s, 0), default=0x1002b0,
                   help="owner original ROM accepts 0x1002B0 series; verify hardware revision")
    p.add_argument("--command-crc", action="store_true",
                   help="host transmits one extra CRC7 command byte")
    p.add_argument("--hif-mailbox", action="store_true",
                   help="implement original WINC HIF grant/notify and RAM;"
                        " does NOT auto-ACK network or association commands")
    args=p.parse_args()
    if not 1024 <= args.port <= 65535:
        p.error("TCP port must be 1024..65535")
    flash = args.flash.read_bytes() if args.flash else None
    chip = Winc1510SPI(flash, args.chip_id, args.command_crc,
                       hif_mailbox=args.hif_mailbox)
    serve(args.listen, args.port, chip)


if __name__ == "__main__":
    main()
