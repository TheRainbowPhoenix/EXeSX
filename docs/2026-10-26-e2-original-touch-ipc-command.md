# 2026-10-26 — E2 correct firmware touch-enable command (original A7 → M4)

## Source-derived control flow

From the user-provided, private `XD-SX9850.0.c` and `XD-SX9850-M4.bin.c` (the decompilation **is not committed**):

1. Original A7 `FUN_6001ec84(arg)` calls `FUN_601782c8(0, 0x180C, &arg, 1)`. Other A7 callers send `FUN_6001ec84(0)` and `FUN_6001ec84(1)` for input-service lifecycle.
2. M4 IPC routine `FUN_1ffdc76a` calls `FUN_1ffdbc8c(*(uint32_t *)(request+0xC))`. The latter uses `FUN_1ffdff08()` to write **PORTB.PCR3 = 0x00080000** when `arg != 1`; it calls `FUN_1ffdff2e()` to write **PORTB.PCR3 = 0** when `arg == 1`.
3. The physical touch controller is the separate **ROHM BU21029 on M4 LPI2C2 at seven-bit 0x40**, not the BU26154 audio codec at 0x1A. Original M4 `FUN_1ffdbcde` samples **GPIOB.PDIR bit3 active-low**. When the M4 driver accepts a pen, `FUN_1ffdba48` uses controller command `0x84`, then `FUN_1ffdba12` requests the genuine **14-byte coordinate report** via I²C address `0x81`.
4. Original A7 E2 `FUN_6005c6bc` receives input through `FUN_60047504`; genuine touch events are type **0x6000** with state and coordinates. It draws lines between successive accepted coordinates. E2 draws the screen border and X, then on a real exit-key event checks framebuffer coverage. Any untouched zero pixel yields **NG**. There is no fixed gesture order and no direct MCU status bit that means E2 passed.

## Verified original-firmware command experiment

During actual unchanged owner OSUP cold boot with both storage devices snapshot-on, the A7 entered the real 16-item factory menu and row 13 E2. The E2 LCD cross was visible. With the device initially **disarmed**, a private QEMU GDB/HMP diagnostic briefly suspended the guest, executed **the unmodified original A7 routine `FUN_6001ec84(0)`**, waited for its actual return, then restored the A7 registers and resumed. The **unchanged M4** observed the command and **PORTB.PCR3 became `0x00080000`**. The diagnostic never wrote PCR3, an NVIC pending flag, touch event queue, framebuffer or factory verdict.

This proves that **the IPC command is real and actually reaches its intended M4 enable handler**. It also proves that entering the direct E2 row alone does not automatically leave that interrupt armed in the observed firmware session. However the first follow-up genuine 1,649-sample cross replay after the debugger-assisted enable **did not produce a verified original OK or visibly erased cross**. That is still an **incomplete end-to-end test**, not an E2 pass.

The next discriminating observation is whether the original M4 services PTB3 and executes `FUN_1ffdba48` / an actual `RX_REQUEST count=14` after the A7 firmware command. If no such read occurs, fix the missing interrupt/worker state transition before trying more raw-coordinate orientations. If it occurs and A7 sees type 0x6000 events, solve the measured firmware calibration and screen coverage. **Do not force PCR3 on a pen file change or inject type 0x6000 records**, as those mask the guest's own missing enable path.

## Reproducible diagnostic (explicit opt-in)

The GUI factory worker now accepts three **disabled by default** variables:

- `EXESX_E2_GDB_PORT=27871`: bind QEMU's GDB stub only on 127.0.0.1
- `EXESX_E2_HMP_PORT=27872`: independent host monitor only on 127.0.0.1
- `EXESX_E2_TRACE_I2C=1`: optional unimplemented/guest-error MMIO log; **not recommended on timing-sensitive boot** unless a separate control verifies menu entry

Start your usual **private** original-OSUP factory-menu runner with `--target 13` and the correct current **I2S0/I2S1** profile. Keep BU21029 bus `EXESX_BU21029_LPI2C_BUS=2` and private touch file `EXESX_BU21029_TOUCH_FILE=/private/touch.txt`. Use the physical cold-boot chord and short 38ms E2 ENTER contact, verified from the original LCD.

Once original E2 ENTER is confirmed by your runner log:

```bash
python scripts/drive_e2_cross.py \
  --touch-file /private/touch.txt \
  --wait-log /private/factory-runner.log \
  --arm-original-a7 --gdb-port 27871 --hmp-port 27872 \
  --offset-step 8 --point-step 18 \
  --finish-key-file /private/factory/gui-contact.txt --finish-hold-ms 60
```

The driver executes **the original A7 function** via `scripts/e2_original_touch_ipc.py` and requires the resulting M4 PCR3 to be 0x80000 before sending any raw sensor samples. It sends 36 pen strokes and releases them, then optionally emits a genuine M4 physical keypad contact to request the original E2 OK/NG verdict. It never declares success itself. **The original LCD result is the sole success criterion.** Debugger-assisted arming is a diagnostic and not proof that normal factory menu entry itself correctly enables the panel.

The firmware-free regression `scripts/probe_e2_touch_ipc.py` verifies saved A7 CPU register preservation, correct 0/1 argument selection, return-PC validation, opt-in loopback-only debug ports, and newline-delimited physical exit contacts on Linux and Windows. A synthetic pass cannot establish real original E2 success.

No private ROM, original decomp, synthetic owner media, trace dumps, QMP frames, MAC/serial or raw touch capture is committed.
