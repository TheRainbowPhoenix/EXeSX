# A7 Data Abort correction and i.MX7ULP early-device bring-up — 2026-10-21

**Real private firmware evidence:** Original SHA256-validated OSUP `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`; native QEMU build from merged SNVS PR #11, `48a0d9ededb8da38d2f8cbe0e092346305f31455`. Both opt-in I2C mirrors and experimental MU IRQ are enabled; SNVS security pulses are **explicitly diagnostic-only**, never an authenticated security state. No private ROM, ELF or raw logs uploaded.

## Correcting the IRQ-return hypothesis

A7 returning from an IRQ to PC **0x20002028** does **not** itself constitute the reported Data Abort. The actual QEMU exception report was **CPU0 DFSR=0x8, DFAR=0x40370024**. An independently reproduced `-d in_asm,int,guest_errors` instruction trace shows:

```armasm
0x60034ED4  str r1,[r0]        ; enable PCC2 USDHC0 clock
...
0x60034F10  mov r0,#0x40000024
0x60034F14  orr r0,r0,#0x370000
0x60034F18  ldr r0,[r0]        ; actual A7 Data Abort at 0x40370024
0x60034F1C  tst r0,#8         ; PRES_STATE.SDSTB, internal SD clock stable
0x60034F20  beq 0x60034F10   ; poll until clock becomes stable
```

The abort is a **missing USDHC0 host-controller status register** on the A7, *not* an established corrupt IRQ return.

## Manufacturer/upstream address map

| Physical address | i.MX7ULP device | Decoded guest access |
| --- | --- | --- |
| `0x40370024` | USDHC0 `PRES_STATE` | A7 polls `SDSTB` bit3; **no card-present bit is asserted** |
| `0x40080000` | DMA1 (A7 eDMA, 32 channels) | A7 reads control CR at `0x601B7F58`, sets bits, stores at `0x601B7F84` |
| `0x40081040` | DMA1 TCD channel 2 | A7 at `0x601B8108` zeroes source and subsequent 16-bit/32-bit descriptor fields; **no data movement** |
| `0x4021000C` | DMAMUX1 channel configuration byte 12 | Read during DMA/clock setup |
| `0x40290010` | LPSPI2 `CR` | A7 at `0x601C2254` reads control, requests FIFO/reset behavior, toggles back |
| `0x601CBC34` | A7 firmware code | Later polls DMA1 `CR` and tests bit31; repeated reads do not alone prove a fault |

These are confirmed by the NXP i.MX7ULP [CM4 CMSIS base addresses](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/MCIMX7U5/MCIMX7U5_cm4_COMMON.h) and the upstream Linux [imx7ulp.dtsi](https://github.com/torvalds/linux/blob/master/arch/arm/boot/dts/nxp/imx/imx7ulp.dtsi), which explicitly maps USDHC0 0x40370000, eDMA1 0x40080000 (0x2000 bytes) and DMAMUX1 0x40210000 (0x1000). [NXP USDHC SDK driver](https://mcuxpresso.nxp.com/api_doc/dev/1581/group__usdhc.html) names `kUSDHC_SdClockStableFlag` and `kUSDHC_CardInsertedFlag` as different bits. [NXP eDMA driver binding](https://kernel.googlesource.com/pub/scm/linux/kernel/git/torvalds/linux/+/7c16f0a4ed1ce7b0dd1c01fc012e5bde89fe7748/Documentation/devicetree/bindings/dma/fsl,edma.yaml) confirms 32 channels.

## Private controlled fault-probe ladder

Using an unchanged QEMU executable and identical private ROM, the following **temporary, non-shipping MMIO overlays** were tested independently. Each added only a documented peripheral window; unsupported accesses still raised A7 Data Aborts.

| Additional test setup | First A7 fault after boot |
| --- | --- |
| Baseline, no new peripheral | `0x40370024` (USDHC0 PRESENT_STATE) |
| USDHC0 PRES_STATE=0x8 only (host SD clock stable; no card) | `0x40080000` (DMA1 control) |
| Plus DMA1 CR initialized to zero | `0x40081040` (DMA1 TCD channel 2) |
| Plus DMA1 TCD descriptor scratch | `0x4021000C` (DMAMUX1) |
| Plus DMAMUX1 channel bytes | `0x40290010` (LPSPI2 CR) |
| Plus LPSPI2 CR register shadow | No A7 Data Abort in 2-second bounded trace; **no verified OS entry** |

The last case repeatedly read DMA1 CR (A7 PC `0x601CBC34`); memtrace verified live reads, not a QEMU error. **None of these temporary overlays implements a storage card, DMA transfers, SPI exchange or interrupts.** Each merely diagnoses the next missing initialization register and must not be interpreted as successful boot.

## Reviewed implementation

A small evidence-backed startup subset is now available in the EXeSX profile and dedicated MMIO modules, tested using `scripts/probe_a7_early_devices.py` (real synthetic A7 ARM guest). It supports:
- USDHC0 only `PRES_STATE+0x24 = 0x8`, indicating the internal host clock has stabilized; **no card-present, response, or transfer**. Other registers fault.
- A7 DMA1 existing early CR/control and **snapshot-backed TCD register storage** for 32 channels, byte/halfword/word access. No channel execution, DMA copy or completion flags.
- DMAMUX1 `CHCFG[0..31]` byte-packed read/write storage with naturally aligned 8/16/32-bit MMIO accesses; no triggered peripheral requests.
- LPSPI2 only CR +0x10 read/write. **No SPI transfer or attached external device**.

**Limits:** USDHC clock readiness is approximated after the BIOS has explicitly enabled PCC2, not modeled cycle-accurately. TCD/DMAMUX state storage alone cannot satisfy real card, DMA or SPI transactions. Unrecognized registers fault. This is early-board discovery, **not a working OS**.

## Follow-up status: next roadblock

The repeated DMA1 `CR` read at A7 PC `0x601CBC34` tests **bit 31, `DMA_CR.ACTIVE`**, confirmed by [NXP PERI_DMA.h](https://github.com/nxp-mcuxpresso/mcux-devices-imx/blob/main/i.MX7ULP/periph/PERI_DMA.h). An idle DMA engine legitimately keeps this bit clear. Real firmware then exposes a **different M4 BusFault at SNVS HPRTCMR (0x41070024)**; see the [SNVS RTC follow-up](2026-10-21-snvs-rtc-m4-followup.md). Determine whether the firmware is simply polling its main event loop or waiting for a real DMA/SPI/card transaction. Only add an actual DMA engine or storage image once it issues a transfer that can be traced and validated.

The maintained [hardware reference library](HARDWARE_REFERENCES.md) collects manufacturer manuals/SDK and Linux sources. Keep all credentials and proprietary files entirely out of GitHub, logs and runnable scripts.
