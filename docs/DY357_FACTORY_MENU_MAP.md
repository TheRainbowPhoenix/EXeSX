# Original DY357 factory/developer menu inventory

Source: owner-provided, unchanged A7 decompilation `XD-SX9850.0.c`; read-only
extraction of literal `FUN_60057550` heading strings and corresponding
`FUN_600575b4` item captions, stopping at the native menu render call.
**This is a firmware-source inventory, not evidence every test has passed or
that every submenu has been dynamically reached in current QEMU.** The
owner's original ROM/decompilation, address book, network settings and images
are not included in GitHub.

## Observed route into original menus

- Cold start: real electrical `0x9c + 0x90` contacts, release after 4 host
  seconds; at original A7 event wait `0x600108a8` press/release `0x93`,
  `0x93`, `0x94` with original M4 debounce/idle checks.
- `TEST MENU` has **16 rows**. Row 1 `MANUAL CHECK` opens `MANUAL MENU` with
  **14 rows**. Row 8 `WLAN AUTO TEST` uses external USB fixture communication,
  distinct from the ATWINC1510 host driver. Row 3 `ARM PATTERN AUTO CHECK`
  has a real 864×480 reference frame with golden PPM SHA-256
  `5a046dd6d3080c97c0c2bff76f130d4e05199a2d4dbae59e6aa5eb741df4eaaf`.
- `TEST MENU → MANUAL CHECK → WIRELESS MENU` (manual row 8) leads to
  `WLAN CHECK MENU`: COMMUNICATION, BATTERY LIFE, POWER SAVE MODE, FIRMWARE,
  MAC ADDRESS. This is the important ATWINC1510 SPI/HIF route.
- `TEST MENU → MANUAL CHECK → DEVELOPER MENU` (manual row 10): WLAN SSID,
  password, IPERF server, WLAN AUTO TEST, filesystem AES and secure-addin.
  **Do not upload unredacted developer LCD frames or stored credentials.**
- `TEST MENU → MANUAL CHECK → SYSTEM MENU → BATTERY MENU → WLAN TEST` leads
  to repeated-connect and iPerf workload tests (some also write eMMC).
- `TEST MENU → MANUAL CHECK → SERVICE MENU` (manual row 13) **requires the
  original password routine** `FUN_6004752C(1)` before SERVICE MENU opens.
  Original five-key sequence for this gate:
  `0x91 → 0x93 → 0x90 → 0x92 → 0x94`. All must arrive as genuine A7 key
  records through original physical M4 contact/debounce. Fifth can be the
  original exit/confirm event type `0x12`. Separate protected operations use
  `FUN_6004752C(0)`, which expects `0x91 → 0x93 → 0x93 → 0x92 → 0x94`.
  **Do not automate SERVICE FULL RESET, RESTORE, DELETE PASSWORD, USERAREA
  ALL FORMAT, OS UPDATE, or any destructive test.**

## Status known before this inventory

- **PASS:** original factory menu entry / LCD painter / safe key navigation;
  ARM PATTERN AUTO CHECK exact golden frame (locally and in configured CI);
  original E2 OK branch in a separate owner-ROM physical-touch test.
- **ENTRY ONLY:** MANUAL, DISPLAY, MEMORY, eMMC, SD, WIRELESS, DEVELOPER,
  VERSION (prior guarded local sweeps); original factory WLAN AUTO TEST
  heading without a real pass; other menu bodies listed below are static.
- **NOT VERIFIED:** all WLAN CHECK results, network association, USB factory
  fixture completion, PCM FFT, SD/media destructive tests and remaining
  factory hardware verdicts. Model inputs are not a proxy for real hardware.

## Complete literal submenu-heading inventory

The following sections contain the original static menu captions in render
order. Never select an operation solely by a counted keypress; the original
LCD inverse-highlighted row must match before ENTER. The word “present”
below means **present in firmware**, not validated in this emulator.

### TEST MENU (16 captions)

MANUAL CHECK; ARM PATTERN MANUAL CHECK; ARM PATTERN AUTO CHECK; FIRST FINAL ASSY FUNC CHECK; SECOND FINAL ASSY FUNC CHECK; SECOND FINAL ASSY CURRENT CHECK; FFT TEST; WLAN AUTO TEST; FINISHING CHECK; RESET; TOUCH PANEL PRESET; LCD UNIT CHECK; E2 PATTERN CHECK; JK PATTERN CHECK; VERSION; OS UPDATE.

### MANUAL MENU (14 captions)

