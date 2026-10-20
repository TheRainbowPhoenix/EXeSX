# EXeSX

Experimental open-source Casio XD-SX Cortex-A7 / Cortex-M4 board bring-up for QEMU. **No Casio firmware is committed.**

Current goal: use upstream QEMU ARM TCG to execute privileged Cortex-A7 CP15 startup instructions, then implement evidence-driven board peripherals. The machine and any browser tools are **experimental** and do not constitute a booted Casio OS.

See the GitHub Actions builds and [measured project status](docs/STATUS.md) for verification results.

**Hardware references:** [NXP i.MX7ULP reference/security manuals, original CMSIS headers, SNVS SDK, MU/Linux drivers, and RTOS naming resources](docs/HARDWARE_REFERENCES.md). Latest [SNVS HP initialization and real-firmware study](docs/2026-10-21-snvs-hp-investigation.md).
