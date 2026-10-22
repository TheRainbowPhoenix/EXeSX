"""Firmware-free tests of command-state and OS entry trace audit."""
import importlib.util
from pathlib import Path
import unittest

source = Path(__file__).resolve().parents[1] / "scripts/audit_osup_boot_handoff.py"
spec = importlib.util.spec_from_file_location("audit", source)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class HandoffAuditTests(unittest.TestCase):
    def test_partition_switch_32_block_reads_and_idle(self):
        data = ("sdhci_send_command CMD06 ARG[0x03b30200]\n"
                "sdhci_send_command CMD17 ARG[0x00000000]\n"
                "sdhci_send_command CMD18 ARG[0x00000040]\n"
                "sdhci_send_command CMD18 ARG[0x00000060]\n"
                "sdhci_send_command CMD06 ARG[0x03b30000]\n"
                "sdhci_send_command CMD17 ARG[0x00000000]\n"
                "sdhci_send_command CMD17 ARG[0x01af5fff]\n"
                "IN:\n0x601cbcf0:  \nOBJD-T: 03f020e3\n"
                "IN:\n0x60007f88:  \n")
        report=mod.audit(data)
        self.assertEqual([(x["partition"],x["lba"]) for x in report["read_lbas"]],
                         [("boot1",0),("boot1",64),("boot1",96),
                          ("user",0),("user",0x01af5fff)])
        self.assertEqual(report["translated_in_os_region"],0)
        self.assertEqual(report["bios_idle_sites_seen"],["0x601cbcf0"])
        self.assertTrue(report["user_region_capacity_probe_hypothesis"])
        self.assertFalse(report["os_entry_translation_observed"])
        self.assertTrue(report["translation_is_not_execution_count"])

    def test_os_entry_is_observed_only_when_translated(self):
        report=mod.audit("IN:\n0x605e3ad0:  \n"
                         "sdhci_send_command CMD13 ARG[0x00020000]\n")
        self.assertTrue(report["os_entry_translation_observed"])
        self.assertEqual(report["translated_in_os_region"],1)

if __name__=="__main__":
    unittest.main()