DISPLAY MENU; MEMORY MENU; eMMC MENU; INPUT MENU; SDCARD MENU; AUDIO MENU; USB MENU; WIRELESS MENU; SYSTEM MENU; DEVELOPER MENU; OTHERS MENU; FLASH UTILITIES; SERVICE MENU; FULL RESET(CONFIG & DICS).

### VERSION MENU (4 captions)

VERSION; ROM CHECK; ROM CHECK(FAST); MTP INFORMATION.

### DISPLAY MENU (7 captions)

DISPLAY TEST; SETTINGS; IMAGE DISPLAY CHECK from SD; JPEG DATA DISPLAY; BMP DATA DISPLAY; MAG DATA DISPLAY; MESSAGE CHECK.

### DISPLAY TEST MENU (11 captions)

8 COLORS AUTO; COLOR BAR 1; COLOR BAR 2; CHIDORI; R-CHIDORI; FRAME; W-B GRADATION; MENU 1; MENU 2; MENU 3; PATTERN AUTO.

### DISPLAY SETTINGS MENU (11 captions)

COLOR MODE; FRAME FREQUENCY; INVERSION; BACK PORCH; FRONT PORCH; BACKLIGHT PWM; BACKLIGHT EN; BACKLIGHT DUTY; BACKLIGHT BRIGHTNESS; BRIGHTNESS TABLE; BOOSTER FREQUENCY.

### MESSAGE CHECK (3 captions)

SELECT DISP LANGAGE; DATA ERROR; HARD ERROR.

### MEMORY MENU (9 captions)

INSIDE SRAM TEST; SECURE RAM TEST; SDRAM TEST; ROM SUM CHECK; BUS TEST; MEMORY BUS TEST; BUS TEST(STRONG); MEMORY BUS TEST(STRONG); VIRTUAL MEMORY TEST.

### INSIDE RAM TEST MENU (10 captions)

A7 WRITE/READ CHECK (Byte Access); A7 WRITE            (Byte Access); A7 READ             (Byte Access); A7 WRITE LOOP       (Byte Access); A7 READ LOOP        (Byte Access); M4 WRITE/READ CHECK (Byte Access); M4 WRITE            (Byte Access); M4 READ             (Byte Access); M4 WRITE LOOP       (Byte Access); M4 READ LOOP        (Byte Access).

### SECURE RAM TEST MENU (5 captions)

WRITE/READ CHECK (Byte Access); WRITE            (Byte Access); READ             (Byte Access); WRITE LOOP       (Byte Access); READ LOOP        (Byte Access).

### SDRAM TEST MENU (11 captions)

WRITE/READ CHECK (Word Access); WRITE            (Word Access); READ             (Word Access); WRITE LOOP       (Word Access); READ LOOP        (Word Access); WRITE/READ CHECK (Byte Access); WRITE            (Byte Access); READ             (Byte Access); WRITE LOOP       (Byte Access); READ LOOP        (Byte Access); AGING TEST.

### eMMC MENU (12 captions)

DISPLAY INFORMATION; DISPLAY CID DUMP; WRITE; RELIABLE WRITE; WRITE LOOP; RELIABLE WRITE LOOP; READ LOOP; READ / RELIABLE WRITE LOOP; READ / WRITE LOOP; DISPLAY INFORMATION; DISPLAY CID DUMP; SELECT SPEED MODE.

### INPUT CHECK MENU (7 captions)

KEY AUTO TEST(COVERING); KEY AUTO TEST(PINPOINT); KEY RANDOM TEST; TOUCHPANEL CALIBRATION; TOUCHPANEL 2-P CALIBRATION; TOUCHPANEL CROSS CALIBRATION; TOUCHPANEL ADCONV TEST.

### SD CARD MENU (11 captions)

FORMAT; WRITE; WRITE LOOP; READ LOOP; READ LOOP(Display OFF); DETECT TEST(PTB14); INFORMATION; FILE COPY TEST; MEDIA FULL TEST; MOUNT TEST; AUTO TEST.

### AUDIO MENU (9 captions)

BZZ TEST; IDEC PLAY TEST; OPUS PLAY TEST; RECORD TEST; AUTO PLAY TEST; MOVIE TEST; PCM OUTPUT; FFT TEST; PRONTEST LIB TEST.

### BZZ TEST MENU (3 captions)

ALARM 1; ALARM 2; Bzz ON (1KHz).

### iDEC AUDIO PLAY MENU (5 captions)

AUDIO SETTINGS; iDEC ENGINE SELECT; PLAY MODE SETTING; PLAY SOUND CHINESE1; PLAY SOUND CHINESE2.

