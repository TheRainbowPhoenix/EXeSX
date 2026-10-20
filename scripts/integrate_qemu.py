#!/usr/bin/env python3
"""Install EXeSX machine into a pinned upstream QEMU source tree."""
from pathlib import Path
import sys
root = Path(__file__).resolve().parents[1]
qemu = Path(sys.argv[1]).resolve()
meson = qemu / "hw/arm/meson.build"
assert meson.is_file() and (qemu / "hw/arm/virt.c").is_file()
target = qemu / "hw/arm/exesx.c"
source = (root / "hw/arm/exesx.c").read_bytes()
if target.exists() and target.read_bytes() != source:
    raise SystemExit("Refusing to overwrite changed upstream exesx.c")
target.write_bytes(source)
module = root / 'hw/arm/exesx-imx7ulp.inc'
module_target = qemu / 'hw/arm/exesx-imx7ulp.inc'
if module_target.exists() and module_target.read_bytes() != module.read_bytes():
    raise SystemExit('Refusing to overwrite changed upstream exesx-imx7ulp.inc')
module_target.write_bytes(module.read_bytes())
scg_module = root / 'hw/arm/exesx-imx7ulp-scg.inc'
scg_target = qemu / 'hw/arm/exesx-imx7ulp-scg.inc'
if scg_target.exists() and scg_target.read_bytes() != scg_module.read_bytes():
    raise SystemExit('Refusing to overwrite changed upstream exesx-imx7ulp-scg.inc')
scg_target.write_bytes(scg_module.read_bytes())
line = "arm_ss.add(when: 'CONFIG_ARM_V7M', if_true: files('exesx.c'))"
content = meson.read_text()
if line not in content:
    meson.write_text(content.rstrip() + "\n" + line + "\n")
print("Installed exesx board into", qemu)
