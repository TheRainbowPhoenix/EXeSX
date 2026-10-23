#!/usr/bin/env python3
"""Bundle a native MinGW QEMU and its recursive non-system DLL imports."""
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess


def bundle(prefix, executable, output):
    root = Path(__file__).resolve().parents[1]
    output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(executable, output / executable.name)
    available = {p.name.lower(): p for p in (prefix / 'bin').glob('*.dll')}
    system = Path(os.environ['SystemRoot']) / 'System32'
    system_dlls = {p.name.lower() for p in system.glob('*.dll')}
    queue, seen = [executable], set()
    while queue:
        binary = queue.pop()
        imports = subprocess.check_output(
            [str(prefix / 'bin/objdump.exe'), '-p', str(binary)], text=True)
        for name in re.findall(r'DLL Name:\s*(\S+)', imports):
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            if key in available:
                source = available[key]
                shutil.copy2(source, output / source.name)
                queue.append(source)
            elif key not in system_dlls and not key.startswith(('api-ms-', 'ext-ms-')):
                raise RuntimeError(f'Unresolved DLL import {name} in {binary}')
    shutil.copytree(root / 'scripts', output / 'scripts',
                    ignore=shutil.ignore_patterns('__pycache__'), dirs_exist_ok=True)
    shutil.copytree(root / 'profiles', output / 'profiles', dirs_exist_ok=True)
    shutil.copytree(prefix / 'share/licenses', output / 'licenses', dirs_exist_ok=True)
    qemu_source = root / 'vendor/qemu'
    for name in ('COPYING', 'COPYING.LIB', 'LICENSE'):
        if (qemu_source / name).is_file():
            shutil.copy2(qemu_source / name, output / name)
    shutil.copy2(root / 'docs/windows.md', output / 'README.md')
    print(f'Bundled {executable.name} and {len(list(output.glob("*.dll")))} DLLs in {output}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', type=Path, required=True)
    parser.add_argument('--executable', type=Path, default=Path('build/qemu-system-arm.exe'))
    parser.add_argument('--output', type=Path, default=Path('dist/exesx-qemu-windows-x86_64'))
    args = parser.parse_args()
    bundle(args.prefix, args.executable, args.output)
