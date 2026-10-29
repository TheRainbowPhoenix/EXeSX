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
                         bytes.fromhex("ca00f3001002b0"))
        self.assertIsNone(self.dev.selected_pcs)

    def test_register_write_and_subsequent_read(self):
        self.dev.shift(1,bytes.fromhex("c900108c12345678"),begin=True,end=True)
        self.assertEqual(self.dev.registers[0x108c],0x12345678)
        self.dev.shift(1,bytes.fromhex("ca00108c"),begin=True)
        self.assertEqual(self.dev.shift(1,bytes(7),end=True),
                         bytes.fromhex("ca00f312345678"))

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

    def test_optional_crc_extra_command_byte(self):
        dev=Winc1510SPI(crc=True)
        dev.shift(0,bytes.fromhex("ca0010005a"),begin=True)
        self.assertEqual(dev.shift(0,bytes(7),end=True),
                         bytes.fromhex("ca00f3001002b0"))


if __name__ == "__main__":
    unittest.main()
