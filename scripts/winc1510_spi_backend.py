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
                 hif_mailbox=False, fixture_ssid=None,
                 fixture_identity=False, frame_spanning_cs=False,
                 fixture_rssi_dbm=-55, fixture_ipv4=None):
        if flash is not None and len(flash) > MAX_FLASH:
            raise ValueError("WINC SPI flash image larger than documented 1 MiB")
        self.flash = bytes(flash) if flash is not None else None
        self.chip_id = chip_id
        self.crc = crc
        # Explicit opt-in. This is the real HIF register handshake, not
        # automatic Wi-Fi association, DHCP or firmware-version success.
        self.hif_mailbox = hif_mailbox
        if fixture_ssid is not None:
            if not hif_mailbox or not isinstance(fixture_ssid, str) or (
                    not 1 <= len(fixture_ssid.encode("utf-8")) <= 32):
                raise ValueError("AP fixture requires HIF and a 1..32-byte SSID")
        # Deliberately deterministic AP fixture: no RF and no TCP/IP.
        # An unconfigured card must NOT auto-report a connection.
        self.fixture_ssid = fixture_ssid
        self.fixture_identity = bool(fixture_identity)
        self.frame_spanning_cs = bool(frame_spanning_cs)
        if not -100 <= fixture_rssi_dbm <= -1:
            raise ValueError("fixture RSSI must be -100..-1 dBm")
        if fixture_ipv4 is not None:
            if fixture_ssid is None or not hif_mailbox:
                raise ValueError("DHCP fixture requires an AP and HIF")
            octets = fixture_ipv4.split(".")
            if len(octets) != 4 or any(
                    not x.isascii() or not x.isdecimal() or
                    not 0 <= int(x) <= 255 for x in octets):
                raise ValueError("invalid fixture IPv4 address")
            self.fixture_ipv4 = bytes(int(x) for x in octets)
        else:
            self.fixture_ipv4 = None
        self.fixture_rssi_dbm = fixture_rssi_dbm
        self.ap_connected = False
        self.power_save_mode = None
        self.sleep_hint = None
        self.deferred_callbacks = deque()
        self.hif_ack_draining = False
        self.hif_outbound_addr = 0x30000
        self.hif_inbound_addr = 0x32000
        self.hif_requests = []
        self.hif_notifications = []
        self.registers = {0x1000: chip_id, 0x13f4: 3,
                          0x1070: 0, 0x1078: 0, 0x1084: 0,
                          0x108c: 0, 0x106c: 0, 0x150400: 0}
        self.memory = {}
        self.events = []
        self._populate_fixture_identity()
        # Board control pins are electrical lines, not HIF "OK" events.
        # Active-low RESET_N and WAKE_N; CHIP_EN is active high.
        self.reset_n = True
        self.wake_n = False
        self.chip_enable = True
        self.selected_pcs = None
        self._reset_transaction()

    def _populate_fixture_identity(self):
        """Optional simulated WINC metadata in the original A7 layout.

        Original FUN_601c14a8/FUN_601c4100 read WINC reg 0xC0008,
        then the eight-byte pointer table at (value | 0x30000).
        The first two little-endian offsets name the six-byte MAC
        and the 40-byte version record. No guest event is injected.
        """
        if not self.fixture_identity:
            return
        self.registers[0xc0008] = 0x1000
        # FUN_601c1298 checks bit0 of WINC 0x207bc for firmware boot.
        self.registers[0x207bc] = 1
        header = (0x1100).to_bytes(4, "little")
        header += (0x1200).to_bytes(4, "little")
        mac = bytes((0x02, 0x35, 0x70, 0x15, 0x10, 0x01))
        version = bytearray(40)
        version[4:7] = bytes((19, 6, 1))
        version[7:10] = bytes((19, 6, 1))
        for address, payload in ((0x31000, header),
                                 (0x31100, mac),
                                 (0x31200, version)):
            for offset, value in enumerate(payload):
                self.memory[address + offset] = value

    def set_pins(self, reset_n=True, wake_n=False, chip_enable=True):
        """Apply genuine board pins supplied by the QEMU GPIO bridge.

        Reset erases volatile registers/RAM, never owner-supplied flash.
        A disabled chip drives high MISO; no SPI/HIF events occur.
        """
        reset_n, wake_n, chip_enable = (
            bool(reset_n), bool(wake_n), bool(chip_enable))
        was_enabled = self.reset_n and self.chip_enable
        will_enable = reset_n and chip_enable
        if was_enabled and not will_enable:
            self.end()
            self.memory.clear()
            self.hif_requests.clear()
            self.hif_notifications.clear()
            self.ap_connected = False
            self.power_save_mode = None
            self.sleep_hint = None
            self.deferred_callbacks.clear()
            self.hif_ack_draining = False
            self.registers.clear()
            self.registers.update({
                0x1000: self.chip_id, 0x13f4: 3,
                0x1070: 0, 0x1078: 0, 0x1084: 0, 0x108c: 0,
                0x106c: 0, 0x150400: 0,
            })
            self._populate_fixture_identity()
            self.events.append(("hardware-reset-or-chip-disabled",))
        self.reset_n = reset_n
        self.wake_n = wake_n
        self.chip_enable = chip_enable

    @property
    def irq_n(self):
        """HIF pending interrupt drives IRQ_N low; never a fabricated OK."""
        return not (self.reset_n and self.chip_enable and
                    (self.registers.get(0x1070, 0) & 1))

    def _reset_transaction(self):
        self.header = bytearray()
        self.pending = deque()
        self.payload_size = 0
        self.data_crc_remaining = 0
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
        # Original DY357 FUN_601c1298 polls WINC 0x1014 bit31 for
        # power/clock readiness before starting HIF. This is physical
        # chip status, never a fabricated guest callback or WLAN PASS.
        if addr == 0x1014:
            return 0x80000000 if self.reset_n and self.chip_enable else 0
        if addr == 0x000f and self.fixture_identity:
            # ORIGINAL A7 FUN_601c10f8: configure chip registers
            # 0x000b and 0x0001, then wait up to five polls for
            # register 0x000f bit 2. Absent this physical device-ready
            # bit the unmodified driver returns exactly -4, shown by
            # factory AUTO DEEP SLEEP as WLAN CONNECT ERROR! E04.
            # Report readiness only after the original guest has
            # programmed the activation bits; no A7 state is injected.
            activated = bool(self.registers.get(0x000b, 0) & 1)
            activated &= bool(self.registers.get(0x0001, 0) & 2)
            return 4 if activated and self.reset_n and self.chip_enable else 0
        if addr in self.registers:
            return self.registers[addr]
        if self.flash is not None and 0x400000 <= addr < 0x400000 + len(self.flash):
            pos = addr - 0x400000
            return int.from_bytes(self.flash[pos:pos+4].ljust(4, b"\xff"), "big")
        return self.memory.get(addr, 0)

    def _write_reg(self, addr, word):
        # Original FUN_601c1298 writes a boot handshake to WINC 0x108c.
        # FUN_601c13d0 waits for the device-side magic ACK. This is
        # firmware-ready register behavior, not an A7 HIF callback.
        if self.fixture_identity and addr == 0x108c and word == 0x13301361:
            self.registers[0x108c] = 0x02532636
            self.events.append(("firmware-boot-ack", addr, word))
            return
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
                # the original device-side HIF callback.
                old_pending = bool(self.registers.get(0x1070, 0) & 1)
                self.registers[0x1070] = word
                if old_pending and not (word & 1):
                    # ORIGINAL FUN_601c0970 clears 0x1070 bit0 BEFORE
                    # reading 0x1084 and DMA-reading the incoming HIF
                    # message. Publishing the next queued callback here
                    # overwrites 0x32000/0x1084 and destroys the first
                    # association result before the A7 can consume it.
                    # Finish the original message before advancing FIFO.
                    self.hif_ack_draining = True
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
        # The device-side simulated radio reacts only to real original
        # A7 HIF commands, and only with an explicit configured AP.
        # The A7 must fetch it through WINC SPI, handle IRQ_N and
        # build its OWN application event. There is no guest SRAM write.
        if group == 1 and opcode == 0x2d and len(payload) >= 2:
            # Original FUN_601cab94 emits this request for auto-deep
            # sleep; record settings but never invent a host OK event.
            self.power_save_mode = (payload[0], payload[1])
            self.events.append(("guest-power-save-request", *self.power_save_mode))
        if group == 1 and opcode == 0x39 and len(payload) >= 2:
            # Original AUTO DEEP SLEEP FUN_601cab94 first sends
            # 0x2D(3,1), then FUN_601c3e2c sends 0x39 with a
            # four-byte setting whose low halfword is 1.
            # Record a genuine guest request; do not synthesize
            # an A7 notification, timer wake, or test PASS.
            self.sleep_hint = int.from_bytes(payload[:2], "little")
            self.events.append(("guest-sleep-hint", self.sleep_hint))
        if self.fixture_ssid is not None and group == 1:
            if opcode == 0xbb:
                # Original FUN_601c37d0 emits group1/0xBB with SSID
                # inside the security/connection structure (up to 0x30).
                expected = self.fixture_ssid.encode("utf-8")
                if expected not in payload:
                    self.events.append(("ap-fixture-ssid-mismatch",))
                    self._defer_hif_callback(1, 0x2c, bytes((0, 1, 0, 0)))
                else:
                    self.ap_connected = True
                    self.events.append(("ap-fixture-associated", self.fixture_ssid))
                    self._defer_hif_callback(1, 0x2c, bytes((1, 0, 0, 0)))
                    if self.fixture_ipv4 is not None:
                        # Device-side WINC DHCP callback 0x32. Original
                        # A7 must handle the IRQ and copy the 24 bytes.
                        lease = self.fixture_ipv4 + bytes(20)
                        self._defer_hif_callback(1, 0x32, lease)
            elif opcode == 0x2b:
                # Original FUN_601c3d78 sends 0x2B disconnect.
                self.ap_connected = False
                self._defer_hif_callback(1, 0x2c, bytes(4))
            elif opcode == 0x2f and self.ap_connected:
                # Original FUN_601ca3d4(SSID, mode=5) requests the
                # 0x2f Wi-Fi connection/AP record (different from
                # 0x05 request -> 0x06 48-byte AP-channel reply).
                # FUN_601c3030 reads a 100-byte device callback;
                # FUN_601c9c4c expects state at 0, channel at 1,
                # SSID beginning at 2 and companion fields at 0x23.
                ssid = self.fixture_ssid.encode("utf-8")
                info = bytearray(100)
                info[0] = 1  # nonzero associated AP state
                info[1] = 6  # explicit simulated channel
                info[2:2 + len(ssid)] = ssid
                self._defer_hif_callback(1, 0x2f, bytes(info))
            elif opcode == 5 and self.ap_connected:
                # Original FUN_601c4088 queries AP info. FUN_601c3030
                # reads 48 bytes; callback reads channel from byte45.
                ssid = self.fixture_ssid.encode("utf-8")
                info = bytearray(48)
                info[:len(ssid)] = ssid
                info[45] = 6
                self._defer_hif_callback(1, 6, bytes(info))
            elif opcode == 3 and self.ap_connected:
                # Original FUN_601c3f6c -> 0x03 query, 0x04 callback.
                self._defer_hif_callback(
                    1, 4, bytes((self.fixture_rssi_dbm & 0xff, 0, 0, 0)))

    def _defer_hif_callback(self, group, opcode, payload):
        if self.registers.get(0x1070, 0) & 1:
            self.deferred_callbacks.append((group, opcode, payload))
        else:
            self.queue_hif_callback(group, opcode, payload)

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
        data = bytes(self.memory.get(addr + i, 0) & 0xff
                     for i in range(size))
        # Source-derived: the A7 has already ACKed IRQ_N but still
        # needs this exact device RAM. Deliver deferred callbacks only
        # AFTER the last byte of the previous HIF message has been
        # clocked over the real C8 DMA read.
        if self.hif_ack_draining:
            length = int.from_bytes(
                bytes(self.memory.get(self.hif_inbound_addr + i, 0)
                      for i in (2, 3)), "little")
            end = self.hif_inbound_addr + length
            if (8 <= length <= 0x63c and
                    addr >= self.hif_inbound_addr and
                    addr < end and addr + size >= end):
                self.hif_ack_draining = False
                if self.deferred_callbacks:
                    group, opcode, payload = self.deferred_callbacks.popleft()
                    self.queue_hif_callback(group, opcode, payload)
        return data

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
            self._populate_fixture_identity()
            self.pending.extend((cmd,) if self.frame_spanning_cs else (cmd, 0))
        elif cmd in (0xc5, 0xc6):
            self.pending.extend((cmd,) if self.frame_spanning_cs else (cmd, 0))
        elif cmd in READ:
            self.pending.extend((cmd, 0, 0xf3))
            # Microchip nmspi.c spi_read_reg assembles b[0] as bits
            # 7:0 and b[3] as bits 31:24. SPI command ADDRESS bytes
            # are big endian but the four returned DATA bytes are LE.
            self.pending.extend(self._read_reg(addr).to_bytes(4, "little"))
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
                # Original FUN_601c19e8 consumes a single F3 data-start
                # marker, then the DMA bytes. Sending two F3 bytes shifts
                # the 8-byte MAC/version pointer table by one byte.
                if not self.frame_spanning_cs:
                    self.pending.append(0xf3)
                self.pending.extend(self._dma_get(addr, length))
            else:
                self.payload_addr = addr
                self.payload_size = length
        self.completed = True

    def _clock_byte(self, byte):
        had_pending_response = bool(self.pending)
        response = self.pending.popleft() if self.pending else 0xff
        if self.payload_size:
            if self.crc and self.frame_spanning_cs and had_pending_response:
                # Original A7 polls command echo/status C7,00,F3 with
                # dummy MOSI clocks BEFORE sending its separate F3
                # data-block marker. They are not DMA payload bytes.
                # Without this guard the 8-byte HIF header becomes
                # 00 00 00 F3 01 3B ... and the guest resets/retries.
                return response
            if byte == 0xf3 and not self.payload:
                return response  # optional data-block start marker
            self.payload.append(byte)
            if len(self.payload) == self.payload_size:
                self._dma_put(self.payload_addr, self.payload)
                self.payload_size = 0
                self.payload_addr = None
                self.payload.clear()
                if self.crc and self.frame_spanning_cs:
                    # Original DY357 FUN_601c1af0 writes two CRC16 bytes
                    # after the C7 DMA payload. FUN_601c18c4 then reads
                    # the WINC *data packet* ACK 0xC3,0x00. Previously
                    # we returned FF,FF,00: the original A7 regarded
                    # this as a failed write, issued CMD_RESET (0xCF)
                    # and retried the same HIF header ten times.
                    # The original A7 reads three response bytes after
                    # the F3 + payload transfer. Observed MOSI/MISO:
                    # 00 00 00 -> FF C3 00. One turnaround dummy clock,
                    # then the real last-data-packet status C3,00.
                    # Do not consume two CRC clocks here: doing so
                    # shifts C3 to byte3, which original FUN_601c18c4
                    # rejects and triggers ten CMD_RESET retries.
                    self.data_crc_remaining = 1
                else:
                    self.pending.extend((0,))
            return response
        if self.data_crc_remaining:
            self.data_crc_remaining -= 1
            if not self.data_crc_remaining:
                self.pending.extend((0xc3, 0))
                self.events.append(("dma-write-data-ack",))
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
        if not self.reset_n or not self.chip_enable:
            self.end()
            return bytes([0xff]) * len(tx)
        if begin:
            if self.frame_spanning_cs and self.selected_pcs == pcs:
                # With split DY357 LPSPI2 frames, zero MOSI clocks continue
                # the pending reply. A NEW genuine command opcode ends the
                # prior read even if a programmed DMA length wasn't fully
                # clocked (no host buffer/event modification).
                if (self.completed and not self.payload_size and tx and
                        tx[0] in RECOGNIZED):
                    self.events.append(("original-next-spi-command", tx[0]))
                    self.end()
                    self.begin(pcs)
            else:
                self.begin(pcs)
        if self.selected_pcs != pcs:
            raise ValueError("SPI transfer without active matching PCS")
        rx = bytes(self._clock_byte(x) for x in tx)
        if end:
            # The original A7 WINC driver uses a separate sequence of
            # LPSPI2 frames for command, echo/status, and response bytes.
            # On the physical board the WLAN slave CS boundary is not
            # established by the LPSPI2 TCR.CONT bit alone. In this
            # explicit compatibility mode, a host frame end cannot
            # truncate an unfinished WINC command or pending reply.
            # Once the reply is fully clocked, reset CS and parser so
            # the next actual original command starts from a clean slate.
            if not (self.frame_spanning_cs and
                    (not self.completed or self.pending or
                     self.payload_size or self.data_crc_remaining)):
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


