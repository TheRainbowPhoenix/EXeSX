/*
 * Minimal owner-opt-in DY357 16-bit MIPI DCS/8080 LCD experiment.
 * D/C = GPIOA16, write port=0xb0000000. NO proprietary pixels included.
 * TE frame period is an explicit approximation, not a verified panel clock.
 */
#define EXESX_LCD_W 864
#define EXESX_LCD_H 480
static bool exesx_lcd_enabled(EXeSXState *s)
{
    return s->lcd && s->lcd->lcd_fb;
}
static void exesx_lcd_screenshot(EXeSXProfileWindow *w)
{
    const char *file = g_getenv("EXESX_LCD_SCREENSHOT");
    FILE *out;
    if (!file || !*file || !w->lcd_fb) {
        return;
    }
    out = fopen(file, "wb");
    if (!out) {
        error_report("EXeSX LCD cannot write screenshot: %s", file);
        return;
    }
    fprintf(out, "P6\n%d %d\n255\n", EXESX_LCD_W, EXESX_LCD_H);
    for (size_t i = 0; i < EXESX_LCD_W * EXESX_LCD_H; i++) {
        uint16_t p = w->lcd_fb[i];
        uint8_t rgb[3] = {
            (uint8_t)(((p >> 11) & 31) * 255 / 31),
            (uint8_t)(((p >> 5) & 63) * 255 / 63),
            (uint8_t)((p & 31) * 255 / 31)
        };
        fwrite(rgb, 1, 3, out);
    }
    fclose(out);
}
static void exesx_lcd_snapshot_tick(void *opaque)
{
    EXeSXProfileWindow *w = opaque;
    exesx_lcd_screenshot(w);
    timer_mod(w->lcd_screenshot_timer,
              qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) + 500000000);
}
static bool exesx_lcd_te_high(EXeSXState *s)
{
    uint64_t phase;
    if (!exesx_lcd_enabled(s) || !s->lcd->lcd_te_enabled) {
        return false;
    }
    /* Experimental 60Hz VSYNC; 1ms active-high blanking pulse. */
    phase = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) % 16666667ULL;
    return phase < 1000000ULL;
}
static void exesx_lcd_gpioa(EXeSXState *s, uint32_t off, uint32_t bits)
{
    if (!exesx_lcd_enabled(s) || !(bits & (1U << 16))) {
        return;
    }
    if (off == 4) {
        s->lcd->lcd_dc = true;
    } else if (off == 8) {
        s->lcd->lcd_dc = false;
    }
}
static void exesx_lcd_parameter(EXeSXProfileWindow *w, uint16_t v)
{
    unsigned n = w->lcd_param_count++;
    switch (w->lcd_cmd) {
    case 0x35: /* TEON */
        w->lcd_te_enabled = true;
        break;
    case 0x34: /* TEOFF */
        w->lcd_te_enabled = false;
        break;
    case 0x2a: case 0x2b: /* address byte pairs */
        if (n < 4) {
            w->lcd_params[n] = v & 255;
        }
        if (n == 3) {
            unsigned start = (w->lcd_params[0] << 8) | w->lcd_params[1];
            unsigned end = (w->lcd_params[2] << 8) | w->lcd_params[3];
            if (w->lcd_cmd == 0x2a) {
                w->lcd_x0 = MIN(start, EXESX_LCD_W - 1);
                w->lcd_x1 = MIN(end, EXESX_LCD_W - 1);
            } else {
                w->lcd_y0 = MIN(start, EXESX_LCD_H - 1);
                w->lcd_y1 = MIN(end, EXESX_LCD_H - 1);
            }
        }
        break;
    case 0x2c: /* RAMWR: one RGB565 pixel per halfword */
        if (w->lcd_x0 <= w->lcd_x1 && w->lcd_y0 <= w->lcd_y1 &&
            w->lcd_y <= w->lcd_y1 && w->lcd_x <= w->lcd_x1) {
            w->lcd_fb[w->lcd_y * EXESX_LCD_W + w->lcd_x] = v;
            if (++w->lcd_x > w->lcd_x1) {
                w->lcd_x = w->lcd_x0;
                ++w->lcd_y;
            }
            ++w->lcd_pixel_writes;
        }
        break;
    case 0x3a: /* COLMOD; only RGB565 data storage supported */
        w->lcd_rgb565 = (v & 255) == 0x55;
        break;
    default:
        break; /* Preserve unknown vendor initialization as inert. */
    }
}
static MemTxResult exesx_lcd_write(EXeSXProfileWindow *w, hwaddr offset,
                                  uint64_t data, unsigned size)
{
    if (offset != 0 || size != 2) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "EXeSX LCD unmodeled WRITE offset=0x%" HWADDR_PRIx
                      " width=%u value=0x%" PRIx64 " DC=%u command=0x%02x "
                      "pixel_writes=%" PRIu64 " -- abort (unknown bus semantics)\n",
                      offset, size, data, w->lcd_dc, w->lcd_cmd,
                      w->lcd_pixel_writes);
        return MEMTX_ERROR;
    }
    if (!w->lcd_dc) {
        w->lcd_cmd = data & 255;
        w->lcd_param_count = 0;
        if (w->lcd_cmd == 0x2c) {
            w->lcd_x = w->lcd_x0;
            w->lcd_y = w->lcd_y0;
        } else if (w->lcd_cmd == 0x34) {
            w->lcd_te_enabled = false;
        }
    } else {
        exesx_lcd_parameter(w, data & 0xffff);
    }
    return MEMTX_OK;
}
