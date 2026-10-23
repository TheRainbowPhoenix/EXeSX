import importlib.util
from pathlib import Path
import unittest
import os
import sys

SPEC = importlib.util.spec_from_file_location(
    'hmp_memory', Path(__file__).resolve().parents[1] / 'scripts/hmp_memory.py')
hmp_memory = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hmp_memory)


class HmpMemoryTests(unittest.TestCase):
    def test_bulk_dump_windows_console_and_crlf(self):
        output = ('(qemu) xp /6wx 0x62002000\x1b[K\r\r\n'
                  '\x1b[K0000000062002000: 0x00000010 0x00000000 0x12345678 0xffffffff\r\r\n'
                  '0000000062002010: 0x00000001 0x00000002\r\r\n(qemu) ')
        self.assertEqual(hmp_memory.memory_words(output, 0x62002000, 6),
                         [16, 0, 0x12345678, 0xffffffff, 1, 2])

    def test_single_word_linux_dump(self):
        self.assertEqual(hmp_memory.memory_words('62000000: 0x45585358\n',
                                                0x62000000, 1), [0x45585358])

    def test_missing_word_fails_with_address(self):
        with self.assertRaisesRegex(AssertionError, '0x62002004'):
            hmp_memory.memory_words('62002000: 0x1\n', 0x62002000, 2)


    def test_qmp_survives_heavy_child_diagnostics(self):
        # A noisy fake QEMU produces >256 KiB of output BEFORE answering its
        # first QMP command. Using an unread subprocess.PIPE would deadlock.
        fake_qemu = r'''
import json
import re
import socket
import sys
arg = sys.argv[sys.argv.index("-qmp") + 1]
port = int(re.search(r":(\d+),server=on", arg).group(1))
with socket.socket() as listener:
    listener.bind(("127.0.0.1", port))
    listener.listen(1)
    with listener.accept()[0] as conn:
        conn.sendall((json.dumps({"QMP": {"version": {}, "capabilities": []}}) + "\n").encode())
        with conn.makefile("rb") as incoming:
            for line in incoming:
                request = json.loads(line)
                # Real EXeSX QEMU emits large diagnostic profile logs.
                sys.stdout.write("early board diagnostics\n" * 16000)
                sys.stdout.flush()
                name = request["execute"]
                result = ("62002000: 0x00000010 0x00000020\n" if
                          name == "human-monitor-command" else {})
                conn.sendall((json.dumps({"return": result}) + "\n").encode())
                if name == "human-monitor-command":
                    break
'''
        values = hmp_memory.qmp_memory_words(
            [sys.executable, "-u", "-c", fake_qemu, "-monitor", "stdio"],
            os.environ.copy(), 0x62002000, 2, delay=0.01)
        self.assertEqual(values, [0x10, 0x20])
