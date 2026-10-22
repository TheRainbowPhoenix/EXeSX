"""Firmware-free unit checks of post-DMA GDB probe packet decoding and scope."""
import importlib.util
from pathlib import Path
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("postdma_probe", ROOT/"scripts/probe_postdma_handoff.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class HandoffProbeTests(unittest.TestCase):
    def test_rsp_packet_checksum(self):
        self.assertEqual(probe.encode_packet("Hg1"), b"$Hg1#d0")
        self.assertEqual(probe.encode_packet("c"), b"$c#63")

    def test_arm_register_endianness(self):
        values = list(range(16))
        values[15] = 0x60048924
        values[14] = 0x6001AE68
        data = struct.pack("<16I", *values).hex()
        regs = probe.decode_registers(data)
        self.assertEqual(regs["r0"], 0)
        self.assertEqual(regs["r14"], 0x6001AE68)
        self.assertEqual(regs["r15"], 0x60048924)
        with self.assertRaises(ValueError):
            probe.decode_registers("deadbeef")

    def test_evidence_only_milestones(self):
        self.assertIn(0x601b450c, probe.MILESTONES)
        self.assertIn(0x60049c04, probe.MILESTONES)
        self.assertIn(0x60400000, probe.MILESTONES)
        self.assertEqual(probe.STATE["service_ready_byte"], (0x62413241, 1))
        self.assertEqual(probe.STATE["component_bits"], (0x622e6fc4, 4))


if __name__ == "__main__":
    unittest.main()
