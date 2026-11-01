"""Public, firmware-free WINC1510 SPI protocol controls."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from winc1510_spi_backend import Winc1510SPI


class SPIProtocolTests(unittest.TestCase):
    def setUp(self):
        self.dev=Winc1510SPI()

    def test_original_rom_chip_id_is_spi_command_not_forged_a7_flag(self):
        header=bytes.fromhex("ca001000")
        self.assertEqual(self.dev.shift(0, header, begin=True),
                         b"\xff" * 4)
        self.assertEqual(self.dev.shift(0,bytes(7),end=True),
                         bytes.fromhex("ca00f3b0021000"))
        self.assertIsNone(self.dev.selected_pcs)

    def test_register_write_and_subsequent_read(self):
        self.dev.shift(1,bytes.fromhex("c900108c12345678"),begin=True,end=True)
        self.assertEqual(self.dev.registers[0x108c],0x12345678)
        self.dev.shift(1,bytes.fromhex("ca00108c"),begin=True)
        self.assertEqual(self.dev.shift(1,bytes(7),end=True),
                         bytes.fromhex("ca00f378563412"))

    def test_dma_read_protocol_and_chip_select(self):
        self.dev._dma_put(0x10000,bytes.fromhex("11223344"))
        self.dev.shift(2,bytes.fromhex("c20100000004"),begin=True)
        self.assertEqual(self.dev.shift(2,bytes(8),end=True),
                         bytes.fromhex("c200f3f311223344"))
        self.assertEqual(self.dev.events[-1],("cs",2,"deassert"))

    def test_unknown_code_and_reset_do_not_connect_to_ap(self):
        self.assertEqual(self.dev.shift(0,b"\x11",begin=True,end=True),
                         b"\xff")
        self.dev.shift(0,bytes.fromhex("c900108c12345678"),begin=True,end=True)
        self.dev.shift(0,bytes.fromhex("cfffffff"),begin=True)
        self.assertEqual(self.dev.shift(0,b"\x00\x00",end=True),
                         bytes.fromhex("cf00"))
        self.assertEqual(self.dev.registers[0x108c],0)
        self.assertNotIn("connected",str(self.dev.events))
        with self.assertRaises(ValueError):
            self.dev.shift(1,b"\x00",begin=False)
        with self.assertRaises(ValueError):
            Winc1510SPI(bytes(1024*1024+1))

    def test_original_hif_dma_mailbox_and_explicit_device_callback(self):
        from winc1510_spi_backend import Winc1510SPI
        dev = Winc1510SPI(hif_mailbox=True)
        # Original FUN_601C0708 writes 2 to this WINC *internal*
        # register via a real SPI write. Only the hardware mailbox
        # grant is automatic; no WLAN success/HIF reply is fabricated.
        dev.shift(2, bytes.fromhex("c900107800000002"),
                  begin=True, end=True)
        self.assertEqual(dev._read_reg(0x1078) & 2, 0)
        self.assertEqual(dev._read_reg(0x150400), 0x30000)
        self.assertEqual(dev.hif_requests, [])
        self.assertEqual(dev._read_reg(0x1070), 0)

        body = b"\x01\x2b\x0c\x00" + bytes(4) + b"TEST"
        dev._dma_put(0x30000, body)
        # Genuine A7 sets request pointer<<2 | 2 after DMA payload.
        dev.shift(2, bytes.fromhex("c900106c000c0002"),
                  begin=True, end=True)
        self.assertEqual(len(dev.hif_requests), 1)
        self.assertEqual(dev.hif_requests[0]["group"], 1)
        self.assertEqual(dev.hif_requests[0]["opcode"], 0x2b)
        self.assertEqual(dev.hif_requests[0]["payload"], b"TEST")
        self.assertEqual(dev._read_reg(0x1070), 0)

        # A device/fixture may later explicitly post a HIF response;
        # it is not posted merely because the host asked to connect.
        dev.queue_hif_callback(1, 0x2c, b"\x01" + bytes(3))
        self.assertEqual(dev._read_reg(0x1070), (12<<2)|1)
        self.assertEqual(dev._read_reg(0x1084), 0x32000)
        self.assertEqual(dev._dma_get(0x32000, 12),
                         bytes.fromhex("012c0c000000000001000000"))
        with self.assertRaises(RuntimeError):
            dev.queue_hif_callback(1, 0x2c, b"\x00")
        dev._write_reg(0x1070, dev._read_reg(0x1070) & ~1)
        self.assertEqual(dev._read_reg(0x1070) & 1, 0)

    def test_hif_malformed_notification_does_not_send_success(self):
        from winc1510_spi_backend import Winc1510SPI
        dev = Winc1510SPI(hif_mailbox=True)
        dev._write_reg(0x106c, 0x400 << 2 | 2)
        self.assertEqual(dev.hif_requests, [])
        self.assertEqual(dev._read_reg(0x1070), 0)
        with self.assertRaises(ValueError):
            dev.queue_hif_callback(1, 0x2c, bytes(0x63c))
        legacy = Winc1510SPI(hif_mailbox=False)
        legacy._write_reg(0x1078, 2)
        self.assertEqual(legacy._read_reg(0x1078), 2)
        self.assertEqual(legacy._read_reg(0x150400), 0)

    def test_opt_in_original_rom_mac_and_version_read_over_spi(self):
        """Original A7 reads 0xC0008 -> pointer table -> two DMA records."""
        legacy = Winc1510SPI()
        self.assertEqual(legacy._read_reg(0xc0008), 0)
        dev = Winc1510SPI(fixture_identity=True)
        dev.shift(2, bytes.fromhex("ca0c0008"), begin=True)
        self.assertEqual(dev.shift(2, bytes(7), end=True),
                         bytes.fromhex("ca00f300100000"))
        dev.shift(2, bytes.fromhex("c20310000008"), begin=True)
        self.assertEqual(dev.shift(2, bytes(12), end=True),
                         bytes.fromhex("c200f3f30011000000120000"))
        dev.shift(2, bytes.fromhex("c20311000006"), begin=True)
        self.assertEqual(dev.shift(2, bytes(10), end=True),
                         bytes.fromhex("c200f3f3023570151001"))
        dev.shift(2, bytes.fromhex("c20312000028"), begin=True)
        payload = dev.shift(2, bytes(44), end=True)
        self.assertEqual(payload[:4], bytes.fromhex("c200f3f3"))
        self.assertEqual(payload[8:14], bytes((19, 6, 1, 19, 6, 1)))
        self.assertEqual(dev.hif_notifications, [])
        # The model's electrical reset retains configured ROM identity.
        dev.set_pins(reset_n=False)
        dev.set_pins(reset_n=True)
        self.assertEqual(dev._read_reg(0xc0008), 0x1000)

    def test_original_split_lpspi2_frames_preserve_winc_response(self):
        """Original A7 transmits a CRC command then polls 8-bit frames."""
        dev = Winc1510SPI(crc=True, fixture_identity=True,
                          frame_spanning_cs=True)
        self.assertEqual(dev.shift(2, bytes.fromhex("cfffffffaa"),
                                   begin=True, end=True), bytes([255]) * 5)
        self.assertEqual(dev.shift(2, bytes([0]), begin=True, end=True),
                         bytes([0xcf]))
        self.assertIsNone(dev.selected_pcs)
        self.assertEqual(dev.shift(2, bytes.fromhex("ca0c0008bc"),
                                   begin=True, end=True), bytes([255]) * 5)
        answer = b"".join(dev.shift(2, bytes([0]), begin=True, end=True)
                          for _ in range(7))
        self.assertEqual(answer, bytes.fromhex("ca00f300100000"))
        self.assertIsNone(dev.selected_pcs)
        self.assertEqual(dev._read_reg(0xc0008), 0x1000)

    def test_original_winc_hardware_ready_and_boot_status(self):
        """Original FUN_601c1298 waits on 0x1014[31] and 0x207bc[0]."""
        chip = Winc1510SPI(fixture_identity=True)
        self.assertEqual(chip._read_reg(0x1014), 0x80000000)
        self.assertEqual(chip._read_reg(0x207bc) & 1, 1)
        chip.set_pins(reset_n=False)
        self.assertEqual(chip._read_reg(0x1014), 0)
        chip.set_pins(reset_n=True)
        self.assertEqual(chip._read_reg(0x1014), 0x80000000)
        self.assertEqual(chip._read_reg(0x207bc) & 1, 1)

    def test_original_winc_firmware_boot_ack_does_not_inject_guest_events(self):
        chip = Winc1510SPI(fixture_identity=True, hif_mailbox=True)
        self.assertEqual(chip._read_reg(0x108c), 0)
        chip._write_reg(0x108c, 0x13301361)
        self.assertEqual(chip._read_reg(0x108c), 0x02532636)
        self.assertEqual(chip.hif_notifications, [])
        self.assertEqual(chip.hif_requests, [])
        self.assertEqual(chip._read_reg(0x1070), 0)
        chip._write_reg(0x108c, 0)
        self.assertEqual(chip._read_reg(0x108c), 0)

    def test_original_c8_data_start_and_next_real_command(self):
        """DY357 reads 8 bytes after C8 then sends a new CA command."""
        dev = Winc1510SPI(crc=True, fixture_identity=True,
                          frame_spanning_cs=True)
        dev.shift(2, bytes.fromhex("c8031000000800aa"),
                  begin=True, end=True)
        response = b"".join(dev.shift(2, bytes([0]), begin=True, end=True)
                            for _ in range(11))
        self.assertEqual(response, bytes.fromhex("c800f30011000000120000"))
        dev.shift(2, bytes.fromhex("ca001014aa"), begin=True, end=True)
        response = b"".join(dev.shift(2, bytes([0]), begin=True, end=True)
                            for _ in range(7))
        self.assertEqual(response, bytes.fromhex("ca00f300000080"))
        self.assertIn(("original-next-spi-command", 0xca), dev.events)
        self.assertEqual(dev.hif_notifications, [])

    def test_original_c8_mac_read_after_pointer_table(self):
        """Exercise the genuine original MAC address register/DMA chain."""
        device = Winc1510SPI(crc=True, fixture_identity=True,
                             frame_spanning_cs=True)
        cases = (
            ("ca0c0008aa", "ca00f300100000"),
            ("c8031000000008aa", "c800f30011000000120000"),
            ("c8031100000006aa", "c800f3023570151001"),
        )
        for command, expected in cases:
            device.shift(2, bytes.fromhex(command), begin=True, end=True)
            reply = b"".join(
                device.shift(2, bytes(1), begin=True, end=True)
                for _ in range(len(expected) // 2))
            self.assertEqual(reply, bytes.fromhex(expected))
        self.assertEqual(device.hif_notifications, [])
        self.assertIsNone(device.selected_pcs)

    @staticmethod
    def original_hif(dev, opcode, payload=b""):
        """Write complete source-derived HIF bytes and notify via WINC reg."""
        body = bytes((1, opcode)) + (8 + len(payload)).to_bytes(2, "little")
        body += bytes(4) + payload
        dev._dma_put(0x30000, body)
        dev._write_reg(0x106c, (0x30000 << 2) | 2)

    def test_real_hif_opcodes_ap_rssi_and_dhcp_fixture(self):
        dev = Winc1510SPI(hif_mailbox=True, fixture_ssid="TestBench",
                          fixture_ipv4="192.0.2.31", fixture_rssi_dbm=-61)
        self.original_hif(dev, 0xbb, b"TestBench" + bytes(39))
        self.assertTrue(dev.ap_connected)
        self.assertEqual(dev.hif_requests[-1]["opcode"], 0xbb)
        self.assertEqual(dev.hif_notifications, [(1, 0x2c, 12)])
        self.assertFalse(dev.irq_n)
        self.assertEqual(dev._dma_get(0x32008, 4), bytes((1, 0, 0, 0)))
        # The DHCP callback must wait until original A7 acknowledges IRQ.
        self.assertEqual(len(dev.deferred_callbacks), 1)
        dev._write_reg(0x1070, 0)
        # Original FUN_601c0970 ACKs BEFORE reading 0x1084/RAM.
        # That ACK must not replace association data with DHCP.
        self.assertEqual(dev._read_reg(0x1070), 0)
        self.assertEqual(dev._dma_get(0x32000, 12),
                         bytes.fromhex("012c0c000000000001000000"))
        self.assertEqual(dev.hif_notifications[-1], (1, 0x32, 32))
        self.assertEqual(dev._dma_get(0x32008, 4), bytes((192, 0, 2, 31)))
        dev._write_reg(0x1070, 0)
        dev._dma_get(0x32000, 32)
        self.original_hif(dev, 5)
        self.assertEqual(dev.hif_notifications[-1], (1, 6, 56))
        self.assertEqual(dev._dma_get(0x32008, 9), b"TestBench")
        self.assertEqual(dev._dma_get(0x32008 + 45, 1), bytes((6,)))
        dev._write_reg(0x1070, 0)
        dev._dma_get(0x32000, 56)
        self.original_hif(dev, 3)
        self.assertEqual(dev.hif_notifications[-1], (1, 4, 12))
        self.assertEqual(dev._dma_get(0x32008, 1), bytes((195,)))  # -61
        dev._write_reg(0x1070, 0)
        # Original A7 consumes the full RSSI callback before next
        # asynchronous device message may reuse HIF inbound RAM.
        dev._dma_get(0x32000, 12)
        self.original_hif(dev, 0x2b)
        self.assertFalse(dev.ap_connected)
        self.assertEqual(dev.hif_notifications[-1], (1, 0x2c, 12))

    def test_ap_fixture_negative_controls_and_power_request(self):
        offline = Winc1510SPI(hif_mailbox=True)
        self.original_hif(offline, 0xbb, b"TestBench" + bytes(39))
        self.assertFalse(offline.ap_connected)
        self.assertEqual(offline.hif_notifications, [])
        mismatch = Winc1510SPI(hif_mailbox=True, fixture_ssid="TestBench")
        self.original_hif(mismatch, 0xbb, b"OtherSSID" + bytes(39))
        self.assertFalse(mismatch.ap_connected)
        self.assertEqual(mismatch._dma_get(0x32008, 2), bytes((0, 1)))
        mismatch._write_reg(0x1070, 0)
        self.original_hif(mismatch, 0x2d, bytes((3, 1, 0, 0)))
        self.assertEqual(mismatch.power_save_mode, (3, 1))
        self.assertFalse(mismatch.ap_connected)
        self.assertTrue(mismatch.irq_n)
        mismatch.set_pins(reset_n=False)
        self.assertIsNone(mismatch.power_save_mode)
        self.assertEqual(mismatch.hif_notifications, [])
        with self.assertRaises(ValueError):
            Winc1510SPI(fixture_ipv4="192.0.2.20")
        with self.assertRaises(ValueError):
            Winc1510SPI(hif_mailbox=True, fixture_ssid="TestBench",
                        fixture_ipv4="300.1.1.1")
        with self.assertRaises(ValueError):
            Winc1510SPI(hif_mailbox=True, fixture_ssid="TestBench",
                        fixture_rssi_dbm=0)

    def test_original_c7_dma_write_crc_then_data_packet_ack(self):
        """Original A7 601c1af0 -> 601c18c4 checks C3/00, not FF/00.

        The guest writes F3 block marker, 8-byte HIF header, CRC16,
        then separately reads a 2-byte data acknowledgment. The HIF
        notification must still be an ORIGINAL A7 0x106c register write.
        """
        dev = Winc1510SPI(crc=True, frame_spanning_cs=True,
                          hif_mailbox=True, fixture_identity=True)
        cmd = bytes.fromhex("c7030000000008aa")
        self.assertEqual(dev.shift(2, cmd, begin=True, end=True),
                         bytes([255]) * len(cmd))
        ack = b"".join(dev.shift(2, bytes([0]), begin=True, end=True)
                       for _ in range(3))
        self.assertEqual(ack, bytes.fromhex("c700f3"))
        # Command-echo polling never contaminates HIF DMA RAM.
        self.assertEqual(dev._dma_get(0x30000, 8), bytes(8))
        dev.shift(2, bytes.fromhex("f3"), begin=True, end=True)
        header = bytes.fromhex("013b0c0000000000")
        dev.shift(2, header, begin=True, end=True)
        self.assertEqual(dev._dma_get(0x30000, 8), header)
        # Original FUN_601c18c4 reads exactly three clocks after the
        # last data byte; the response must be FF,C3,00 (not FF,FF,C3).
        self.assertEqual(dev.shift(2, bytes(3), begin=True, end=True),
                         bytes.fromhex("ffc300"))
        self.assertIsNone(dev.selected_pcs)
        self.assertIn(("dma-write-data-ack",), dev.events)
        self.assertEqual(dev.hif_requests, [])
        self.assertEqual(dev.hif_notifications, [])

    def test_complete_original_spi_c7_hif_ap_notification(self):
        """No direct _dma_put/_write_reg calls: replay A7 MOSI frames."""
        dev = Winc1510SPI(crc=True, frame_spanning_cs=True,
                          fixture_identity=True, hif_mailbox=True,
                          fixture_ssid="BenchAP", fixture_ipv4="192.0.2.31")

        def shift(data):
            return dev.shift(2, data, begin=True, end=True)

        def dma_write(address, data):
            cmd = b"\xc7" + address.to_bytes(3, "big")
            cmd += len(data).to_bytes(3, "big")
            self.assertEqual(shift(cmd), bytes([255]) * 7)
            self.assertEqual(shift(bytes(1)), bytes([255]))
            self.assertEqual(shift(bytes(2)), bytes.fromhex("c700"))
            self.assertEqual(shift(bytes.fromhex("f3")), bytes.fromhex("f3"))
            shift(data)
            self.assertEqual(shift(bytes(3)), bytes.fromhex("ffc300"))

        payload = b"BenchAP" + bytes(41)
        header = bytes((1, 0xbb))
        header += (8 + len(payload)).to_bytes(2, "little") + bytes(4)
        dma_write(0x30000, header)
        dma_write(0x30008, payload)
        self.assertEqual(dev.hif_requests, [])
        # The HIF event is sent only after actual original A7 SPI
        # register write (C9) to the WINC internal mailbox 0x106C.
        notify = b"\xc9" + (0x106c).to_bytes(3, "big")
        notify += ((0x30000 << 2) | 2).to_bytes(4, "big")
        self.assertEqual(shift(notify), bytes([255]) * 8)
        self.assertEqual(shift(bytes(3)), bytes.fromhex("ffc900"))
        self.assertEqual(len(dev.hif_requests), 1)
        self.assertEqual(dev.hif_requests[0]["opcode"], 0xbb)
        self.assertTrue(dev.ap_connected)
        self.assertEqual(dev.hif_notifications, [(1, 0x2c, 12)])
        self.assertEqual(len(dev.deferred_callbacks), 1)

    def test_original_e04_clock_activation_and_reset_negative_controls(self):
        """Original FUN_601c10f8: 0xB[0], 0x1[1] -> 0xF[2].

        Without 0xF bit2 the real A7 returns -4 (factory E04).
        The model must not return ready before the ORIGINAL SPI
        register initialization, nor while the card is disabled.
        """
        dev = Winc1510SPI(fixture_identity=True)
        self.assertEqual(dev._read_reg(0xf) & 4, 0)
        dev._write_reg(0xb, 1)
        self.assertEqual(dev._read_reg(0xf) & 4, 0)
        dev._write_reg(1, 2)
        self.assertEqual(dev._read_reg(0xf) & 4, 4)
        dev.set_pins(reset_n=False)
        self.assertEqual(dev._read_reg(0xf) & 4, 0)
        dev.set_pins(reset_n=True)
        self.assertEqual(dev._read_reg(0xf) & 4, 0)
        dev._write_reg(0xb, 1)
        dev._write_reg(1, 2)
        self.assertEqual(dev._read_reg(0xf) & 4, 4)
        legacy = Winc1510SPI()
        legacy._write_reg(0xb, 1)
        legacy._write_reg(1, 2)
        self.assertEqual(legacy._read_reg(0xf) & 4, 0)

    def test_original_72_byte_wpa_ap_hif_three_real_spi_dma_writes(self):
        """A7 FUN_601c0708(1,BB,48+16) must reach 0x106c as one HIF.

        The previous original E06 trace clocked a separate 108-byte message but never
        reached a connection callback. Replay the complete A7 physical
        SPI sequence instead of writing mailbox state directly.
        """
        dev = Winc1510SPI(crc=True, frame_spanning_cs=True,
                          fixture_identity=True, hif_mailbox=True,
                          fixture_ssid="BenchAP",
                          fixture_ipv4="192.0.2.31")

        def spi(data):
            return dev.shift(2, data, begin=True, end=True)

        def write_block(addr, content):
            cmd = bytes((0xc7,)) + addr.to_bytes(3, "big")
            cmd += len(content).to_bytes(3, "big") + bytes((0xaa,))
            spi(cmd)
            self.assertEqual(spi(bytes(3)), bytes.fromhex("c700f3"))
            spi(bytes.fromhex("f3"))
            spi(content)
            self.assertEqual(spi(bytes(3)), bytes.fromhex("ffc300"))
            self.assertIsNone(dev.selected_pcs)

        body = bytearray(48)
        body[0:7] = b"BenchAP"
        security = bytes(16)
        length = 8 + len(body) + len(security)
        hif = bytes((1, 0xbb)) + length.to_bytes(2, "little") + bytes(4)
        write_block(0x30000, hif)
        write_block(0x30008, bytes(body))
        write_block(0x30038, security)
        self.assertEqual(dev.hif_requests, [])
        command = bytes((0xc9,)) + (0x106c).to_bytes(3, "big")
        command += ((0x30000 << 2) | 2).to_bytes(4, "big")
        command += bytes((0xaa,))
        spi(command)
        self.assertEqual(spi(bytes(3)), bytes.fromhex("c900ff"))
        self.assertEqual(len(dev.hif_requests), 1)
        self.assertEqual(dev.hif_requests[0]["opcode"], 0xbb)
        self.assertEqual(dev.hif_requests[0]["length"], 72)
        self.assertTrue(dev.ap_connected)
        self.assertEqual(dev.hif_notifications[0][:2], (1, 0x2c))
        self.assertEqual(dev.deferred_callbacks[0][:2], (1, 0x32))

    def test_original_auto_deep_sleep_two_real_hif_commands(self):
        """A7 FUN_601cab94 emits group1 0x2D then 0x39, no magic OK."""
        dev = Winc1510SPI(hif_mailbox=True, fixture_identity=True)
        self.assertIsNone(dev.power_save_mode)
        self.assertIsNone(dev.sleep_hint)
        self.original_hif(dev, 0x2d, bytes((3, 1, 0, 0)))
        self.assertEqual(dev.power_save_mode, (3, 1))
        self.assertIsNone(dev.sleep_hint)
        self.original_hif(dev, 0x39, bytes((1, 0, 0, 0)))
        self.assertEqual(dev.sleep_hint, 1)
        self.assertEqual(dev.hif_notifications, [])
        self.assertFalse(dev.ap_connected)
        dev.set_pins(reset_n=False)
        self.assertIsNone(dev.power_save_mode)
        self.assertIsNone(dev.sleep_hint)

    def test_hif_request_between_original_irq_ack_and_dma_read_is_deferred(self):
        """No overwrite after 0x1070 ACK; A7 must first finish C8 read."""
        dev = Winc1510SPI(hif_mailbox=True, fixture_ssid="BenchAP")
        self.original_hif(dev, 0xbb, b"BenchAP" + bytes(41))
        self.assertEqual(dev.hif_notifications, [(1, 0x2c, 12)])
        dev._write_reg(0x1070, 0)  # original A7 ACK before fetching RAM
        self.assertTrue(dev.hif_ack_draining)
        self.original_hif(dev, 3)  # a second actual original HIF request
        # RSSI query needs association and must be queued, not overwrite
        # the 0x2c connection state that the original has yet to read.
        self.assertEqual(len(dev.deferred_callbacks), 1)
        self.assertEqual(dev.hif_notifications, [(1, 0x2c, 12)])
        original_connection = dev._dma_get(0x32000, 12)
        self.assertEqual(original_connection,
                         bytes.fromhex("012c0c000000000001000000"))
        self.assertEqual(dev.hif_notifications[-1], (1, 4, 12))
        self.assertFalse(dev.hif_ack_draining)
        dev._write_reg(0x1070, 0)
        self.assertEqual(dev._dma_get(0x32008, 1), bytes((201,)))

    def test_optional_crc_extra_command_byte(self):
        dev=Winc1510SPI(crc=True)
        dev.shift(0,bytes.fromhex("ca0010005a"),begin=True)
        self.assertEqual(dev.shift(0,bytes(7),end=True),
                         bytes.fromhex("ca00f3b0021000"))


if __name__ == "__main__":
    unittest.main()