### OPUS AUDIO PLAY MENU (2 captions)

AUDIO SETTINGS; PLAY OPUS FILE.

### AUDIO PLAY SETTING MENU (7 captions)

AUDIO PLAY VOLUME; CH SPEED RATE; SOFT CLIP ENABLE; SOFT CLIP THRESHOLD H; SOFT CLIP THRESHOLD M; SOFT CLIP THRESHOLD L; SOFT CLIP GAIN.

### AUDIO RECORD MENU (5 captions)

PCM RECORDING SETTING; PCM RECORD(to RAM); PCM PLAY(from RAM); PCM PLAY(from SD); RECORDING TEST.

### PCM RECORD SETTINGS MENU (7 captions)

PLAY BACK VOLUME; PLAY BACK CH SPEED; RECORD GAIN; PLAY BACK/RECORD SAMPLE; RECORD TIME(sec); RECORD WAIT(*10ms); NOISE GATE.

### AUTO PLAY TEST MENU (5 captions)

iDEC1 FILE; iDEC2 FILE; iDEC3 FILE; OPUS FILE; RAW DATA FILE.

### PCM OUTPUT MENU (4 captions)

iDEC1 FILE to PCM FILE(.raw); iDEC2 FILE to PCM FILE(.raw); iDEC3 FILE to PCM FILE(.raw); OPUS FILE to PCMFILE(.raw).

### USB MENU (9 captions)

FUNCTION TEST MENU; HOST TEST MENU; USB DETECT TEST; SPEED MODE SETTING; DD RESET TIME SETTING; PROJECTOR LINK TEST; PROJECTOR TRANSFER TEST; USB OS UPDATE; DTV LINK TEST.

### USB FUNCTION MENU (7 captions)

FACTORY TEST; LOOP BACK TEST; LOOP BACK PACKET TEST; LOOP BACK RANDOM TEST; PORT OPEN/CLOSE TEST; RECEIVE LOOP TEST; COMPLIANCE TEST.

### USB HOST MENU (6 captions)

FACTORY TEST; LOOP BACK TEST; LOOP BACK PACKET TEST; LOOP BACK RANDOM TEST; PORT OPEN/CLOSE TEST; COMPLIANCE TEST.

### WLAN CHECK MENU (5 captions)

COMMUNICATION; BATTERY LIFE; POWER SAVE MODE; FIRMWARE; MAC ADDRESS.

### WLAN DHCP SETTING MENU (6 captions)

DHCP ENABLE/DISABLE; HOST IP ADDRESS; SUBNET MASK; DEFAULT GATEWAY; PRIMARY DNS SERVER; SECONDARY DNS SERVER.

### SYSTEM MENU (5 captions)

CPU MENU; PMIC MENU; TI CHARGER; POWER MANAGEMENT MENU; BATTERY MENU.

### DEVELOPER MENU (6 captions)

WLAN SSID SETING; WLAN PASSWORD SETTING; WLAN IPERF IP ADDRESS SETTING; WLAN AUTO TEST; AES DECRYPTION ON FILE SYSTEM; EXECUTE SECURE ADDIN.

### FLASH UTILITIES MENU (4 captions)

DATA OUT; DATA IN; USERAREA ALL FORMAT; USERAREA TEST.

### ROM DATA OUT MENU (2 captions)

FILESYSTEM AREA; DB AREA.

### ROM DATA IN MENU (2 captions)

FILESYSTEM AREA; DB AREA.

### USERAREA TEST MENU (10 captions)

USERAREA COPY(DRV0 -> SD); USERAREA COPY(SD -> DRV0); USERAREA COPY(DRV1 -> SD); USERAREA COPY(SD -> DRV1); TJFS PHYSICAL DRV0 FORMAT; TJFS PHYSICAL DRV1 FORMAT; USERAREA FULLMEM(DRV0); USERAREA FULLMEM(DRV1); USERAREA FULLMEM LOOP; USERAREA COPY TEST.

### SERVICE MENU (12 captions)

AUTO CHECK; MANUAL CHECK; VERSION; ROM CHECK(CHECK SUM); CALIBRATION(TOUCH PANEL); BACK UP; DELETE PASSWORD; RESTORE; RESET for SERVICE MODE; DB PATCH CHECK; MACHINE UNIQUE ID CHECK; SERVICE FULL RESET.

### MANUAL MENU FOR SERVICE MODE (9 captions)

