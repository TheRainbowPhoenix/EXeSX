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
