"""Exercise recursive PE dependency closure without a Windows toolchain."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    'bundle_windows', Path(__file__).resolve().parents[1] / 'scripts/bundle_windows.py')
bundle_windows = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bundle_windows)


class WindowsBundleTests(unittest.TestCase):
    def run_bundle(self, imports):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prefix = root / 'mingw64'
            (prefix / 'bin').mkdir(parents=True)
            (prefix / 'share/licenses').mkdir(parents=True)
            (root / 'windows/System32').mkdir(parents=True)
            (root / 'windows/System32/KERNEL32.dll').touch()
            executable = root / 'qemu-system-arm.exe'
            executable.write_bytes(b'test executable')
            for name in ('libglib.dll', 'libintl.dll'):
                (prefix / 'bin' / name).write_bytes(name.encode())

            def objdump(command, **kwargs):
                return '\n'.join('DLL Name: ' + name
                                 for name in imports[Path(command[-1]).name])

            with patch.dict(os.environ, {'SystemRoot': str(root / 'windows')}), \
                    patch.object(bundle_windows.subprocess, 'check_output', side_effect=objdump):
                output = root / 'dist'
                bundle_windows.bundle(prefix, executable, output)
            return {p.name for p in output.iterdir()}

    def test_recursive_imports_cycles_and_system_dlls(self):
        names = self.run_bundle({
            'qemu-system-arm.exe': ['libglib.dll', 'KERNEL32.dll', 'api-ms-win-core-test.dll'],
            'libglib.dll': ['libintl.dll'],
            'libintl.dll': ['libglib.dll', 'kernel32.dll'],
        })
        self.assertTrue({'qemu-system-arm.exe', 'libglib.dll', 'libintl.dll',
                         'scripts', 'profiles', 'README.md'} <= names)
        self.assertNotIn('KERNEL32.dll', names)

    def test_unresolved_non_system_import_fails(self):
        with self.assertRaisesRegex(RuntimeError, 'Unresolved DLL import missing.dll'):
            self.run_bundle({'qemu-system-arm.exe': ['missing.dll']})
