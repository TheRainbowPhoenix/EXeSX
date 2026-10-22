"""Synthetic only — test the private LCD trace metadata decoder."""
import importlib.util
from pathlib import Path
import unittest

p = Path(__file__).resolve().parents[1] / "scripts/decode_lcd_bus_trace.py"
spec = importlib.util.spec_from_file_location("lcdtrace", p)
lcdtrace = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lcdtrace)


def line(pc, val, width=2, addr=0xb0000000):
    return (f"EXESX_VALUE cpu=0 pc=0x{pc:08x} kind=WRITE "
            f"virtual=0x{addr:08x} width={width} value=0x{val:08x}")


class LcdTraceTests(unittest.TestCase):
    def test_realistic_init_and_rgb565_data(self):
        data = [
            line(0x6001514c, 0x35), line(0x600151f8, 0),
            line(0x6001514c, 0x3a), line(0x600151f8, 0x55),
            line(0x60015268, 0x2a),
            *(line(0x6001527c, x) for x in (0,0,3,0x35f)),
            line(0x600152c0, 0x2b),
            *(line(0x600152d4, x) for x in (0,0,1,0x1df)),
            line(0x60015314, 0x2c),
            line(0x6001550c, 0xffff),
            line(0x60015518, 0xffff),
            line(0x60015518, 0xf800),
        ]
        result = lcdtrace.decode_lines(data)
        self.assertTrue(result["te_enable_observed"])
        self.assertTrue(result["rgb565_mode_observed"])
        self.assertEqual(result["column_windows"][0]["count"], 864)
        self.assertEqual(result["row_windows"][0]["count"], 480)
        self.assertEqual(result["column_windows"][0]["params_above_byte_range"], 1)
        self.assertEqual(result["pixel_samples"],3)
        self.assertEqual(result["pixel_top_colors"][0],
                         {"rgb565":"0xffff","count":2})
        self.assertEqual(result["write_widths"],{2:18})

    def test_legacy_capture_and_control_write(self):
        lines = [
            "EXESX_LCD cpu=0 pc=6001514c addr=b0000000 width=2 val=0000002a",
            "EXESX_LCD cpu=0 pc=600151f8 addr=b0000000 width=2 val=00000000",
            "EXESX_LCD cpu=0 pc=600151f8 addr=b0000000 width=2 val=00000000",
            "EXESX_LCD cpu=0 pc=600151f8 addr=b0000000 width=2 val=00000003",
            "EXESX_LCD cpu=0 pc=600151f8 addr=b0000000 width=2 val=0000001f",
            "EXESX_LCD cpu=0 pc=60015900 addr=44f00000 width=4 val=00010000"]
        result = lcdtrace.decode_lines(lines)
        self.assertEqual(result["column_windows"][0]["count"],800)
        self.assertEqual(result["other_bus_control_write_count"],1)
        self.assertEqual(result["pixel_samples"],0)

if __name__=="__main__":
    unittest.main()
