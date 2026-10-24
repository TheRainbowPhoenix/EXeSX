# Experimental removable SD card for EXeSX

This is the real QEMU SD card state machine, NOT a hard-coded pass signal.
A7 USDHC0 is at 0x40370000 and IRQ is GIC SPI42, verified against Linux
i.MX7ULP DTS. USDHC1 at 0x40380000/SPI43 is the separate eMMC host.

## Enable

Create a disposable card (FORMAT, FILE COPY and MEDIA FULL tests destroy data):

```sh
qemu-img create -f qcow2 test-sd.qcow2 2G
export EXESX_USDHC0_SD=1
export EXESX_USDHC0_SD_DETECT_GPIO=1
# Keep the existing A7/M4 boot, memory profile, firmware loader and eMMC drive flags.
# Add this separate drive to that QEMU command:
-drive if=none,id=exesx-sd,file=test-sd.qcow2,format=qcow2
```

EXESX_USDHC0_SD=1 overlays the real `TYPE_IMX_USDHC` host over the
otherwise unchanged diagnostic no-media USDHC0 profile and attaches QEMU's
`TYPE_SD_CARD` using drive `exesx-sd`. Card images must be >=2GiB and
512-byte aligned. Legacy/no-SD behavior is retained without opt-in.

EXESX_USDHC0_SD_DETECT_GPIO=1 enables the separately observed physical
PTB14 card detect: M4 GPIOB.PDIR bit14 high is removed; low is inserted.
Original A7 FUN_60035250 publishes inverted PDIR14 to 0x2f029214;
FUN_60035280 consumes that state. The physical pin and the USDHC CINST
register are different; neither implies that the SD filesystem has mounted.
The opt-in GPIO coupling represents fixed-at-start insertion, not live eject.

## Reproducible TEST > MANUAL > SD MENU selection

A cold-boot GDB redirect at an arbitrary CPU state can diverge into the
UC3 scheduler. The experimental suite saves the original A7/M4 VM state
**at the third 0x60046ff0 selector (SD MENU selector entry)**, rather than
at a nested handler. Restore it, set R0 to the selected *1-based visual menu
position*, and return from the selector to LR. The original handlers then
run unmodified.

Menu display order is cases 0,1,2,3,4,11,5,6,7,8,9,10.
A selector return of 0 is Cancel; do NOT supply raw case 0 for FORMAT.

IMPORTANT: `savevm` must save **both writable disks**, including the SD
card image. Never use `snapshot=on` for the SD card when making a persistent
VM snapshot: QEMU puts its SD snapshot in a temporary overlay, and a
later `loadvm` fails with "Snapshot ... does not exist in one or more devices".
Use persistent QCOW2 for BOTH eMMC and SD, with matched snapshot names.

## Evidence / test status (experimental)

- No-card USDHC0 PRES_STATE: 0x00000008
- Card-present USDHC0 PRES_STATE: 0x01ff0008
- SD host capabilities: 0x05e80080
- All 12 original SD MENU handler entries reached from the same restored
  selector checkpoint in isolated launches.
- INFORMATION reached SD CMD13 and INT_STATUS=0x00000001 (command complete).
- The firmware's FORMAT, READ/WRITE, loop, mount, detect, and automatic
  tests have **NOT** all reported PASS. Handler entry is not test completion.
  READ expects a card file `\\crd0\\FONT\\GyZen12n.cjf`, which a blank card
  image does not contain. Filesystem/media fixture and prolonged execution
  are required before claiming complete factory-test coverage.

No firmware bytes are changed. All experimental RAM/PC selection redirects
are diagnostic-only and must never be mistaken for natural factory boot.
