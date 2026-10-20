"""Firmware-free verification of A7 semaphore/MU trace reducer."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1] / "scripts"))
from analyze_a7_kernel_mu import analyze

class Tests(unittest.TestCase):
    def test_counts(self):
        sample='''EXESX_ACCESS cpu=0 pc=0x601e19cc kind=WRITE virtual=0x621eaedc physical=0x621eaedc width=2 backing=RAM
EXESX_ACCESS cpu=0 pc=0x601e17a4 kind=WRITE virtual=0x621eaedc physical=0x621eaedc width=2 backing=RAM
EXeSX MU busy TR2 at 0x40220028 ignored data=0x00000001\\n
EXeSX MU WRITE @0x41022060 data=0x00000000
...taking pending nonsecure exception 38
Exception return: magic PC fffffffd previous exception 38
'''
        r=analyze(sample)
        self.assertEqual(r["a7_semaphore31"]["count_decrement_writes"],1)
        self.assertEqual(r["a7_semaphore31"]["count_increment_writes"],1)
        self.assertEqual(r["messaging_unit"]["busy_transmit_attempts"]["TR2@0x40220028"],1)
        self.assertEqual(r["m4_irq22"]["entries_per_zero_status_write"],1)

    def test_absent_events_are_not_success(self):
        r=analyze("IN: 0x60179a7c:")
        self.assertEqual(r["m4_irq22"]["entries"],0)
        self.assertIsNone(r["m4_irq22"]["entries_per_zero_status_write"])

if __name__=="__main__":
    unittest.main()
