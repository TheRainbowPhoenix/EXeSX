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
tpm_module = root / 'hw/arm/exesx-imx7ulp-tpm.inc'
tpm_target = qemu / 'hw/arm/exesx-imx7ulp-tpm.inc'
if tpm_target.exists() and tpm_target.read_bytes() != tpm_module.read_bytes():
    raise SystemExit('Refusing to overwrite changed upstream exesx-imx7ulp-tpm.inc')
tpm_target.write_bytes(tpm_module.read_bytes())
pmc_module = root / 'hw/arm/exesx-imx7ulp-pmc.inc'
pmc_target = qemu / 'hw/arm/exesx-imx7ulp-pmc.inc'
if pmc_target.exists() and pmc_target.read_bytes() != pmc_module.read_bytes():
    raise SystemExit('Refusing to overwrite changed upstream exesx-imx7ulp-pmc.inc')
pmc_target.write_bytes(pmc_module.read_bytes())
port_module = root / 'hw/arm/exesx-imx7ulp-port.inc'
port_target = qemu / 'hw/arm/exesx-imx7ulp-port.inc'
if port_target.exists() and port_target.read_bytes() != port_module.read_bytes():
    raise SystemExit('Refusing to overwrite changed upstream exesx-imx7ulp-port.inc')
port_target.write_bytes(port_module.read_bytes())
lpit_module = root / 'hw/arm/exesx-imx7ulp-lpit.inc'
lpit_target = qemu / 'hw/arm/exesx-imx7ulp-lpit.inc'
if lpit_target.exists() and lpit_target.read_bytes() != lpit_module.read_bytes():
    raise SystemExit('Refusing to overwrite changed upstream exesx-imx7ulp-lpit.inc')
lpit_target.write_bytes(lpit_module.read_bytes())
lptmr_module = root / 'hw/arm/exesx-imx7ulp-lptmr.inc'
lptmr_target = qemu / 'hw/arm/exesx-imx7ulp-lptmr.inc'
if lptmr_target.exists() and lptmr_target.read_bytes() != lptmr_module.read_bytes():
    raise SystemExit('Refusing to overwrite changed upstream exesx-imx7ulp-lptmr.inc')
lptmr_target.write_bytes(lptmr_module.read_bytes())
mu_module = root / 'hw/arm/exesx-imx7ulp-mu.inc'
mu_target = qemu / 'hw/arm/exesx-imx7ulp-mu.inc'
if mu_target.exists() and mu_target.read_bytes() != mu_module.read_bytes():
    raise SystemExit('Refusing to overwrite changed upstream exesx-imx7ulp-mu.inc')
mu_target.write_bytes(mu_module.read_bytes())
lpi2c_module = root / 'hw/arm/exesx-imx7ulp-lpi2c.inc'
lpi2c_target = qemu / 'hw/arm/exesx-imx7ulp-lpi2c.inc'
if lpi2c_target.exists() and lpi2c_target.read_bytes() != lpi2c_module.read_bytes():
    raise SystemExit('Refusing to overwrite changed upstream exesx-imx7ulp-lpi2c.inc')
lpi2c_target.write_bytes(lpi2c_module.read_bytes())
sema_module = root / 'hw/arm/exesx-imx7ulp-sema42.inc'
sema_target = qemu / 'hw/arm/exesx-imx7ulp-sema42.inc'
if sema_target.exists() and sema_target.read_bytes() != sema_module.read_bytes():
    raise SystemExit('Refusing to overwrite changed upstream exesx-imx7ulp-sema42.inc')
sema_target.write_bytes(sema_module.read_bytes())
line = "arm_ss.add(when: 'CONFIG_ARM_V7M', if_true: files('exesx.c'))"
content = meson.read_text()
if line not in content:
    meson.write_text(content.rstrip() + "\n" + line + "\n")
print("Installed exesx board into", qemu)
