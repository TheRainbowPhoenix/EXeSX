"""Host-only regressions for full 49-key original-ROM map and worker UI."""
import importlib.util
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import factory_control_panel as gui
from lcd_qmp import rgb565_to_rgb888, FRAME_BYTES


class FloatingKeyboardTests(unittest.TestCase):
    def test_49_original_m4_keys_and_all_letters(self):
        source = (ROOT / "hw/arm/exesx-imx7ulp-keyboard.inc").read_text()
        m = re.search(r"static const EXeSXM4KeyContact exesx_m4_key_contacts\[\] = \{(.*?)\};",
                      source, re.S)
        self.assertIsNotNone(m)
        entries = [(int(code,16), int(row), int(col))
                   for code,row,col in re.findall(
                       r"\{\s*0x([0-9a-fA-F]+),\s*(\d+),\s*(\d+)\s*\}", m[1])]
        self.assertEqual(len(entries),49)
        self.assertEqual(len({code for code,_,_ in entries}),49)
        by_code = {code:(row,col) for code,row,col in entries}
        self.assertEqual(by_code[0x9c], (4,5))
        self.assertEqual(by_code[0x90], (7,6))
        self.assertEqual(by_code[0x93], (8,7))
        self.assertEqual(by_code[0x94], (6,6))
        self.assertEqual(by_code[0x91], (6,7))
        for label in "".join(gui.ASCII_ROWS):
            self.assertIn(ord(label.lower()), by_code)

    def test_rgb565_reads_only_original_pixels(self):
        self.assertEqual(FRAME_BYTES,829440)
        class FakeMmap:
            def __len__(self): return FRAME_BYTES
            def __getitem__(self, item):
                if isinstance(item,slice): return b"\x00\xf8"*414720
                raise IndexError
        pixels = gui.pure_rgb565_lcd(FakeMmap())
        self.assertEqual(pixels[:6], b"\xff\x00\x00"*2)
        self.assertEqual(len(pixels),864*480*3)

    def test_original_menu_highlight_survives_header_inversion(self):
        white = bytearray(b"\xff" * (864 * 480 * 3))
        self.assertIsNone(gui.original_menu_highlight(white))
        for y in range(25, 49):
            for x in (610, 720, 820, 850):
                pos = 3 * (864*y + x)
                white[pos:pos+3] = b"\x00\x00\x00"
        self.assertEqual(gui.original_menu_highlight(white), 25)
        # Header inversion must not make valid selected-row detection fail.
        for x in range(864):
            pos = 3 * (864*10 + x)
            white[pos:pos+3] = b"\xff\xff\xff"
        self.assertEqual(gui.original_menu_highlight(white), 25)
        for y in range(25, 49):
            for x in (610, 720, 820, 850):
                pos = 3 * (864*y + x)
                white[pos:pos+3] = b"\xff\xff\xff"
        for y in range(72, 96):
            for x in (610, 720, 820, 850):
                pos = 3 * (864*y + x)
                white[pos:pos+3] = b"\x00\x00\x00"
        self.assertEqual(gui.original_menu_highlight(white), 72)

    def test_headless_factory_ipc_parser_and_blocked_semantics(self):
        from headless_factory_menu_checks import parse_ipc_dump, check
        payload = ("0x2f028000: 0xeeeeeeee 0x00000000 0x04010800 0x0001400b\n"
                   "0x2f028010: 0x00000002 0x000000af\n")
        result = parse_ipc_dump(payload)
        self.assertEqual(result["request"], "0x0001400b")
        self.assertEqual(result["argument"], 2)
        self.assertEqual(result["status"], "0x04010800")
        self.assertEqual(check("menu painter", False, "IPC not completed")["status"],
                         "BLOCKED")
        self.assertEqual(check("menu painter", False)["status"], "FAIL")

    def test_event10_guard_read_only_decoder(self):
        from headless_factory_menu_checks import parse_m4_event10_guard
        normal = parse_m4_event10_guard("000000001ffecd58: 0x00000000")
        self.assertTrue(normal["accessible"])
        self.assertFalse(normal["bit0_or_bit2_blocks_event10"])
        for mask in (1, 4, 5):
            guard = parse_m4_event10_guard(
                "000000001ffecd58: 0x{:08x}".format(mask))
            self.assertTrue(guard["bit0_or_bit2_blocks_event10"])
        inaccessible = parse_m4_event10_guard("Cannot access memory")
        self.assertFalse(inaccessible["accessible"])
        self.assertIsNone(inaccessible["bit0_or_bit2_blocks_event10"])

    def test_single_tcg_factory_combo_checks_scan_and_release_and_real_a7_gate(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        import queue

        actions, updates = queue.Queue(), queue.Queue()
        args = SimpleNamespace(tcg_thread="single", hold=.08, gap=.06)
        worker = gui.EmulatorWorker(args, actions, updates)
        worker.mode = "menu"
        worker.sequence = ["0x93", "0x93", "0x94"]
        worker.seq_gated = True
        worker.seq_stage = "press"
        worker.seq_deadline = 0
        contacts = []
        worker.physical = lambda code: contacts.append(code)

        class FakeQMP:
            def __init__(self):
                self.states = iter([2, 0, 2, 0, 2, 0])

            def hmp(self, command):
                assert command == "xp /1wx 0x1ffea320"
                return "000000001ffea320: 0x{:08x}".format(next(self.states))

        worker.qmp = FakeQMP()
        for t in (1, 1.08, 1.16, 1.24, 1.32, 1.40,
                  1.48, 1.56, 1.64):
            with patch.object(gui.time, "monotonic", return_value=t):
                worker.sequence_step()
        self.assertEqual(contacts, [0x93, None, 0x93, None, 0x94, None])
        self.assertEqual(worker.sequence, [])
        self.assertFalse(worker.seq_gated)
        self.assertIsNotNone(worker.last_menu_keys_at)

    def test_factory_combo_does_not_send_next_key_without_release(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        import queue
        worker = gui.EmulatorWorker(
            SimpleNamespace(tcg_thread="single", hold=.08, gap=.06),
            queue.Queue(), queue.Queue())
        worker.mode = "menu"
        worker.sequence = ["0x93", "0x93", "0x94"]
        worker.seq_gated = True
        worker.seq_stage = "press"
        worker.seq_deadline = 0
        contacts = []
        worker.physical = lambda code: contacts.append(code)
        class StillHeld:
            def hmp(self, command):
                return "000000001ffea320: 0x00000002"
        worker.qmp = StillHeld()
        for t in (1.0, 1.08, 1.2, 4.61):
            with patch.object(gui.time, "monotonic", return_value=t):
                worker.sequence_step()
        self.assertEqual(contacts, [0x93, None, None])
        self.assertFalse(worker.sequence)
        self.assertFalse(worker.seq_gated)

    def test_original_factory_verdict_is_read_only_and_never_guessed(self):
        data = [1, 0xffffffff, 0xfffffffe] + [0] * 13
        raw = "\\n".join(
            "000000006234{:04x}: ".format(0x4ef0 + 4*i) +
            " ".join("0x{:08x}".format(n) for n in data[i:i+4])
            for i in range(0, 16, 4))
        result = gui.decode_original_factory_results(
            raw, "0000000062344eec: 0x00000001",
            "0000000062413258: 0x03000000")
        self.assertTrue(result["accessible"])
        self.assertTrue(result["active"])
        self.assertEqual(result["cursor"], 3)
        self.assertEqual([(e["slot"], e["status"]) for e in result["entries"]],
                         [(1, "OK"), (2, "NG"), (3, "SKIPPED")])
        unwritten = gui.decode_original_factory_results(
            raw.replace("0x00000001", "0x00000000")
               .replace("0xffffffff", "0x00000000")
               .replace("0xfffffffe", "0x00000000"),
            "0000000062344eec: 0x00000001",
            "0000000062413258: 0x03000000")
        self.assertEqual(unwritten["entries"], [])
        self.assertFalse(gui.decode_original_factory_results(
            "Cannot access memory", "", "")["accessible"])

    def test_raw_key_labels_are_not_guessed(self):
        self.assertIn(("DOWN",0x91), gui.KNOWN)
        self.assertIn(("BOOT",0x9c), gui.KNOWN)
        self.assertIn(("0x94",0x94), gui.KNOWN)


if __name__ == "__main__":
    unittest.main()
