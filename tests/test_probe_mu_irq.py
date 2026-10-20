"""Firmware-free regressions for nonconsuming MU IRQ state decoder."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from probe_mu_irq import decode

class MuStatusTests(unittest.TestCase):
    def test_first_irq_is_receive_channel_two_not_general_purpose(self):
        x=decode(0x04f00000,0xff000000)
        self.assertEqual((x["rf"],x["rien"],x["gip"]),(4,15,0))
        self.assertEqual(x["irq_sources"],{"tx_empty":0,"rx_full":4,"general":0})
    def test_second_and_repeated_irq_is_receive_channel_zero(self):
        x=decode(0x05f00000,0xfb000000)
        self.assertEqual((x["rf"],x["rien"],x["gip"]),(5,11,0))
        self.assertEqual(x["irq_sources"],{"tx_empty":0,"rx_full":1,"general":0})
    def test_no_interrupt_when_receive_interrupt_disabled(self):
        x=decode(0x05f00000,0xf0000000)
        self.assertEqual(x["irq_sources"]["rx_full"],0)

if __name__=="__main__":
    unittest.main()
