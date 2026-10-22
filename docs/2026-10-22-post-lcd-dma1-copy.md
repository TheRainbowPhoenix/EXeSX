Post-LCD DMA1 investigation (22 October 2026)

The LCD abort previously described as a read was actually a 32-bit RAMWR data write with command 0x2C and GPIOA16 selecting data. Main now supports two packed RGB565 halfwords per 32-bit RAMWR write. This original-firmware path produces a white screenshot and passes the modeled GPIOF13 TE transition.

The next original BIOS barrier is DMA1 channel 15 at 0x601B82BC, waiting for CSR.DONE after a descriptor requests 0xCA800 bytes from guest RAM 0x61080000 to 0x6114A800. The previous model stored TCD data without copying. This branch adds an opt-in, bounded memory-to-memory transfer using actual guest RAM reads and writes, enabled only when the DMAMUX channel is enabled and always-on. Source/dest offsets and 32-byte transfer sizes must match the observed descriptor, and DONE is set only after all writes complete. Peripheral request types and full DMA timing remain unimplemented.

The CI synthetic ARM test scripts/probe_dma1_memcpy.py verifies that disabling the experimental path leaves the destination and DONE untouched, whereas enabling it copies RAM and sets DONE. The first CI attempt failed because the actual profile kind was imx7ulp-dmamux (not imx7ulp-dmamux1). That identification has been fixed in the subsequent commit. Original-firmware progress is not yet claimed.

Next: inspect original DMAMUX ch15 configuration, rerun original OSUP with the experimental option on, and require a genuine return from BIOS DMA wait before claiming the blocker cleared. No vendor firmware or installed disk image is committed.
