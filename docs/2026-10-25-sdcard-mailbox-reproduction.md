# SD-card kit, mailbox evidence, and factory TEST MENU reproduction (2026-10-25)

Branch: `experiment/dy357-m4-inputs-0804-20261023`. This note is **firmware-free**; original `OSUP.BIN`, extracted ELF, eMMC, private QCOW2 checkpoints, screenshots, and unredacted runtime traces must remain local.

## Status and evidence boundaries

**Already observed in the unchanged owner ROM, 2026-10-24:** the original M4 built keyboard type=2/subtype=1 events after physical matrix contacts `0x93,0x93,0x94`; the M4 keyboard dequeue/router/envelope functions ran; original M4 MU TX words were accepted and matched by original A7 RR read/ACKs; the original A7 executed key checks `0x60010910`, `0x60010928` and real factory TEST MENU entry `0x6003A878`. See [authentic-menu study](2026-10-24-authentic-factory-menu-entry-and-400b.md). The MU TX words are zero-valued doorbells, **not decoded keycode payloads**; do not claim a byte-for-byte shared-envelope match. The genuine BIOS branch is stronger evidence of end-to-end key acceptance than a status bit.

**Already observed, still blocked:** after authentic menu entry the A7 submitted original shared request `0x0001400B` with argument `2`; M4 MU callback `0x1FFE4776` ran, but the real `0x400B(2)` service completion, A7 return `0x60006268`, initializer return `0x6003A7F0`, and menu painter `0x60057668` were not observed. The LCD stayed black. *Code entry and visible menu are separate gates.*

## Re-testing the attached SD-card local suite (2026-10-25)

The supplied ZIP was built at `bb1f5925dfd87328e7daaf973840dba2bea62bad`. Its sparse eMMC, ELF, disposable 2-GiB SD image and Linux QEMU are **private, local assets**, not repository source. The independently supplied original `OSUP.BIN` hashes to SHA256 `d5791bec1c7739315fb6113b5d6890a21f6c454fcf7a05a0381cfaaa70808fb0`, matching the recorded owner ROM. The supplied ZIP contains **no** `version-event-wait` QCOW2 snapshot. The SD medium is blank and no 12-item SD diagnostic PASS should be inferred from a host smoke-test log.

For the latest test, the passing Linux QEMU artifact from [Actions run 40081307575](https://github.com/TheRainbowPhoenix/EXeSX/actions/runs/40081307575) was downloaded for this branch head `44276ad55d2fe98f15c050827422f72d0cd7ec1b`. Its source build identifier is `4aa890337b458e1d2205b33283a22fcd8fd4c487`. Tests executed against native QEMU with its matching `profiles/imx7ulp-early-boot.ini`:

- `python3 probe_m4_key_matrix.py --qemu ./qemu-system-arm --profile profiles/imx7ulp-early-boot.ini` **PASS**: genuine synthetic ARM GPIO row-selection and column readback for 0x93 at row8/column7 and 0x94 at row6/column6; no-key/wrong-output controls do not falsely trigger.
- `python3 probe_mu_v1_channels.py --qemu ./qemu-system-arm --profile profiles/imx7ulp-early-boot.ini` **PASS**: all four real ARM MU channels; RR reads clear RF and restore the sending peer's TE, including GP W1C tests.

These are **firmware-free hardware-model tests**, not a new observation of three original-ROM keyboard payloads.

Two 65-second new-build `drive_factory_menu.py` cold experiments with physical-matrix enablement and staged GPIO readiness reached `0x60010898` with original IPC `0x0804` result `R0=1` (pre-ready); the host then changed the M4 GPIO input files to ready masks `A=0x808c6008`, `B=0xc8`. Neither run observed a subsequent `R0=0` or `0x600108A8` event-wait checkpoint in its bounded window. One variant enabled diagnostic A7 TPM6 32 kHz and M4 TPM0 48 MHz. **Neither run confirms new key receipt or a fresh TEST MENU entry**. These bounded negative observations do not negate the authentic owner-private replay already documented above.

## Minimal authenticated replay / required local prerequisites

First obtain an **owner-private, validated** `version-event-wait` checkpoint via `scripts/drive_factory_menu.py`; it must reference the unchanged absolute path of its raw sparse eMMC backing file. No such checkpoint was included in the SD-card ZIP. Only after confirming `saved_checkpoint=true`, run (from the release directory, with matching private checkpoint/ELF/profile in `private/factory-menu`):

```bash
python3 drive_physical_menu_qmp.py \
  --qemu ./qemu-system-arm --output-dir private/factory-menu \
  --keys 0x93,0x93,0x94 --tpm0-mhz 48 \
  --a7-tpm6-khz 32 --lptmr-pcs-clocks \
  --hold 0.07 --gap 0.03 --seconds 2 --poll 0.02 \
  --no-wait-idle --trace --mailbox-trace \
  --save-menu-snapshot --overwrite
```

Use **independent** gates in the generated private report/trace:

1. M4 key queue at `0x1FFEA34C` contains original type2/subtype1 codes 0x93,0x93,0x94 in order.
2. M4 `0x1FFD838A` dequeue, `0x1FFD874A` route, `0x1FFDE672` envelope, `0x1FFDE74A` enqueue execute.
3. Each accepted M4 `0x41022020..2c` TR is matched to A7 `0x40220040..4c` RR with `rf_before=1`; this proves hardware ACK, **not** keyboard-payload identity.
4. Original A7 receive buffer `FUN_60009FB0` or `0x600108CC` contains typed 0x93/0x94 keys (use read-only breakpoint inspection separately when required); original execution at `0x60010910` / `0x60010928` / `0x6003A878` proves sequence acceptance and menu entry.
5. To claim a **visible menu**, separately observe the genuine `0x400B(2)` service reply, A7 return `0x60006268` and painter `0x60057668`, and check the LCD screenshot.

Do not fake A7 key events, force register/PC changes, or patch `0x400B` responses to claim authentic entry. For SD tests, retain `snapshot=on` (or private QCOW2 copy-on-write overlay): factory FORMAT/WRITE/FULL tests can destroy media.
