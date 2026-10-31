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

    def test_optional_crc_extra_command_byte(self):
        dev=Winc1510SPI(crc=True)
        dev.shift(0,bytes.fromhex("ca0010005a"),begin=True)
        self.assertEqual(dev.shift(0,bytes(7),end=True),
                         bytes.fromhex("ca00f3b0021000"))


if __name__ == "__main__":
    unittest.main()