DISPLAY CHECK; KEY CHECK; SDCARD CHECK; AUDIO CHECK; USB CHECK; CLOCK; SW CONDITION; OPEN SW CHECK; RECORD CHECK.

### DB PATCH MENU (2 captions)

IMPORT DBPATCH; ERASE DBPATCH.

### BATTERY TEST MENU (4 captions)

DEFAULT SETTINGS; WLAN TEST; BATTERYLIFE TEST (COMPATIBLE); BATTERYLIFE TEST.

### DEFAULT SETTING MENU (10 captions)

LCD BRIGHTNESS 0; LCD BRIGHTNESS 3; SOUND VOLUME; SOUND SELECT; SOUND ENGINE; COLOR MODE IN SOUND PLAY; COLOR MODE IN BRIGHTNESS 0; SET BLD1 VOLTAGE; SET BLD2 VOLTAGE; SET WLAN TIMEOUT.

### BATTERYLIFE TEST SELECT MENU (9 captions)

DISPLAY CONTINUATION; 1:11(ROM_SUM); 1:11(SD CARD); SOUND CONTINUATION; SDCard READ iDEC2 TEST; 1:11(eMMC); 1:11(ACTUAL USE); BUSINESS(BATTERY_TEST1); BUSINESS(BATTERY_TEST2).

### WLAN TEST MENU (8 captions)

REPEAT CONNECT; REPEAT CONNECT(MANUAL SOUND); REPEAT CONNECT(AUTO SOUND); REPEAT CONNECT(EMMC WRITE); IPERF RX TEST (EMMC WRITE); IPERF TX TEST (EMMC READ); IPERF RX TEST (EMMC WRITE+BROWSER); IPERF TX TEST (EMMC READ+BROWSER).

### PMIC MENU (6 captions)

VERSION CHECK; DCIN CONTROL; VBAT SETTINGS; CHARGER STATUS; CHARGER SETTINGS; NTC SETTINGS.

### FFT TEST MENU (3 captions)

RECORD TARGET DATA; COPY DATA(eMMC to SD); EXECUTE FFT TEST.

### PRONTEST LIBRARY TEST MENU (8 captions)

VOICE TYPE; MANUAL RECORD for ENGINE; SENTENCE CHECK WITH MIC; SENTENCE CHECK FROM SD; WORD CHECK WITH MIC; WORD CHECK FROM SD; AUTO SENTENCE CHECK; AUTO WORD CHECK.

### CPU MENU (4 captions)

CLOCK FREQUENCY SETTINGS; POWER MODE SETTINGS; CPU UID DISPLAY; SPREAD SPECTRUM SETTINGS.

### CPU CLOCK FREQUENCY SETTING MENU (2 captions)

A7 Core Setting; M4 Core Setting.

### CPU SPECTRUM SPREAD SETTING MENU (3 captions)

A7 SPLL Setting; A7 APLL Setting; M4 APLL Setting.

### POWER MANAGEMENT MENU (7 captions)

POWER STATUS; POWER MODE SELECT; SETTINGS; THERMISTER CHECK; USB BC CHECK; DCIN BYPASS CHECK(PATTERN); DCIN BYPASS CHECK(SECOND ASSY).

### POWER SETTINGS MENU (2 captions)

AUTO POWER OFF TIME; DISPLAY BACKLIGHT DARKEN TIME.

### TI CHARGER MENU (3 captions)

REGISTER CHECK; CHARGER STAT; CHARGER SETTING.

### CHARGER SETTING MENU (9 captions)

CHG_CONFIG; IINDPM; IPRECHG; ITERM; CHG_TIMER; JEITA_ISET; JEITA_VSET; VINDPM; SYS_MIN.

## Test plan (read-only first)

1. Save two identical original LCD frames for every safely reachable
   **submenu**, compare screenshot hashes/color statistics; log original
   A7 menu-painter TB and menu title. Blank or unchanged frame is inconclusive.
2. Prioritize *WLAN CHECK MENU* Communication, Firmware and MAC before AP
   association; enable host SPI/FIFO and DMA traces and record only non-secret
   command/status metadata, never fake host callbacks or successful association.
3. Explore USB function/host menu **without starting data transfer**, since
   factory WLAN AUTO TEST needs a different external USB-style fixture.
4. Survey input, audio, power, memory and storage test screens non-destructively.
   Keep writes, resets, user-area format, password deletion and update actions
   excluded. Use snapshot-on disposable media for any separately authorized tests.
5. A passing screenshot of a heading is **menu entry only**; a factory `OK`
   needs a real original result branch and appropriate hardware behavior.