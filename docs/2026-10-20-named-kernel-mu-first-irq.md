# A7 kernel naming + first M4 MU IRQ22 state — 2026-10-20

This is **measured private DY357/XD-SX9850 firmware** in native EXeSX/QEMU 10.1.0, not evidence of hardware authenticity or OS text/LCD output. The user's checksum-validated OSUP source is SHA256 `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`. The verified BIOS section SHA256 is `eb7dafa1b544bbb8d79081866af280e6c0f88197de9f635c6887f8486155da66`. **No ROM, guest RAM dump, debugger log or snapshot is committed**.

## Reusable kernel names — use uC3 as an API dictionary, not a firmware match

- [shun0847/uC3](https://github.com/shun0847/uC3) contains eForce **Micro C Cube / μC3 Standard** (especially `Kernel/Standard/inc/kernel.h`, `Kernel/Standard/inc/uC3fncode.h`, task / semaphore wrappers and scheduler-related `Kernel/Standard/src/AArch64` code). Its `TFN_WAI_SEM`, `TFN_SIG_SEM`, `T_CTSK`, `T_CSEM`, `T_RSEM` and idle/task/ISR concepts are extremely useful for reading our firmware. **That repository's demonstrated port is AArch64/i.MX8**, not the Cortex-A7 ARMv7 binary Casio supplied.
- [DerEchteJoghurt/uNet3s_iMX25_ewarm_eva](https://github.com/DerEchteJoghurt/uNet3s_iMX25_ewarm_eva) has the *μNet3/Standard* evaluation SDK from eForce (2016 documentation; an ARM926EJ-S/i.MX25 port, ARMv5T `itron.h` and `kernel.h`). Useful confirmation of older naming conventions, **not matching platform code**. It provides compiled libraries rather than full ARMv7 Casio kernel source.
- [eForce's μC3 Standard API index](https://www.eforce.co.jp/uc3-standard-api/) independently defines functions such as `wai_sem`, `sig_sem`, `ref_sem`, `act_tsk` and `cre_tsk`.

**Important precision:** A current uC3 header defines `TFN_WAI_SEM = -0x25`, but the Casio A7 disassembly's observed kernel-dispatch value was `0xFFFFDB01`; these are **not interchangeable encodings**. We have not established a byte-identical μC3 kernel build, exact private μITRON syscall numbering, object layout or scheduler ABI. Names below are anchored in real observed Casio code/arguments, not transplanted disassemblies or fixed vendor addresses.

Ghidra-ready high-confidence function and instruction-site annotations: [`reverse/a7_kernel_named_sites.tsv`](../reverse/a7_kernel_named_sites.tsv). The hash-guarded Ghidra Java post-script [`ghidra/ExesxA7KernelNames.java`](../ghidra/ExesxA7KernelNames.java) names only known function-entry candidates and marks individual instruction sites without pretending they are separate functions. Preserves existing analyst function names and checks the entire BIOS fingerprint. **Ghidra Java execution was not tested in this tool runtime.**

Selected readable names:

| Private A7 address | Proposed label | Grounding |
| --- | --- | --- |
| `0x6017A11C` | `A7_Kernel_InitializeFromConfig` | Copies caller-provided kernel configuration |
| `0x601797A8` | `A7_Kernel_ScheduleNextReadyTask` | Scheduler after task/sem events |
| `0x60179D20` | `A7_Kernel_SearchReadyQueues` | Queue search under idle transitions |
| `0x60179A68` | `A7_IdleTask_CheckOptionalHook` | Tests optional kernel callback at state +0x8C |
| `0x601E1A08` | `A7_Kernel_WaitSemaphore_Impl` | Validated `wai_sem(31)` implementation |
| `0x601E17D8` | `A7_Kernel_SignalSemaphore_Impl` | Validated `sig_sem(31)` release implementation |
| `0x60037DA8` | `A7_MainTask_Entry` | Task name and task control block observed |
| `0x6004A0B4` | `A7_MainTask_BootStartup` | MainTask next startup routine |

The idle callback `0x62148F8C` is **deliberately initialized to NULL**, and full-speed MainTask sem31 traffic progresses; see [earlier correction](2026-10-20-a7-callback-semaphore-mu-irq.md). An idle PC snapshot alone is not an OS crash.

## Direct MU IRQ22 experiment

Native binary: verified EXeSX QEMU GitHub CI artifact `exesx-qemu-native-aa5f55b0d4513d2f2847903a9aae16c5d4993f7e`; source `aa5f55b0d4513d2f2847903a9aae16c5d4993f7e`. Real private A7 firmware with M4 release. Opt-in flags `EXESX_EXPERIMENTAL_MU_IRQ=1`, `EXESX_I2C4B_REGISTER_MIRROR=1`, `EXESX_I2C40_REGISTER_MIRROR=1`. The I²C mirrors are **diagnostic inventions**, not real chips.

`scripts/probe_mu_irq.py` launches separate real Cortex-A7 and Cortex-M4 CPUs under QEMU, breaks on the actual **M4 IRQ22 handler entry `0x1FFED180`**, and reads *only* MUA/MUB **SR at +0x60 and CR at +0x64** using GDB RSP. These reads do not change emulator mailbox state. It never accesses **RRn +0x40..0x4C**, because that would clear RF status, free the peer TX slot, and ruin the experiment. It lets the unmodified M4 handler execute to the *next* IRQ entry and samples again, using the same breakpoint; the guest writes the real register values.

The probe takes a QMP savevm snapshot at IRQ entry 1 and restores it after capturing the entries, verifying M4 PC and *both* MU windows' original SR/CR values to catch bad VMState rollback.

| M4 IRQ22 entry | MUA SR | MUA CR | MUA RF | MUA RIE | Pending `RF & RIE` | MUA GIP | MUB TE |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **1** | `0x04F00000` | `0xFF000000` | `0x4` | `0xF` | `0x4` — RR2 | `0x0` | `0xB` |
| **2** | `0x05F00000` | `0xFB000000` | `0x5` | `0xB` | `0x1` — RR0 | `0x0` | `0xA` |
| **3–6** | `0x05F00000` | `0xFB000000` | `0x5` | `0xB` | `0x1` — RR0 | `0x0` | `0xA` |

**Definitive for this emulator version:** The first IRQ source is **receive-full channel 2, not GIP0**. After the first handler, M4 has masked **RIE2** (`0xF→0xB`), but a second MUA receive (channel **0**) becomes full. Repeated IRQ entries 2–6 are due to **`RF0=1 & RIE0=1`**, not any GP-flag pending bit. MUA RF0/RF2 continue full, MUB transmit-empty bits 0/2 continue deasserted. Neither is released by an M4 RR read in these observed consecutive entries. Original firmware is still executing; the condition may be missing handler registration or an uninitialized receive consumer. We **cannot yet prove** whether the original Casio kernel would have consumed RR0 after additional startup; do not invent an ACK.

**Control check:** Reran the native firmware-free ARM regression `python3 scripts/probe_imx7ulp.py --qemu ... --profile ...`; it PASSED the actual two-sided MU mailbox test: guest writes MUA TR0, peer MUB RF0 becomes full, guest reads MUB RR0, RF0 clears, and MUA TE0 becomes empty again. Therefore the current model **does release the slot when the receiver reads RRn**. In this private real-firmware trace RR0/RR2 remain full at each captured entry; root cause points toward missing/delayed guest receive dispatch or subtle timing/interrupt integration, NOT a demonstrated broken basic release operation.

The i.MX7ULP [MU SR field layout](https://community.nxp.com/t5/i-MX-Processors/imx7ulp-different-values-fro-MUA-SR-from-CA7-and-CM4/td-p/1393066) and [NXP i.MX7ULP manual, Chapter 9](https://manuals.plus/m/3fcef56ef531d2f11af138e90b262f740cb4b850405f230406bb863805f74d1c.pdf) support the 4-bit **TE, RF, GIP** nibbles and masked RIEn behavior. Thus the model's **basic** status and IRQ-level calculation are consistent with this specific trace; this is not evidence that *all* MU register semantics are correct.

## Verified A7 sender for the second MU IRQ

A real GDB hardware **write watchpoint** on the A7-side MUB TR0 `0x40220020` stopped A7 at **PC `0x60177EC0`** between the first and second M4 IRQ22 entries. Registers: **`r0=0x40220020`, `r4=0x00000006`, `r6=0`**. SHA-verified A7 ARM disassembly proves:

```armasm
0x60177DFC  push  {r2,r3,r4,r5,r6,r7,r8,lr}  ; A7_MU_TransmitDescriptor
...
0x60177EB8  mov   r0, #0x40000020
0x60177EBC  orr   r0, r0, #0x00220000        ; r0 = 0x40220020
0x60177EC0  str   r4, [r0,r6,lsl #2]          ; TR[r6] = message 6, r6=0
```

A7 earlier sent value **0** into TR2 `0x40220028`, and its next **1..5** attempted TR2 messages were rejected as busy in the emulator. It then sent **6** to TR0, explaining the independently observed change `MUB.TE=0xB→0xA`, `MUA.RF=0x4→0x5` between the first and second IRQ22 entries. This sender has been added to the [A7 Ghidra names](../reverse/a7_kernel_named_sites.tsv). A QEMU model in which RR0/RR2 are never read will leave both slots full; it may reflect unfinished M4 callback initialization, delayed receive dispatch, or a model mismatch, none yet confirmed as the root cause.

## Re-run against your firmware, privately

```sh
python3 scripts/prepare_osup.py /path/to/OSUP.BIN -o private/a7-firmware.elf
python3 scripts/probe_mu_irq.py private/a7-firmware.elf \
  --qemu build/qemu-system-arm \
  --profile profiles/imx7ulp-early-boot.ini \
  --entries 6 --out private/mu-first-irq
```

The tool outputs `private/mu-first-irq/mu-irq-readonly.json`, `guest-private.log` and `qemu-console-private.log`. **Do not commit any of these**. The file-name convention indicates the outputs contain private firmware execution information.

For labels, import the A7 ELF into Ghidra, then:

```sh
"$GHIDRA/support/analyzeHeadless" /absolute/path/to/private/project EXeSX_A7 \
  -import /absolute/path/to/private/a7-firmware.elf \
  -scriptPath /absolute/path/to/EXeSX/ghidra \
  -postScript ExesxA7KernelNames.java \
  /absolute/path/to/EXeSX/reverse/a7_kernel_named_sites.tsv
```

## Next targeted blocker

1. Determine the actual A7 instruction/caller that writes **MUB TR0 at 0x40220020** between the first two M4 IRQ entries; record payload and why it arrives then. Previous A7-side MUB TR2 at `0x40220028` also remains busy.
2. Trace M4's IRQ22 callback/ISR dispatch table from `0x1FFED180` to generic M4 exception dispatcher `0x1FFD3270`; determine whether the actual MU-specific handler is registered before its RIE0/RIE2 masks are enabled and whether it ever reads `0x41022040` (MUA RR0) or `0x41022048` (MUA RR2).
3. Only if live guest and reference manual agree, repair the **specific register or interrupt timing** in the QEMU model. Do **not** clear IRQs just to advance the PC: that would hide why real firmware cannot consume messages.
4. OS entry `0x60400000`/`0x605E3AD0`, framebuffer and LCD/text remain unproven.

