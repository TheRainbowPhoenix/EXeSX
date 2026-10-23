# DY357 LCD: two real MADCTL modes and firmware pre-transposition

23 October 2026. Evidence: checksum-valid owner-held original `OSUP.BIN`,
source-derived synthetic eMMC, native EXeSX QEMU 10.1.0 build
`466ab3d84886234a550175ae5bda82a52692772f`,
and independently supplied **864×480 screenshots**.
No ROM, raw framebuffer, guest pixel stream or synthetic eMMC is committed.

## Original source of the rotated MODEL dialog

Original A7 function `0x600105CC` calls `FUN_60010438(0x130, 0xA0, 0x100,
0x88)`, drawing a `256×136` border box with top-left `(304,160)`.
The parent rectangle/fill path writes into a **normal row-major 864×480
RGB565 memory framebuffer**, using `0x6C0` (=864*2) as line stride in
`LCD_RenderImage` at `0x601B31xx`.

The actual display-transfer path `A7_LCD_WriteFrameAfterGPIOF13Sync`
at `0x601B40CC` then does:

1. `FUN_601B25E4(source, 864, 480)` — **pre-transpose the source
   framebuffer** into temporary destination buffer 5.
2. `FUN_60015328(1)` — verified original ARM code sends DCS `0x36`,
   parameter **`0x40`** if mode differs.
3. `FUN_60015248(0, 480, 0, 864)` — DCS CASET/PASET/RAMWR
   for a **480×864** controller write window.
4. Wait for diagnostic GPIOF13 high/low TE edge, then send **829,440
   bytes** (`864×480×2`) from the **pre-transposed** buffer.
5. `FUN_60015328(0)` — send DCS `0x36`, parameter **`0x60`**,
   restoring direct landscape mode.

Original ARM disassembly of `0x601B25E4` proves the transposition.
It calculates `stride_words = width/2 = 432` at `0x601B25FC`,
then traverses source memory in **864-pixel row strides** via
`ADD R3,R3,R7,LSL #2` at `0x601B262C`; it writes two destination
halfword streams at `0x601B2634` and `0x601B263C`, with their
destinations separated by `height*2`. Thus pixels at source `(x,y)`
are streamed at portrait controller `(column=y, row=x)`.

The original simulator correctly handled *direct* landscape
`MADCTL=0x60`, but incorrectly treated `0x40` as a horizontally
mirrored direct-landscape mode. This misplaced the portrait controller
rectangle and clipped it at the 480px screenshot edge.

## Screenshot and real QEMU A/B evidence

The owner screenshot has a `MODEL` border around screen
`x=571..706`, `y=304..479` (bottom truncated). Running the genuine,
unchanged OSUP with the latest **pre-fix** Linux QEMU in an independent
private session reproduced `x≈568..703`, `y=304..479` with white
background. That specific bbox is predicted by the incorrectly
modeled `0x40` transform:

- Original rectangle: `x=304..559, y=160..295`
- Pre-transpose for 480×864 transfer: controller
  `x=160..295, y=304..559`
- Old modeled output `screen_x=863-controller_x`,
  `screen_y=controller_y` gives `x=568..703, y=304..559`,
  clipped at screenshot Y=479

The evidence rules out a simple `FUN_600105CC` text-layout bug.
The required *presentation* mapping for this original portrait
transfer is `screen_x=controller_y, screen_y=controller_x`,
with the controller RAMWR cursor advancing across its inclusive
column window (0..479) then wrapping through rows (0..863).
The `0x60` path remains `screen_x=controller_x, screen_y=controller_y`.

The experimental LCD code now explicitly models this **verified
original-firmware mode pair**; it does not rotate every screenshot or
assert a physical panel model. Other generic MADCTL variants remain
provisional.

## Regression and build

`scripts/probe_lcd_landscape.py` now synthesizes **genuine ARM guest
MMIO writes** in both modes:

- `0x60`: centered 3×2 window + distant X=700 sample
- `0x40`: 2×3 portrait-controller window at controller columns
  160..161, rows 304..306; assert six corresponding landscape screen
  pixels at X=304..306, Y=160..161 in correct RGB565 order
- `0x40`: portrait-controller row Y=700 maps to **screen X=700**
- `0x60` restoration after the transposed transfer
- Strict inclusive cursor wrap and clipping, no pixel spill

Both Linux and Windows CI execute this synthetic probe. Run the
original firmware privately again with `--dma1-m2m --gpiob3-high`
and compare `private/<run>/lcd-screenshot.ppm`; synthetic tests
alone cannot verify font-layout correctness or final boot.

The Linux artifact was also corrected to bundle
`summarize_lcd_screenshot.py` so `run_osup.py` can complete
without a missing-module exception after saving the framebuffer.
