# Execution status

QEMU v10.1.0 Cortex-A7 TCG implements architectural privileged CP15 operations. The EXeSX board is experimental and provides ROM-like loading RAM, vector alias, SRAM, shared RAM, and a powered-off Cortex-M4/NVIC. Addresses beyond the validated firmware image locations remain provisional.

The firmware-specific BL at 0x60000068 to 0x60179564 has only been reached in a **limited Python subset interpreter**, not in verified QEMU guest execution. There is no LCDIF, touchscreen, storage, inter-core release, or verified OS boot.

Synthetic tests must never be described as Casio firmware boot success. The repository must remain firmware-free.
