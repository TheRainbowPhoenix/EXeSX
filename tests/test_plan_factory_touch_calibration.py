"""No private firmware required: verify BU21029 factory calibration planner."""
import importlib.util
from pathlib import Path
import struct
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "plan_factory_touch_calibration.py"
spec = importlib.util.spec_from_file_location("plan_factory_touch_calibration", SCRIPT)
planner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(planner)


def fake_elf():
    data = bytearray(0x1000)
    data[:16] = b"\x7fELF\x01\x01\x01" + bytes(9)
    struct.pack_into("<HHIIIIIHHHHHH", data, 16,
                     2, 40, 1, 0x60174d00, 52, 0, 0,
                     52, 32, 1, 0, 0, 0)
    struct.pack_into("<8I", data, 52, 1, 0x100,
                     0x60174d00, 0x60174d00, 0x400, 0x400, 5, 0x100)
    four = [(0,100,200,900,1100),(1,2000,300,3900,1200),
            (2,110,2200,890,3400),(3,2100,2300,3800,3500)]
    two = [four[0],four[3]]
    for address, regions in [(0x60174d88,four),(0x60174dc4,two)]:
        start=0x100+address-0x60174d00
        for i,entry in enumerate(regions):
            struct.pack_into("<iHHHH",data,start+i*12,*entry)
        struct.pack_into("<iHHHH",data,start+len(regions)*12,-1,0,0,0,0)
    return bytes(data)


class CalibrationTouchTests(unittest.TestCase):
    def test_four_points_and_exact_one_touch_packet_layout(self):
        recs=planner.source_rectangles(fake_elf(),"four")
        self.assertEqual(len(recs),4)
        self.assertEqual(recs[0]["physical_contact"],"1 500 650 800 1200")
        packet=bytes.fromhex(recs[0]["serial_14_byte_hex"])
        self.assertEqual(len(packet),14)
        words=struct.unpack(">7H",packet)
        self.assertEqual(words,(650<<4,500<<4,800<<4,1200<<4,0,0,0))

    def test_two_point_region_count(self):
        recs=planner.source_rectangles(fake_elf(),"two")
        self.assertEqual(len(recs),2)
        self.assertEqual([x["target"] for x in recs],[0,1])

    def test_wrong_firmware_and_invalid_table_fail_closed(self):
        with self.assertRaises(ValueError):
            planner.source_rectangles(b"not ELF","four")
        data=bytearray(fake_elf())
        struct.pack_into("<H",data,0x100+0x88+4, 4095)
        struct.pack_into("<H",data,0x100+0x88+8, 10)
        with self.assertRaises(ValueError):
            planner.source_rectangles(bytes(data),"four")


if __name__=="__main__":
    unittest.main()
