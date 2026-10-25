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
static void exesx_lcd_screenshot_file(EXeSXProfileWindow *w,
                                      const char *file)
{
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
/*
 * Opt-in capture handshake for deterministic host-stage screenshots.
 * The host atomically renames a small UTF-8 request file containing an
 * absolute output pathname. On the next guest-virtual-time timer tick
 * EXeSX writes exactly ONE PPM. No RAM writes, fake pixels, or A7 events.
 *
 * If this opt-in is absent, preserve the historical 0.5s periodic
 * EXESX_LCD_SCREENSHOT behavior for existing scripts/tests.
 */
static void exesx_lcd_snapshot_tick(void *opaque)
{
    EXeSXProfileWindow *w = opaque;
    const char *request = g_getenv("EXESX_LCD_CAPTURE_REQUEST_FILE");
    if (request && *request) {
        gchar *path = NULL;
        if (g_file_get_contents(request, &path, NULL, NULL)) {
            g_strstrip(path);
            if (*path) {
                exesx_lcd_screenshot_file(w, path);
            }
            g_free(path);
            remove(request);
        }
    } else {
        exesx_lcd_screenshot_file(w, g_getenv("EXESX_LCD_SCREENSHOT"));
    }
    /*
     * Host-driven capture requests are independent of guest virtual time.
     * On an idling guest (especially Windows TCG/WFI), the virtual clock
     * can stop advancing after a screenshot request was created. Poll the
     * request with QEMU's host realtime clock instead. No pixel I/O occurs
     * unless the host actually requests a screenshot.
     */
    QEMUClockType clock = request && *request ?
        QEMU_CLOCK_REALTIME : QEMU_CLOCK_VIRTUAL;
    timer_mod(w->lcd_screenshot_timer,
              qemu_clock_get_ns(clock) +
              (clock == QEMU_CLOCK_REALTIME ? 200000000 : 500000000));
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
/*
 * The guest provides raw DCS column/page coordinates. MADCTL changes the
 * address-to-panel mapping as well as RAMWR's major traversal axis.
 * Preserve full 16-bit inclusive CASET/PASET endpoints; clamp only the final
 * physical panel address, never the guest window (which would make writes
 * with an off-panel endpoint wrap into visible pixels).
 *
 * This is experimental panel orientation using standard DCS MX/MY/MV bits.
 * Exact Casio LCD glass mounting, vendor-specific offsets and scan order
 * remain unverified.
 */
static void exesx_lcd_ramwr_pixel(EXeSXProfileWindow *w, uint16_t rgb565)
{
    unsigned x = w->lcd_x;
    unsigned y = w->lcd_y;
    /*
     * The original DY357 selects MADCTL=0x60 for its landscape
     * 864x480 framebuffer and sends landscape CASET/PASET coordinates.
     * These coordinates already describe the displayed orientation:
     * swapping them a second time (and then making RAMWR page-major)
     * clips all columns >=480 and paints only a 480px-wide stripe.
     *
     * Keep other MADCTL modes on the existing experimental mapping
     * until the panel/controller identity and portrait dimensions are
     * independently established.  This is not a global rotate hack.
     */
    bool landscape = (w->lcd_madctl & 0xe0) == 0x60;
    /*
     * Original 0x601B25E4 explicitly converts source[480][864] into a
     * transposed 480x864 stream; 0x60015328(1) selects MADCTL=0x40 for
     * this transfer.  The 0x40 CASET/PASET window is 480 columns by
     * 864 rows, so (controller column, row) -> (screen Y, screen X).
     * Unlike 0x60's direct landscape clear, these pixels have already
     * been transposed by original ROM, NOT by the LCD controller.
     */
    bool transposed_frame = (w->lcd_madctl & 0xe0) == 0x40;
    bool swap = (w->lcd_madctl & 0x20) != 0 && !landscape;
    int px, py;

    if (w->lcd_x0 > w->lcd_x1 || w->lcd_y0 > w->lcd_y1 ||
        x > w->lcd_x1 || y > w->lcd_y1) {
        return; /* Do not wrap RAMWR into another rectangle. */
    }

    if (landscape) {
        px = (int)x;
        py = (int)y;
    } else if (transposed_frame) {
        px = (int)y;
        py = (int)x;
    } else if (swap) {
        px = (w->lcd_madctl & 0x40) ?
            (EXESX_LCD_W - 1 - (int)y) : (int)y;
        py = (w->lcd_madctl & 0x80) ?
            (EXESX_LCD_H - 1 - (int)x) : (int)x;
    } else {
        px = (w->lcd_madctl & 0x40) ?
            (EXESX_LCD_W - 1 - (int)x) : (int)x;
        py = (w->lcd_madctl & 0x80) ?
            (EXESX_LCD_H - 1 - (int)y) : (int)y;
    }
    if (px >= 0 && px < EXESX_LCD_W && py >= 0 && py < EXESX_LCD_H) {
        w->lcd_fb[py * EXESX_LCD_W + px] = rgb565;
    }
    ++w->lcd_pixel_writes;

    /*
     * Both genuine framebuffer paths send consecutive pixels along
     * the LCD window's column axis: 0x60 has 864 columns x 480 rows;
     * 0x40 has 480 columns x 864 rows after firmware transposition.
     * Keep wrapping at the *guest's* inclusive column endpoint and
     * clip only after mapping to the panel's 864x480 presentation.
     * Other MV modes retain the experimental page-first traversal.
     */
    if (swap) {
        if (++w->lcd_y > w->lcd_y1) {
            w->lcd_y = w->lcd_y0;
            ++w->lcd_x;
        }
    } else {
        if (++w->lcd_x > w->lcd_x1) {
            w->lcd_x = w->lcd_x0;
            ++w->lcd_y;
        }
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
    case 0x36: /* DCS MADCTL: MY/MX/MV (+ independent BGR color order) */
        if (n == 0) {
            w->lcd_madctl = v & 255;
        }
        break;
    case 0x2a: case 0x2b: /* address byte pairs, inclusive bounds */
        if (n < 4) {
            w->lcd_params[n] = v & 255;
        }
        if (n == 3) {
            unsigned first = (w->lcd_params[0] << 8) | w->lcd_params[1];
            unsigned last = (w->lcd_params[2] << 8) | w->lcd_params[3];
            if (w->lcd_cmd == 0x2a) {
                w->lcd_x0 = first;
                w->lcd_x1 = last;
            } else {
                w->lcd_y0 = first;
                w->lcd_y1 = last;
            }
        }
        break;
    case 0x2c: /* RAMWR: one RGB565 pixel per DBI halfword */
        exesx_lcd_ramwr_pixel(w, v);
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
    /* Genuine BIOS switches to word stores for optimized RAMWR,
     * e.g. 0xffffffff after the white clear. On a 16-bit DBI/FlexBus
     * path this is two consecutive RGB565 data halfwords. Never
     * widen COMMAND writes or unrelated vendor registers silently.
     */
    if (offset == 0 && size == 4 && w->lcd_dc &&
        w->lcd_cmd == 0x2c) {
        exesx_lcd_parameter(w, (uint16_t)data);
        exesx_lcd_parameter(w, (uint16_t)(data >> 16));
        return MEMTX_OK;
    }
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
