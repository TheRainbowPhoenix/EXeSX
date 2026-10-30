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
/*
 * Debugger-only, opt-in read-only LCD framebuffer export.
 * QMP/HMP pmemsave(0xb1000000, 864*480*2) reads real RGB565 pixels
 * synchronously, without any emulated LCD timer or periodic disk writes.
 * This is a diagnostic host interface, NOT an invented guest controller.
 */
#define EXESX_LCD_EXPORT_BASE UINT64_C(0xb1000000)
#define EXESX_LCD_EXPORT_SIZE (EXESX_LCD_W * EXESX_LCD_H * 2)
static uint64_t exesx_lcd_export_read(void *opaque, hwaddr offset,
                                       unsigned size)
{
    EXeSXState *board = opaque;
    uint64_t result = 0;
    if (!board->lcd || !board->lcd->lcd_fb ||
        offset > EXESX_LCD_EXPORT_SIZE ||
        size > EXESX_LCD_EXPORT_SIZE - offset) {
        return 0;
    }
    for (unsigned i = 0; i < size; i++) {
        hwaddr addr = offset + i;
        uint16_t pixel = board->lcd->lcd_fb[addr / 2];
        result |= (uint64_t)((pixel >> (8 * (addr & 1))) & 255)
                  << (8 * i);
    }
    return result;
}
static void exesx_lcd_export_write(void *opaque, hwaddr offset,
                                   uint64_t value, unsigned size)
{
    /* The debugger export is immutable from the guest address space. */
}
static const MemoryRegionOps exesx_lcd_export_ops = {
    .read = exesx_lcd_export_read,
    .write = exesx_lcd_export_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 1, .max_access_size = 8, .unaligned = true },
    .impl = { .min_access_size = 1, .max_access_size = 8, .unaligned = true },
};

/* Read-only diagnostic window: raw DCS state, never an LCD verdict.
 * WORD0 signature, WORD1 flags, WORD2 cmd/MADCTL/param-count,
 * WORD3 brightness/last-data, WORD4/5 raw vendor B2 bytes,
 * WORD6 opt-in byte-swapped RAMWR count, WORD7 pixel-write count.
 */
#define EXESX_LCD_STATUS_EXPORT_BASE UINT64_C(0xb1100000)
#define EXESX_LCD_STATUS_EXPORT_SIZE 64
static uint64_t exesx_lcd_status_read(void *opaque, hwaddr offset, unsigned size)
{
    EXeSXState *board = opaque;
    EXeSXProfileWindow *w = board->lcd;
    uint32_t words[16] = { 0 };
    uint64_t result = 0;
    if (!w || offset >= EXESX_LCD_STATUS_EXPORT_SIZE ||
        size > EXESX_LCD_STATUS_EXPORT_SIZE - offset) {
        return 0;
    }
    words[0] = 0x3144434c; /* "LCD1" */
    words[1] = (w->lcd_rgb565 ? 1U : 0U) |
               (w->lcd_te_enabled ? 2U : 0U) |
               (w->lcd_display_on ? 4U : 0U) |
               (w->lcd_sleep_out ? 8U : 0U) |
               (w->lcd_inverted ? 16U : 0U) |
               (w->lcd_idle ? 32U : 0U);
    words[2] = (uint32_t)w->lcd_cmd |
               ((uint32_t)w->lcd_madctl << 8) |
               ((w->lcd_param_count & 0xffffU) << 16);
    words[3] = (uint32_t)w->lcd_dcs_brightness |
               ((uint32_t)w->lcd_last_data << 8);
    for (unsigned i = 0; i < 8; ++i) {
        words[4 + i / 4] |= (uint32_t)w->lcd_b2[i] << (8 * (i & 3));
    }
    words[6] = w->lcd_swapped_writes;
    words[7] = (uint32_t)w->lcd_pixel_writes;
    /*
     * Host-only signal observer, explicitly NOT the unknown vendor
     * panel PWM register. The original UI displays 16 MHz/divisor
     * and initializes duty 0xCC. Model an ideal digital waveform
     * only when the diagnostic option is enabled. RGB565 GRAM
     * and real GPIOF/PTB register behavior are not changed.
     */
    if (w->lcd_pwm_diagnostic && w->lcd_pwm_divisor) {
        uint64_t period_ns =
            ((uint64_t)w->lcd_pwm_divisor * UINT64_C(1000000000) +
             UINT64_C(8000000)) / UINT64_C(16000000);
        uint64_t high_ns =
            (period_ns * w->lcd_pwm_duty + 127U) / 255U;
        uint64_t phase_ns =
            qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) % period_ns;
        words[8] = (uint32_t)period_ns;
        words[9] = (uint32_t)high_ns;
        words[10] = (phase_ns < high_ns) ? 1 : 0;
        words[11] = (w->lcd_pwm_duty * 10000U + 127U) / 255U;
        words[12] = w->lcd_pwm_divisor;
        words[13] = UINT32_C(16000000) / w->lcd_pwm_divisor;
        words[14] = w->lcd_pwm_duty;
        words[15] = 0x50574d31; /* PWM1, diagnostic model only */
    }
    for (unsigned i = 0; i < size; ++i) {
        unsigned pos = offset + i;
        result |= (uint64_t)((words[pos / 4] >> (8 * (pos & 3))) & 255)
                  << (8 * i);
    }
    return result;
}
static const MemoryRegionOps exesx_lcd_status_ops = {
    .read = exesx_lcd_status_read,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 1, .max_access_size = 8, .unaligned = true },
    .impl = { .min_access_size = 1, .max_access_size = 8, .unaligned = true },
};

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
    /*
     * Original DY357 transposed 16-bit image transfer (MADCTL=0x40):
     * owner-ROM MENU 1 evidence shows reversed RGB565 byte lanes.
     * Experimental opt-in until the exact FlexBus transfer provenance
     * is established. Never alter normal 0x60/PIO color-bar pixels.
     */
    if (w->lcd_transposed_byteswap && (w->lcd_madctl & 0xe0) == 0x40) {
        rgb565 = (uint16_t)((rgb565 >> 8) | (rgb565 << 8));
        ++w->lcd_swapped_writes;
    }
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
    w->lcd_last_data = v & 255;
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
    case 0x51: /* Standard DCS brightness register, 0..255 */
        if (n == 0) {
            w->lcd_dcs_brightness = v & 255;
            if (w->lcd_pwm_diagnostic) {
                /* Explicit experimental PWM mapping: never a claim that
                 * DY357 vendor BACKLIGHT DUTY uses DCS 0x51.
                 */
                w->lcd_pwm_duty = v & 255;
            }
        }
        break;
    case 0xb2: /* Preserve original vendor data; semantics not guessed */
        if (n < G_N_ELEMENTS(w->lcd_b2)) {
            w->lcd_b2[n] = v & 255;
        }
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
        /* DCS power and inversion are panel state, not GRAM mutations. */
        switch (w->lcd_cmd) {
        case 0x10: w->lcd_sleep_out = false; break;
        case 0x11: w->lcd_sleep_out = true; break;
        case 0x20: w->lcd_inverted = false; break;
        case 0x21: w->lcd_inverted = true; break;
        case 0x28: w->lcd_display_on = false; break;
        case 0x29: w->lcd_display_on = true; break;
        case 0x38: w->lcd_idle = false; break;
        case 0x39: w->lcd_idle = true; break;
        default: break;
        }
    } else {
        exesx_lcd_parameter(w, data & 0xffff);
    }
    return MEMTX_OK;
}
