"""Synthetic, firmware-free DMA descriptor and eMMC trace decoder regressions."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

def load(name):
    spec=importlib.util.spec_from_file_location(name, ROOT/"scripts"/(name+".py"))
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

dma=load("inspect_dma1_tcd")
mmc=load("inspect_emmc_cmds")

class DMAAndMMCMetadataTests(unittest.TestCase):
    def test_tcd_major_copy_has_no_completion(self):
        base=0x400811e0
        words=[0x61080000, 0x05050020, 0x000ca800, 0,
               0x6114a800, 0x00010020, 0, 0x0001000a]
        decoded=dma.decode_tcd({base+i*4:x for i,x in enumerate(words)},15)
        self.assertEqual(decoded["minor_bytes"],0xca800)
        self.assertEqual((decoded["citer"],decoded["biter"]),(1,1))
        self.assertEqual((decoded["source_offset"],decoded["dest_offset"]),(32,32))
        self.assertTrue(decoded["ram_to_ram_candidate"])
        self.assertFalse(decoded["done"])
        self.assertTrue(decoded["disable_request"])

    def test_missing_register_is_not_silently_zero(self):
        with self.assertRaisesRegex(ValueError,"missing"):
            dma.decode_tcd({0x400811e0:0x61080000},15)

    def test_monitor_ansi_and_width(self):
        text="\\x1b[0m00000000400811fc: 0x0001000a\\n"
        self.assertEqual(dma.parse_monitor(text)[0x400811fc],0x1000a)

    def test_cmd6_selects_boot1_and_cmd17_is_partition_relative(self):
        trace=(
            "sdhci_send_command CMD06 ARG[0x03b30200]\\n"
            "sdhci_send_command CMD17 ARG[0x00000000]\\n"
            "sdhci_send_command CMD17 ARG[0x00000020]\\n"
        )
        items=mmc.decode(trace)
        self.assertEqual(items[0]["selected_partition"],"boot1")
        self.assertEqual([r["block_address"] for r in items[1:]],[0,32])
        self.assertEqual([r["byte_offset"] for r in items[1:]],[0,16384])
        self.assertTrue(all(r["partition"]=="boot1" for r in items[1:]))

if __name__=="__main__":
    unittest.main()
