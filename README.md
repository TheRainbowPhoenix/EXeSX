# EXeSX

Experimental open-source Casio XD-SX Cortex-A7 / Cortex-M4 board bring-up for QEMU. **No Casio firmware is committed.**

Current goal: use upstream QEMU ARM TCG to execute privileged Cortex-A7 CP15 startup instructions, then implement evidence-driven board peripherals. The machine and any browser tools are **experimental** and do not constitute a booted Casio OS.

See the GitHub Actions builds and `docs/STATUS.md` for measured verification results.