def serve(host, port, chip, gpio_status=False, trace_events=False,
          idle_timeout=120):
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
                # Original OSUP can spend much more than five seconds
                # in its A7/M4 ISR/task work between two genuine SPI
                # frames when QEMU TCG single-thread and QMP capture
                # share the host. The previous five-second socket idle
                # timeout silently discarded pending HIF/CRC state
                # exactly after a genuine 108-byte C7 DMA write.
                # This is an idle bound, not a packet-completion timer.
                conn.settimeout(idle_timeout)
                trace_index = len(chip.events)
                try:
                    while True:
                        header = conn.recv(4)
                        if not header:
                            break
                        while len(header) < 4:
                            header += recv_exact(conn, 4-len(header))
                        pcs, flags, count = struct.unpack("<BBH", header)
                        if count > MAX_FRAME or flags & ~(0x3f if gpio_status else 3):
                            raise ValueError("invalid QEMU SPI segment")
                        # Host can query the asynchronous IRQ_N line
                        # without clocking SPI or changing PCS. This is a
                        # real electrical status query, never a guest event.
                        if gpio_status and flags == 0x20 and count == 0:
                            conn.sendall(bytes([int(chip.irq_n)]))
                            continue
                        tx = recv_exact(conn, count)
                        if gpio_status:
                            chip.set_pins(reset_n=bool(flags & 4),
                                          wake_n=bool(flags & 8),
                                          chip_enable=bool(flags & 16))
                        rx = chip.shift(pcs, tx, bool(flags & 1),
                                        bool(flags & 2))
                        # Opt-in byte appended to the *existing* response,
                        # sampled by the GPIO bridge only: 1=IRQ_N high.
                        # Legacy wire protocol remains strictly RX[n].
                        conn.sendall(rx + (bytes([int(chip.irq_n)])
                                           if gpio_status else b""))
                        if trace_events:
                            # No SSID/password bytes, guest RAM or flash in
                            # the host log. Pure command metadata for local
                            # sweep triage; original LCD remains the verdict.
                            for event in chip.events[trace_index:]:
                                kind = event[0]
                                if kind == "spi-command":
                                    record = {"event": kind, "pcs": event[1],
                                              "opcode": hex(event[2]),
                                              "address": hex(event[3])}
                                elif kind in (
                                        "hif-request", "hif-device-callback"):
                                    record = {"event": kind, "group": event[1],
                                              "opcode": hex(event[2]),
                                              "size": event[3]}
                                elif kind in (
                                        "guest-power-save-request",
                                        "hardware-reset-or-chip-disabled",
                                        "firmware-boot-ack",
                                        "ap-fixture-ssid-mismatch",
                                        "ap-fixture-associated"):
                                    record = {"event": kind}
                                else:
                                    continue
                                print("WINC_EVENT " + json.dumps(record),
                                      flush=True)
                            trace_index = len(chip.events)
                            if trace_index > 20000:
                                del chip.events[:trace_index]
                                trace_index = 0
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
    p.add_argument("--idle-timeout", type=float, default=120,
                   help="seconds allowed between actual guest SPI frames; "
                        "default 120 for slow single-threaded original OSUP")
    p.add_argument("--trace-events", action="store_true",
                   help="local redacted SPI/HIF event metadata for sweep")
    p.add_argument("--gpio-status", action="store_true",
                   help="extended bridge: RESET_N/WAKE_N/EN control flags and"
                        " one sampled IRQ_N status byte after each SPI response")
    p.add_argument("--frame-spanning-cs", action="store_true",
                   help="keep WINC command/response state over original "
                        "DY357 LPSPI2 frame boundaries until all response "
                        "bytes clock; opt-in board-CS compatibility")
    p.add_argument("--fixture-identity", action="store_true",
                   help="simulated WINC ROM metadata (MAC 02:35:70:15:10:01, "
                        "firmware 19.6.1); no guest status injection")
    p.add_argument("--fixture-ssid", type=str,
                   help="opt-in deterministic simulated AP name (NO real radio,"
                        " internet proxy, DHCP or socket semantics)")
    p.add_argument("--fixture-rssi-dbm", type=int, default=-55,
                   help="simulated RSSI (-100..-1 dBm), only after query")
    p.add_argument("--fixture-ipv4", type=str,
                   help="explicit simulated DHCP address, no host network")
    p.add_argument("--hif-mailbox", action="store_true",
                   help="implement original WINC HIF grant/notify and RAM;"
                        " does NOT auto-ACK network or association commands")
    args=p.parse_args()
    if not 1024 <= args.port <= 65535:
        p.error("TCP port must be 1024..65535")
    flash = args.flash.read_bytes() if args.flash else None
    chip = Winc1510SPI(flash, args.chip_id, args.command_crc,
                       hif_mailbox=args.hif_mailbox,
                       fixture_ssid=args.fixture_ssid,
                       fixture_identity=args.fixture_identity,
                       frame_spanning_cs=args.frame_spanning_cs,
                       fixture_rssi_dbm=args.fixture_rssi_dbm,
                       fixture_ipv4=args.fixture_ipv4)
    if not 5 <= args.idle_timeout <= 3600:
        p.error("--idle-timeout must be 5..3600 seconds")
    serve(args.listen, args.port, chip, args.gpio_status,
          args.trace_events, args.idle_timeout)


if __name__ == "__main__":
    main()
